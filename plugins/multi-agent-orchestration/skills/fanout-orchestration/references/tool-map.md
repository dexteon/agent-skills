# Tool map: the same discipline on Claude Code and Hermes

The skill body is runtime-neutral. This file maps each need to the concrete tool, with the error strings and paths you will actually see. Hermes facts were checked against the 0.21.3 CLI and source; Claude Code facts against the Agent tool as shipped in 2026.

## Spawning

| Need | Claude Code | Hermes |
|---|---|---|
| One child | one `Agent` call with a `prompt` and optional `name` | `delegate_task(goal=..., context=...)` |
| N children in parallel | N `Agent` calls in one message (they run concurrently) | `delegate_task(tasks=[{goal, context, output_schema}, ...])` |
| Structured return | ask for a fixed report shape in the prompt | `output_schema` per task |
| Re-delegation | a child can spawn its own agents unless told not to | children are leaves; they cannot call `delegate_task` |
| Concurrency cap | no fixed count; your own context and token budget | `delegation.max_concurrent_children` (default 10 on 0.21.x, 3 on older builds); a longer `tasks` array is rejected whole |
| Cap error text | n/a | `Too many tasks: N provided, but max_concurrent_children is M` |
| Loop guard | n/a | a mangled batch counts every phantom entry; the `loop_subagent_cap` guard then blocks delegation for the rest of the turn |

Read the Hermes cap with `hermes config get delegation`. Raise it with `hermes config set delegation.max_concurrent_children <n>`.

## Watching and steering

| Need | Claude Code | Hermes |
|---|---|---|
| Who is running | you get a notification when each child finishes; keep your own list of names | `delegate_task(action="list")` returns ids, goals, status and transcript paths |
| Course-correct | `SendMessage` to the child's name | `delegate_task(action="steer", subagent_id=..., message=...)`; lands at the child's next tool boundary |
| Steer that did not land | the message is simply unread | the result carries `missed_steer` and the error text `steer did not land before the subagent stopped` |
| Stop | `TaskStop` | `delegate_task(action="stop", subagent_id=...)`; a stale id errors, so list first |
| Live transcript | none; put "append progress to `<file>` every few tool calls" in the prompt | `~/.hermes/cache/delegation/live/<deleg_id>/task-<n>.log` (under the active profile's home when profiles are in use); a `manifest.json` sits beside the logs |

## Completion

| Need | Claude Code | Hermes |
|---|---|---|
| Result | the child's final report, delivered to you (not shown to the user) | the batch result, one entry per task with `status` and summary |
| Truncation | the report is whatever the child wrote | `truncated: true` when the child hit `max_iterations`; long summaries get a `[SUMMARY TRUNCATED]` footer with the path of the full output on disk |
| Verifying | read the artifact; the report can claim things the artifact lacks | same; also `git status` the workspace for uncommitted work |

## Shared-state writes

| Need | Claude Code | Hermes |
|---|---|---|
| Write fence | a rule you write into the prompt ("do not edit the board / registry / plan file") | enforced: board mutation from a child fails with `delegate_task child contexts cannot mutate Kanban tasks or boards` (CLI form: `kanban: delegate_task child contexts cannot mutate Kanban tasks via the CLI`) |
| Fence mechanism | none | inherited env var `HERMES_DELEGATED_CHILD_CONTEXT`; a coordinator shell that inherited it is refused too, so `unset` it there |
| Board or task writes | you, after verifying | you, after verifying: `hermes kanban --board <b> complete <t_id> --result "<what landed>"` |

## Mapping a goal between runtimes

Write the goal once, runtime-neutral, then add the runtime block:

```
Goal: <one sentence>
Budget: 5 minutes of search or scan; report partial findings when it expires; ask for more with what remains.
Progress: append each finding to <workspace>/<lane>-progress.md as you go.
Do not: write to the board, the registry, or any shared plan file. Report requested changes instead.
Report: changed files, commit hashes, tests run with output, open questions.
Fallback: if search returns quota errors or zero results twice, switch to direct reads of known URLs.
Environment: repo <path>, interpreter <path>, network via <configured proxy>.
```

Claude Code: pass it as `prompt`, give the agent a `name` so you can `SendMessage` it later. Hermes: pass the first line as `goal` and the rest as `context`, and add an `output_schema` when you want machine-readable results.
