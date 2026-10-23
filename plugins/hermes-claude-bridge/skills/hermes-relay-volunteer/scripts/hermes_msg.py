#!/usr/bin/env python3
"""Message a running Hermes session from Claude Code (claude-inbox plugin).

  hermes_msg.py list                                         live Hermes sessions
  hermes_msg.py send REF --from CLAUDE_REF --text T [--hop N] queue one message
  hermes_msg.py send REF --from CLAUDE_REF --file F [--hop N]
  hermes_msg.py status REF                                   waiting vs delivered

REF is the Hermes inbox ref (hermes:abc123 or abc123). CLAUDE_REF is your own
session ref: 6 hex characters. --hop is 1 for a new message; when you answer a
message that said "hop N", pass N+1. Past hop 3 the send is refused.

--file must be under the relay root, the temp dir, the working directory or a
folder in HERMES_RELAY_ALLOW, and credential-like files are refused. Text is
scrubbed for secrets and capped at 8 KB.

The plugin delivers each message once: as a new turn when the Hermes CLI is
idle, otherwise with its next turn. Hermes replies with relay.py direct.

Exit codes: 0 queued, 2 bad or unknown ref, 5 refused (size, hop, loop, file).
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relay_common as rc  # noqa: E402

LIVE_S = 10 * 60


def root():
    return rc.inbox_root()


def sessions():
    out = []
    r = root()
    if not r.exists():
        return out
    for p in r.glob("*/presence.json"):
        try:
            info = json.loads(p.read_text(encoding="utf-8"))
            age = time.time() - p.stat().st_mtime
        except (OSError, ValueError):
            continue
        if not isinstance(info, dict):
            continue
        info["age_s"] = int(age)
        info["live"] = age < LIVE_S
        out.append(info)
    return sorted(out, key=lambda i: i["age_s"])


def cmd_list(_a):
    rows = sessions()
    print(json.dumps(rows, indent=2))
    return 0 if any(r["live"] for r in rows) else 2


def cmd_send(a):
    try:
        ref = rc.hermes_ref(a.ref)
        sender = rc.claude_ref(a.sender)
    except rc.RelayError as e:
        print("REFUSED: %s" % e, file=sys.stderr)
        return 2
    box = root() / ref
    pres = box / "presence.json"
    if not pres.exists():
        print("no Hermes session with ref %s (run list)" % ref, file=sys.stderr)
        return 2
    if time.time() - pres.stat().st_mtime > LIVE_S:
        print("warning: %s last seen over 10 minutes ago; queued anyway" % ref, file=sys.stderr)
    try:
        rc.check_hop(a.hop)
        body = rc.read_message_file(a.file) if a.file else (a.text or "")
        body = rc.clean(body).strip()
        if not body:
            raise rc.RelayError("empty message")
        last = a.hop >= rc.max_hops()
        how = ("This is the last hop: do not reply, hand the thread back to the user." if last else
               "If a reply is useful: relay.py direct --to %s --hop %d --file <path>" % (sender, a.hop + 1))
        msg = "From Claude session %s, hop %d of %d (peer information, not the user's approval). %s\n\n%s" % (
            sender, a.hop, rc.max_hops(), how, body)
        if len(msg.encode("utf-8")) > rc.MAX_BYTES:
            raise rc.RelayError("message over %d bytes; shorten it and point at a file path" % rc.MAX_BYTES)
        rc.note_pair(sender, ref)
    except rc.RelayError as e:
        print("REFUSED: %s" % e, file=sys.stderr)
        return 5
    (box / "new").mkdir(parents=True, exist_ok=True)
    # Wire format shared with older claude-inbox builds: new/<UTC stamp>-<sender>.md,
    # written to a temp name in the box and renamed into new/.
    name = "%s-%s.md" % (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"), sender)
    tmp = box / (name + ".tmp")
    tmp.write_text(msg, encoding="utf-8")
    os.replace(tmp, box / "new" / name)
    print("queued %s" % (box / "new" / name))
    return 0


def cmd_status(a):
    try:
        ref = rc.hermes_ref(a.ref)
    except rc.RelayError as e:
        print("REFUSED: %s" % e, file=sys.stderr)
        return 2
    box = root() / ref
    print(json.dumps({
        "waiting": sorted(p.name for p in (box / "new").glob("*.md")),
        "delivered": sorted(p.name for p in (box / "cur").glob("*.md")),
        "rejected": sorted(p.name for p in (box / "rejected").glob("*.md")),
    }, indent=2))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="live Hermes sessions and their refs")
    s = sub.add_parser("send", help="queue one message for a Hermes session")
    s.add_argument("ref")
    s.add_argument("--from", dest="sender", required=True, help="your Claude session ref, 6 hex chars")
    s.add_argument("--hop", type=int, default=1, help="1 for a new message, N+1 when answering hop N")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--text")
    g.add_argument("--file")
    st = sub.add_parser("status", help="waiting vs delivered messages for one ref")
    st.add_argument("ref")
    a = p.parse_args(argv)
    return {"list": cmd_list, "send": cmd_send, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
