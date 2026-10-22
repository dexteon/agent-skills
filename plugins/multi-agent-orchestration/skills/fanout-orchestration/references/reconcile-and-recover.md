# Reconciling completions and recovering dead children

Each item below is a rule plus the run that produced it. Read it once; the short form lives in the skill body.

## 1. Verify artifacts before any board write or user claim

`ls` the claimed output files. `git log --oneline` for claimed commits. Run the test suite with the lane's own interpreter, not whatever `python` is on PATH. Only then complete the card. On Hermes the flag is `--result`: `hermes kanban --board <b> complete <t_id> --result "<what landed>"`. There is no `--note`, and `done` is not a subcommand.

## 2. Success claims with a missing deliverable

A child can report success while its deliverable failed at the final save, typically when a file tool rejects non-string content (a list or dict passed where text was expected) and the child does not notice. Always check the declared output path after a completion. When the file is missing, re-dispatch a leaner child whose context points at the completed sibling artifacts (read and extend, do not re-research) and that carries the "serialize to a string before writing" rule.

The opposite false alarm exists too. A runtime may flag a child's first failed write even when the child recovered through a fallback and the file is present and complete. Parse the file (count entries, check the schema) before treating any failure flag as ground truth and re-dispatching.

## 3. Ground-truth inherited expectations

A child inherits expectations from prior labels (a vision model's read of a screenshot, an LLM classification, a note from an earlier session). Those can be wrong. Before baking an expectation into a test or a card, grep the actual fixture, page or output for the expected signature. If the raw bytes contradict the label, change the expectation to match the bytes. Never add a signature that a real input cannot match, and prefer one distinctive token over a phrase whose exact order might differ.

## 4. TRUNCATED is partial progress

A child that hit its iteration cap returns truncated with real work behind it. Read the transcript tail for its own diagnosis and `git status` for its uncommitted work. Then either finish the small remainder yourself or re-dispatch with the diagnosis and the WIP state inlined as context. Never respawn from zero, never discard the WIP.

## 5. Died at the final write

A child that dies at the write step has usually done the work. Check its declared output path first. If the file is missing, reconstruct from the live transcript: the reasoning and assistant lines hold interim conclusions and the tool lines show what was verified. A child that wrote "all checks verified, writing now" left a verdict trail. Write the reconstructed result yourself, labeled as reconstructed, instead of rerunning the lane and repeating thirty minutes of verified work.

## 6. Read the dead child's transcript before re-probing its wall

When a child timed out against an environmental wall (an API that ignores filters, a page gated behind scripts), its transcript already holds the probe attempts and their results. Re-hitting the same wall from the coordinator repeats the failure. If the transcript shows the same failure from two independent angles, the wall is structural: document it in the deliverable with the evidence and hand the user the manual path. Do not dispatch another child to die on it.

## 7. Backfill freed slots immediately

When a child finishes, dispatch the next ready (or just-unblocked) task onto that slot in the same turn. Whoever watches slot utilization reads an idle slot as stalling.

## 8. Review children pair with fix children

A read-only review child produces a numbered findings list. That list plus any uncommitted WIP becomes the fix child's context, one finding per item, so the fix child does not re-derive the diagnosis.

## 9. Verify commits before claiming completion

A child reporting a commit hash can be wrong without knowing it (a shared index conflict, a hook rejection). `git show <hash>` it. When the hash does not resolve, check the working tree: the edit usually landed even though the commit failed, and committing it yourself is cheaper than re-dispatching the lane.

## 10. Sensitive-data lanes

When a lane's material includes credentials, personal records, or anything that must stay in its store, the child does not need to hold it. Write the goal as a generic tool description, lock the data read-only, require a written findings document, and forbid code edits and commits. The child then does judgment work (policy gaps, parser robustness, config hygiene) without the specifics ever entering its context or its report.

## 11. Reconstructed results are labeled

Any result you assemble from a transcript rather than from the child's own output carries the word "reconstructed" in the card, the report and the commit message. The next reader must know which verdicts were observed and which were inferred.
