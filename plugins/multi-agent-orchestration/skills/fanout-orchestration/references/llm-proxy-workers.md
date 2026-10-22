# LLM-proxy worker lanes

Sometimes the plan routes work through an OpenAI-compatible endpoint (a LiteLLM proxy, a local server, a gateway with per-key budgets) instead of the runtime's own subagents. Each worker is then a background process running a chat-completions tool loop against that endpoint, with the model pinned by the plan. One harness script drives one task card. You are still the coordinator.

## Harness shape

- **Tool loop, not one-shot.** The endpoint returns one assistant turn per request. Loop until `finish_reason == "stop"`, dispatching tool calls (read file, write file, edit file, run command) as they come. A one-shot harness "completes" after the model's first tool call and exits with an empty result.
- **At most four simple tools.** Read, write, edit, run. Every tool result and model message goes to a JSONL trace (`{"turn": N, "msg": ...}`). The trace is your monitoring channel and your retry context.
- **Enforce the plan's rules in code, not in the prompt.** A per-task write fence (the worker may only write under its task folder), a read-deny list for sensitive paths, the interpreter pin. Prompt-only rules drift.
- **HTTP retry with backoff inside the request function.** Six attempts on 500, 429 and connection errors. A transient proxy 500 mid-run otherwise kills a long unattended worker; one died on a 500 mid-edit and its half-edits poisoned the next run.
- **Nudge, do not die, on empty final turns.** An empty content turn with no tool calls gets up to three "keep going" nudges before the run ends. Workers run out of steam before writing their deliverable. Three empty nudges in a row means done; check what landed.

## Worker discipline

- The same model for worker and coordinator is fine and often intended ("spawn myself in an isolated context"). Never treat the worker's PASS as truth: rerun the acceptance commands yourself and record the verdict in the DONE file.
- A worker that keeps exploring without writing a small mechanical deliverable (a scan script, a report): retry with a retry-note file that says what the dead run already read and instructs "stop exploring, write now." Cap attempts at about three; after that the coordinator builds it inline.
- **Interpreter:** pass the exact pinned path in the worker's environment note. A bare `python` on PATH can be a different minor version that fails exactly one test, and the worker burns a turn discovering it. Note any broken shims (a package-manager alias pointing at a missing install) so the worker does not rediscover them.
- **Slot budget:** the proxy's concurrent-slot count, not the runtime's subagent cap, is your fan-out limit. Monitor the trace files. A frozen trace with a live process is a long generation, not a hang.

## Handoff between sessions

- DONE files are the cross-session contract: a status line, files written, commands with pasted output, the acceptance verdict. A second session (another agent, another model) that continues a round honors DONE files already on disk, and checks for foreign DONE files before relaunching a task.
- A DONE file may be finished by a different agent than the one that built the work. Say so in the file ("finished by the build session"). Keep the coordinator's verdict separate from the worker's claim.
- On handoff, verify the current tree state yourself (run the gate) before planning retries. A dead worker may have left half-edits that change what the retry must do.
