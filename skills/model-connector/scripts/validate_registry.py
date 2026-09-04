#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""model-connector 注册表校验脚本（编辑注册表后必跑；CI 门禁用）。

用法：python3 validate_registry.py [registry.json ...]
不传参数时自动校验脚本目录上一级的 models_registry.json 与 models_registry.local.json（若存在）。

规则：
- 公共表（文件名不含 .local）：url 域名必须 ∈ trustedDomains[vendor]，缺厂商或缺域名 = ERROR
- 私有表（.local）：域名不在白名单 = WARN（中转端点合法，但发 key 前须声明）
- 字段类型/取值域、lastVerified 日期格式、probe 结构、freeTier 与 freeTierCheckedOn 成对、
  altProtocol 结构、墓碑必填字段、alias 规范化跨条目碰撞（同 alias 或 alias=他条目 id）
退出码：0=通过（可有 WARN） 1=存在 ERROR
"""

import json
import os
import re
import sys

CONFIDENCES = {"tested", "documented", "estimate"}
DATE_RE = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[0-1]))?$")
PROBE_INT_KEYS = {"outputTested", "outputRejected", "outputDocClaimed", "contextTotal"}
PROBE_STR_KEYS = {"imageInput", "toolCall", "contextPolicy"}


def host_of(url):
    m = re.match(r"^https?://([^/:]+)", url or "")
    return m.group(1).lower() if m else None


def check_entry(mid, m, errors, warns, where):
    tag = "[%s:%s]" % (where, mid)
    if not isinstance(m, dict):
        errors.append(tag + " 条目必须是对象")
        return
    for k in ("aliases", "vendor", "url", "protocol", "auth", "modelId",
              "maxInputTokens", "maxOutputTokens", "confidence", "verifiedBy"):
        if k not in m:
            errors.append(tag + " 缺必填字段 " + k)
    for k in ("supportsToolCall", "supportsImages", "supportsReasoning"):
        if not isinstance(m.get(k), bool):
            errors.append(tag + " %s 必须为 bool" % k)
    if not isinstance(m.get("maxInputTokens", 0), int) or m.get("maxInputTokens", 0) <= 0:
        errors.append(tag + " maxInputTokens 必须为正整数")
    if not isinstance(m.get("maxOutputTokens", 0), int) or m.get("maxOutputTokens", 0) <= 0:
        errors.append(tag + " maxOutputTokens 必须为正整数")
    if m.get("confidence") not in CONFIDENCES:
        errors.append(tag + " confidence 必须 ∈ %s" % sorted(CONFIDENCES))
    if not isinstance(m.get("aliases"), list) or not all(isinstance(a, str) for a in m.get("aliases", [])):
        errors.append(tag + " aliases 必须为字符串数组")
    if not str(m.get("url", "")).startswith("https://"):
        errors.append(tag + " url 必须 https")
    if m.get("confidence") == "tested" and not m.get("lastVerified"):
        warns.append(tag + " tested 条目建议补 lastVerified（分级探针判级依赖它）")
    lv = m.get("lastVerified")
    if lv is not None and not (isinstance(lv, str) and DATE_RE.match(lv)):
        errors.append(tag + " lastVerified 格式须 YYYY-MM 或 YYYY-MM-DD")
    probe = m.get("probe")
    if probe is not None:
        if not isinstance(probe, dict):
            errors.append(tag + " probe 必须为对象")
        else:
            for k, v in probe.items():
                if k in PROBE_INT_KEYS and not (isinstance(v, int) and v > 0):
                    errors.append(tag + " probe.%s 必须为正整数" % k)
                if k in PROBE_STR_KEYS and not isinstance(v, str):
                    errors.append(tag + " probe.%s 必须为字符串" % k)
            for k in probe:
                if k not in PROBE_INT_KEYS and k not in PROBE_STR_KEYS:
                    warns.append(tag + " probe.%s 非标准键，确认 schema" % k)
    quirks = m.get("quirks")
    if quirks is not None and (not isinstance(quirks, list) or not all(isinstance(q, str) for q in quirks)):
        errors.append(tag + " quirks 必须为字符串数组")
    alt = m.get("altProtocol")
    if alt is not None:
        if not isinstance(alt, dict) or not alt.get("protocol") or not str(alt.get("url", "")).startswith("https://"):
            errors.append(tag + " altProtocol 须含 protocol 与 https url")
        elif not alt.get("status"):
            warns.append(tag + " altProtocol 建议带 status（documented-未实测 / tested）")
    ft, fc = m.get("freeTier"), m.get("freeTierCheckedOn")
    if ft is not None:
        if ft not in ("free", "trial", "paid"):
            errors.append(tag + " freeTier ∈ free/trial/paid")
        if not (isinstance(fc, str) and DATE_RE.match(fc)):
            errors.append(tag + " freeTier 与 freeTierCheckedOn 必须成对（后者 YYYY-MM[-DD]）")


def check_collisions(models, errors):
    alias_owner = {}
    for mid, m in models.items():
        for a in (m.get("aliases") or []):
            na = re.sub(r"[\s\-]+", " ", a.strip().lower())
            if na in alias_owner and alias_owner[na] != mid:
                errors.append("alias 碰撞：%r 同时属于 %s 与 %s" % (a, alias_owner[na], mid))
            alias_owner[na] = mid
    for mid in models:
        nm = re.sub(r"[\s\-]+", " ", mid.strip().lower())
        if nm in alias_owner and alias_owner[nm] != mid:
            errors.append("alias %r 与条目 id %r 冲突" % (alias_owner[nm], mid))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(here)
    paths = sys.argv[1:] or [
        os.path.join(skill_dir, "models_registry.json"),
        os.path.join(skill_dir, "models_registry.local.json"),
    ]
    errors, warns = [], []
    tables = {}
    for path in paths:
        if not os.path.exists(path):
            if path.endswith(".local.json"):
                continue  # 私有表可缺省
            errors.append("文件不存在: %s" % path)
            continue
        where = "local" if ".local" in os.path.basename(path) else "public"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            errors.append("[%s] JSON 解析失败: %s" % (where, e))
            continue
        tables[where] = data
        if not data.get("version"):
            errors.append("[%s] 缺 version" % where)
        models = data.get("models")
        if not isinstance(models, dict) or not models:
            errors.append("[%s] models 必须为非空对象" % where)
            continue
        td = data.get("trustedDomains") or {}
        if where == "local":
            td_public = (tables.get("public") or {}).get("trustedDomains") or {}
        for mid, m in models.items():
            check_entry(mid, m, errors, warns, where)
            host = host_of(m.get("url"))
            vendor = m.get("vendor")
            allowed = td.get(vendor) or ([] if where == "public" else td_public.get(vendor) or [])
            if host and allowed and host not in allowed:
                msg = "url 域名 %s 不在 trustedDomains[%s] 内" % (host, vendor)
                (errors if where == "public" else warns).append(
                    ("[%s:%s] " % (where, mid)) + msg + ("（中转端点，发 key 前须向用户声明）" if where == "local" else ""))
            elif host and not allowed and where == "public":
                errors.append("[%s:%s] trustedDomains 缺厂商 %s 的域名记录" % (where, mid, vendor))
            elif host and not allowed and where == "local":
                warns.append("[local:%s] 厂商 %s 无任何白名单域名记录，按中转端点处理（发 key 前声明非官方域名）"
                             % (mid, vendor))
        check_collisions(models, errors)
        for t in data.get("retiredModels") or []:
            for k in ("id", "reason", "retiredOn"):
                if not t.get(k):
                    errors.append("[retired] 墓碑缺必填字段 " + k)
            if t.get("recheckAfter") and not DATE_RE.match(t["recheckAfter"]):
                errors.append("[retired] recheckAfter 格式须 YYYY-MM[-DD]")
        if where == "local" and tables.get("public"):
            pm = tables["public"].get("models") or {}
            for mid, m in models.items():
                if mid in pm and host_of(pm[mid].get("url")) != host_of(m.get("url")):
                    warns.append("[local:%s] 覆盖了公共表同名条目且换了端点域名（%s → %s），确认这是本机意图"
                                 % (mid, host_of(pm[mid].get("url")), host_of(m.get("url"))))

    for w in warns:
        print("WARN: " + w)
    for e in errors:
        print("ERROR: " + e)
    print("SUMMARY: %d error(s), %d warn(s)" % (len(errors), len(warns)))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
