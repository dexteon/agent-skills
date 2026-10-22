# Direct task creation with sqlite3

For batch expansion or scripted board changes where the CLI is too slow, insert straight into the board's DB. Prefer the CLI (`hermes kanban --board <slug> create ... --json`) whenever it is fast enough: it emits the `created` event, resolves the workspace, and keeps the dispatcher's invariants. Direct inserts skip all of that.

## Schema (0.21.3, confirmed columns)

```sql
SELECT id, title, body, status, assignee, priority,
  created_by, created_at, started_at, completed_at,
  workspace_kind, workspace_path, branch_name, project_id,
  claim_lock, claim_expires, tenant, result, idempotency_key,
  consecutive_failures, worker_pid, last_failure_error,
  max_runtime_seconds, last_heartbeat_at, current_run_id,
  workflow_template_id, current_step_key, skills,
  model_override, provider_override, reasoning_effort,
  max_retries, goal_mode, goal_max_turns, session_id,
  block_kind, block_recurrences, completion_contract
FROM tasks;
```

Run `PRAGMA table_info(tasks)` on your version first; the list above will drift.

## Insert a task

Task ids are `t_` followed by 8 hex characters (the CLI generates `"t_" + secrets.token_hex(4)`). Commands such as `complete` and `show` resolve ids by that format, so an id without the prefix is a row the CLI cannot address.

```sql
INSERT INTO tasks (id, title, body, status, assignee, priority, created_by, created_at, goal_mode)
VALUES (
  't_' || lower(hex(randomblob(4))),
  '<title>',
  '<body>',
  'ready',
  '<profile>',
  0,
  'script',
  strftime('%s','now'),
  0
);
```

- `status`: `triage`, `todo`, `scheduled`, `ready`, `running`, `blocked`, `review`, `done`, `archived`. A card for the dispatcher starts as `ready` (or `todo` when it has parents in `task_links`).
- `priority`: integer, higher dispatches first on 0.21.3.
- `goal_mode`: 1 wraps the worker in the goal loop (set `goal_max_turns` too); 0 is a one-shot worker. It does not mean "has a goal": every card has one.
- `max_runtime_seconds`: a per-task cap the dispatcher enforces.
- Parent links go in `task_links`; insert the parents first.

Commit explicitly after a multi-statement batch. Do not rely on autocommit.

## When this is worth it

- Creating dozens of similar cards from a list (one row per input).
- Scripted state changes where the CLI round trip dominates.
- Setting a column the CLI does not expose on `create`.

Everything else: use the CLI.
