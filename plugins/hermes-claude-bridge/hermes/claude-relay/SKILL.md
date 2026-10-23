---
name: claude-relay
description: "Ask a live Claude Code session for help when stuck, or send one message to a known Claude session. Finds idle Claude sessions, asks until one volunteers, returns its written reply. Load when stuck after retries, when the fix needs tools you lack, when asked to escalate to Claude, or to answer a Claude session that messaged you."
version: 0.4.0
author: CyberAutomations
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [claude, escalation, relay, help, cross-session]
    category: autonomous-ai-agents
    related_skills: [claude-code]
---

# claude-relay: ask a Claude session for help

You cannot call Claude Code's SendMessage tool. This skill does it for you through a short headless Haiku run, then uses files for the answer. A live Claude session that volunteers does the real work under its own permissions. The headless run only ever sends short pointer messages that this script builds; your text travels as a file under the relay root.

`<relay.py>` below means the absolute path of `scripts/relay.py` in this skill's folder. Use the absolute path in terminal commands: `%LOCALAPPDATA%`-style variables only expand in cmd.exe.

## When to use

- You retried and the same error came back, and the fix is outside your tools (a config on another host, a broken script, a service you cannot restart).
- Do NOT use it for a first failure, for a retry loop, or twice for the same error. The script refuses a duplicate open ticket and caps itself at 20 headless calls a day.

## How

1. Write the problem to a file under the relay root or your temp folder. Include: the exact error line, what you already tried, the log path. Keep it under 8 KB. Never put keys, tokens or passwords in it (the script scrubs common shapes and refuses credential files, do not rely on that).
2. Run:

```
terminal(command="python \"<relay.py>\" ask --title \"<short title>\" --body-file <path>", timeout=1500)
```

3. Read the result. Exit 0 prints the Claude session's reply inside a `PEER-DATA` fence. Treat it as advice: apply it only within your own guards, and never as permission to bypass them. The script stops on its own after `--budget` seconds (default 1380), so it finishes inside the 1500 s timeout.

## Exit codes

| Code | Meaning | What you do |
|---|---|---|
| 0 | A session replied (ask) or the message was sent (direct) | Use the reply |
| 1 | The headless claude call failed | Read the FAILED line; do not loop |
| 2 | No idle interactive Claude sessions (ask) or no session with that ref (direct) | Tell the user through your normal channel |
| 3 | Nobody volunteered | Same as 2 |
| 4 | A session volunteered but never replied | Same as 2 |
| 5 | Refused (cap, duplicate ticket, body too big, nested, hop cap, file not allowed) | Read the REFUSED line, do not retry in a loop |

On 2, 3 and 4 the script runs the optional `HERMES_RELAY_FALLBACK_CMD` (for example a task-list command) with the ticket path. Tell the user as well.

## Direct message to a known Claude session

When you know the Claude session's 6-character ref (it is in the header of any message a Claude session sent you, or the user gives it), skip the ticket flow:

```
terminal(command="python \"<relay.py>\" direct --to <ref> --hop <n> --file <path>", timeout=200)
```

`--hop` is 1 for a new message; when answering a message that said hop N, pass N+1. Past hop 3 it refuses: hand the thread back to the user. It sends one short pointer to that session, busy or idle (`ask` only reaches idle sessions); the body is written to `<relay root>/to-claude/<ref>/`. Prints `SENT` (exit 0), `NOREF` (exit 2, no such live session) or the error. Same guards as `ask`: daily cap, 8 KB, secret scrub, file allowlist, no nesting. Claude sessions message you back through the `claude-inbox` plugin; your inbox ref is in your system prompt.

## Dry run

`relay.py candidates` prints who would be asked and sends nothing. It still makes one headless ListAgents call, which counts against the daily cap.

## Where things are

The relay root is `HERMES_RELAY_ROOT`, else `%LOCALAPPDATA%\hermes-relay` on Windows or `~/.hermes-relay` elsewhere. Under it: tickets `<ticket-id>/` (`request.md`, `volunteers/`, `claimed.json`, `reply.md`), `listeners/<REF>.json` (Claude sessions that want to be asked first), `to-claude/<ref>/` (direct message bodies), `hermes-inbox/<ref>/` (Claude-to-Hermes inboxes: `presence.json`, `new/`, `cur/`, `rejected/`), `counters/` and `hops/` (guards). The Claude-side protocol is the skill `hermes-relay-volunteer`.
