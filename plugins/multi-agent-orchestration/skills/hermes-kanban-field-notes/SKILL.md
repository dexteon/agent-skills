---
name: hermes-kanban-field-notes
description: "Hermes only. Reliable ways to query Hermes kanban boards from the CLI and straight from each board's SQLite file: the --json forms that return full ids, the DB path, the tables and task_events kinds, why 'show' says 'no such task' for an id that exists, and what 'set-model' does not show you. Load when a kanban command returns the wrong board's tasks, 'no such task', or 'unrecognized arguments', or when you need to know whether anything is happening on a board right now."
license: MIT
version: 0.1.0
---
# Hermes kanban field notes: query the board you think you are querying

Short, verified patterns for reading Hermes kanban state. Checked against the 0.21.3 CLI and `kanban_db` schema; the schema reference lists what to re-check on a newer build.

## Board state

```bash
hermes kanban boards list --json          # slug, name, is_current, counts per board
hermes kanban boards show                 # active slug plus "DB path:"
```

Do not trust `boards switch` from a script. Pass `--board <slug>` on every call or set `HERMES_KANBAN_BOARD=<slug>`. Board slugs do not always match the project's name: list all boards and search both `slug` and `name` before concluding a board does not exist.

## Task queries

```bash
hermes kanban --board <slug> list --status ready --json
hermes kanban --board <slug> show <t_id>
hermes kanban --board <slug> complete <t_id> --result "what landed"
```

- `--json` is the reliable output. The text table omits fields.
- Task ids are `t_` plus 8 hex characters. Short labels from your own notes (`SO-01`) are not ids; `complete` wants the `t_` form.
- `list --json` does not include card bodies; `show` does.
- `hermes kanban show <id>` without `--board` can say `no such task` for an id that exists: it is on a different board. Add `--board <slug>` or query the DB.
- `hermes kanban list --board <slug>` is a usage error. `--board` goes right after `kanban`.
- `set-model` prints success, and `list --json` still does not show the override. Confirm with `show <t_id>` (the `model:` line) or `SELECT model_override FROM tasks WHERE id='t_...'`. An unconfirmed `set-model` is unconfirmed.

## Direct DB access

When the CLI is slow or ambiguous, read the board's SQLite file. The path is on `boards show`; on a default layout it is `~/.hermes/kanban/boards/<slug>/kanban.db` (under `~/.hermes/profiles/<name>/` for a named profile).

```bash
sqlite3 "<db_path>" "SELECT id, title, status FROM tasks WHERE status IN ('todo','blocked') ORDER BY created_at"
sqlite3 "<db_path>" "SELECT task_id, kind, created_at FROM task_events ORDER BY created_at DESC LIMIT 20"
```

The second query is the fastest answer to "is anything happening on this board". `heartbeat`, `spawned` and `claimed` mean a worker is live or was just now; `crashed`, `timed_out` and `gave_up` carry a `retry_status` in their payload. `tasks` has no `updated_at` column; recency lives in `task_events`. Tables, columns and the full kinds list: [references/schema-and-events.md](references/schema-and-events.md).

## Creating many cards at once

The CLI with `--json` is the right default. For a batch of dozens, a direct `INSERT` is faster; the id must be `t_` plus 8 hex or the CLI cannot address the row afterward. Recipe and the columns that matter: [references/direct-task-creation.md](references/direct-task-creation.md).

## Before reporting a board's state

1. Status from the DB, then `task_events` recency. A sibling agent may be mid-run; never claim a card with a fresh `heartbeat`.
2. Check that the paths a card references exist on this machine. A card blocked on paths from another host is stale; rewrite or retire it.
3. Report per board, terse, what is actionable. The reader wants the survey fast.

---
Part of [agent-skills](https://github.com/dexteon/agent-skills) by [CyberAutomations](https://cyberautomations.com).
