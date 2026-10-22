# Board schema and the task_events log

Facts below are from the Hermes 0.21.3 `kanban_db` module. Check `PRAGMA table_info(<table>)` on your version before writing queries that must not fail quietly.

## Where the DB is

Each board has its own SQLite file. `hermes kanban boards show` prints `DB path:` for the active board (switch first, or set `HERMES_KANBAN_BOARD`). On a default layout it is `<hermes-home>/kanban/boards/<slug>/kanban.db`, where `<hermes-home>` is `~/.hermes` or `~/.hermes/profiles/<name>` for a named profile.

## Tables

`tasks`, `task_links` (parent and child), `task_comments`, `task_events` (activity log), `task_runs` (one row per worker attempt), `task_attachments`, `kanban_notify_subs`.

- `tasks` has **no `updated_at` column**. Order by `created_at`; recency comes from `task_events`, not the task row.
- Card bodies live in `tasks.body`. `list --json` omits them; use `show <id>` or query the column.
- `model_override` and `provider_override` are columns on `tasks`. `set-model` writes them and prints success, but `list --json` does not show them. `SELECT model_override FROM tasks WHERE id='t_...'` is the confirmation.

## Reading activity

The fastest answer to "is anything happening on this board":

```sql
SELECT task_id, kind, created_at FROM task_events ORDER BY created_at DESC LIMIT 20;
```

Timestamps are unix epochs (`datetime.datetime.fromtimestamp` in Python). Event kinds seen in 0.21.3:

| Kind | Meaning |
|---|---|
| `created`, `linked`, `unlinked`, `assigned`, `commented`, `attached` | card edits |
| `spawned`, `claimed`, `heartbeat` | a worker run is live or ran recently |
| `completed`, `review_requested`, `changes_requested` | lifecycle moves |
| `blocked`, `unblocked`, `scheduled`, `dependency_wait` | waiting states; `blocked` payload carries the reason |
| `block_loop_detected` | the card went to `triage` |
| `crashed`, `timed_out`, `spawn_failed`, `gave_up`, `stale`, `reclaimed`, `reclaim_deferred`, `respawn_guarded` | failure and recovery; payloads carry a `retry_status` where the card is re-dispatchable |
| `model_override_set`, `promoted_manual`, `reconciled`, `archived` | operator actions |

## Per-board sweeps

`hermes kanban list --board <slug>` is a usage error (`--board` belongs before the subcommand). `hermes kanban --board <slug> list --status <st> --json` works. For a sweep across many boards, a loop over `boards list --json` slugs with the DB query above is faster than N CLI invocations.

## Board state when several agents share the boards

Status counts alone mislead when Hermes workers, other agent sessions and review gates all write to the same boards. Before reporting a board's state or claiming a card:

1. Read card status from the DB, then `task_events` recency. A sibling may be mid-run right now; never claim a card whose latest event is a recent `heartbeat` or `claimed`.
2. Verify each card's referenced artifacts exist (repo paths, workspace paths, fixtures named in the body). A card written against a layout that was never built, or blocked citing paths from another machine, is stale: rewrite or retire it, do not work it as written.
3. If the project gates completion on a shared git remote or a hub repository, done-ness has layers: the kanban status, the branch in the hub, and the merge on origin. A card marked done may exist only as an unmerged branch. Check the log and the remote refs before reporting what has landed.
4. Report the board-level picture as soon as the load-bearing facts are confirmed: terse, per board, what is actionable.
