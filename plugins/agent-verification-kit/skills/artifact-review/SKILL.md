---
name: artifact-review
description: "Check a written artifact's claims against the live system before anyone acts on it. Load when asked to review a plan, report, spec, handoff or summary from another session or agent: \"review this plan\", \"is this handoff right\", \"check it before we integrate\", \"make sure the plan is sound\"."
license: MIT
version: 0.1.0
---
# Artifact review

A plan written by another session or agent reads as confident whether or not it is true. Before anyone executes it, check every concrete claim against the system it describes, fix what is wrong in place, and report the fixes.

This is not code review (that reviews a diff) and not planning (that writes the plan). It reviews a document's **factual claims** and **internal consistency**, so the person who acts on it does not edit the wrong file, run a broken command, or chase a target that cannot be reached.

## When to use

- Someone asks you to review, sanity-check or "make sound" a plan, report, spec, handoff or summary.
- The artifact is on disk and the next step depends on it being true.

Skip it for: reviewing a code diff, auditing a whole codebase, or a document no one will act on.

## Procedure

1. **Read the whole artifact.** List every concrete claim: file paths, line numbers, "X exists", "X does not exist", "already does Y", counts, sums, exit codes, git state, env vars, versions, URLs.
2. **Check each claim with a read-only command.** Do not trust the document. `references/verification-checklist.md` gives the check and the expected signal for each claim type. You are hunting wrong paths, impossible numbers and missing pieces, not re-deriving the author's reasoning.
3. **Check internal consistency.** Parts must add up to the stated total. A baseline and a target must be on the same scale. An expected count must be reachable from the input set. Flag anything arithmetically or logically impossible, even when no command disproves it.
4. **Fix the artifact in place.** Edit the exact sentence that is wrong. Write the corrected value and the reason it was wrong, so the next reader does not repeat the mistake. Replace the misleading sentence; never append "UPDATE: actually...". Add a short NOTE only where a wrong path has a plausible lookalike.
5. **Report.** One line per fix: what was wrong, the verified value, where it lives. List anything you left alone and why. Do not narrate every check you ran.

## Worked example

The plan says: "Add the new rule to `src/rules.py`; the loader already imports it."

```bash
ls src/rules.py src/core/rules.py          # both exist
grep -rn "import.*rules" src/loader.py     # from core import rules
```

The loader imports `src/core/rules.py`. The plan names the sibling file, which exists but is never loaded. A rule added there would do nothing and every test would still pass. Fix the sentence to: "Add the new rule to `src/core/rules.py` (the loader imports `core.rules`; `src/rules.py` is an unused older copy)."

## Pitfalls

- **A claim that looks true is the dangerous kind.** A wrong path with the right shape (a sibling file that exists but is not the one imported) misleads far more often than an obviously bogus one. Confirm which file a symbol is actually loaded from, not which file matches the name.
- **Existence claims need a direct check.** "No directory exists" and "the file already exists" are both common in plans. Run `ls` on the path instead of inferring from the narrative. A directory can exist and hold files while the plan assumes it is empty or absent.
- **Moved tools resolve paths differently.** A script that finds its data relative to its own location can behave differently after a copy or move, and fail with a misleading exit code (for example "no data" instead of the expected baseline). Run the copy from its new location and check the exit code before trusting the plan.
- **Impossible numbers pass every per-claim check.** "51 pass + 2 fail" on a 43-item corpus survives each individual check and is still wrong. Do the arithmetic against the stated input size yourself.
- **Do not verify with the mechanism the artifact assumes.** If the plan reasons from how a tool behaves, run the tool or read its source rather than trusting the plan's description of it.

## Done when

- Every concrete claim maps to a check you ran, and each check either matched or produced a fix.
- Every fix is a targeted edit of the wrong sentence, not a rewrite of the document.
- The corrected artifact has no wrong or unreachable path, existence, version or arithmetic claim.

---
Part of [agent-skills](https://github.com/dexteon/agent-skills) by [CyberAutomations](https://cyberautomations.com).
