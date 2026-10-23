# Changelog

## v0.4.0 (unreleased)

- New **hermes-claude-bridge** plugin: two-way messaging between Claude Code and Hermes Agent sessions through files under a relay root.
  - `hermes-relay-volunteer` (Claude Code skill) with `hermes_msg.py`: read relay pointers as data, volunteer for a Hermes ticket, write `reply.md` via a temp file and rename, message a running Hermes chat.
  - `claude-relay` (Hermes skill) with `relay.py`: `ask` finds idle Claude sessions and returns a volunteer's reply inside a nonce fence; `direct` sends one message.
  - `claude-inbox` (Hermes plugin, needs Hermes 0.21.3+): per-process inbox, delivered once as a new turn when the chat is idle or with the next turn.
  - Hardened from a ranked review: refs validated against path traversal and argv injection; `--file` limited to the relay root, temp and working directory, credential files refused; the headless Haiku hop sends only constant pointer messages, with the prompt on stdin, UTF-8, JSON output and an exact `SENT` check; read-then-claim delivery that returns messages to `new/` on failure; oversize messages moved to `rejected/` once; race-free daily counter; volunteers chosen first-come among sessions actually asked; one shared scrub module (JWT, PEM, `github_pat_`, `sk-ant-`, `user:pass@` URLs, `Authorization` headers, quoted values; git SHAs left alone); hop cap of 3 plus a per-pair rate cap; headless runs in an empty temp folder with `--strict-mcp-config`, `--setting-sources project` and `--no-session-persistence`; no hardcoded paths (`HERMES_RELAY_ROOT`, `HERMES_RELAY_FALLBACK_CMD`, `HERMES_RELAY_SCRIPT`).
  - Offline test suite in `tests/test_bridge.py`. Roadmap in the plugin README: atomic self-claim, presence-file candidates, asynchronous `ask`.

## v0.3.0 (2026-10-22)

- New **multi-agent-orchestration** plugin with five skills:
  - `fanout-orchestration`: coordinate parallel subagents on Claude Code (`Agent`, `SendMessage`, `TaskStop`) or Hermes (`delegate_task`): a wall-clock budget in every goal, one probe before the batch commits, single-writer discipline, steer instead of respawn, and a verify-before-you-write-the-board checklist. References: tool map for both runtimes, TRUNCATED and dead-child recovery, LLM-proxy worker harnesses, one-shot review fan-out.
  - `hermes-bot-team` (Hermes): isolated profile teams with secrets tiering, what a new profile does not inherit, the delegation cap, and a kanban CLI cheatsheet.
  - `hermes-kanban-project-launch` (Hermes): the explore-to-dispatch pipeline for board-driven refactors, with `kanban_graph.py` (creates a dependency-linked task graph from JSON, parents first).
  - `hermes-kanban-triage-and-chains` (Hermes): moving a card out of `triage`, and sequential board chains with `chain_boards.py` as a no-agent cron poller.
  - `hermes-kanban-field-notes` (Hermes): reliable CLI and SQLite queries, the board schema, `task_events` kinds.
  - Hermes commands and flags were checked against Hermes 0.21.3. Two corrections to earlier notes: `--priority` sorts higher-first (not 1 = critical), and task ids are `t_` plus 8 hex characters.

## v0.2.0 (2026-10-21)

- New **windows-agent-survival** plugin with two skills:
  - `git-bash-on-windows`: the top traps for agents on Windows (MSYS path rewriting, `cd /d`, backslashes eaten in heredocs, CRLF rewrites, PowerShell 5.1 vs 7, killing by captured PID, background jobs, retry loops, Npcap notes), each with symptom, cause and fix. Path behaviors verified live on Windows 11.
  - `everything-search`: file search with voidtools Everything's `es.exe`, its silent-failure traps (missing `-instance`, `-p` vs `-path`, `a | b` vs `a|b`), and `es_find.py`, a wrapper that runs a positive control before the real query.

## v0.1.0 (2026-10-21)

First release.

- **agent-verification-kit** plugin with four skills:
  - `evidence-ladder`: verify by effect, never by proxy. Evidence levels, a catalogue of proxy traps, and three probe scripts (`http-evidence.py`, `llm-smoke.py`, `hook-pipe-test.py`).
  - `measure-before-you-quote`: seven measurement recipes, KV-cache and VRAM math, cost per unit of work, four Python scripts and one PowerShell script; `rate_window.py` and `block_bootstrap.py` have `--demo` modes that need no infrastructure.
  - `artifact-review`: check a plan or handoff against the live system, with a per-claim verification checklist.
  - `api-verification`: get evidence for a library's installed API before calling it, and gate remote writes.
