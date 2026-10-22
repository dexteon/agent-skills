# Hermes kanban CLI cheatsheet

Copy-paste forms, checked against the Hermes 0.21.3 argparse tree (`hermes kanban --help` and each subcommand's `--help`). `--board <slug>` goes right after `kanban`, before the subcommand; a `--board` after the subcommand is a usage error.

## Boards

```bash
hermes kanban init                                   # create kanban.db once (idempotent)
hermes kanban boards create <slug> --name "Display"  # slug is the only positional
hermes kanban boards create <slug> --switch --default-workdir <project_dir>
hermes kanban boards switch <slug>                   # set the active board
hermes kanban boards show                            # print the active slug and DB path
hermes kanban boards list --json                     # all boards with counts
hermes kanban boards set-default-workdir <slug> <project_dir>
```

Scripts should not rely on the active board. Pass `--board <slug>` on every call, or set `HERMES_KANBAN_BOARD=<slug>` in the environment (it takes precedence over the persisted switch).

## Tasks

```bash
# Basic task
hermes kanban --board <slug> create "Task title" \
  --assignee <profile> --priority 2 \
  --body "What to do" \
  --workspace "dir:<project_dir>"

# Goal-mode worker (judge re-checks the card after each turn; keeps going until done or budget)
hermes kanban --board <slug> create "Title" \
  --assignee <profile> \
  --goal --goal-max-turns 200 \
  --body "Acceptance criteria, written as checks the judge can apply" \
  --workspace "dir:<project_dir>"

# Dependency gate at creation (repeat --parent for several parents)
hermes kanban --board <slug> create "Child task" \
  --assignee <profile> --parent <parent_id> --parent <other_parent_id> \
  --body "Waits for its parents" --workspace "dir:<project_dir>"

# Machine-readable id back
hermes kanban --board <slug> create "Title" --assignee <profile> --body "..." --json
```

```bash
hermes kanban --board <slug> list                    # alias: ls
hermes kanban --board <slug> list --status ready --json
hermes kanban --board <slug> show <t_id>             # body, comments, events
hermes kanban --board <slug> link <parent_id> <child_id>   # positional, parent first
hermes kanban --board <slug> complete <t_id> --result "what landed"
hermes kanban --board <slug> block <t_id> waiting on the API key
hermes kanban --board <slug> unblock <t_id>          # ids only; use --reason "text" for a note
hermes kanban --board <slug> set-model <t_id> <model> --provider <provider>
hermes kanban --board <slug> reassign <t_id> <profile> --reclaim
hermes kanban --board <slug> archive <t_id>
```

## Dispatcher

```bash
hermes gateway start                      # the dispatcher runs inside the gateway
hermes gateway status
hermes kanban --board <slug> dispatch     # one pass now: reclaim stale, promote ready, spawn
hermes kanban --board <slug> stats --json # by_status, by_assignee, oldest_ready_age_seconds
hermes kanban --board <slug> watch        # live event stream
hermes kanban --board <slug> tail <t_id>  # follow one task
hermes kanban --board <slug> diagnostics  # "Ready for Xh with no worker" and friends
```

`hermes kanban daemon` is deprecated in 0.21.x (hidden `--force` still exists for hosts that cannot run the gateway). Do not run a daemon beside a gateway: two dispatchers on one board fight over claims.

## Priority

`--priority` is an integer tiebreaker. On 0.21.3 the default sort is `priority DESC, created_at ASC`, so a **higher** number dispatches first. Do not assume "1 means critical"; that convention is the opposite of what the code does. Pick one scale for your boards and write it in the board description.

## Key flags

| Flag | Purpose |
|---|---|
| `--assignee <profile>` | profile that runs the card; an unknown name sits in `ready` forever |
| `--body "..."` | task description (there is no `--description` on `create`) |
| `--priority N` | integer, higher first |
| `--workspace dir:<path>` | run in that directory; also `scratch`, `worktree`, `worktree:<path>` |
| `--parent <id>` | dependency gate, repeatable |
| `--goal` / `--goal-max-turns N` | goal loop with a turn budget (default 20) |
| `--model <m>` / `--provider <p>` | per-task override without changing the profile |
| `--max-runtime 30m` | SIGTERM then SIGKILL the worker past the cap, re-queue the task |
| `--max-retries N` | per-task circuit breaker |
| `--skill <name>` | force-load a skill into the worker, repeatable |
| `--json` | machine-readable output on `create`, `list`, `show`, `stats`, `boards list` |
