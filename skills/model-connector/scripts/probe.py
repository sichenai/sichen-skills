#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""model-connector 探针脚本（stdlib-only，零依赖；宿主需能执行 python3 命令才可用，否则按 SKILL.md 手动等价流程）。

子命令：
  smoke           最简文本请求（默认）；--stream 用流式形态验证
  output-limit    验证 maxOutputTokens：先试 claimed（200 即收工），被拒才二分（上限 8 轮）
  image           图片输入探针（内嵌 1x1 红色 PNG，问颜色；200=支持，4xx=不支持）
  tool            工具调用探针（哑工具 get_weather，检查 tool_calls）
  input-limit     输入上限探针：超长 filler 触发 400，从错误体提取真实上限（ EXPERIMENTAL，
                  大 pad 有真实 token 成本，>50000 tokens 须加 --confirm）
  context-metadata 无 key 白拿 OpenRouter /models 的 context_length 元数据

通用参数：--url --model --key（传 "-" 从 stdin 读，避免进 shell 历史/进程列表）
安全门禁：--expect-domain <domain> 时，url 域名必须等于或为其子域，否则 exit 3 拒发（key 保护）。

429 纪律（内建，手动流程等价）：退避 2s→8s→30s，三次仍 429 即熔断（exit 4），
result 标 "rate_limited_aborted"；429 永不计入上限边界。

