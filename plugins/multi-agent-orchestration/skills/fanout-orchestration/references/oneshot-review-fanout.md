# One-shot review fan-out (no subagent slots consumed)

For multi-model review of a document set (mixture-of-agents critique, plan validation), independent one-shot runs are lighter than runtime subagents: no board, no write fence, no concurrency cap, and each reviewer is a separate process you can background.

## Procedure

1. **Build prompt files first.** Each file holds a shared CONTEXT block (product, constraints, corrections already known), one review angle (strategy, compliance, technical), a strict output format, and the full document text inlined. A format that has worked:

   ```
   TOP 5 PROBLEMS / FACTUAL ERRORS / MISSING / NONSENSE DETECTOR / KEEP / VERDICT
   ```

   Inline the documents rather than pointing at paths. One-shot reviewers sometimes narrate about files instead of reading them.

2. **Pick models that will answer.** A model name that resolves on one provider can fail instantly on another with HTTP 402 "Insufficient credits" and no warning beforehand. List the gateway's live models (its `/v1/models` endpoint) before choosing, and run one cheap call per model first.

3. **Isolate the run from user config.** User config can carry a toolset or plugin the CLI build rejects, and the run then exits immediately with an empty output file. Use the runtime's isolation flag.

4. **Launch all reviewers in one background shell**, each redirecting to its own output file, append a completion marker per reviewer (`echo DONE >> review-status.txt`), then poll the files. Do not wait on any single process.

5. **Treat findings as leads, not verdicts.** Reviewers assert wrong platform policies with confidence. Verify each factual claim against live sources before editing the document. Fix the points where all reviewers converge, with your own verified research.

## Runtime forms

Hermes (checked on 0.21.3):

```bash
hermes chat -Q --oneshot --query-file review-strategy.md --model <model> --provider <provider> --ignore-user-config > out-strategy.md 2>&1; echo DONE >> review-status.txt
```

`-Q` suppresses banner, spinner and tool previews; `--oneshot` answers and exits; `--query-file` reads the prompt from a file (or pass `-q "<text>"`); `--ignore-user-config` drops `config.yaml` so a rejected toolset cannot abort the run (a symptom of that is the line `Warning: Unknown toolsets: ...` followed by an empty output file).

Claude Code:

```bash
claude -p "$(cat review-strategy.md)" --model <model> > out-strategy.md 2>&1; echo DONE >> review-status.txt
```

`-p` is the non-interactive print mode. Any other CLI with a one-shot mode works the same way; the procedure does not depend on the runtime.
