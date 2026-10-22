#!/usr/bin/env python3
"""Pipe a synthetic payload into a hook script and judge the JSON it prints.
Read-only, stdlib only.

Hook runners usually fail open: they exit 0 whatever happens, and a rule with
a broken regex is reported on stderr and then treated as "no match". The exit
code therefore proves nothing. The JSON on stdout is the only evidence a rule
is alive, and this script reads it for you.

Usage (Python 3.8+):
  python hook-pipe-test.py --hook ~/.claude/hooks/pre.py --tool Bash --command "ls -la" --expect none
  python hook-pipe-test.py --hook ~/.claude/hooks/pre.py --tool Bash --command "rm -rf /" --expect deny
  python hook-pipe-test.py --hook ~/.claude/hooks/pre.py --tool Bash --command-file ./positive.txt --expect deny --rule my-rule
  python hook-pipe-test.py --hook ~/.claude/hooks/prompt.py --prompt "some text" --expect warn
  python hook-pipe-test.py --hook ./hook.sh --payload-file ./payload.json --expect none
  python hook-pipe-test.py --hook ./hook.py --tool Bash --command "ls" -v      # just show the verdict

The payload follows the Claude Code hook shape: {"session_id", "hook_event_name",
"tool_name", "tool_input": {"command": ...}} for tool hooks and {"prompt": ...}
for UserPromptSubmit. --payload-file sends any JSON you give it verbatim.

Verdict mapping (anything not listed is UNKNOWN, never a pass):
  deny   exit code 2, or JSON with decision "block" / "deny", permissionDecision
         "deny", or continue false
  ask    permissionDecision "ask"
  allow  permissionDecision "allow"
  warn   exit 0 and JSON that adds a message but does not block
         (systemMessage, additionalContext, reason or message)
  none   exit 0 and empty stdout, or JSON with no decision and no message
  error  the hook crashed (exit code other than 0 or 2) or could not be run

--rule NAME additionally requires NAME to appear in the hook's output
(stdout or stderr), so you know which rule fired, not just that one did.

TEMP/TMP are pointed at a throwaway directory for the run, so a hook that
keeps "already warned this session" state never sees a stale copy.

Exit 0 when the verdict matched --expect (and --rule, if given), 1 otherwise.
With no --expect the script prints the verdict and exits 0 only for deny,
ask, allow, warn or none; UNKNOWN and error exit 1.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

WARN_KEYS = ("systemMessage", "additionalContext", "reason", "message", "warning")


def classify(returncode, stdout, stderr):
    """Return (verdict, detail). Default UNKNOWN."""
    out = (stdout or "").strip()
    if returncode == 2:
        return "deny", "exit 2 (blocking exit code)"
    if returncode != 0:
        return "error", "exit %s" % returncode
    if not out:
        return "none", "exit 0, empty stdout"
    try:
        d = json.loads(out)
    except ValueError:
        return "UNKNOWN", "stdout is not JSON: " + " ".join(out.split())[:160]
    if not isinstance(d, dict):
        return "UNKNOWN", "stdout JSON is not an object"
    spec = d.get("hookSpecificOutput") or {}
    if not isinstance(spec, dict):
        spec = {}
    decision = str(d.get("decision", "")).lower()
    perm = str(spec.get("permissionDecision", "")).lower()
    if d.get("continue") is False or decision in ("block", "deny") or perm == "deny":
        return "deny", "json decision=%s permissionDecision=%s continue=%s" % (
            decision or "-", perm or "-", d.get("continue", "-"))
    if perm == "ask":
        return "ask", "json permissionDecision=ask"
    if perm == "allow":
        return "allow", "json permissionDecision=allow"
    if any(d.get(k) for k in WARN_KEYS) or any(spec.get(k) for k in WARN_KEYS):
        return "warn", "json carries a message but does not block"
    if decision or perm:
        return "UNKNOWN", "unrecognised decision=%r permissionDecision=%r" % (decision, perm)
    return "none", "json with no decision and no message"


def build_payload(a):
    if a.payload_file:
        with open(a.payload_file, encoding="utf-8") as f:
            p = json.load(f)
        if not isinstance(p, dict):
            sys.exit("--payload-file must hold a JSON object")
    elif a.prompt is not None or a.prompt_file:
        text = a.prompt if a.prompt is not None else open(a.prompt_file, encoding="utf-8").read()
        p = {"hook_event_name": a.event or "UserPromptSubmit", "prompt": text}
    elif a.command is not None or a.command_file:
        text = a.command if a.command is not None else open(a.command_file, encoding="utf-8").read()
        p = {"hook_event_name": a.event or "PreToolUse", "tool_name": a.tool or "Bash",
             "tool_input": {"command": text}}
    else:
        sys.exit("give --command, --command-file, --prompt, --prompt-file or --payload-file")
    p.setdefault("session_id", a.session_id)
    if a.event:
        p["hook_event_name"] = a.event
    return p


def run_hook(hook, payload, interpreter, timeout):
    tmp = tempfile.mkdtemp(prefix="hook-pipe-test-")
    env = dict(os.environ, TEMP=tmp, TMP=tmp, TMPDIR=tmp)
    if interpreter:
        cmd = [interpreter, hook]
    elif hook.lower().endswith(".py"):
        cmd = [sys.executable, hook]
    else:
        cmd = [hook]
    try:
        return subprocess.run(cmd, input=json.dumps(payload), capture_output=True,
                              text=True, env=env, timeout=timeout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(
        description="Pipe a synthetic payload into a hook script and judge the JSON it prints.",
        epilog="Exit 0 when the verdict matched --expect (and --rule), 1 otherwise.")
    ap.add_argument("--hook", required=True, help="path to the hook script or executable")
    ap.add_argument("--interpreter", help="run the hook with this program (default: python for .py, else direct)")
    ap.add_argument("--event", help="hook_event_name (default: PreToolUse for --command, UserPromptSubmit for --prompt)")
    ap.add_argument("--tool", help="tool_name for tool hooks (default Bash)")
    ap.add_argument("--command", help="tool_input.command text")
    ap.add_argument("--command-file", help="file holding the command text (avoids the self-deny trap)")
    ap.add_argument("--prompt", help="prompt text for UserPromptSubmit hooks")
    ap.add_argument("--prompt-file", help="file holding the prompt text")
    ap.add_argument("--payload-file", help="JSON file sent verbatim as the payload")
    ap.add_argument("--expect", choices=["deny", "ask", "allow", "warn", "none"],
                    help="verdict the hook must produce")
    ap.add_argument("--rule", help="name that must appear in the hook's output")
    ap.add_argument("--session-id", default="hook-pipe-test-%d" % os.getpid())
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("-v", "--verbose", action="store_true", help="print raw stdout and stderr")
    a = ap.parse_args()

    hook = os.path.expanduser(a.hook)
    if not os.path.isfile(hook):
        print("FAIL  hook not found: %s" % hook)
        return 1
    payload = build_payload(a)
    try:
        r = run_hook(hook, payload, a.interpreter, a.timeout)
    except subprocess.TimeoutExpired:
        print("FAIL  verdict=error  hook did not finish within %.0fs" % a.timeout)
        return 1
    except OSError as e:
        print("FAIL  verdict=error  could not run hook: %s" % e)
        return 1

    verdict, detail = classify(r.returncode, r.stdout, r.stderr)
    blob = (r.stdout or "") + "\n" + (r.stderr or "")
    rule_ok = (a.rule is None) or (a.rule in blob)
    if a.expect:
        ok = verdict == a.expect and rule_ok
    else:
        ok = verdict in ("deny", "ask", "allow", "warn", "none")
    print("%s  verdict=%-7s rc=%s  %s%s" % (
        "PASS" if ok else "FAIL", verdict, r.returncode, detail,
        ("  rule=%s %s" % (a.rule, "seen" if rule_ok else "NOT seen")) if a.rule else ""))
    if a.verbose or not ok:
        if r.stdout.strip():
            print("  stdout: " + " ".join(r.stdout.split())[:300])
        if r.stderr.strip():
            print("  stderr: " + " ".join(r.stderr.split())[:300])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
