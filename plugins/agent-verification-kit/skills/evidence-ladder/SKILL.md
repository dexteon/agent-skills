---
name: evidence-ladder
description: "What counts as proof that something works, and how to get it. Load this before saying \"done\", \"fixed\", \"verified\", \"healthy\", \"it works\" or \"it does not exist\", whenever someone asks \"is it working?\", \"can you verify that?\", \"smoke test it\", \"did it run?\", or when the only evidence so far is a 200, an exit code 0, a green health check, an empty grep, a model listing, a clean build, or a subagent's summary. Also load it before writing a new smoke test, load test, hook test or acceptance check."
license: MIT
version: 0.1.0
---
# Evidence ladder: verify by effect, never by proxy

A **proxy** is a cheap signal that usually travels with "it works" but does not prove it: an HTTP 200, exit code 0, an empty grep, a green `/health`, a tool listing, a compile that passed, a report that says so. Every one of these has said "works" while the real thing was broken. The rule of this skill:

> Verify by effect, at the level the claim needs, and say which level you reached.

## Terms

- **Evidence level (L0 to L4)**: how close a check gets to the real work. See the ladder.
- **Nonce**: a random token you put in a request that the reply must echo back. It proves this request was answered now, not served from a cache.
- **Sentinel**: a marker a remote shell prints before your command runs. Seeing it proves a shell actually ran.
- **Pipe-test**: feeding a synthetic payload into a hook or filter on stdin and reading the JSON it prints.
- **Positive control**: a probe for something you know is there. It proves the search can find things before you trust an empty result.
- **Stamp-on-change**: a freshness date written only when the watched input actually changed, never just because a step exited 0.

## The ladder

| Level | What you observed | It proves | Enough for |
|---|---|---|---|
| L0 | A doc, memory, index, summary or agent report says so | Someone claimed it | Nothing. It tells you where to look |
| L1 | A process exists, a port listens, a container is "Up" | Something is running | "It is running" |
| L2 | The protocol answers: 200, `/health` ok, `tools/list`, PONG, exit 0 | The front door opens | "It responds". Never "it works" |
| L3 | The shipped entrypoint did real work and you checked the value: the body holds the field, the nonce came back, the row exists, the unauthenticated client was refused | It works for this input | "Done", "fixed", "verified" |
| L4 | L3 at real size, real concurrency, held for a sustained window | It works under the real load | Capacity, throughput, "it scales", picking a worker count |

Report the level in words. "The gateway answers `/health` (L2); the tools are not verified" is a correct report. "The gateway is up" is not: a real gateway returned `{"status":"ok"}` while every proxied tool behind it failed on a real call, because the upstream registrations pointed at a dead address.

### Absence claims

"X does not exist" or "zero references" needs a completed search plus a positive control:

1. Confirm the search process finished. Check its own exit status, not the size of its output file. A backgrounded recursive grep that was killed mid-walk writes an empty file, and an empty file reads as "zero matches".
2. Run the same search for a token you know is present and see it found.
3. Confirm the tool covers the place you searched. Filename indexes skip drives, `find` does not cross some junctions and mounts, and an exact-path check misses a folder with a space in its name.

### Classifiers default to UNKNOWN

Any code that maps tool output to a verdict must list the known-good and known-bad strings explicitly. The fallback branch prints `UNKNOWN` plus the raw output, never success. A `case` statement once printed "config opened OK" for a "wrong password" reply because the catch-all defaulted to success. Every script in this skill follows the rule and exits 0 PASS, 1 FAIL, 2 UNKNOWN.

## Proxy traps, short form

The full catalogue of incidents is in `references/proxy-traps.md`. Read it once.

