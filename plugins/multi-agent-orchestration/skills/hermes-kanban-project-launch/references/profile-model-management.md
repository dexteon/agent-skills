# Profile and model management for kanban projects

Commands checked against Hermes 0.21.3. Model names are placeholders; your fleet is your own.

## Switching a profile's model

```bash
hermes -p <profile> config set model.default <model-name>
hermes -p <profile> config set model.provider <provider>      # when the model lives on another backend
hermes profile show <profile>                                 # the Model line must reflect the change
```

`-p/--profile` is a global flag parsed before the subcommand, so it goes right after `hermes`. `hermes -p <profile> model <model>` is not a valid form: `hermes model` is an interactive picker with no positional argument and errors with "unrecognized arguments".

Per-task overrides without touching the profile: `hermes kanban --board <b> set-model <t_id> <model> --provider <provider>`, or `--model`/`--provider` on `create`. Verify with `show <t_id>`: the `model:` line must show the override before you dispatch. `list --json` does not surface `model_override`; the DB column of that name does (see the field-notes skill).

## Credential pools

Hermes keeps a multi-key pool per provider. Each entry tracks status (ok or exhausted), request count, priority and source. When one key hits a rate limit, Hermes marks it exhausted and rotates to the next.

```bash
hermes auth list                       # all providers
hermes auth list <provider>            # one provider
hermes auth add <provider> --type api-key --label "<label>"   # prompts for the key; --api-key <value> also works
hermes auth reset <provider>           # clear exhausted status
hermes config set credential_pool_strategies.<provider> round_robin
```

Strategies are `fill_first` (default: burn one key until exhausted, then the next) and `round_robin` (rotate on every request). For free-tier providers with per-key rate limits, `round_robin` spreads the load.

## Model tiers for a board

| Task type | Tier | Why |
|---|---|---|
| Implementation | a stable local or paid model | no rate limits mid-task; a crash mid-edit poisons the next run |
| Research, RAG | free tier or local | free tiers crash under load; switch to local when they bottleneck |
| LLM integration | the model the task integrates | match the target |
| Safety review | high-reasoning model, no rate-limit risk | a review that dies halfway passes nothing |
| Testing, docs | any local model | methodical work, no exotic capability needed |

When a free tier bottlenecks, switch the assignee profile (first block above) and the remaining incomplete cards (`set-model`). Leave the `default` profile alone unless told; it is usually not what the boards run on.

## Context window reported by a proxy

When Hermes routes through an OpenAI-compatible proxy, the context window can be set in more than one place, and they must agree:

1. **Hermes `model_overrides`** in `config.yaml` (fields include `context_window`): a hard override that wins over what the proxy reports. Check your version's `config.yaml.example` for the exact key path under `model_overrides` before setting it.
2. **The proxy's own model metadata** (for LiteLLM: `model_info.max_input_tokens` and `max_output_tokens` on the route, in YAML or in its database for routes created through the admin UI).

The trap: the proxy caches model metadata on open. After changing it, restart the proxy and verify through its API:

```bash
curl -s -H "Authorization: Bearer $PROXY_KEY" http://<proxy-host>:<port>/v1/models | \
  python -c "import sys,json; [print(m['id'], m.get('max_input_tokens')) for m in json.load(sys.stdin)['data']]"
```

A running proxy is not evidence of fresh metadata. A stale one answers from cache with no error.
