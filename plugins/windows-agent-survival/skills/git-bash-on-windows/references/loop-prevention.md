# Stop retrying a failing tool

When a tool returns the same failure across repeated calls, retrying it again (or firing
several copies in parallel) spends tokens and hides the real cause. It also turns a
setup problem into a wall of near-identical error output that is hard to read back.

## The rule

1. One failing attempt: investigate the cause, fix the setup state, retry once.
2. Two or more failing attempts, especially after a human correction ("stop using X,
   use Y"): stop firing that tool immediately. It is malfunctioning, not "needs another
   try."
3. Switch to a working engine, or fix the broken setup, then continue.
4. If a guardrail or the harness halts a repeated identical call, treat that halt as the
   correction. Do not repeat the identical call. A long streak of identical failures is
   the ceiling, not a target.

## Probe before a batch

Before running the same operation across many inputs, run it once on a single cheap
input and confirm it actually worked (check the artifact, not just the exit code). Only
then fan out. A batch built on an untested call multiplies one silent failure into many.

## This is a preference, not a permanent verdict

A tool that is broken now may recover when its setup changes (a driver reinstalled, a
dependency fixed, a path corrected). "Stop firing it" means stop for this run, not
"declare it dead forever." When the setup changes, re-probe once.

## Verify the identifier before wiring it in

A repeated failure is sometimes a single wrong name: a misspelled import, a wrong case
in a module name, a target string with the wrong capitalization. Confirm the exact
identifier with one cheap probe before building it into a larger script:

```bash
python -c "import some_module; print('ok')"
```

One correct name confirmed up front beats a dozen repeated failures that look like
environment bugs but are plain typos.
