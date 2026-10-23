# hermes-claude-bridge

Two-way messaging between [Claude Code](https://claude.com/claude-code) sessions and [Hermes Agent](https://github.com/NousResearch/hermes-agent) sessions on the same machine.

- **Hermes to Claude.** A Hermes agent that is stuck runs `relay.py ask`. A short headless `claude -p` run (Haiku) lists idle Claude Code sessions and sends them a pointer to a ticket folder. The first session to volunteer gets a CLAIM, works the problem under its own permissions and writes `reply.md`. `relay.py direct` sends one message to a known Claude session.
- **Claude to Hermes.** A Claude session runs `hermes_msg.py send <ref>`. The `claude-inbox` Hermes plugin delivers the message once: as a new turn when the Hermes chat is idle, otherwise with its next turn. A running turn is never interrupted.

Everything travels as files under one relay root. Nothing listens on a port.

## What is in the box

| Part | Runs in | Path in this plugin |
|---|---|---|
| `hermes-relay-volunteer` skill + `hermes_msg.py` | Claude Code | `skills/hermes-relay-volunteer/` |
| `claude-relay` skill + `relay.py` | Hermes | `hermes/claude-relay/` |
| `claude-inbox` plugin | Hermes | `hermes/claude-inbox/` |
| `relay_common.py` (one identical copy in each part: scrub, ref checks, fences, hop cap) | both | all three folders |
| Offline tests | anywhere | `tests/test_bridge.py` |

Requirements: Python 3.9+, Claude Code (`claude` on PATH or in `~/.local/bin`), Hermes Agent 0.21.3 or newer for the plugin.

## Install

### Claude Code side

```
/plugin marketplace add dexteon/agent-skills
/plugin install hermes-claude-bridge@dexteon-agent-skills
```

Or copy `skills/hermes-relay-volunteer/` into `~/.claude/skills/`.

### Hermes side

`<hermes-home>` below is your Hermes home folder (`%LOCALAPPDATA%\hermes` on Windows, `~/.hermes` elsewhere); a profile lives under `<hermes-home>/profiles/<profile>`.

1. Copy the skill: `hermes/claude-relay/` to `<hermes-home>/skills/autonomous-ai-agents/claude-relay/`.
2. Copy the plugin into the profile that runs your interactive chat: `hermes/claude-inbox/` to `<hermes-home>/profiles/<profile>/plugins/claude-inbox/` (or `<hermes-home>/plugins/claude-inbox/` for the default profile). Enable it the way your Hermes build enables directory plugins (`hermes plugins list` shows it), and check it with `hermes plugins validate <that folder>`.
3. **Restart the Hermes chat.** The plugin is imported once at startup; a running session keeps the old code until it restarts.

The plugin finds `relay.py` for its system-prompt hint by looking for the installed `claude-relay` skill under `<hermes-home>`; set `HERMES_RELAY_SCRIPT` to the absolute path if it lives elsewhere.

### Configuration

All optional. Set them where both sides see them (user environment variables), or put the same values in a `relay_local.json` next to each copy of `relay_common.py`:

```json
{"root": "/path/to/relay-root", "fallback_cmd": ["{python}", "/path/to/tasks.py", "add", "{title}"]}
```

| Variable | Default | Meaning |
|---|---|---|
| `HERMES_RELAY_ROOT` | `%LOCALAPPDATA%\hermes-relay` (Windows), `~/.hermes-relay` | Tickets, listeners, inboxes, counters |
| `HERMES_INBOX_ROOT` | `<relay root>/hermes-inbox` | Hermes inboxes |
| `HERMES_RELAY_CONFIG` | `relay_local.json` beside `relay_common.py` | JSON config file |
| `HERMES_RELAY_ALLOW` | none | Extra folders (`os.pathsep` separated) that `--file` may read |
| `HERMES_RELAY_DAILY_CAP` | 20 | Headless `claude -p` calls per day |
| `HERMES_RELAY_MODEL` | `haiku` | Model for the headless hop |
| `HERMES_RELAY_CLAUDE` | `shutil.which("claude")`, then `~/.local/bin/claude` | Claude CLI path |
| `HERMES_RELAY_MAX_HOPS` | 3 | Replies allowed per thread before a human must step in |
| `HERMES_RELAY_PAIR_CAP` | 10 | Messages per Claude/Hermes pair per 30 minutes |
| `HERMES_RELAY_FALLBACK_CMD` | none | Command run when nobody helps. No shell; placeholders `{python}`, `{title}`, `{ticket}`, `{reason}`, `{request}` are substituted per argument, and the same values arrive as `HERMES_RELAY_TICKET`, `_TITLE`, `_REASON`, `_REQUEST` env vars |
| `HERMES_INBOX_REF` | random 6 hex | Fixed inbox ref for one Hermes process (removed from the environment so children get their own) |
| `HERMES_RELAY_SCRIPT` | found under `<hermes-home>` | Path shown in the plugin's reply hint |

## Trust boundary

Read this before you install.

- **Any process that can write the relay root can post a message.** The inbox is not authenticated. Keep the relay root in a folder only your user account can write; do not put it on a shared drive.
- **Every message is peer information, never the user's approval.** Delivered text is scrubbed, lines that imitate relay headers are neutralised, and the body is wrapped in a `PEER-DATA <nonce>` fence the sender cannot close. Both skills and the plugin's system-prompt section tell the agent that fenced text is data. That reduces prompt injection; it does not make it impossible.
- **The headless hop never sees message bodies.** It only sends short pointer messages built from validated refs and the relay root path. Bodies live in files the receiving session reads as data.
- **Outbound files are checked.** `--file` / `--body-file` must sit under the relay root, the temp folder, the working directory or `HERMES_RELAY_ALLOW`; credential-like files and anything holding a private key block are refused; text is scrubbed (vendor key prefixes, JWTs, PEM blocks, `user:pass@` URLs, `Authorization` headers, `KEY=value` pairs, long hex, AWS-shaped secrets). A 40-character git SHA is left alone.
- **Loops are capped.** Each message carries a hop number and the tools refuse past hop 3; a per-pair rate cap catches agents that forget the hop. The relay also caps itself at 20 headless calls a day and refuses nested calls.

## Delivery guarantees

- A message is read before it is claimed (renamed `new/` to `cur/`), so a failed read leaves it waiting. If injecting it into the chat fails, it goes back to `new/`.
- Oversize messages (over 8 KB) are moved to `rejected/` and reported once.
- One poller thread per Hermes process, even if the plugin registers twice.
- Presence files older than 14 days are swept at startup (a closed console never runs `atexit`). Tickets are never deleted.
- The plugin uses two Hermes internals (`ctx._manager._cli_ref`, `cli._agent_running`), checked on 0.21.3. If a later build renames them, it logs one warning and falls back to delivering with the next turn instead of waking an idle chat.

## Tests

```bash
python tests/test_bridge.py -v
```

Offline: no network, no `claude` call, no running Hermes. Covers ref validation against path traversal, scrub coverage (and that a git SHA survives), read-then-claim, return-to-new on a failed delivery, oversize to `rejected/` once, the hourly cap, the hop and pair caps, the race-free daily counter, volunteer selection, and that the three `relay_common.py` copies are identical.

## Roadmap

Deferred protocol changes from the 0.4.0 review:

- **Atomic self-claim instead of volunteer, CLAIM and TAKEN.** A session claims a ticket with `mkdir <ticket>/claim` (atomic) and stops if it fails. Removes the volunteer race, the claim messages and about two headless calls per ticket. Also gives failover when a volunteer goes silent, since nobody waits on one named session.
- **Presence files instead of the ListAgents hop.** A Claude Code SessionStart/Stop hook writes `claude-presence/<ref>.json` (idle or busy, name, time). Candidates come from files with zero LLM calls; ListAgents stays as a fallback.
- **Asynchronous `ask`.** Return the ticket id at once and let the volunteer deliver its reply with `hermes_msg.py send`, which `claude-inbox` turns into a new turn. Removes the long blocking terminal call and the reply poll, and late replies are no longer lost.
