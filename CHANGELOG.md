# Changelog

## v0.2.0 (2026-10-21)

- New **windows-agent-survival** plugin with two skills:
  - `git-bash-on-windows`: the top traps for agents on Windows (MSYS path rewriting, `cd /d`, backslashes eaten in heredocs, CRLF rewrites, PowerShell 5.1 vs 7, killing by captured PID, background jobs, retry loops, Npcap notes), each with symptom, cause and fix. Path behaviors verified live on Windows 11.
  - `everything-search`: file search with voidtools Everything's `es.exe`, its silent-failure traps (missing `-instance`, `-p` vs `-path`, `a | b` vs `a|b`), and `es_find.py`, a wrapper that runs a positive control before the real query.

## v0.1.0 (2026-10-21)

First release.

- **agent-verification-kit** plugin with four skills:
  - `evidence-ladder`: verify by effect, never by proxy. Evidence levels, a catalogue of proxy traps, and three probe scripts (`http-evidence.py`, `llm-smoke.py`, `hook-pipe-test.py`).
  - `measure-before-you-quote`: seven measurement recipes, KV-cache and VRAM math, cost per unit of work, four Python scripts and one PowerShell script; `rate_window.py` and `block_bootstrap.py` have `--demo` modes that need no infrastructure.
  - `artifact-review`: check a plan or handoff against the live system, with a per-claim verification checklist.
  - `api-verification`: get evidence for a library's installed API before calling it, and gate remote writes.