| Proxy | Why it lies | Real check |
|---|---|---|
| HTTP 200 | Error bodies ship under 200 (`{"error":{"code":400}}`, MCP `isError: true`) | `scripts/http-evidence.py <url> --expect <text>` |
| `/health`, `tools/list`, "healthy" | Never touches the upstream or its credential | One real call, assert `isError` is false, read the result |
| PONG or a tiny prompt | Passes while real-size requests fail on a memory cap | A request at the real size |
| Exit 0 | Pipes report the last command; SSH check modes, hook runners and wrappers exit 0 on failure by design | Read the output for a value or sentinel; `${PIPESTATUS[0]}` |
| 200 from an LLM gateway | A cache hit, a fallback model, or null content from a reasoning model | `scripts/llm-smoke.py` (no-cache, nonce, no fallbacks) |
| An empty grep or search | Killed search, unindexed location, path not walked | Positive control plus the process's own exit status |
| A model listing | Listed is not working: billing 402, blocked 403, rate-limited 429 all night | A real no-cache call per model group |
| A clean build | Compiles is not runs is not correct | Run the shipped artifact on a real input |
| A subagent's summary | The report can claim things the artifact lacks | Read the artifact |
| A burst benchmark | Measures the burst allowance, not the sustained rate | 150 s or more of continuous load |

## Recipes

### 1. HTTP endpoint

```bash
python scripts/http-evidence.py "$API_URL/api/items" --expect '"items"'
python scripts/http-evidence.py "$API_URL/private" --expect-status 401
python scripts/http-evidence.py "$PUBLIC_URL/" --expect-redirect login
python scripts/http-evidence.py "$API_URL/me" --header-env AUTH_HEADER --expect '"user"'
```

Without `--expect`, `--expect-status` or `--expect-redirect`, the script can only say UNKNOWN. That is on purpose: a 2xx with no asserted content proves nothing. A redirect to a login page is the correct healthy answer for an unauthenticated client on a gated site, so assert on it instead of calling it a failure. `--header-env` reads the header value from an environment variable and never prints it.

### 2. LLM gateway or model group

Gateways cache. One answered the same prompt twice in 0.41 s and then 0.027 s, with the same response id and a cache-key header. Every proof call needs all four:

- a cache bypass in the request body (`"cache": {"no-cache": true}` on OpenAI-compatible gateways that support it)
- a fresh nonce in the prompt, which must appear in `choices[0].message.content`
- fallbacks disabled, so a dead primary cannot hide behind its fallback
- `max_tokens` of 400 or more: with `max_tokens 16` a reasoning model returned 200, `finish_reason=length` and `content: null`, because all 16 tokens went to reasoning

```bash
export GATEWAY_URL=http://127.0.0.1:4000
python scripts/llm-smoke.py --model my-group --key-env MY_GATEWAY_KEY
python scripts/llm-smoke.py --model my-group --key-env MY_GATEWAY_KEY --max-tokens 16   # expect FAIL NO-ECHO on a reasoning model
```

Expected: `PASS (1/1 calls proven by nonce echo, no cache)`. Never use `/v1/models` as proof that a tier works.

### 3. MCP server

L2 is `tools/list` or the gateway's health page. L3 is one real `tools/call` per upstream that touches its credential or backend, with `isError` false and a non-empty result you read. In an agent session the simplest L3 is to call the tool itself with a harmless read-only argument.

### 4. Remote command

Never gate on the SSH exit code. One SSH check mode held the connection for a browser approval for two minutes, ran nothing, and exited 0.

```bash
out=$(ssh "$HOST" 'echo __ok_sentinel__; uptime')
case "$out" in *__ok_sentinel__*) echo "ran: $out";; *) echo "UNKNOWN: no sentinel, nothing ran";; esac
```

### 5. Hooks and filters: pipe-test and read the JSON

Hook runners usually fail open: every entry point exits 0, and a rule with a broken regex is reported on stderr and then treated as "no match". The JSON on stdout is the only evidence a rule is alive.

