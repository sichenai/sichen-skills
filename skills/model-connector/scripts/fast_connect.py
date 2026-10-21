#!/usr/bin/env python3
"""fast_connect.py — model-connector 一键接入编排器（v1.20，快速接入模式的执行器）。

把「注册表匹配 → 宿主体检 → 修配置 → smoke 探针 → 宿主加载验证 → 注册表回写」
压进一次 Bash 调用，agent 轮数从 40+ 压到 ≤10。纯标准库零依赖。

用法:
  fast_connect.py inspect <phrase>              # 匹配 + 宿主体检（零网络）
  fast_connect.py fix <phrase> [--dry-run]      # 按注册表值修宿主条目（写前重读、写后读回）
  fast_connect.py verify <phrase> [--image]     # smoke 探针（可选图片探针）+ 宿主加载检查
  fast_connect.py book <phrase> [--backlog 文字] # 注册表回写 lastVerified/probe + 慢车道待办
  fast_connect.py run <phrase> [--image] [--no-book] [--dry-run]  # 一键全链

输出: stdout 单行 JSON（agent 友好）；summary 字段含人读摘要。
安全:
  - key 只从宿主配置读、经 stdin 传 probe.py，不进 argv / 不落盘 / 不打印
  - 只改宿主目标条目的元数据字段（id/url/vendor/能力/上限），**绝不覆盖 apiKey / name**
  - 域名白名单门禁透传 probe.py（--expect-domain 取注册表 url 域名）
  - 写文件前重读比对（防并发覆盖），原子写（tempfile + rename）
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
DEFAULT_HOST = os.path.expanduser("~/.workbuddy/models.json")

# 宿主元数据字段 = 注册表同名字段（apiKey / name 除外，永不触碰）
META_FIELDS = ["url", "vendor", "supportsToolCall", "supportsImages", "supportsReasoning",
               "maxInputTokens", "maxOutputTokens"]


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False))


def fail(step, detail, **kw):
    emit({"ok": False, "step": step, "detail": detail, **kw})
    sys.exit(1)


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def atomic_write_json(path, data):
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".fc_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def file_sig(path):
    """写前重读比对用的文件签名（size+mtime）。"""
    st = os.stat(path)
    return (st.st_size, st.st_mtime_ns)


# ---------------- 注册表层 ----------------

def run_match(phrase):
    """调 match_registry.py，返回 (status, payload)。非零退出码也带 JSON 输出。"""
    r = subprocess.run([sys.executable, os.path.join(HERE, "match_registry.py"), phrase],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"status": "registry_unavailable", "detail": r.stdout[-200:] + r.stderr[-200:]}


def locate_entry_layer(model_id):
    """条目所在层：local 优先（local 整体覆盖 public）。返回 (path, data)。"""
    local_p = os.path.join(SKILL_DIR, "models_registry.local.json")
    public_p = os.path.join(SKILL_DIR, "models_registry.json")
    for p in (local_p, public_p):
        d = load_json(p)
        if d and isinstance(d.get("models"), dict) and model_id in d["models"]:
            return p, d
    return public_p, load_json(public_p) or {"models": {}, "version": "0"}


# ---------------- 宿主层 ----------------

def find_host_entry(host, model_id):
    """宿主条目按 id == 注册表 modelId 查找（id 原样透传铁律）。"""
    if not isinstance(host, list):
        return None
    for m in host:
        if isinstance(m, dict) and m.get("id") == model_id:
            return m
    return None


def diagnose(reg, host_entry):
    """对比注册表值与宿主条目，返回缺陷列表。"""
    defects = []
    if host_entry is None:
        return [{"field": "*", "current": None, "expected": "新建条目",
                 "action": "宿主无此条目，fix 将新建骨架（apiKey 留空需用户补）"}]
    for f in META_FIELDS:
        exp, cur = reg.get(f), host_entry.get(f)
        if exp is not None and cur != exp:
            defects.append({"field": f, "current": cur, "expected": exp, "action": "fix 覆盖为注册表值"})
    return defects


def apply_fix(reg, host, host_path, dry_run):
    """修宿主条目元数据（不动 apiKey/name）。返回 (new_host, changed_fields, created)。"""
    model_id = reg["modelId"]
    entry = find_host_entry(host, model_id)
    created = entry is None
    if created:
        entry = {"id": model_id, "name": model_id, "apiKey": ""}
        host = list(host) + [entry] if isinstance(host, list) else [entry]
    changed = []
    for f in META_FIELDS:
        exp = reg.get(f)
        if exp is not None and entry.get(f) != exp:
            changed.append({"field": f, "from": entry.get(f), "to": exp})
            entry[f] = exp
    if dry_run:
        return host, changed, created
    sig = file_sig(host_path)
    current = load_json(host_path)
    if current is not None and file_sig(host_path) != sig:
        fail("fix", "写前重读发现宿主配置在处理期间被修改（并发冲突），已中止；请重跑",
             conflict=True)
    atomic_write_json(host_path, host)
    back = load_json(host_path)
    if back is None:
        fail("fix", "写后读回失败（文件不可解析）")
    return back, changed, created


# ---------------- 探针层 ----------------

def run_probe(subcmd, url, model_id, key, expect_domain, timeout=90):
    """调 probe.py 子命令，key 经 stdin 传入。返回 (ok, payload)。"""
    cmd = [sys.executable, os.path.join(HERE, "probe.py"), subcmd,
           "--url", url, "--model", model_id, "--key", "-", "--timeout", str(timeout)]
    if expect_domain:
        cmd += ["--expect-domain", expect_domain]
    r = subprocess.run(cmd, input=key + "\n", capture_output=True, text=True)
    try:
        payload = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        payload = {"result": "script-error", "stdout": r.stdout[-200:], "stderr": r.stderr[-200:]}
    return r.returncode == 0, payload


def host_load_check(model_id):
    """宿主加载验证：codebuddy --help 列表找 custom-local:<id>。CLI 不可用仅警告。"""
    try:
        r = subprocess.run(["codebuddy", "--help"], capture_output=True, text=True, timeout=30)
        loaded = ("custom-local:" + model_id) in (r.stdout + r.stderr)
        return {"checked": True, "loaded": loaded,
                "detail": "CLI 列表已确认加载" if loaded else "CLI 列表未见该条目（可能未加载或 CLI 版本差异）"}
    except Exception as e:
        return {"checked": False, "loaded": None, "detail": "codebuddy CLI 不可用，跳过宿主加载检查: %s" % e}


# ---------------- 回写层 ----------------

def book_registry(reg, model_id, probe_results, backlog_text):
    """注册表回写 lastVerified/probe；写前重读比对。"""
    path, data = locate_entry_layer(model_id)
    if not data or model_id not in (data.get("models") or {}):
        fail("book", "目标条目不在任何注册表层，无法回写（应先走读文档流程收录）")
    sig = file_sig(path)
    entry = data["models"][model_id]
    today = datetime.date.today().isoformat()
    entry["lastVerified"] = today
    probe = entry.setdefault("probe", {})
    for k, v in probe_results.items():
        probe[k] = v
    note = entry.get("verifiedBy") or ""
    entry["verifiedBy"] = (note + " | fast_connect %s 复验：%s" % (
        today, "、".join("%s %s" % (k, v) for k, v in probe_results.items()))).strip(" |")
    # version bump
    ver = data.get("version") or "0"
    data["version"] = ver.split(".")[0] + "." + str(int(ver.split(".")[-1]) + 1 if ver.split(".")[-1].isdigit() else 1)
    if file_sig(path) != sig:
        fail("book", "写前重读发现注册表在处理期间被修改（并发冲突），已中止；请重跑", conflict=True)
    atomic_write_json(path, data)
    out = {"registry_path": path, "lastVerified": today, "version": data["version"]}
    if backlog_text:
        bl = os.path.join(SKILL_DIR, "curation_backlog.md")
        with open(bl, "a", encoding="utf-8") as f:
            f.write("- %s | %s | %s | 下次接入同厂商 / 用户点名 / 定期清理\n"
                    % (today, model_id, backlog_text.strip()))
        out["backlog"] = "appended"
    return out


# ---------------- 子命令 ----------------

def resolve(phrase, entry_id=None):
    if entry_id:
        _, data = locate_entry_layer(entry_id)
        if data and entry_id in (data.get("models") or {}):
            return data["models"][entry_id]
        fail("match", "--id 指定的条目不在注册表: %s" % entry_id)
    m = run_match(phrase)
    st = m.get("status")
    if st != "unique":
        emit({"ok": False, "step": "match", "status": st, "match": m,
              "detail": {"ambiguous": "多条命中，agent 单条提问让用户二选一",
                         "miss": "0 命中，退回读文档全流程",
                         "tombstone": "墓碑短路，转免费发现层",
                         "disabled": "渠道已停用，转免费发现层/读文档",
                         "registry_unavailable": "注册表不可用，视同 0 命中"}.get(st, "非唯一命中，转人工分流")})
        sys.exit(1)
    return m["hits"][0]["entry"]


def cmd_inspect(args):
    reg = resolve(args.phrase, getattr(args, "id", None))
    host_path = os.path.expanduser(args.host_config)
    host = load_json(host_path)
    if host is None:
        fail("inspect", "宿主配置不可读: %s" % host_path)
    entry = find_host_entry(host, reg["modelId"])
    defects = diagnose(reg, entry)
    emit({"ok": True, "step": "inspect", "modelId": reg["modelId"], "confidence": reg.get("confidence"),
          "lastVerified": reg.get("lastVerified"), "host_entry_found": entry is not None,
          "defects": defects, "host_config": host_path,
          "summary": "宿主条目 %s，缺陷 %d 处：%s" % (
              "存在" if entry else "缺失", len(defects),
              "、".join(d["field"] for d in defects) or "无")})


def cmd_fix(args):
    reg = resolve(args.phrase, getattr(args, "id", None))
    host_path = os.path.expanduser(args.host_config)
    host = load_json(host_path)
    if host is None:
        fail("fix", "宿主配置不可读: %s" % host_path)
    new_host, changed, created = apply_fix(reg, host, host_path, args.dry_run)
    emit({"ok": True, "step": "fix", "modelId": reg["modelId"], "created": created,
          "dry_run": args.dry_run, "changed": changed,
          "need_key": created,
          "summary": "%s条目 %s：%s%s" % (
              "新建" if created else "修正", reg["modelId"],
              "、".join("%s %s→%s" % (c["field"], c["from"], c["to"]) for c in changed) or "无需改动",
              "；apiKey 为空需用户补" if created and not (new_host and any(
                  m.get("id") == reg["modelId"] and m.get("apiKey") for m in new_host if isinstance(m, dict))) else "")})


def cmd_verify(args):
    reg = resolve(args.phrase, getattr(args, "id", None))
    host_path = os.path.expanduser(args.host_config)
    host = load_json(host_path)
    entry = find_host_entry(host or [], reg["modelId"]) if host is not None else None
    key = (entry or {}).get("apiKey") or ""
    if not key:
        fail("verify", "宿主条目缺 apiKey（新建条目需先由用户补 key）", need_key=True)
    domain = None
    try:
        from urllib.parse import urlparse
        domain = urlparse(reg["url"]).netloc
    except Exception:
        pass
    ok_s, smoke = run_probe("smoke", reg["url"], reg["modelId"], key, domain)
    results = {"smoke": smoke.get("result")}
    ok = ok_s
    if args.image:
        ok_i, img = run_probe("image", reg["url"], reg["modelId"], key, domain)
        results["imageInput"] = img.get("result")
        if img.get("body_excerpt"):
            results["imageBody"] = img["body_excerpt"][:160]
        ok = ok and ok_i
    load = host_load_check(reg["modelId"])
    emit({"ok": ok, "step": "verify", "modelId": reg["modelId"], "probes": results,
          "host_load": load, "smoke": smoke,
          "summary": "探针：%s；宿主加载：%s" % (
              "、".join("%s %s" % (k, v) for k, v in results.items()),
              load["detail"])})


def cmd_book(args):
    reg = resolve(args.phrase, getattr(args, "id", None))
    results = {}
    if args.probe_results:
        try:
            results = json.loads(args.probe_results)
        except Exception:
            fail("book", "--probe-results 不是合法 JSON")
    out = book_registry(reg, reg["modelId"], results, args.backlog)
    emit({"ok": True, "step": "book", "modelId": reg["modelId"], "book": out,
          "summary": "注册表已回写（%s，version %s）%s" % (
              out["registry_path"], out["version"],
              "，慢车道待办已登记" if out.get("backlog") else "")})


def cmd_run(args):
    reg = resolve(args.phrase, getattr(args, "id", None))
    host_path = os.path.expanduser(args.host_config)
    sig0 = file_sig(host_path) if os.path.exists(host_path) else None
    host = load_json(host_path)
    if host is None:
        fail("run", "宿主配置不可读: %s" % host_path)
    entry = find_host_entry(host, reg["modelId"])
    defects = diagnose(reg, entry)
    created = entry is None
    changed = []
    if defects and not args.dry_run:
        host, changed, created = apply_fix(reg, host, host_path, False)
    elif defects:
        changed = [{"field": d["field"], "from": d["current"], "to": d["expected"]} for d in defects]

    steps = {"inspect": {"defects": defects}}
    need_key = created and not find_host_entry(load_json(host_path) or [], reg["modelId"]).get("apiKey", "") \
        if (created and not args.dry_run) else False
    if args.dry_run:
        emit({"ok": True, "step": "run", "dry_run": True, "modelId": reg["modelId"],
              "planned_fix": changed, "summary": "dry-run：将修 %d 处，不发探针不回写" % len(changed)})
        return

    key = (find_host_entry(load_json(host_path) or [], reg["modelId"]) or {}).get("apiKey") or ""
    if not key:
        emit({"ok": False, "step": "run", "modelId": reg["modelId"], "need_key": True,
              "fix_applied": changed,
              "summary": "配置已修好但 apiKey 为空——请用户提供 key 后补 verify/book（或走合并提问）"})
        return

    domain = None
    try:
        from urllib.parse import urlparse
        domain = urlparse(reg["url"]).netloc
    except Exception:
        pass
    ok_s, smoke = run_probe("smoke", reg["url"], reg["modelId"], key, domain)
    probe_results = {"smoke": smoke.get("result")}
    ok = ok_s
    if args.image:
        ok_i, img = run_probe("image", reg["url"], reg["modelId"], key, domain)
        probe_results["imageInput"] = img.get("result")
        ok = ok and ok_i
    load = host_load_check(reg["modelId"])
    steps["verify"] = {"probes": probe_results, "host_load": load}

    book_out = None
    if ok and not args.no_book:
        book_out = book_registry(reg, reg["modelId"], probe_results, args.backlog)
        steps["book"] = book_out

    emit({"ok": ok, "step": "run", "modelId": reg["modelId"], "created": created,
          "fix_applied": changed, "probes": probe_results, "host_load": load, "book": book_out,
          "summary": "%s｜修 %d 处｜探针 %s｜宿主加载 %s｜回写 %s" % (
              reg["modelId"], len(changed),
              "、".join("%s %s" % (k, v) for k, v in probe_results.items()),
              load.get("detail"), "已回写" if book_out else ("跳过" if args.no_book else "未回写（探针未全过）"))})


def main():
    ap = argparse.ArgumentParser(description="model-connector 一键接入编排器")
    ap.add_argument("--host-config", default=DEFAULT_HOST)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("inspect", help="匹配 + 宿主体检（零网络）")
    p.add_argument("phrase")
    p.add_argument("--id", default=None, help="直接指定注册表条目 id（ambiguous 二选一后用）")
    p.set_defaults(fn=cmd_inspect)

    p = sub.add_parser("fix", help="按注册表值修宿主条目")
    p.add_argument("phrase")
    p.add_argument("--id", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_fix)

    p = sub.add_parser("verify", help="smoke 探针 + 宿主加载检查")
    p.add_argument("phrase")
    p.add_argument("--id", default=None)
    p.add_argument("--image", action="store_true")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("book", help="注册表回写 + 慢车道待办")
    p.add_argument("phrase")
    p.add_argument("--id", default=None)
    p.add_argument("--probe-results", default="{}", help='JSON 如 {"smoke":"ok-200"}')
    p.add_argument("--backlog", default=None)
    p.set_defaults(fn=cmd_book)

    p = sub.add_parser("run", help="一键全链 inspect→fix→verify(smoke)→book")
    p.add_argument("phrase")
    p.add_argument("--id", default=None)
    p.add_argument("--image", action="store_true")
    p.add_argument("--no-book", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--backlog", default=None)
    p.set_defaults(fn=cmd_run)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
