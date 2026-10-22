#!/usr/bin/env python3
"""Smoke or load-test an OpenAI-compatible LLM endpoint with evidence that
cannot come from a cache. Read-only; each call spends one request on the
target, so point it at a free tier or a local model when you can.

Every call carries a fresh nonce the model must echo back. A call counts as
OK only when the HTTP status is 200 AND the reply content contains the nonce
AND no cache header came back. So a cached reply, a fallback model answering
for a dead one, and a reasoning model that spent its whole budget thinking
(200, content null) all fail.

Usage (Python 3.8+, stdlib only):
  export GATEWAY_URL=http://127.0.0.1:4000
  export MY_KEY=...                       # never passed on the command line
  python llm-smoke.py --model my-group --key-env MY_KEY
  python llm-smoke.py --model a --model b --key-env MY_KEY
  python llm-smoke.py --model my-group --key-env MY_KEY --concurrency 4 --duration 150
  python llm-smoke.py --model my-group --key-env MY_KEY --max-tokens 16
      (on a reasoning model this should FAIL NO-ECHO: that is the trap being caught)

Gateway extras: by default the body also carries {"cache": {"no-cache": true}}
and "disable_fallbacks": true, which LiteLLM-style gateways honour. Pass
--plain for a strict endpoint that rejects unknown fields. The cache header
checked is --cache-header (default x-litellm-cache-key); set it to whatever
your gateway sends on a cache hit, or "" to skip the header check.

--duration 0 (default) sends ONE call per worker: a volley. A volley measures
the burst allowance, never a sustained rate, and the output says so.

--refuse=REGEX (or env LLM_SMOKE_REFUSE) skips model names you never want to
hit from a test, e.g. names that load a local GPU model or evict a resident
one. Use the = form when the pattern starts with a hyphen (--refuse='-local-').
A refused model counts as FAIL so it cannot pass by being skipped.

The API key is read from the env var named by --key-env and is never printed.
Exit 0 when every model PASSed, 1 otherwise.
"""
import argparse
import concurrent.futures as cf
import json
import os
import random
import re
import statistics
import sys
import time
import urllib.error
import urllib.request


def api_key(name):
    if not name:
        return ""
    k = os.environ.get(name)
    if not k:
        sys.exit("env var %s is not set (pass the NAME of the var with --key-env, not the key)" % name)
    return k


def one_call(base, key, model, max_tokens, timeout, plain, cache_header):
    nonce = "qa-%d-%06d" % (time.time(), random.randint(0, 999999))
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user",
                          "content": "Repeat this token exactly and nothing else: " + nonce}]}
    if not plain:
        body["disable_fallbacks"] = True
        body["cache"] = {"no-cache": True}
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(base + "/v1/chat/completions",
                                 data=json.dumps(body).encode(), headers=headers)
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
            cached = bool(cache_header and r.headers.get(cache_header))
        secs = time.time() - t
        ch = (d.get("choices") or [{}])[0]
        content = (ch.get("message") or {}).get("content") or ""
        served = str(d.get("model", ""))[:40]
        if cached:
            return "CACHED", secs, "%s header present: reply came from the cache" % cache_header
        if nonce not in content:
            why = "finish_reason=%s, content=%r" % (ch.get("finish_reason"), content[:60])
            return "NO-ECHO", secs, why
        return "OK", secs, served
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            msg = json.loads(raw).get("error", {})
            msg = msg.get("message", "") if isinstance(msg, dict) else str(msg)
        except ValueError:
            msg = raw
        # Error bodies can echo request fields; keep it short and never print headers.
        return "HTTP%d" % e.code, time.time() - t, " ".join(msg.split())[:120]
    except Exception as e:
        return "ERR", time.time() - t, "%s: %s" % (type(e).__name__, str(e)[:100])


def worker(args, deadline):
    out = [one_call(*args)]
    while deadline and time.time() < deadline:
        out.append(one_call(*args))
    return out


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100.0 * (len(xs) - 1))))]


def main():
    ap = argparse.ArgumentParser(
        description="Nonce-echo smoke/load test for an OpenAI-compatible chat endpoint.",
        epilog="PASS means every call returned 200, echoed the nonce, and carried no cache header.")
    ap.add_argument("--gateway", default=os.environ.get("GATEWAY_URL", ""),
                    help="base URL, e.g. http://127.0.0.1:4000 (default: env GATEWAY_URL)")
    ap.add_argument("--model", action="append", required=True,
                    help="model or model-group name (repeatable)")
    ap.add_argument("--key-env", default="GATEWAY_API_KEY",
                    help="NAME of the env var holding the API key (default GATEWAY_API_KEY); "
                         "pass '' for an endpoint with no auth")
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--duration", type=float, default=0,
                    help="seconds of sustained load; 0 = one volley (burst only)")
    ap.add_argument("--max-tokens", type=int, default=400,
                    help="keep generous: reasoning models spend tokens before answering")
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--plain", action="store_true",
                    help="omit gateway-only fields (cache no-cache, disable_fallbacks)")
    ap.add_argument("--cache-header", default="x-litellm-cache-key",
                    help="response header that marks a cache hit; '' to skip the check")
    ap.add_argument("--refuse", default=os.environ.get("LLM_SMOKE_REFUSE", ""),
                    help="regex of model names to refuse (default: env LLM_SMOKE_REFUSE)")
    a = ap.parse_args()

    if not a.gateway:
        sys.exit("no gateway: pass --gateway or set GATEWAY_URL")
    base, key = a.gateway.rstrip("/"), api_key(a.key_env)
    refuse = re.compile(a.refuse) if a.refuse else None
    rc = 0
    for model in a.model:
        if refuse and refuse.search(model):
            print("REFUSED %s: matches --refuse %r" % (model, a.refuse))
            rc = 1
            continue
        start = time.time()
        deadline = start + a.duration if a.duration > 0 else 0
        call_args = (base, key, model, a.max_tokens, a.timeout, a.plain, a.cache_header)
        with cf.ThreadPoolExecutor(a.concurrency) as ex:
            futs = [ex.submit(worker, call_args, deadline) for _ in range(a.concurrency)]
            res = [r for f in futs for r in f.result()]
        window = time.time() - start
        ok = [s for v, s, _ in res if v == "OK"]
        counts = {}
        for v, _, _ in res:
            counts[v] = counts.get(v, 0) + 1
        mode = ("SUSTAINED %.0fs" % window) if a.duration > 0 else ("VOLLEY (burst only, %.1fs)" % window)
        print("%s  %s  workers=%d  calls=%d  %s" % (
            model, mode, a.concurrency, len(res),
            " ".join("%s=%d" % kv for kv in sorted(counts.items()))))
        if ok:
            print("  latency OK calls: p50=%.2fs p95=%.2fs max=%.2fs  rate=%.2f ok/s over the window"
                  % (statistics.median(ok), pct(ok, 95), max(ok), len(ok) / window))
        for v, s, info in res:
            if v != "OK":
                print("  %-8s %6.2fs  %s" % (v, s, info))
                break
        verdict = "PASS" if ok and len(ok) == len(res) else "FAIL"
        print("  %s  (%d/%d calls proven by nonce echo, no cache)" % (verdict, len(ok), len(res)))
        if verdict == "FAIL":
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
