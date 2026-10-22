# Claude Code skills that stop AI agents from faking success

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-d97757.svg)](#install)
[![Release](https://img.shields.io/github/v/release/dexteon/agent-skills)](https://github.com/dexteon/agent-skills/releases)

**agent-skills** is a Claude Code plugin marketplace of field-tested skills for AI coding agents. They also work with any agent that loads `SKILL.md` folders, such as Hermes. Every skill came out of a real failure in daily agent work and teaches the agent the habit that would have caught it.

Built and maintained by [CyberAutomations](https://cyberautomations.com).

## Why these exist

Agents are confident by default. These are the kinds of mistakes the skills catch:

- **A cached answer passed as a live one.** An LLM gateway smoke test "passed" in 0.027 s. The first call took 0.41 s and the second returned the same response id: it came from a response cache, so nothing was tested.
- **A 200 with nothing in it.** A reasoning model returned HTTP 200 with `content: null` because every one of its 16 output tokens went to reasoning.
- **A speedup that was not real.** A "3.3x faster" result showed zero change in production. The control run had shared its network link with a live job.
- **A plan that named the wrong file.** The plan said to edit `src/rules.py`. The loader imports `src/core/rules.py`. The change would have done nothing and every test would still pass.
- **A model that "fit" in VRAM.** The first deploy ran out of memory by 166 MiB. The estimate reused a safety margin from a different model; measured use per slot was 10,214 MiB against 8.3 to 8.7 GiB on paper.

## Plugins

### agent-verification-kit

Verification, measurement and review habits for Claude Code and other AI agents.

| Skill | What it does | Loads when you say |
|---|---|---|
| [evidence-ladder](plugins/agent-verification-kit/skills/evidence-ladder/SKILL.md) | Verify by effect, never by proxy. Named evidence levels, a catalogue of proxy traps, and probe scripts for HTTP endpoints, LLM gateways and Claude Code hooks. | "is it working", "verify that", "smoke test it", "it returned 200" |
| [measure-before-you-quote](plugins/agent-verification-kit/skills/measure-before-you-quote/SKILL.md) | Measure before stating a number: VRAM and KV-cache math, cost per unit of work instead of per hour, measurement windows, and a baseline before calling a difference real. | "how much VRAM", "will it fit", "is X faster", "what does this cost" |
| [artifact-review](plugins/agent-verification-kit/skills/artifact-review/SKILL.md) | Check a plan, report or handoff against the live system before anyone acts on it, then fix the wrong sentences in place. | "review this plan", "check the handoff" |
| [api-verification](plugins/agent-verification-kit/skills/api-verification/SKILL.md) | Get evidence for a library's installed API before changing calls into it, and require approval before remote writes. | a `TypeError` or `ImportError` from a library, "plan only" |

### windows-agent-survival

For agents running shell commands on Windows, where Git Bash and PowerShell make commands look successful while they quietly do the wrong thing.

| Skill | What it does | Loads when you say |
|---|---|---|
| [git-bash-on-windows](plugins/windows-agent-survival/skills/git-bash-on-windows/SKILL.md) | The top traps with symptom, cause and fix: MSYS path rewriting, `cd /d`, backslashes eaten in heredocs, CRLF rewrites, `powershell` 5.1 vs `pwsh` 7, killing by captured PID, background jobs that die, and retry loops. | "Git Bash", "path mangling", "command not found", "process won't die" |
| [everything-search](plugins/windows-agent-survival/skills/everything-search/SKILL.md) | Find files by name in under a second with Everything's `es.exe` instead of a recursive walk, plus the flags that silently return nothing. Includes a wrapper that runs a positive control first. | "where is X", "find all *.ext", "biggest files under" |

## Install

### Claude Code plugin marketplace

```
/plugin marketplace add dexteon/agent-skills
/plugin install agent-verification-kit@dexteon-agent-skills
/plugin install windows-agent-survival@dexteon-agent-skills
```

### Any agent that reads SKILL.md folders

```bash
git clone https://github.com/dexteon/agent-skills
cp -r agent-skills/plugins/agent-verification-kit/skills/evidence-ladder ~/.claude/skills/
```

The scripts are plain Python 3 (one PowerShell) with no required dependencies. Each one supports `--help`.

## Contributing

Issues and pull requests are welcome. A good report includes the failure the skill should have caught, the command output that proved it, and the agent you were using.

## License

MIT. See [LICENSE](LICENSE). Release notes are in [CHANGELOG.md](CHANGELOG.md).

---

Want agent workflows like these built for your team? [CyberAutomations](https://cyberautomations.com) designs and runs AI automation for small businesses and creators.
