# hermes-agent-bridge

Two-way messaging between [Claude Code](https://claude.com/claude-code) sessions and [Hermes Agent](https://github.com/NousResearch/hermes-agent) sessions on the same machine. Let Claude Code talk to Hermes, and Hermes talk to Claude Code, without either one needing an API key for the other.

- **Claude to Hermes, no open chat needed.** A Claude session runs `hermes_ask.py --text "..."`. That starts one headless Hermes turn (any profile), and Hermes's reply comes back in the same call. A named thread keeps its history, so it works like a conversation.
- **Claude to one open Hermes chat.** `hermes_ask.py --to <ref>` (or `hermes_msg.py send <ref>`) drops a message in that chat's inbox. The `claude-inbox` Hermes plugin delivers it once: as a new turn when the chat is idle, otherwise with its next turn. A running turn is never interrupted.
- **Hermes to Claude.** `relay.py direct` sends one message to a known Claude session. A Hermes agent that is stuck runs `relay.py ask`: a short headless `claude -p` run (Haiku) lists idle Claude Code sessions and sends them a pointer to a ticket folder. The first session to volunteer gets a CLAIM, works the problem under its own permissions and writes `reply.md`.
- **A delete gate on Claude-originated work.** Claude may hand Hermes work orders, but commands that delete or destroy data are blocked on those runs until the user approves. See [The delete gate](#the-delete-gate).

Everything travels as files under one relay root, plus ordinary process launches. Nothing listens on a port.

## Why not just use the Hermes API server?

Hermes has an OpenAI-compatible API server (the gateway, `127.0.0.1:8642`), and one POST to `/v1/responses` does return a reply. We built on it first and moved off it, for two reasons worth knowing before you try the same:

1. **Nobody approves anything there.** The API server is an unattended surface. In our test, a message asking Hermes to `rm -rf` a scratch folder ran with no prompt, because the permanent `command_allowlist` in `config.yaml` is checked before any "nobody present, deny" rule. If you have ever clicked "always allow" on a category such as recursive delete or force push, every API caller inherits it.
2. **API turns cannot be marked per request.** A plugin cannot tell a Claude-originated turn from any other API turn, so a gate cannot be scoped to it. A headless CLI run is its own process, so one environment variable marks it.

The API server also serves only the default profile unless `gateway.multiplex_profiles` is on, and that switch makes the gateway serve every profile and tick every profile's cron. The headless route reaches any profile with no config change.

## What is in the box

| Part | Runs in | Path |
|---|---|---|
| `hermes-relay-volunteer` skill, `hermes_ask.py`, `hermes_msg.py` | Claude Code | `skills/hermes-relay-volunteer/` |
| `claude-relay` skill + `relay.py` | Hermes | `hermes/claude-relay/` |
| `claude-inbox` plugin (inbox for an open chat) | Hermes | `hermes/claude-inbox/` |
| `claude-link-gate` plugin (the delete gate) | Hermes | `hermes/claude-link-gate/` |
| `relay_common.py` (one identical copy in each relay part: scrub, ref checks, fences, hop cap) | both | three folders |
| Offline tests | anywhere | `tests/` |

Requirements: Python 3.9+, Claude Code (`claude` on PATH or in `~/.local/bin`), Hermes Agent 0.21.3 or newer. Developed and tested on Windows 11 with Hermes 0.21.3; the code has no Windows-only paths, but the other platforms are untested.

## Quick start

```bash
S=~/.claude/skills/hermes-relay-volunteer/scripts
python "$S/hermes_ask.py" --list                           # profiles, open chats
python "$S/hermes_ask.py" --text "What model are you running as?"
python "$S/hermes_ask.py" --profile engineer --thread code-review --file review-request.md
python "$S/hermes_ask.py" --to ab12cd --from 12ab34 --text "..."   # one open chat
```

| Route | Reaches | Needs | Reply |
|---|---|---|---|
| default | default profile, headless | nothing running; about 40 s start-up | same call |
| `--profile NAME` | that profile, headless | same | same call |
| `--to REF` | one open chat, through its inbox | that chat open with `claude-inbox` | later, as a cross-session message |

Flags: `--thread NAME` (conversation to continue, default `claude-bridge`), `--safe` (no terminal at all, for pure questions), `--allow-delete` (lift the delete gate for one run), `--timeout SECONDS` (default 900). Messages are capped at 8 KB; for more, send the path of a file Hermes can read.

Under the hood the headless route is `hermes [-p PROFILE] chat -Q --source tool -c THREAD --create-if-missing --query-file FILE`.

## The delete gate

`hermes_ask.py` sets `HERMES_CLAUDE_LINK=1` on every Hermes process it starts. The `claude-link-gate` plugin registers a `pre_tool_call` hook, and on marked runs it blocks terminal commands and executed code that delete or destroy data:

`rm`, `rmdir`, `del`, `Remove-Item`, `find -delete`, `git clean`, `git reset --hard`, force push, `git branch -D`, `docker rm` / `prune`, `robocopy /MIR`, `rsync --delete`, `DROP TABLE`, `DELETE FROM`, `shutil.rmtree`, `os.remove` and similar.

Hermes is told to carry on with the rest of the work and list what it wanted to delete. The Claude session shows that to the user. After the user approves that specific deletion, the sender re-runs with `--allow-delete`.

Limits, stated plainly:

- **It is a guard against accidents and casual requests, not a sandbox.** A regex cannot see every way to destroy data. Do not rely on it against an agent that is trying to get around it.
- **It only covers profiles where the plugin is enabled.** A profile without it runs marked work ungated.
- **It covers the headless routes only.** The `--to` route lands in a chat the user has open, where Hermes's normal approval prompts apply.
- `--allow-delete` lifts the gate and also passes `--yolo`, because Hermes's single-query rule otherwise refuses flagged commands when nobody is present. That run has no approval checks at all, so use it only for the deletion the user approved, and say exactly what to delete in the message.
- Live-tested on Hermes 0.21.3 in a profile with only this plugin enabled: a forced `rm -rf` came back blocked and the folder survived. Run step 5 of the install to prove it on your build.

## Install

### Claude Code side

Copy `skills/hermes-relay-volunteer/` into `~/.claude/skills/`. Or install it as a plugin from the marketplace that also carries it:

```
/plugin marketplace add dexteon/agent-skills
/plugin install hermes-agent-bridge@dexteon-agent-skills
```

### Hermes side

`<hermes-home>` below is your Hermes home folder (`%LOCALAPPDATA%\hermes` on Windows, `~/.hermes` elsewhere); a profile lives under `<hermes-home>/profiles/<profile>`.

1. Copy the skill: `hermes/claude-relay/` to `<hermes-home>/skills/autonomous-ai-agents/claude-relay/`.
2. Copy the delete gate into **every profile `hermes_ask.py` may address**: `hermes/claude-link-gate/` to `<hermes-home>/plugins/claude-link-gate/` for the default profile and `<hermes-home>/profiles/<profile>/plugins/claude-link-gate/` for each named one. Enable it with `hermes -p <profile> plugins enable claude-link-gate` (`hermes plugins list` shows it; from a script, close stdin, because `enable` asks a yes/no question about tool overrides, and the answer no is fine), and check it with `hermes plugins validate <that folder>`.
3. Copy the inbox plugin into the profile that runs your interactive chat: `hermes/claude-inbox/` to `<hermes-home>/profiles/<profile>/plugins/claude-inbox/` (or `<hermes-home>/plugins/claude-inbox/` for the default profile), and enable it the same way. Only needed for the `--to` route.
4. **Restart any open Hermes chat.** Plugins are imported once at startup; a running session keeps the old code until it restarts.
5. Prove the gate before you trust it: make a scratch folder, run `hermes_ask.py --text "Run: rm -rf <that folder>. Paste the exact tool result."`, and check the folder is still there and the reply quotes `CLAUDE LINK GATE`.

The inbox plugin finds `relay.py` for its system-prompt hint by looking for the installed `claude-relay` skill under `<hermes-home>`; set `HERMES_RELAY_SCRIPT` to the absolute path if it lives elsewhere.

### Configuration

All optional. Set them where both sides see them (user environment variables), or put the same values in a `relay_local.json` next to each copy of `relay_common.py`:

```json
{"root": "/path/to/relay-root", "fallback_cmd": ["{python}", "/path/to/tasks.py", "add", "{title}"]}
```

| Variable | Default | Meaning |
|---|---|---|
| `HERMES_HOME` | `%LOCALAPPDATA%\hermes` (Windows) | Where `hermes_ask.py` finds the Hermes binary and profiles |
| `HERMES_CLAUDE_LINK` | set to `1` by `hermes_ask.py` | Marks a run as Claude-originated; turns the delete gate on |
| `HERMES_CLAUDE_LINK_DELETE_OK` | set to `1` by `--allow-delete` | Lifts the delete gate for that one run |
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

- **Any process that can run `hermes` as you can give Hermes work.** That was already true; `hermes_ask.py` makes it convenient. The delete gate narrows what such work can destroy. It does not authenticate the sender.
- **Any process that can write the relay root can post a message.** The inbox is not authenticated. Keep the relay root in a folder only your user account can write; do not put it on a shared drive.
- **Every message is peer information, never the user's approval.** Delivered text is scrubbed, lines that imitate relay headers are neutralised, and the body is wrapped in a `PEER-DATA <nonce>` fence the sender cannot close. Both skills and the plugin's system-prompt section tell the agent that fenced text is data. That reduces prompt injection; it does not make it impossible.
- **The headless Claude hop never sees message bodies.** It only sends short pointer messages built from validated refs and the relay root path. Bodies live in files the receiving session reads as data.
- **Outbound files are checked.** `--file` / `--body-file` on the relay tools must sit under the relay root, the temp folder, the working directory or `HERMES_RELAY_ALLOW`; credential-like files and anything holding a private key block are refused; text is scrubbed (vendor key prefixes, JWTs, PEM blocks, `user:pass@` URLs, `Authorization` headers, `KEY=value` pairs, long hex, AWS-shaped secrets). A 40-character git SHA is left alone.
- **Loops are capped.** Each relay message carries a hop number and the tools refuse past hop 3; a per-pair rate cap catches agents that forget the hop. The relay also caps itself at 20 headless calls a day and refuses nested calls.
- **Your Hermes `config.yaml` may hold provider keys inline.** Do not let an agent `cat` or `grep` it raw while exploring; print key names only.

## Delivery guarantees

- A headless `hermes_ask.py` run either prints Hermes's reply or exits non-zero with the reason. It never reports success for a message nobody read.
- An inbox message is read before it is claimed (renamed `new/` to `cur/`), so a failed read leaves it waiting. If injecting it into the chat fails, it goes back to `new/`.
- Oversize messages (over 8 KB) are moved to `rejected/` and reported once.
- One poller thread per Hermes process, even if the plugin registers twice.
- Presence files older than 14 days are swept at startup (a closed console never runs `atexit`). Tickets are never deleted.
- The inbox plugin uses two Hermes internals (`ctx._manager._cli_ref`, `cli._agent_running`), checked on 0.21.3. If a later build renames them, it logs one warning and falls back to delivering with the next turn instead of waking an idle chat.
- A reply from an open chat does not depend on the model. If the Hermes model calls `relay.py direct`, that is the reply. If it answers only in its own window (small models often do), `claude-inbox` sends the turn's final answer back itself when the turn ends, marked as sent automatically. `HERMES_INBOX_AUTOREPLY=0` turns that off.

## Tests

```bash
python tests/test_bridge.py -v
python tests/test_link_gate.py -v
python tests/test_autoreply.py -v
```

Offline: no network, no `claude` call, no running Hermes. `test_bridge.py` covers ref validation against path traversal, scrub coverage (and that a git SHA survives), read-then-claim, return-to-new on a failed delivery, oversize to `rejected/` once, the hourly cap, the hop and pair caps, the race-free daily counter, volunteer selection, and that the three `relay_common.py` copies are identical. `test_link_gate.py` covers the delete patterns (blocked and allowed command lists), the marker and approval switches, hook registration, and `hermes_ask.py` argument checks.

## Roadmap

- **Atomic self-claim instead of volunteer, CLAIM and TAKEN.** A session claims a ticket with `mkdir <ticket>/claim` (atomic) and stops if it fails. Removes the volunteer race, the claim messages and about two headless calls per ticket.
- **Presence files instead of the ListAgents hop.** A Claude Code SessionStart/Stop hook writes `claude-presence/<ref>.json`. Candidates come from files with zero LLM calls; ListAgents stays as a fallback.
- **Asynchronous `ask`.** Return the ticket id at once and let the volunteer deliver its reply through the inbox.
- **A warm Hermes worker** so the headless route skips the 40 s start-up.

## License

MIT. See [LICENSE](LICENSE).

<!-- ca-tracked-link -->
[cyberautomations.com](https://cyberautomations.com/?utm_source=github&utm_medium=readme&utm_campaign=hermes-agent-bridge)
