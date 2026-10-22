# agent-skills

Field-tested skills for Claude Code and other agents that load `SKILL.md` files (Hermes, and anything that follows the same format). Each one came out of a real failure: an agent said "done" on a 200, quoted a number it never measured, or executed a plan that named the wrong file.

Built and maintained by [CyberAutomations](https://cyberautomations.com).

## Plugins

### agent-verification-kit

Stop agents from reporting false success.

| Skill | What it does |
|---|---|
| [evidence-ladder](plugins/agent-verification-kit/skills/evidence-ladder/SKILL.md) | Verify by effect, never by proxy. Named evidence levels, a catalogue of proxy traps (a 200 from a cache, a fallback answering for a dead primary, a reasoning model returning empty content), and small probe scripts. |
| [measure-before-you-quote](plugins/agent-verification-kit/skills/measure-before-you-quote/SKILL.md) | Measure before stating a number: VRAM and KV-cache math, cost per unit of work instead of per hour, measurement windows, and a baseline before calling a difference real. |
| [artifact-review](plugins/agent-verification-kit/skills/artifact-review/SKILL.md) | Check a plan, report or handoff against the live system before anyone acts on it, then fix the wrong sentences in place. |
| [api-verification](plugins/agent-verification-kit/skills/api-verification/SKILL.md) | Get evidence for a library's installed API before changing calls into it, and gate remote writes behind approval. |

## Install

### Claude Code (plugin marketplace)

```
/plugin marketplace add dexteon/agent-skills
/plugin install agent-verification-kit@dexteon-agent-skills
```

### Any agent that reads SKILL.md folders

Copy a skill folder into your agent's skills directory, for example:

```bash
git clone https://github.com/dexteon/agent-skills
cp -r agent-skills/plugins/agent-verification-kit/skills/evidence-ladder ~/.claude/skills/
```

## Contributing

Issues and pull requests are welcome. A good report includes the failure the skill should have caught, the command output that proved it, and the agent you were using.

## License

MIT. See [LICENSE](LICENSE).

---

Need agent workflows like these built for your team? Visit [cyberautomations.com](https://cyberautomations.com).
