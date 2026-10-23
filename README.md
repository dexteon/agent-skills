# Claude Code skills that stop AI agents from faking success

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-d97757.svg)](#install)
[![Release](https://img.shields.io/github/v/release/dexteon/agent-skills)](https://github.com/dexteon/agent-skills/releases)

**agent-skills** is a Claude Code plugin marketplace of field-tested skills for AI coding agents. They also work with any agent that loads `SKILL.md` folders, such as Hermes. Every skill came out of a real failure in daily agent work and teaches the agent the habit that would have caught it.

Built and maintained by [CyberAutomations](https://cyberautomations.com).

## Why these exist

Agents are confident by default. These are the kinds of mistakes the skills catch:

- **A cached answer passed as a live one.** An LLM gateway smoke test "passed" in 0.027 s. The first call took 0.41 s and the second returned the same response id: it came from a response cache, so nothing was tested.
- **A 200 with nothing in it.** A reasoning model returned HTTP 200 with `content: null` because every one of its 16 output tokens went to reasoning.
- **A speedup that was not real.** A "3.3x faster" result showed zero change in production. The control run had shared its network link with a live job.
- **A plan that named the wrong file.** The plan said to edit `src/rules.py`. The loader imports `src/core/rules.py`. The change would have done nothing and every test would still pass.
- **A model that "fit" in VRAM.** The first deploy ran out of memory by 166 MiB. The estimate reused a safety margin from a different model; measured use per slot was 10,214 MiB against 8.3 to 8.7 GiB on paper.
- **A subagent that said "written".** The child's summary reported the deliverable saved. The file was not there: its final write had been rejected and the child never noticed. The sibling that was respawned from zero to redo it threw away thirty minutes of verified work that was sitting in the dead child's transcript.

## Plugins

### agent-verification-kit

Verification, measurement and review habits for Claude Code and other AI agents.

| Skill | What it does | Loads when you say |
|---|---|---|
| [evidence-ladder](plugins/agent-verification-kit/skills/evidence-ladder/SKILL.md) | Verify by effect, never by proxy. Named evidence levels, a catalogue of proxy traps, and probe scripts for HTTP endpoints, LLM gateways and Claude Code hooks. | "is it working", "verify that", "smoke test it", "it returned 200" |
| [measure-before-you-quote](plugins/agent-verification-kit/skills/measure-before-you-quote/SKILL.md) | Measure before stating a number: VRAM and KV-cache math, cost per unit of work instead of per hour, measurement windows, and a baseline before calling a difference real. | "how much VRAM", "will it fit", "is X faster", "what does this cost" |
| [artifact-review](plugins/agent-verification-kit/skills/artifact-review/SKILL.md) | Check a plan, report or handoff against the live system before anyone acts on it, then fix the wrong sentences in place. | "review this plan", "check the handoff" |
| [api-verification](plugins/agent-verification-kit/skills/api-verification/SKILL.md) | Get evidence for a library's installed API before changing calls into it, and require approval before remote writes. | a `TypeError` or `ImportError` from a library, "plan only" |

### windows-agent-survival

For agents running shell commands on Windows, where Git Bash and PowerShell make commands look successful while they quietly do the wrong thing.

| Skill | What it does | Loads when you say |
|---|---|---|
| [git-bash-on-windows](plugins/windows-agent-survival/skills/git-bash-on-windows/SKILL.md) | The top traps with symptom, cause and fix: MSYS path rewriting, `cd /d`, backslashes eaten in heredocs, CRLF rewrites, `powershell` 5.1 vs `pwsh` 7, killing by captured PID, background jobs that die, and retry loops. | "Git Bash", "path mangling", "command not found", "process won't die" |
| [everything-search](plugins/windows-agent-survival/skills/everything-search/SKILL.md) | Find files by name in under a second with Everything's `es.exe` instead of a recursive walk, plus the flags that silently return nothing. Includes a wrapper that runs a positive control first. | "where is X", "find all *.ext", "biggest files under" |

### multi-agent-orchestration

For agents that coordinate other agents. The headline skill is runtime-neutral and maps its tools to both Claude Code (`Agent`, `SendMessage`, `TaskStop`) and Hermes (`delegate_task`). The other four are **Hermes-specific**: they drive `hermes profile` and `hermes kanban` and were checked against Hermes 0.21.3; load them only on a Hermes setup.

| Skill | What it does | Loads when you say |
|---|---|---|
| [fanout-orchestration](plugins/multi-agent-orchestration/skills/fanout-orchestration/SKILL.md) | Coordinate parallel subagents: a wall-clock budget in every goal, one probe before the batch commits, single-writer discipline, steer instead of respawn, and a checklist that verifies every self-reported "done" before it is written down. References cover TRUNCATED and dead-child recovery, LLM-proxy workers, and one-shot review fan-out. | "fan out", "spawn N agents", "start all of them", "cut back to N", a child reports done or TRUNCATED |
| [hermes-bot-team](plugins/multi-agent-orchestration/skills/hermes-bot-team/SKILL.md) | Hermes. Build a team of isolated profiles (role, model, secrets tier, toolsets, MCPs each) and run them through `delegate_task` or a kanban board. What a new profile does not inherit, the delegation cap, secrets tiering, the kanban flags that differ from what you would guess. | "build a team of bots", "add N more bots", a new profile cannot use web search |
| [hermes-kanban-project-launch](plugins/multi-agent-orchestration/skills/hermes-kanban-project-launch/SKILL.md) | Hermes. Explore, classify, design, spec, decompose into a dependency-linked task graph, create an isolated board, dispatch, gate with safety and code review. Ships `kanban_graph.py` (parents first, ids captured, missing parents refused). | "unify this project", "refactor it with a kanban board" |
| [hermes-kanban-triage-and-chains](plugins/multi-agent-orchestration/skills/hermes-kanban-triage-and-chains/SKILL.md) | Hermes. Move a card the dispatcher parked in `triage` (no normal command does), and run boards in sequence with a blocked gate plus `chain_boards.py` as a no-agent cron poller. | status `triage`, "kick off the next board when this one finishes" |
| [hermes-kanban-field-notes](plugins/multi-agent-orchestration/skills/hermes-kanban-field-notes/SKILL.md) | Hermes. Query boards reliably from the CLI and straight from each board's SQLite file: `--json` forms, the DB path, tables and `task_events` kinds, why `show` says "no such task" for a real id. | wrong board's tasks, "no such task", "is anything happening on this board" |

### hermes-agent-bridge

Two-way messaging between Claude Code sessions and Hermes Agent sessions on one machine, through files under a relay root. The Claude skill installs like any other; the Hermes skill and the `claude-inbox` Hermes plugin are copied into Hermes by hand (see the [plugin README](plugins/hermes-agent-bridge/README.md) for install steps, configuration and the trust boundary).

| Part | What it does | Loads when you say |
|---|---|---|
| [hermes-relay-volunteer](plugins/hermes-agent-bridge/skills/hermes-relay-volunteer/SKILL.md) | Claude side. Read relay messages as data, volunteer for a Hermes ticket, write `reply.md` atomically, and message a running Hermes chat with `hermes_msg.py` (hop-capped, scrubbed, 8 KB). | "Hermes needs help. Ticket", "CLAIM", a pointer from `hermes:<ref>`, "listen for Hermes" |
| [claude-relay](plugins/hermes-agent-bridge/hermes/claude-relay/SKILL.md) | Hermes side. `relay.py ask` finds idle Claude sessions and returns a volunteer's reply; `relay.py direct` sends one message. The headless Haiku hop only sends pointers, never bodies. | stuck after retries, "escalate to Claude" |
| [claude-inbox](plugins/hermes-agent-bridge/hermes/claude-inbox/__init__.py) | Hermes plugin. Per-process inbox; read-then-claim delivery as a new turn when idle or with the next turn; oversize to `rejected/`; nonce-fenced peer data. | (always on once installed) |

## Install

### Claude Code plugin marketplace

```
/plugin marketplace add dexteon/agent-skills
/plugin install agent-verification-kit@dexteon-agent-skills
/plugin install windows-agent-survival@dexteon-agent-skills
/plugin install multi-agent-orchestration@dexteon-agent-skills
/plugin install hermes-agent-bridge@dexteon-agent-skills
```

### Any agent that reads SKILL.md folders

```bash
git clone https://github.com/dexteon/agent-skills
cp -r agent-skills/plugins/agent-verification-kit/skills/evidence-ladder ~/.claude/skills/
```

The scripts are plain Python 3 (one PowerShell) with no required dependencies. Each one supports `--help`. The two kanban scripts call the `hermes` CLI and are only useful on a Hermes setup.

## Contributing

Issues and pull requests are welcome. A good report includes the failure the skill should have caught, the command output that proved it, and the agent you were using.

## License

MIT. See [LICENSE](LICENSE). Release notes are in [CHANGELOG.md](CHANGELOG.md).

---

Want agent workflows like these built for your team? [CyberAutomations](https://cyberautomations.com) designs and runs AI automation for small businesses and creators.


<!-- ca-tracked-link -->
---
Built by [CyberAutomations](https://cyberautomations.com/?utm_source=github&utm_medium=readme&utm_campaign=agent-skills). Need something like this built for your business? Start there.
