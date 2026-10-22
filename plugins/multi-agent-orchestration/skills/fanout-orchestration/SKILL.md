---
name: fanout-orchestration
description: "Coordinate parallel subagents (Claude Code Agent tool, Hermes delegate_task, or LLM-proxy workers) across independent work lanes. Load before spawning more than one child, when someone says \"fan out\", \"run these in parallel\", \"spawn N agents\", \"start all of them\", \"cut back to N agents\", or when a child reports done, comes back TRUNCATED, or keeps retrying the same failing call. Covers wall-clock budgets, probe-before-batch, single-writer rules, steer vs respawn, and verifying self-reported completion before anything is written down."
license: MIT
version: 0.1.0
---
# Fan-out orchestration: budget, probe, verify, never respawn from zero

When you hold an agent budget and several work lanes (boards, task lists, workstreams) should move at once, you are the coordinator. You spawn one child per lane, keep every write to shared state for yourself, and verify every dispatch and every completion. Children do the work. You own the truth about what landed.

Every rule here came from a run where the opposite happened: a child polled a dead network path for six minutes, a child said "written" about a file that did not exist, a respawn threw away thirty minutes of verified work, a stale id error stopped a steer. Tool names differ between runtimes; the discipline does not. Exact tool mapping is in [references/tool-map.md](references/tool-map.md).

## Terms

- **Lane**: one independent stream of work with its own child. Lanes that share an output are one lane.
- **Child**: a subagent you spawned. It runs with its own context and reports back a summary.
- **Budget**: a wall-clock or iteration limit written into the child's goal, plus the concurrency cap on how many children can run.
- **Steer**: a message queued to a running child that lands at its next tool boundary and keeps its gathered context. The alternative, stop and respawn, discards that context.
- **Write fence**: the rule (and in some runtimes the mechanism) that children do not write shared state such as boards, cards or registries. You apply every change they request.
- **Self-report**: a child's own "done" summary. It is a claim, not evidence, until you check the artifact.

## Tool map, short form

| Need | Claude Code | Hermes |
|---|---|---|
| Spawn N children | N `Agent` calls in one message | `delegate_task(tasks=[...])` |
| See who is running | completion notifications; name agents to address them | `delegate_task(action="list")` |
| Course-correct a child | `SendMessage` to the agent name | `delegate_task(action="steer", subagent_id=..., message=...)` |
| Stop a child | `TaskStop` | `delegate_task(action="stop", subagent_id=...)` |
| Concurrency cap | context and token budget, no fixed count | `delegation.max_concurrent_children` (10 on 0.21.x, 3 on older builds) |
| Live progress | the child's own progress file (ask for one in the goal) | `~/.hermes/cache/delegation/live/<deleg_id>/task-<n>.log` |

## Step 0: Ground the roster before spawning

- Read lane state live (the board, the task list, the repo) right before dispatch. Never plan from remembered state.
- Check each lane for existing automation (a cron job, a dispatcher, a loop driver) before assigning a child. A child on top of a driver duplicates the work and burns a slot. When the user later cuts the agent count, cut the duplicated lane first.
- A network-bound child (one that calls a registry, an API, a proxy) must use the configured network path and nothing else. Grep its driver for a raw socket or direct connection that bypasses the configured proxy, fix that before dispatch, and re-read the file after patching: the read you took while editing can be stale.

## Step 1: Dispatch within the cap

- **Give every child a wall-clock budget in its goal.** A default of 5 minutes of search or scan time works; the child must wrap up and report partial findings when the budget expires, and must ask for more time (saying what it still needs to check) if it wants an extension. Children walking directories with no end condition have burned 20 minutes with nothing to show.
- **Require incremental output.** The goal tells the child to append findings to a workspace file (or print a progress line every few tool calls), so a stop or crash does not lose what it already found.
- **Read the concurrency cap first** (Hermes: `hermes config get delegation`, key `max_concurrent_children`). A batch longer than the cap is rejected whole. Split into batches of at most the cap and dispatch the rest when a slot frees.
- **A mangled payload burns the whole turn.** If the runtime reports far more tasks than you sent (Hermes: `Too many tasks: N provided, but max_concurrent_children is M`), the array was stringified or split on delimiters in transit. Every phantom entry still counts against the per-turn spawn cap, and one such call can trip the loop guard that blocks all delegation for the rest of the turn. Keep each task a real object with compact goal text, avoid long comma-heavy strings in goals, and if the guard has fired, finish inline or end the turn and dispatch fresh next turn. Never resend the same shape mid-turn.
- **One child per lane with a self-contained goal**: exact repo path, interpreter path, network and env notes when network-bound, the plan file path when one exists, and the report format (changed files, commit hashes, pass or fail).
- **Research children need a search-failure fallback in the goal**: "if search returns quota errors or zero results twice, switch to direct reads of known URLs and stop retrying search." Without it a child burns its budget retrying a quota-limited engine.
- Tell children not to touch shared boards or registries even when their lane is one. The write fence blocks them and the attempts burn their iterations.

## Step 2: Verify the dispatch took

- Immediately after dispatch, list the children and confirm the expected ones show as running. A rejected or interrupted batch leaves slots idle with nothing surfaced to you, and idle slots read as stalling to whoever is watching.
- **Probe the network path once before the batch commits.** For a network-bound child, make one call yourself through the same proxy and endpoint the child will use. If it succeeds, the batch will succeed. If it fails, fix the path (auth, receive loop, bind address) and re-dispatch with the diagnosis in the child's context. The run this corrects: a child read the driver, judged the path fine, launched the full batch, then polled a background process for six minutes while the result count stayed at zero. One probe would have exposed the fix in seconds.
- Before stopping or steering a child by id, list again. Finished children disappear from the tree and a stop by stale id errors.

