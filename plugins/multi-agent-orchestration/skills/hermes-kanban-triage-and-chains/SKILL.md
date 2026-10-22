---
name: hermes-kanban-triage-and-chains
description: "Hermes only. Two field notes for Hermes kanban boards: how to move a task the dispatcher parked in 'triage' (no normal CLI command does), and how to run several boards one after another with a blocked gate task and a no-agent cron poller (cross-board links do not exist). Load when a card shows status triage, when 'reclaim', 'unblock' or 'promote' refuse to move a card, or when someone says \"kick off the next board when this one finishes\"."
license: MIT
version: 0.1.0
---
# Kanban triage recovery and sequential board chains

Two situations where the Hermes board looks stuck and the obvious command does nothing. Both have a mechanism behind them; both have a short fix. Checked against Hermes 0.21.3.

## 1. A card is in `triage`

`triage` is where the dispatcher parks a card after `block_loop_detected`: the same typed block recurred past the limit (an install that times out every run, a missing compiler, a dependency that never arrives). It is the dispatcher giving up to prevent an infinite retry loop, not a failure you can retry past.

What does not move it: `reclaim`, `reassign`, `schedule`, `unblock`, `block`, `promote` (promote accepts only `todo` and `blocked`). What does:

- `hermes kanban --board <slug> specify <t_id>`: rewrites the card into a concrete spec through the auxiliary LLM and promotes it to `todo`.
- `hermes kanban --board <slug> decompose <t_id>`: splits it into child cards, or falls back to specify.
- A direct DB reset to `ready` after you have fixed the cause.

The rule: fix the root cause first (background the long install, install the binary, split the command, raise `--max-runtime`), confirm it independently, then clear the parking state and `dispatch`. Steps, the SQL and the verification are in [references/triage-recovery.md](references/triage-recovery.md).

## 2. Boards that must run in sequence

`link` is per board. A link to a task on another board fails with `unknown task(s)`. The mechanism for "board B starts when board A finishes" is:

1. Board B's first task is a gate; its descendants are already behind it via `--parent`.
2. Block the gate: `hermes kanban --board B block <gate_id> waiting on board A`.
3. A poller checks A's `stats --json` each tick and unblocks the gate when A is complete.
4. The poller runs as a no-agent cron job, so nobody has to remember to trigger B.

Complete means `by_status` has zero `triage`, `todo`, `scheduled`, `ready`, `running`, `blocked` and `review`. The JSON has no `total` key, and `done >= total` would be wrong anyway: a `triage` card never advances, so the chain stalls until you fix it (section 1).

```bash
cp scripts/chain_boards.py ~/.hermes/scripts/
python scripts/chain_boards.py --help          # JSON config format
hermes cron create "20m" --name chain-<project> --no-agent --script chain_boards.py --deliver local
```

The script prints `CONTINUE <active boards>` or `DONE`; remove the job after `DONE`. It is idempotent: a tick that sees an already-unblocked gate does nothing. Details and the CLI traps that bit the first version in [references/sequential-chains.md](references/sequential-chains.md).

## CLI traps that produced these notes

- `unblock` takes ids only; trailing words become bogus ids: `cannot unblock <word> (not blocked/scheduled?)`. A note goes in `--reason "..."`.
- `block <id> <reason words>` does take free text.
- `boards create <slug>` takes only the slug positionally; the display name is `--name`.
- `--board <slug>` goes before the subcommand. Scripts pass it on every call.
- A ready card with an unknown assignee or a stale workspace path is never spawned and never errors on the card. `hermes kanban --board <slug> diagnostics` says why.

---
Part of [agent-skills](https://github.com/dexteon/agent-skills) by [CyberAutomations](https://cyberautomations.com).
