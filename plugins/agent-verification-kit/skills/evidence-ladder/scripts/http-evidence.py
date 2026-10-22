#!/usr/bin/env python3
"""GET a URL and judge the BODY, not the status code. Read-only, stdlib only.

A 200 is a proxy. This probe reads the body and says PASS only when the body
carries the evidence you asked for. Without --expect, --expect-status or
--expect-redirect it can never say PASS: the best it gives is UNKNOWN
("status looks fine, nothing proven").

Usage (Python 3.8+):
  python http-evidence.py http://127.0.0.1:8000/api/items --expect '"items"'
  python http-evidence.py "$API_URL/health" --expect '"ok"' --expect '"db"'
  python http-evidence.py "$API_URL/private" --expect-status 401
  python http-evidence.py "$PUBLIC_URL/" --expect-redirect login
  python http-evidence.py "$API_URL/me" --header-env AUTH_HEADER --expect '"user"'
      (AUTH_HEADER holds the full header, e.g. "Authorization: Bearer ...";
       the value is never printed)

Verdicts:
  PASS     the asserted status/redirect/body evidence is all present and no
           error marker was found in a 2xx body
  FAIL     non-2xx (unless asserted), an error marker inside a 2xx body, a
           missing --expect string, or a transport error
  UNKNOWN  2xx and clean, but nothing was asserted: nothing was proven
Exit 0 on PASS, 1 on FAIL, 2 on UNKNOWN.

Error markers caught under a 200: a JSON `error` or `errors` key, `isError:
true` (MCP), `result.isError: true`, and `status` of error/fail/failed.
Add your own with --error-marker <substring> (repeatable).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def error_markers(body_text, extra):
    hits = []
    try:
        d = json.loads(body_text)
    except ValueError:
        d = None
    if isinstance(d, dict):
        if d.get("error"):
            hits.append("json key 'error'")
        if d.get("errors"):
            hits.append("json key 'errors'")
        if d.get("isError") is True:
            hits.append("json isError=true")
        if str(d.get("status", "")).lower() in ("error", "fail", "failed"):
            hits.append("json status=%s" % d.get("status"))
        res = d.get("result")
        if isinstance(res, dict) and res.get("isError") is True:
            hits.append("json result.isError=true (MCP tool call failed)")
    low = body_text[:8000].lower()
    for m in extra:
        if m.lower() in low:
            hits.append("marker %r present" % m)
    return hits


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def main():
    ap = argparse.ArgumentParser(
        description="GET a URL and judge the body, not the status code.",
        epilog="Exit 0 PASS, 1 FAIL, 2 UNKNOWN. Without an --expect* flag the best verdict is UNKNOWN.")
    ap.add_argument("url")
    ap.add_argument("--expect", action="append", default=[],
                    help="substring that must appear in the body (repeatable)")
    ap.add_argument("--expect-status", type=int,
                    help="assert this exact status code (for negative tests, e.g. 401 or 404)")
    ap.add_argument("--expect-redirect",
                    help="assert a 3xx whose Location header contains this substring")
    ap.add_argument("--error-marker", action="append", default=[],
                    help="extra substring that means failure even under a 2xx (repeatable)")
    ap.add_argument("--header", action="append", default=[],
                    help='literal header "Name: value" (repeatable; prefer --header-env for secrets)')
    ap.add_argument("--header-env", action="append", default=[],
                    help='name of an env var holding a full "Name: value" header (never printed)')
    ap.add_argument("--method", default="GET")
    ap.add_argument("--timeout", type=float, default=15)
    a = ap.parse_args()

    req = urllib.request.Request(a.url, method=a.method,
                                 headers={"User-Agent": "evidence-ladder/1.0"})
    for h in a.header:
        k, _, v = h.partition(":")
        req.add_header(k.strip(), v.strip())
    for name in a.header_env:
        raw = os.environ.get(name)
        if not raw or ":" not in raw:
            print("FAIL  env var %s is unset or not of the form 'Name: value'" % name)
            return 1
        k, _, v = raw.partition(":")
        req.add_header(k.strip(), v.strip())

    opener = urllib.request.build_opener(NoRedirect)
    t = time.time()
    location = ""
    try:
        r = opener.open(req, timeout=a.timeout)
        code, body, ctype = r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        code, body, ctype = e.code, e.read(), e.headers.get("Content-Type", "")
        location = e.headers.get("Location", "") or ""
    except Exception as e:
        print("FAIL  transport error: %s: %s" % (type(e).__name__, str(e)[:200]))
        return 1
    secs = time.time() - t
    text = body.decode("utf-8", errors="replace")
    print("status=%s  time=%.2fs  bytes=%d  type=%s" % (code, secs, len(body), ctype[:40]))
    if location:
        print("location=%s" % location[:120])

    if a.expect_redirect:
        if 300 <= code < 400 and a.expect_redirect in location:
            print("PASS  redirect goes where expected")
            return 0
        print("FAIL  expected a 3xx whose Location contains %r" % a.expect_redirect)
        return 1

    reasons = []
    if a.expect_status is not None:
        if code != a.expect_status:
            reasons.append("status %s, expected %s" % (code, a.expect_status))
    elif not 200 <= code < 300:
        reasons.append("status %s" % code)
    marks = error_markers(text, a.error_marker)
    if 200 <= code < 300 and marks:
        reasons.append("2xx with an error body: " + "; ".join(marks))
    missing = [s for s in a.expect if s not in text]
    if missing:
        reasons.append("missing expected text: %r" % missing)
    if reasons:
        print("FAIL  " + " | ".join(reasons))
        print("body head: " + " ".join(text[:200].split()))
        return 1
    if not a.expect and a.expect_status is None:
        print("UNKNOWN  status is fine but nothing was proven; rerun with "
              "--expect <text only the working thing returns>")
        return 2
    print("PASS  " + ("status matches" if not a.expect else "body carries the expected evidence"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
