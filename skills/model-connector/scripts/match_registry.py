#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""model-connector 双层注册表匹配脚本（SKILL.md Step 0 的可执行版，手动流程等价）。

用法：python3 match_registry.py "用户口语模型名" [--dir SKILL目录]
默认 --dir = 本脚本所在目录的上一级（即 skill 根目录）。

流程：加载公共表 → local 覆盖合并（条目级整体替换）→ 墓碑短路 → 规范化（小写、
空格/连字符统一）→ 子串匹配（用户词 ∈ 条目 id 或 alias）→ 唯一命中/多命中/未命中分流。

退出码：0=唯一命中 1=未命中（退回读文档全流程） 2=多命中（单条追问二选一）
3=墓碑命中（不预填不追问 key，转免费发现层） 4=注册表不可读（视同 0 命中退回读文档）
输出：stdout 单行 JSON。
"""

import argparse
import json
import os
import re
import sys


def norm(s):
    return re.sub(r"[\s\-]+", " ", s.strip().lower())


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


LEAD_WORDS = ["帮我", "帮忙", "给我", "请", "接入", "接", "接入到", "配置", "配", "连接", "连", "换", "切换", "用", "使用"]
TRAIL_WORDS = ["模型", "大模型", "这个模型", "api", "渠道", "端点"]


def strip_colloquial(phrase):
    """剥离常见动词/客套前后缀（如「接 mimo pro」→「mimo pro」）。只剥一轮，防误伤。"""
    p = phrase
    changed = True
    while changed:
        changed = False
        for w in LEAD_WORDS:
            if p.startswith(w) and len(p) > len(w):
                p = p[len(w):].strip()
                changed = True
        for w in TRAIL_WORDS:
            if p.endswith(w) and len(p) > len(w):
                p = p[: -len(w)].strip()
                changed = True
    return p


def match_in(merged, user):
    hits = []
    for mid, m in merged.items():
        matched_via = None
        for key in [mid] + (m.get("aliases") or []):
            if user in norm(key):
                matched_via = key
                break
        if matched_via:
            hits.append({"id": mid, "matched_via": matched_via, "vendor": m.get("vendor"),
                         "url": m.get("url"), "modelId": m.get("modelId"),
                         "confidence": m.get("confidence"), "lastVerified": m.get("lastVerified"),
                         "freeTier": m.get("freeTier")})
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phrase", help="用户口语模型名")
    ap.add_argument("--dir", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = ap.parse_args()

    public_path = os.path.join(args.dir, "models_registry.json")
    local_path = os.path.join(args.dir, "models_registry.local.json")
    public = load_json(public_path)
    if public is None or not isinstance(public.get("models"), dict):
        print(json.dumps({"status": "registry_unavailable",
                          "detail": "公共表缺失或解析失败，视同 0 命中，退回读文档全流程（不打断）"},
                         ensure_ascii=False))
        sys.exit(4)

    local = load_json(local_path) if os.path.exists(local_path) else None
    merged = dict(public["models"])
    if local and isinstance(local.get("models"), dict):
        for mid, m in local["models"].items():  # 条目级整体替换
            merged[mid] = m

    user = norm(args.phrase)
    if not user:
        print(json.dumps({"status": "miss", "user": args.phrase, "hits": []}, ensure_ascii=False))
        sys.exit(1)

    # 墓碑短路（公共表为主，local 若带 retiredModels 同样参与）
    for t in (public.get("retiredModels") or []) + ((local.get("retiredModels") if local else None) or []):
        keys = [t.get("id", "")] + (t.get("aliases") or [])
        if any(user in norm(k) for k in keys if k):
            print(json.dumps({"status": "tombstone", "user": args.phrase, "id": t.get("id"),
                              "retiredOn": t.get("retiredOn"), "reason": t.get("reason"),
                              "detail": "不预填不追问 key，转免费优先发现层推荐替代"},
                             ensure_ascii=False))
            sys.exit(3)

    hits = match_in(merged, user)
    if not hits and strip_colloquial(user) != user:
        user2 = strip_colloquial(user)
        hits = match_in(merged, user2)
        if hits:
            user = user2 + "（剥离口语前后缀后）"

    if len(hits) == 1:
        h = hits[0]
        h["entry"] = merged[h["id"]]
        print(json.dumps({"status": "unique", "user": args.phrase, "hits": hits}, ensure_ascii=False))
        sys.exit(0)
    if len(hits) > 1:
        print(json.dumps({"status": "ambiguous", "user": args.phrase, "hits": hits,
                          "detail": "单条提问二选一，防兄弟模型能力错配"}, ensure_ascii=False))
        sys.exit(2)
    print(json.dumps({"status": "miss", "user": args.phrase, "hits": [],
                      "detail": "0 命中，退回 Step 1-3 读文档全流程"}, ensure_ascii=False))
    sys.exit(1)


if __name__ == "__main__":
    main()