```bash
python scripts/hook-pipe-test.py --hook ~/.claude/hooks/pre.py --tool Bash --command "ls -la" --expect none
python scripts/hook-pipe-test.py --hook ~/.claude/hooks/pre.py --tool Bash --command "rm -rf /" --expect deny
python scripts/hook-pipe-test.py --hook ~/.claude/hooks/prompt.py --prompt "some text" --expect warn
```

Every new or changed rule needs one positive test (it fires) and one negative (a harmless near-miss stays silent). A block rule also needs a read-only near-miss, because block false positives stop read-only work. If the hook also inspects the command line of the tool call running your test, put the test text in a file and pass `--command-file`.

### 6. Sustained load (L4)

Before you choose a worker count, slot count or concurrency setting, or claim "handles N agents":

1. Stop competing work on the same resource, or the control arm is wrong. A live job sharing the link once produced a fake 3.3x win.
2. Use real inputs at real size. Repeated synthetic text tokenizes cheaply and hits caches. An 8-way test at 5k context hid a 3 to 4x slowdown at 100k to 175k.
3. Hold continuous load for at least 150 s. One volley of 16 workers measured 45.9 units/s; sustained, 12 workers timed out and throughput fell to 2.7/s.
4. Sweep concurrency upward (2, 4, 6) and stop at the first level where errors appear or throughput stops rising.
5. Test the shipped code path. A probe with a bare client passed while the shipped code, which shared one session across threads, hung.
6. Pass only when every call is proven (nonce echoed, no cache). Report p50, p95 and the window.

```bash
python scripts/llm-smoke.py --model my-group --key-env MY_GATEWAY_KEY --concurrency 4 --duration 150
```

## Acceptance thresholds

| Claim | Minimum evidence |
|---|---|
| "Done", "fixed", "works" | L3 through the shipped entrypoint, run verbatim from a clean shell, plus one negative test when auth, paths or secrets are involved |
| "Model group X works" | `llm-smoke.py` PASS: 200, nonce echoed, no cache header, fallbacks disabled |
| "Gateway healthy after a change" | Every group that passed before still passes; any new FAIL explained |
| "MCP server works" | One real `tools/call` per upstream, `isError` false, non-empty result |
| "Endpoint works" | `http-evidence.py` PASS with an `--expect` that only the working thing returns |
| "Hook rule live" | Positive and negative pipe-tests PASS |
| "Handles N concurrent" | 100% proven calls over 150 s or more at N workers, real-size inputs, p95 reported |
| "Not present" | Completed search, a positive control found, coverage of the searched location confirmed |
| "Remote command ran" | Sentinel seen in the output |
| "Data is fresh" | The watched input's hash changed since the last stamp, not just a successful exit |
| Any rate, % or ETA | A stated window of at least one full work cycle or about 5 samples |

## How to add a check

1. **Name the failure it catches.** One sentence of the form "this fails when X, which proxy Y would miss". If you cannot write it, the check is ceremony.
2. **Pick the home.** A pattern in commands an agent types: a hook rule, pipe-tested. A service that can break while health stays green: an L3 probe in your fleet check. A data tile that can go stale: a stamp-on-change producer. A repeatable acceptance test for one component: a read-only script beside it.
3. **Make it fail first.** Run it against a known-bad case and watch it say FAIL. If you have never seen it fail, you do not know that it can.
4. **Default to UNKNOWN.** Enumerate good and bad outputs; everything else is UNKNOWN with the raw text attached.
5. **No side effects.** A check must not restart anything, write config, load a GPU, or spend a paid quota. Free-tier calls are fine when stated.
6. **Record it** next to the thing it checks, with the command and its expected output.

## Reporting evidence

- State the level: "verified (L3): `llm-smoke.py --model my-group` PASS 1/1".
- Quote the command and the decisive output line, not a paraphrase.
- Put caveats beside the headline. Never write "built and verified" above a line that says "not run".
- When a check could not run, say "not verified" and why. Never upgrade a claim to fill the gap.

---
Part of [agent-skills](https://github.com/dexteon/agent-skills) by [CyberAutomations](https://cyberautomations.com).
