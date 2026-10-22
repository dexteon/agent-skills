---
name: hermes-bot-team
description: "Hermes only. Build a team of isolated Hermes profiles (one role, model, secrets tier and toolset each) and run them in parallel with delegate_task or a kanban board. Load when someone says \"build a team of bots\", \"add N more bots\", \"create agents for this project\", \"orchestrator and workers\", or asks why a new profile cannot use web search, a browser or any MCP. Covers what a new profile does and does not inherit, the delegation cap, secrets tiering, and the kanban flags that differ from what you would guess."
license: MIT
version: 0.1.0
---
# Hermes bot team: isolated profiles working one project

A bot team is a set of Hermes profiles that share a project but not each other's secrets. Each profile gets its own `SOUL.md` (role), model, `.env`, toolsets, MCP servers and preloaded skills, and lives at `~/.hermes/profiles/<name>/`. Bots run as parallel subagents through `delegate_task`, or pick cards off a kanban board through the gateway dispatcher. Commands below were checked against Hermes 0.21.3.

The two facts that cost people an afternoon: a new profile inherits almost nothing, and the parent's secrets must not flow into bots by default.

## Procedure

### 1. Inventory the parent

```bash
hermes profile list
hermes profile show <orchestrator-profile>
```

Read the parent's `config.yaml` for the model, toolsets and MCP servers it uses. Decide, per item, inherit or isolate (the secrets tiering table below).

### 2. Create the profiles

```bash
for name in scout analyst engineer reviewer reporter; do
  hermes profile create "$name" --description "<one sentence on what this profile is good at>"
done
```

`--description` matters: the kanban decomposer routes cards by description, not only by name. `--clone` copies `config.yaml`, `.env`, `SOUL.md` and skills from the active profile; use it only for a trusted bot that should start from the parent's setup, because it copies the parent's secrets.

### 3. Write SOUL.md per role

One file per profile: role, mission, which files it owns, working rules, project path. Short and imperative.

### 4. Set models per profile

```bash
hermes -p engineer config set model.default <model>
hermes -p engineer config set model.provider <provider>
hermes profile show engineer        # the Model line must reflect it
```

For a batch, patch each profile's `config.yaml` with a short YAML script. Model tiers by role are in [references/kanban-cli-cheatsheet.md](references/kanban-cli-cheatsheet.md) and the project-launch skill's `profile-model-management.md`.

### 5. Write each bot's `.env` (secrets tiering)

A new profile's `.env` is empty. Fill it with the shareable tier only.

| Tier | Examples | Bots get it? |
|---|---|---|
| Shareable | a free-tier model key, a per-bot virtual key minted on your LLM gateway, a local model base URL, a self-hosted search endpoint with no auth | yes |
| Orchestrator only | gateway master keys, messaging session tokens, mail OAuth, vault sessions, anything billed or personal | no |
| Never in any `.env` | production credentials with write access to money, mail or identity | use an external secret source |

Mint a scoped key per bot on the gateway when it supports it, so spend and abuse are attributable. For the orchestrator's own secrets, prefer `hermes secrets` (Bitwarden Secrets Manager or 1Password at process startup) over a long-lived session token pasted into `.env`. Never script a vault unlock from a plaintext password in the environment; it defeats the vault.

### 6. Configure toolsets, MCPs, plugins and skills

A new profile starts with the `hermes-cli` toolset only and no MCP servers. It cannot search the web, open a browser or call any external tool until you add them:

```python
config["toolsets"] = ["hermes-cli"]
config["platform_toolsets"] = {"cli": ["browser", "delegation", "file", "memory", "skills", "terminal", "todo", "web"]}
config["mcp_servers"] = {...}            # only the shareable ones
config["plugins"] = {"enabled": [...], "disabled": []}   # disabled is a deny-list that wins
```

Skills are per profile: they live under `~/.hermes/profiles/<name>/skills/` (copy the ones each role needs), and a card can force-load one with `hermes kanban create ... --skill <name>`. There is no preload list key in `config.yaml` on 0.21.3.