退出码：0=探针通过 1=探针否定（被拒/不支持） 2=不确定 3=域名门禁拒绝 4=限流熔断
输出：stdout 单行 JSON（机器可读）；进度注释走 stderr。
"""

import argparse
import base64
import json
import re
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

BACKOFFS = [2, 8, 30]
UA = "model-connector-probe/1.10"


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False))


def http_json(url, key=None, payload=None, method=None, timeout=90):
    headers = {"Content-Type": "application/json", "User-Agent": UA}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # URLError/timeout/ssl/OSSysError 归并为网络层错误
        return 0, "network-error: %s" % e


def http_raw(url, key, payload, timeout=90, read_cap=8192):
    """流式请求：只读前 read_cap 字节判断是否真在流式返回，不读完。"""
    headers = {"Content-Type": "application/json", "User-Agent": UA, "Accept": "text/event-stream"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            head = resp.read(read_cap).decode("utf-8", "replace")
            return resp.status, head
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, "network-error: %s" % e


def with_backoff(fn):
    """429 退避熔断：2/8/30s 三次重试，仍 429 返回 (429, 熔断标记)。"""
    for i, wait in enumerate([0] + BACKOFFS):
        if wait:
            print("[backoff] 429，退避 %ds（第 %d/%d 次）" % (wait, i, len(BACKOFFS)), file=sys.stderr)
            time.sleep(wait)
        status, body = fn()
        if status != 429:
            return status, body
    return 429, json.dumps({"probe_error": "rate_limited_aborted",
                            "detail": "backoff %s 后仍 429，熔断；上限标「限流阻断未定界」" % BACKOFFS})


def check_domain(url, expect, allow_untrusted):
    if not expect:
        return True
    host = re.sub(r":\d+$", "", urllib.parse.urlsplit(url).netloc.lower())
    ok = host == expect.lower() or host.endswith("." + expect.lower())
    if ok or allow_untrusted:
        return True
    emit({"gate": "domain_refused", "url_host": host, "expected": expect,
          "detail": "url 域名不在 --expect-domain 内，拒发（key 保护）。确认无误可用 --allow-untrusted 显式放行"})
    sys.exit(3)


def read_key(args):
    if args.key == "-":
        line = sys.stdin.readline().strip()
        if not line:
            emit({"gate": "no_key", "detail": "stdin 未读到 key"})
            sys.exit(2)
        return line
    return args.key


def tiny_red_png_datauri():
    """内嵌生成 1x1 红色 PNG（不依赖外部图片/硬编码 base64）。"""
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1, 8bit, RGB
    raw = b"\x00\xff\x00\x00"                            # filter0 + RGB(255,0,0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def chat_payload(args, messages, extra=None):
    p = {"model": args.model, "messages": messages, "stream": False}
    if extra:
        p.update(extra)
    return p


# ---------------- 子命令 ----------------

def cmd_smoke(args):
    check_domain(args.url, args.expect_domain, args.allow_untrusted)
    key = read_key(args)
    msgs = [{"role": "user", "content": "你好"}]
    if args.stream:
        status, body = with_backoff(lambda: http_raw(args.url, key, chat_payload(args, msgs, {"stream": True}),
                                                     timeout=args.timeout))
        ok = status == 200 and "data:" in body
        emit({"probe": "smoke", "mode": "stream", "status_code": status,
              "result": "ok-200-stream" if ok else ("rejected-%d" % status if status >= 400 else "inconclusive"),
              "head": body[:400]})
        sys.exit(0 if ok else (1 if status >= 400 else (4 if status == 429 else 2)))
    status, body = with_backoff(lambda: http_json(args.url, key, chat_payload(args, msgs, {"max_tokens": 16}),
                                                  timeout=args.timeout))
    ok = status == 200
    emit({"probe": "smoke", "status_code": status, "result": "ok-200" if ok else "rejected-%d" % status,
          "body_excerpt": body[:400]})
    sys.exit(0 if ok else (4 if status == 429 else 1))


def cmd_output_limit(args):
    check_domain(args.url, args.expect_domain, args.allow_untrusted)
    key = read_key(args)
    msgs = [{"role": "user", "content": "你好"}]
    rounds = 0

    def try_max_tokens(n):
        nonlocal rounds
        rounds += 1
        return with_backoff(lambda: http_json(args.url, key, chat_payload(args, msgs, {"max_tokens": n}),
                                              timeout=args.timeout))

    status, body = try_max_tokens(args.claimed)
    if status == 200:
        emit({"probe": "output-limit", "verified": args.claimed, "rejected": None,
              "rounds": rounds, "result": "claimed_ok", "detail": "claimed 值一次通过，未二分"})
        sys.exit(0)
    if status != 400:
        emit({"probe": "output-limit", "status_code": status, "result": "inconclusive",
              "body_excerpt": body[:400], "detail": "非 400 拒绝，见错误码决策表"})
        sys.exit(4 if status == 429 else 2)

    # 找可行下界
    lo = None
    for candidate in (1024, 256, 64):
        s, _ = try_max_tokens(candidate)
        if s == 200:
            lo = candidate
            break
        if s != 400:
            emit({"probe": "output-limit", "status_code": s, "result": "inconclusive",
                  "detail": "找下界时遇非 400，见错误码决策表"})
            sys.exit(4 if s == 429 else 2)
    if lo is None:
        emit({"probe": "output-limit", "result": "inconclusive", "detail": "max_tokens=64 仍 400，端点本身异常"})
        sys.exit(2)

    hi = args.claimed
    converged = False
    while rounds < args.max_rounds and hi - lo > 1:
        mid = (lo + hi) // 2
        s, _ = try_max_tokens(mid)
        if s == 200:
            lo = mid
        elif s == 400:
            hi = mid
        else:
            emit({"probe": "output-limit", "status_code": s, "result": "inconclusive",
                  "verified_so_far": lo, "detail": "二分中遇非 400/429，见错误码决策表"})
            sys.exit(4 if s == 429 else 2)
    if hi - lo <= 1:
        converged = True
    gap_pct = round((hi - lo) * 100.0 / max(hi, 1), 1)
    emit({"probe": "output-limit", "verified": lo, "rejected": hi, "rounds": rounds,
          "converged": converged, "result": "verified" if converged else "boundary_coarse",
          "caveat": None if converged else "达轮次上限未收敛，区间 [verified, rejected)，写入取 verified 并在交付说明标注区间",
          "gap_pct": gap_pct})
    sys.exit(0)


def cmd_image(args):
    check_domain(args.url, args.expect_domain, args.allow_untrusted)
    key = read_key(args)
    uri = tiny_red_png_datauri()
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "What color is this image? Reply with one word."},
        {"type": "image_url", "image_url": {"url": uri}},
    ]}]
    status, body = with_backoff(lambda: http_json(args.url, key, chat_payload(args, msgs, {"max_tokens": 32}),
                                                  timeout=args.timeout))
    if status == 200:
        emit({"probe": "image", "status_code": 200, "result": "ok-200", "body_excerpt": body[:400],
              "detail": "注意核对回复是否正确识别红色；答非所问也计支持（接受即支持），但写入 quirks"})
        sys.exit(0)
    snippet = body[:300]
    unsupported = status == 404 and ("support" in snippet.lower() or "endpoint" in snippet.lower())
    emit({"probe": "image", "status_code": status, "result": "rejected-%d" % status,
          "unsupported_clear": unsupported, "body_excerpt": snippet})
    sys.exit(1)


def cmd_tool(args):
    check_domain(args.url, args.expect_domain, args.allow_untrusted)
    key = read_key(args)
    tool = {"type": "function", "function": {
        "name": "get_weather", "description": "Get current weather for a city",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}
    msgs = [{"role": "user", "content": "What is the weather in Tokyo? Use the get_weather tool."}]
    status, body = with_backoff(lambda: http_json(
        args.url, key, chat_payload(args, msgs, {"max_tokens": 256, "tools": [tool], "tool_choice": "auto"}),
        timeout=args.timeout))
    if status == 200:
        try:
            msg = json.loads(body)["choices"][0]["message"]
            has_calls = bool(msg.get("tool_calls"))
        except Exception:
            emit({"probe": "tool", "status_code": 200, "result": "inconclusive",
                  "body_excerpt": body[:400], "detail": "200 但响应结构与 OpenAI 不一致，人工核对"})
            sys.exit(2)
        emit({"probe": "tool", "status_code": 200,
              "result": "ok-200" if has_calls else "no-tool-call",
              "detail": None if has_calls else "200 但未发起 tool_calls（可能未理解工具或方言不同），人工核对"})
        sys.exit(0 if has_calls else 2)
    emit({"probe": "tool", "status_code": status, "result": "rejected-%d" % status, "body_excerpt": body[:300]})
    sys.exit(1)


def cmd_input_limit(args):
    check_domain(args.url, args.expect_domain, args.allow_untrusted)
    key = read_key(args)
    pad_tokens = args.pad_tokens
    if pad_tokens > 50000 and not args.confirm:
        emit({"gate": "cost_confirm_required",
              "detail": "pad_tokens>50000 会产生真实输入 token 费用，确认成本后加 --confirm 重跑（或改用 context-metadata 元数据档）"})
        sys.exit(2)
    filler = "lorem ipsum dolar sit amet " * max(1, int(pad_tokens * 4 / 27))
    msgs = [{"role": "user", "content": filler + "\nReply with: ok"}]
    status, body = with_backoff(lambda: http_json(args.url, key, chat_payload(args, msgs, {"max_tokens": 16}),
                                                  timeout=args.timeout))
    digits = set()
    for pat in (r"(?i)maximum[^\d]{0,80}([\d,]{3,})", r"(?i)context[^\d]{0,80}([\d,]{3,})",
                r"([\d,]{4,})\s*(?:tokens|token)"):
        for m in re.finditer(pat, body):
            digits.add(int(m.group(1).replace(",", "")))
    result = {0: "network_error", 200: "pad_accepted", 400: "disclosed" if digits else "rejected_no_disclosure"}.get(
        status, "rejected-%d" % status)
    emit({"probe": "input-limit", "status_code": status, "result": result,
          "pad_tokens_approx": pad_tokens, "disclosed_candidates": sorted(digits), "body_excerpt": body[:500],
          "detail": "disclosed_candidates 须人工判断口径（总量 vs 输入；输入+输出合并时按 SKILL.md 合计口径保守拆分）"})
    sys.exit(0 if result == "disclosed" else (1 if status == 400 else (4 if status == 429 else 2)))


def cmd_context_metadata(args):
    url = args.endpoint
    status, body = with_backoff(lambda: http_json(url, None, None, method="GET", timeout=30))
    if status != 200:
        emit({"probe": "context-metadata", "status_code": status, "result": "inconclusive",
              "body_excerpt": body[:300]})
        sys.exit(2)
    try:
        entries = json.loads(body)["data"]
    except Exception:
        emit({"probe": "context-metadata", "result": "inconclusive", "detail": "响应无 data 数组"})
        sys.exit(2)
    hits = [e for e in entries if e.get("id") == args.model]
    if not hits:
        frag = args.model.lower()
        sub = [e for e in entries if frag in e.get("id", "").lower()]
        if len(sub) == 1:
            hits = sub
        elif len(sub) > 1:
            emit({"probe": "context-metadata", "result": "ambiguous",
                  "candidates": [e.get("id") for e in sub[:10]],
                  "detail": "子串命中多条，需精确 id"})
            sys.exit(2)
    if not hits:
        emit({"probe": "context-metadata", "result": "not_found", "model": args.model})
        sys.exit(1)
    e = hits[0]
    emit({"probe": "context-metadata", "result": "ok", "id": e.get("id"),
          "context_length": e.get("context_length"),
          "pricing": e.get("pricing"),
          "detail": "context_length 为厂商自报元数据，采信为 maxInputTokens 的 documented 来源（仍按探针分级复核）"})
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(description="model-connector 探针脚本（见文件头 docstring）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, need_model=True):
        p.add_argument("--url", required=True, help="chat/completions 完整 url")
        if need_model:
            p.add_argument("--model", required=True)
        p.add_argument("--key", default=None, help="API key；传 - 从 stdin 读（推荐，避免进进程列表）")
        p.add_argument("--expect-domain", default=None, help="域名白名单门禁，如 api.deepseek.com")
        p.add_argument("--allow-untrusted", action="store_true", help="显式放行域名门禁（中转端点用户确认后用）")
        p.add_argument("--timeout", type=int, default=90)

    p = sub.add_parser("smoke", help="最简文本请求")
    common(p)
    p.add_argument("--stream", action="store_true", help="流式形态验证")
    p.set_defaults(fn=cmd_smoke)

    p = sub.add_parser("output-limit", help="输出上限验证/二分")
    common(p)
    p.add_argument("--claimed", type=int, required=True, help="注册表/文档 maxOutputTokens 值")
    p.add_argument("--max-rounds", type=int, default=8)
    p.set_defaults(fn=cmd_output_limit)

    p = sub.add_parser("image", help="图片输入探针")
    common(p)
    p.set_defaults(fn=cmd_image)

    p = sub.add_parser("tool", help="工具调用探针")
    common(p)
    p.set_defaults(fn=cmd_tool)

    p = sub.add_parser("input-limit", help="输入上限错误体披露探针（EXPERIMENTAL）")
    common(p)
    p.add_argument("--pad-tokens", type=int, required=True)
    p.add_argument("--confirm", action="store_true", help="确认大 pad 的真实成本")
    p.set_defaults(fn=cmd_input_limit)

    p = sub.add_parser("context-metadata", help="OpenRouter models 元数据（无 key）")
    p.add_argument("--model", required=True)
    p.add_argument("--endpoint", default="https://openrouter.ai/api/v1/models")
    p.set_defaults(fn=cmd_context_metadata)

    args = ap.parse_args()
    if getattr(args, "key", None) is None and args.cmd != "context-metadata":
        emit({"gate": "no_key", "detail": "探针需要 key（--key 或 stdin）；context-metadata 子命令除外"})
        sys.exit(2)
    args.fn(args)


if __name__ == "__main__":
    main()
