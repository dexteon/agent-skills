# Sequential board chains

Use when several boards must run one after another ("kick off the next board when this one finishes") rather than in parallel.

## Why a poller

Cross-board `link` does not work: links are per board, and `hermes kanban --board <b> link <p> <c>` with a task from another board fails with `unknown task(s)`. The mechanism is a blocked gate task on each later board plus a poller that unblocks it when the previous board is complete. Do not leave the chain on manual dispatch: whoever is supposed to trigger the next board will forget.

## Pattern

1. On every board except the first, the first task is the gate. Its descendants are already linked behind it with `--parent`, so they sit in `todo`.
2. Block the gate: `hermes kanban --board <next> block <gate_id> waiting on <prev> board`.
3. Run `scripts/chain_boards.py` on a schedule. Each tick it:
   - reads `hermes kanban --board <slug> stats --json` for each board and checks `by_status`: a board is complete when `triage`, `todo`, `scheduled`, `ready`, `running`, `blocked` and `review` are all zero. There is no `total` key in that JSON, and `done >= total` is the wrong test anyway because a `triage` or `blocked` card never advances.
   - unblocks the next gate (`hermes kanban --board <next> unblock <gate_id>`) when its predecessor is complete and the gate is still blocked (idempotent: a stale tick that sees an already-ready gate does nothing).
   - prints `CONTINUE <active boards>` or `DONE`.
4. Schedule it as a no-agent cron job (the script is the job; its stdout is delivered verbatim; empty stdout is silent):

   ```bash
   cp scripts/chain_boards.py ~/.hermes/scripts/
   # write ~/.hermes/scripts/chain_boards.json (see the script's --help)
   hermes cron create "20m" --name chain-<project> --no-agent --script chain_boards.py --deliver local
   ```

   `--script` takes a path under `~/.hermes/scripts/` and no arguments, so the chain definition lives in a JSON file beside the script.

5. When the poller prints `DONE`, remove the job: `hermes cron remove <job_id>` (or `pause` it if the chain will be reused).

## CLI traps

- `boards create` takes only the slug positionally; the display name is `--name`.
- `unblock` takes task ids as positionals. Extra words are parsed as more task ids and fail with `cannot unblock <word> (not blocked/scheduled?)`. A note goes in `--reason "text"`.
- `block <id> <reason...>` does take free reason text.
- A `triage` card does not count as done and stalls the chain. Fix the cause, then reset it (see triage-recovery.md).
- Do not assume every ready task gets claimed. The dispatcher spawns nothing for an unknown assignee or a stale workspace path; check `hermes kanban --board <slug> diagnostics` when a board sits still.