MCP servers safe to share are the ones that need no personal secret: a gateway MCP with a per-bot key, a self-hosted search server, a browser server without stored sessions, a public knowledge base. Anything that carries a user session (mail, chat, vault, a paid API key) stays on the orchestrator.

### 7. Write the team protocol file

In the project directory, a `TEAM_PROTOCOL.md` with the roster (bot, role, model, profile, MCPs), coordination protocol, domain ownership (which files each bot owns), shared files that need coordination, safety rules, and access levels (trusted vs sandboxed). If your project also has an `AGENTS.md`, keep the team roster separate from it; some setups protect `AGENTS.md` with a hook and a bot's write to it will be refused.

### 8. Raise the delegation cap

`delegation.max_concurrent_children` defaults to 10 on 0.21.x (3 on older builds). A `tasks` array longer than the cap is rejected whole.

```bash
hermes config get delegation
hermes config set delegation.max_concurrent_children 8
```

### 9. Dispatch in parallel

`delegate_task` with `tasks=[...]`, one entry per bot: `goal` (the first assignment, scoped to the role), `context` (project path, team structure, what to read first), `output_schema` (the return shape). Bots run as leaf subagents and cannot re-delegate. Results come back as a batch when all complete. Everything in the `fanout-orchestration` skill applies from here: budgets in goals, probe before the batch, verify every self-report.

### 10. Or route through a board

```bash
hermes kanban init
hermes kanban boards create <project-slug> --name "<Project>" --switch --default-workdir <project_dir>
hermes kanban --board <project-slug> create "Task title" --assignee engineer --priority 2 \
  --body "Description" --workspace "dir:<project_dir>"
hermes kanban --board <project-slug> link <parent_id> <child_id>
hermes gateway start
```

The dispatcher runs inside the gateway, ticks every 60 seconds, and spawns the assigned profile for each ready card. `hermes kanban --board <slug> dispatch` runs one pass now. Full flag list and the priority trap in [references/kanban-cli-cheatsheet.md](references/kanban-cli-cheatsheet.md). A new project with the same team is a new board; profiles persist.

## Pitfalls

- **New profiles inherit the model config but not toolsets, MCPs, plugins or `platform_toolsets`.** An unconfigured bot has the `hermes-cli` toolset and zero MCPs.
- **`delegate_task` caps at `delegation.max_concurrent_children`.** Raise it before dispatching more bots than the cap or the call is rejected.
- **Kanban `create` uses `--body`, not `--description`; `--priority` is an integer and a higher number dispatches first on 0.21.3.** Do not assume 1 means critical.
- **An unknown `--assignee` sits in `ready` forever.** The dispatcher does not autocorrect profile names. `hermes kanban --board <slug> assignees` lists what it knows.
- **Bot profiles are CLI and subagent profiles, not chat-platform bot accounts.** Do not create messaging bots unless asked; `--clone-channels` is the only thing that copies channel tokens, and it refuses when the source is served by a live multiplexed gateway.
- **Goal mode needs room.** For open-ended autonomous cards, `--goal --goal-max-turns 100` to `500`; the default budget of 20 turns ends most research cards early and blocks them for review.
- **Researcher bots want `reasoning_effort: high`** in their model config; workers do not.

## Checklist

1. `hermes profile list` shows every bot with the intended model.
2. Each bot's `.env` holds only shareable-tier keys, verified by reading the file, not by recalling what you wrote.
3. Each bot's `config.yaml` names its toolsets, `platform_toolsets`, MCPs and skills explicitly.
4. The delegation cap is at least the team size.
5. The team protocol file is in the project directory.
6. One real `delegate_task` or one dispatched card has returned a verified artifact before you report the team as working.

---
Part of [agent-skills](https://github.com/dexteon/agent-skills) by [CyberAutomations](https://cyberautomations.com).
