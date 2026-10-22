---
name: hermes-kanban-project-launch
description: "Hermes only. Run a multi-agent refactor or consolidation on a Hermes kanban board: explore, classify, clarify, design, spec, decompose into a dependency-linked task graph, create an isolated board, dispatch to profiles, and gate the end with safety and code review. Load when someone says \"unify this project\", \"consolidate these tools\", \"refactor it with a kanban board\", or wants a durable dependency-ordered board with review gates. Carries the CLI traps (sticky board switch, unblock arg parsing, stalled dispatch, cross-board links) that otherwise wreck the task graph without an error."
license: MIT
version: 0.1.0
---
# Kanban project launch: from codebase to a running task graph

A pipeline for architectural work that needs several profiles in parallel: unify three tools into one package, consolidate duplicated code, restructure a project. The board makes the work durable and dependency-ordered; the review gates stop errors from several agents compounding unchecked. Commands checked against Hermes 0.21.3.

## When not to use it

- A single-file fix or a bounded change: just do it.
- A task with no dependencies: `delegate_task` directly.
- Pure research: a research skill, not a board.

## Prerequisites

1. A brainstorming or design skill if you have one (for example `superpowers:brainstorming` from the superpowers plugin); it governs phases 3 to 5. Optional.
2. `hermes profile list` to discover the profiles and models that actually exist. The dispatcher spawns nothing for an unknown assignee.
3. Read the target codebase: file tree, every README, every requirements file, `git status`.

## The pipeline

### Phase 1: Explore

`find <project> -maxdepth 3 -type f`, `git log --oneline -10`, `git status`, every README and requirements file. Identify duplicated code, overlapping tools, consolidation candidates.

### Phase 2: Classify

Spike (feasibility probe, no board), bounded (single-flow change, no board), or architectural (multi-tool consolidation, new package structure: this skill). Announce the classification.

### Phase 3: Clarify

One question at a time. For consolidations: the form of the unified app (CLI, CLI plus dashboard, web app), storage (SQLite, CSV, API layer), external integrations, production safety constraints (read-only, rate limits), and whether a knowledge base should inform the work.

### Phase 4: Design

Present in sections and get approval per section: package structure, key decisions (storage, CLI, safety, integrations), consolidation map (what merges into what), task graph preview (waves, dependencies, profiles).

### Phase 5: Spec

Write the approved design to `docs/specs/YYYY-MM-DD-<topic>-design.md` (or your design skill's path). Self-review for placeholders, consistency, scope and ambiguity. Ask the user to review.

### Phase 6: Create the board

```bash
hermes kanban boards create <slug> --name "<Project>" --default-workdir <project_path>
```

Use a project-specific slug, and pass `--board <slug>` on every later command. The persisted "current board" has not been reliable across subprocess calls on earlier builds (`boards switch` printed success while `boards current` still showed the old slug); `--board` or `HERMES_KANBAN_BOARD=<slug>` is explicit and cheap.

Before dispatching, confirm the workdir is real: `git -C <project_path> log --oneline -1`. A board can carry a stale path from before a repo moved, and every worker then fails to spawn with no useful error on the card.

### Phase 7: Decompose into the task graph

Rules:

1. One card per workstream. Do not bundle independent lanes.
2. Independent lanes have no parent links, so the dispatcher fans them out.
3. Gated work uses `--parent <id>` at creation so it stays in `todo` until its parents complete.
4. Match profiles to task type (table in [references/profile-model-management.md](references/profile-model-management.md)).
5. The last two cards are gates: a safety review (read-only guards, rate limits, exclusions; grounded in a knowledge base if one exists) and a full code review (reads the code, runs the tests, greps for unsafe patterns, produces PASS or FAIL and files follow-up cards).

Create parents first and capture their ids, then children with `--parent`. If a parent's creation failed and you pass `None` through, the child creation fails with `unknown parent task(s)`, so check every id before using it. `scripts/kanban_graph.py` does this from a JSON spec: topological order, `--json` id capture, abort on a missing parent, `--dry-run` to print the commands.

```bash
python scripts/kanban_graph.py --board <slug> graph.json --dry-run
python scripts/kanban_graph.py --board <slug> graph.json --ids-out ids.json
```

Use subprocess list arguments, never shell string interpolation, for card bodies. Bodies hold quotes, backticks and dollar signs.

If a knowledge base should inform a card, put the exact query instructions (store path or endpoint, collection, score threshold) in the card body. Workers do not know your database details.

### Phase 8: Dispatch and monitor

```bash
hermes gateway status
hermes kanban --board <slug> dispatch        # prints "Spawned: N"
hermes kanban --board <slug> ls
hermes kanban --board <slug> stats
hermes kanban --board <slug> watch
hermes kanban --board <slug> tail <t_id>
```

The dispatcher inside the gateway ticks every 60 s, promotes `todo` to `ready` as parents complete, and reclaims crashed tasks. Ready tasks can still sit unspawned for a long time (observed: over an hour, with `diagnostics` reporting "Ready for Xh with no worker"). An explicit `dispatch` is the fast path; run it after each parent completes instead of waiting for ticks, and run `ls` after it to confirm the spawn.

### Phase 9: Startup script

Write `START_KANBAN.sh` at the project root: board slug, task graph summary, profile and model table, the monitoring commands above. The next session starts from that file.

## Sequential boards

Several boards that must run one after another use a blocked gate task per board and a no-agent cron poller. Cross-board `link` does not work. The pattern and the poller script live in the `hermes-kanban-triage-and-chains` skill.

## Pitfalls

1. The current-board setting is not something a script should depend on. Always `--board <slug>`.
2. A missing `--board` lands cards on the wrong board with no error.
3. Creating all cards in parallel and linking afterward is a race: the dispatcher can claim a child before its parents exist. Parents first.
4. Shell-interpolated bodies break on special characters. List arguments.
5. No terminal review gates: errors from several agents compound unchecked.
6. Not verifying after dispatch: `ls` after every `dispatch`.
7. **Mutating kanban commands fail while a `delegate_task` child is running**, even from the parent session: `kanban: delegate_task child contexts cannot mutate Kanban tasks via the CLI`. Wait for the child, or write the board spec to files and create the board afterward. Read-only commands (`boards list`, `ls`, `stats`) still work.
8. **Designing without dispatching is valid.** When asked to "build them out in detail" but "not run them tonight", the deliverable is the spec files (task graph, card bodies, profile assignments, start script). Do not create the board until told.
9. Free-tier models crash under load. Switch the bottlenecked profile to a stable model (`hermes -p <profile> config set model.default <model>`) and verify with `hermes profile show <profile>`.

## Checklist

- [ ] Profiles and models listed live
- [ ] Codebase read, classification announced
- [ ] Questions asked one at a time, design approved per section
- [ ] Spec written, self-reviewed, user-reviewed
- [ ] Board created; every command carries `--board <slug>`; workdir verified with git
- [ ] Parents created first; children linked at creation; no `None` parent ids
- [ ] Safety review and full code review cards at the end
- [ ] Gateway running; `dispatch` run; `ls` shows workers spawned
- [ ] `START_KANBAN.sh` written

---
Part of [agent-skills](https://github.com/dexteon/agent-skills) by [CyberAutomations](https://cyberautomations.com).
