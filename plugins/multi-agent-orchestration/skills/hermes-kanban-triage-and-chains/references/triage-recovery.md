# Triage recovery

`triage` is the status the dispatcher assigns after `block_loop_detected`: the same typed block kind recurred past the recurrence limit (an install timing out every run, a missing compiler, a dependency that never appears). It is a parking state, not a user block. The worker process exits, no claim TTL applies, and the row stays `triage` until something moves it.

## What moves a triage task (Hermes 0.21.3)

- `hermes kanban --board <slug> specify <t_id>`: the auxiliary LLM rewrites title and body into a concrete spec and promotes `triage -> todo`. `--all` sweeps every triage task.
- `hermes kanban --board <slug> decompose <t_id>`: splits a triage task into child cards routed by profile description, or falls back to specify-style promotion.
- A direct DB update (below).

Nothing else does. `reclaim`, `reassign`, `schedule`, `unblock`, `block` and `promote` all refuse (`promote` only accepts `todo` and `blocked`). Do not try them first; skip to the fix.

## Fix steps

1. Read `hermes kanban --board <slug> show <t_id>` and `hermes kanban --board <slug> runs <t_id>` to identify the repeated failure.
2. Fix the root cause, not the retry: switch a long foreground install to a background process with a log, install the missing binary, split the command, raise `--max-runtime`.
3. Confirm the cause is corrected independently (import the module, run the binary), not by rerunning the same command.
4. Move the task. Prefer `specify` when the card body should change anyway. Otherwise reset the row directly; the DB path is printed by `hermes kanban boards show` (switch to the board first) and is `~/.hermes/kanban/boards/<slug>/kanban.db` on a default layout (under the profile directory for a named profile):

   ```bash
   sqlite3 "<db_path>" "UPDATE tasks SET status='ready', consecutive_failures=0, block_kind=NULL, block_recurrences=0, claim_lock=NULL, claim_expires=NULL, last_failure_error=NULL WHERE id='t_<hex>'"
   ```

   Column names are from the 0.21.3 schema. Check `PRAGMA table_info(tasks)` on your version before running it; a column rename makes the statement fail loudly, which is the good outcome.

5. Re-dispatch: `hermes kanban --board <slug> dispatch`.
6. Verify the new run claimed the task: watch for `heartbeat` events (`hermes kanban --board <slug> tail <t_id>`), not just the dispatch line.

Never restate the failure as the rule. The rule is "clear the parking state after fixing the cause", never "retry the broken command until it goes through".
