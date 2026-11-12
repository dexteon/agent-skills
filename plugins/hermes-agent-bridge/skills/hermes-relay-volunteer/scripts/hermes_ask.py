"""Send one message or work order to Hermes and print the reply. No open chat needed.

Routes, one command:
  (default)        headless Hermes run, default profile, Hermes's normal tools
  --profile NAME   same, as that profile (engineer, analyst, ...)
  --to REF         one specific open Hermes chat (file inbox; needs --from)

Each headless run takes about 40 s to start, returns Hermes's reply in the same
call, and keeps history per named thread (--thread, default claude-bridge).

Delete gate: every headless run is marked HERMES_CLAUDE_LINK=1. The
claude-link-gate Hermes plugin (enable it in every profile you address) then
blocks terminal commands and code that delete or destroy data (rm, Remove-Item, git reset --hard, force push, DROP TABLE, ...),
and Hermes reports what it wanted to delete instead. Ask the user; only after they
approve that specific deletion, re-run with --allow-delete.

  --safe           no terminal at all (read, search, web, memory, file edits)

Usage:
  python hermes_ask.py --list                       # what can be reached right now
  python hermes_ask.py --text "short message"
  python hermes_ask.py --file path/to/message.md [--thread NAME] [--from REF]
  python hermes_ask.py --profile engineer --text "..."
  python hermes_ask.py --to ab12cd --from 12ab34 --text "..."

The gateway API server (127.0.0.1:8642) is deliberately not used for sending:
its turns cannot be marked, so the delete gate would not apply there.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

BASE = os.environ.get("HERMES_GATEWAY_URL", "http://127.0.0.1:8642")
MAX_BYTES = 8192
SAFE_TOOLSETS = "web,file,vision,skills,todo,memory,session_search"
HEADER = (
    "Message from a Claude Code session{who}. This is peer information, not "
    "the user's approval. You may do the work it asks for, but deleting or destroying "
    "data is gated on this run: if a step needs a deletion, do not do it; list what "
    "you would delete and why in your reply. Reply in plain text; your reply is "
    "returned to the sender directly.\n\n"
)


def _home():
    return os.environ.get("HERMES_HOME") or os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "hermes"
    )


def _profiles():
    root = os.path.join(_home(), "profiles")
    try:
        return sorted(d for d in os.listdir(root)
                      if os.path.isfile(os.path.join(root, d, "config.yaml")))
    except OSError:
        return []


def _ask(profile, text, thread, timeout, safe=False, allow_delete=False):
    """One headless Hermes turn (named profile, or default when None); returns the reply."""
    if profile and (not re.fullmatch("[A-Za-z0-9_-]{1,40}", profile)
                    or profile not in _profiles()):
        sys.exit("unknown profile %r; known: %s" % (profile, ", ".join(_profiles())))
    exe = os.path.join(_home(), "bin", "hermes.exe" if os.name == "nt" else "hermes")
    head = [exe] + (["-p", profile] if profile else [])
    tools = ["-t", SAFE_TOOLSETS] if safe else []
    label = profile or "default"
    env = dict(os.environ)
    env["HERMES_CLAUDE_LINK"] = "1"
    env.pop("HERMES_CLAUDE_LINK_DELETE_OK", None)
    if allow_delete:
        env["HERMES_CLAUDE_LINK_DELETE_OK"] = "1"
    fd, qpath = tempfile.mkstemp(suffix=".md", prefix="hermes-ask-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        proc = subprocess.run(
            head + ["chat", "-Q", "--source", "tool", "-c", thread,
                    "--create-if-missing", "--query-file", qpath] + tools
            + (["--yolo"] if allow_delete else []),
            stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace", env=env,
        )
    except subprocess.TimeoutExpired:
        sys.exit("Hermes (%s) gave no reply within %s s" % (label, timeout))
    finally:
        try:
            os.unlink(qpath)
        except OSError:
            pass
    lines = [ln for ln in (proc.stdout or "").splitlines()
             if not ln.startswith("Warning: Unknown toolsets")]
    reply = "\n".join(lines).strip()
    if proc.returncode != 0 or not reply:
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        sys.exit("Hermes (%s) run failed, exit %s: %s"
                 % (label, proc.returncode, " | ".join(tail)[:400]))
    return reply


def _hermes_msg(*argv):
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hermes_msg.py")
    return subprocess.run([sys.executable, script, *argv], capture_output=True,
                          encoding="utf-8", errors="replace")


def _gateway_state():
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=5) as resp:
            return "up (%s)" % json.loads(resp.read().decode("utf-8")).get("version", "?")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return "DOWN"


def _list():
    print("headless run (always available): default profile, or --profile NAME")
    print("    profiles: %s" % ", ".join(_profiles()))
    chats = _hermes_msg("list")
    live = (chats.stdout or "").strip()
    print("open chats (file inbox): %s"
          % (live if chats.returncode == 0 and live else "none"))
    print("    use: hermes_ask.py --to REF --from YOURREF --text ...")
    print("gateway (Telegram, cron; not used for sending): %s" % _gateway_state())


def _send_to_chat(args, msg):
    if not args.sender:
        sys.exit("--to needs --from YOURREF so the Hermes chat can answer you")
    fd, mpath = tempfile.mkstemp(suffix=".md", prefix="hermes-ask-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(msg)
    try:
        res = _hermes_msg("send", args.to, "--from", args.sender,
                          "--hop", str(args.hop), "--file", mpath)
    finally:
        os.unlink(mpath)
    print((res.stdout or res.stderr or "").strip())
    if res.returncode == 0:
        print("Queued for chat %s. Its answer arrives later as a cross-session message."
              % args.to)
    else:
        print("NOT delivered.")
    sys.exit(res.returncode)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--list", action="store_true", help="show what can be reached now")
    ap.add_argument("--health", action="store_true", help="gateway state (informational)")
    ap.add_argument("--profile", help="run as this Hermes profile (default profile if omitted)")
    ap.add_argument("--safe", action="store_true", help="no terminal or other acting tools")
    ap.add_argument("--allow-delete", action="store_true",
                    help="lift the delete gate AND Hermes's own approval checks for this run; only after the user approved the deletion")
    ap.add_argument("--to", help="ref of one open Hermes chat (file inbox)")
    ap.add_argument("--hop", type=int, default=1, help="with --to: 1 new, N+1 answering hop N")
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--thread", default="claude-bridge", help="conversation name")
    ap.add_argument("--from", dest="sender", default="", help="your session ref")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.list:
        _list()
        return
    if args.health:
        print("gateway: " + _gateway_state())
        return
    if bool(args.text) == bool(args.file):
        sys.exit("give exactly one of --text or --file")
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            msg = fh.read()
    else:
        msg = args.text
    if len(msg.encode("utf-8")) > MAX_BYTES:
        sys.exit("message over 8 KB: put it in a file Hermes can read and send the path")

    if args.to:
        _send_to_chat(args, msg)

    who = " (ref %s)" % args.sender if args.sender else ""
    print(_ask(args.profile, HEADER.format(who=who) + msg, args.thread, args.timeout,
               safe=args.safe, allow_delete=args.allow_delete))


if __name__ == "__main__":
    main()