## Step 3: Single-writer discipline

- Children do not mutate shared state. In Hermes the fence is enforced: a child's board write fails with `delegate_task child contexts cannot mutate Kanban tasks or boards`. In Claude Code it is a rule you write into every goal. Either way, you are the only writer; children request changes in their report.
- The Hermes fence is an inherited environment variable (`HERMES_DELEGATED_CHILD_CONTEXT`), not a security boundary. A coordinator shell that inherited it is refused too. Unset it in your own shell instead of concluding that board writes are impossible.
- **Checkpoint the shared workspace.** `git init` the working folder before dispatching and commit after every artifact write. A workspace shared by the coordinator and children is not durable storage: files have vanished with no culprit in any transcript, and restoring from git plus rerunning the pipeline from the last commit takes minutes instead of a rebuild from zero.

## Step 4: Triage blockers while children run

For each blocked task, read the reason and act by kind. Never unblock blind.

| Kind | Check | Action |
|---|---|---|
| Stale claim from a crashed run | Is the claiming PID dead? | Unblock only if dead. A live claim means a worker is mid-run |
| Capability block (a service is down) | Probe the service yourself | If truly down, leave it blocked and add a dated comment with the verified state |
| Dependency block (parent unfinished) | Nothing | Leave it; parent completion promotes it |
| Blocked on an approval you now hold | Nothing | Unblock and let a free child pick it up |

## Step 5: Report progress from live output, and steer instead of respawn

Tail the live transcript or progress file when asked for progress. Do not wait for completion messages.

A child stuck retrying the same failing call is a steer target, not a respawn. The same tool returning the same error three or more times in the tail means it will not self-correct. Queue a steer with the exact workaround inline (for example, when a file tool rejects non-string content: "write a small script that serializes the payload and run it"). The steer lands at the child's next tool boundary and keeps everything it has gathered. A stop and respawn discards it.

## Step 6: Reconcile completions

A child's "done" is a self-report. Verify, then write the board or tell the user. The full checklist with the incidents behind each item is in [references/reconcile-and-recover.md](references/reconcile-and-recover.md). The short form:

1. **Verify artifacts yourself**: `ls` the claimed output paths, `git log --oneline` for claimed commits, run the lane's tests with the lane's interpreter. Only then mark the card done.
2. **A child can report success while its deliverable silently failed**, usually at the final write. Check the declared output path after every completion, and parse the file (count entries) before trusting either a success claim or a failure flag.
3. **Ground-truth inherited expectations.** Expectations a child picked up from a label (a classifier, a model, a prior note) can be wrong. Check the raw data before baking them into tests or cards.
4. **TRUNCATED means partial progress, not failure.** Read the transcript tail for the diagnosis and `git status` for uncommitted work, then finish the small remainder yourself or re-dispatch with both inlined. Never respawn from zero.
5. **A child that died at the final write has usually done the work.** Reconstruct from its transcript and label the result as reconstructed.
6. **Read a dead child's transcript before re-hitting the wall it died on.** If two independent angles failed, the wall is structural: document it with the evidence and hand the user the manual path.
7. **Verify claimed commits with `git show <hash>`.** When the hash is absent, check the working tree: the edit usually landed and the cheapest fix is committing it yourself.
8. **Backfill freed slots in the same turn.** An idle slot reads as stalling.
9. **Pair review children with fix children.** The review's numbered findings plus any uncommitted work become the fix child's context.
10. **Sensitive-data lanes get a read-only child.** When a lane's material includes credentials, personal data, or anything that must not leave its store, write the goal as a generic tool description with the data locked read-only, require a written findings document, and forbid code edits and commits. The child does judgment work without holding the specifics.

## Other worker types

- **LLM-proxy workers** (background processes driving an OpenAI-compatible endpoint through a tool loop) instead of runtime subagents: [references/llm-proxy-workers.md](references/llm-proxy-workers.md).
- **One-shot review fan-out** (several independent reviewers over a document set, no slots consumed): [references/oneshot-review-fanout.md](references/oneshot-review-fanout.md).

## Rules of engagement

- A compute resource named in the user's instruction ("use the big box for this") is model placement, not an action item. Do not SSH into it, health-check it, or explore it before spawning. If a child needs it, the child will say so. The reverse holds too: "leave that box alone" means stop all work on it immediately, mid-command if needed.
- A plan stays a plan until an explicit start instruction. A request to review, present or update the plan is not approval to execute it. When the user asks "is it complete?" they want the plan shown, not a diff log of work you already did.
- "Start all of them" means spawn now and steer after. Dispatch verification (Step 2) comes after the spawn, not before.
- When asked to see a saved plan (to review it or hand it to a fresh session), put the full plan text in chat, not just the path.
- A corrected number mid-course ("cut back two agents") is a whole-budget directive. It may mean a different roster across the same number of slots, not a subtraction. If the correction and the follow-up seem to conflict, the lighter reading is usually right.
- A scope or budget cut after dispatch is a steer, not a re-dispatch. Send each running child the new cap, the reduced list and an explicit skip list, so it finishes cheap from its own context. Steers land at the next tool boundary, so re-check any usage meter yourself: a child may complete one more queued action before the steer arrives.

## Checklist before you claim a lane is done

1. The output path exists and parses, checked by you.
2. Claimed commits resolve with `git show`, or you committed the landed edit yourself.
3. Tests ran with the lane's interpreter, output quoted.
4. The card or task was written by you, after the checks, with what actually landed.
5. The freed slot has its next task.

---
Part of [agent-skills](https://github.com/dexteon/agent-skills) by [CyberAutomations](https://cyberautomations.com).
