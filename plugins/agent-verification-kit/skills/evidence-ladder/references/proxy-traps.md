# Proxy-evidence traps: the incident catalogue

Every row is a time a cheap signal said "works" (or "absent") and the truth was the opposite. All of them happened on real systems; names, hosts and dates are stripped, the numbers are kept. Read the row before you trust that kind of signal again.

The pattern is always the same: the proxy measures the front door, the failure is behind it. The fix is always the same too: make the thing do one unit of real work and read the value it produces.

## HTTP status and health endpoints

| Proxy said | Truth | The real check |
|---|---|---|
| A map-tile feature service URL returned 200 | The body was `{"error":{"code":400,"message":"Invalid URL"}}`. A delegated team then spent a day finding the real endpoint | Read the body. `scripts/http-evidence.py <url> --expect <field>` flags a JSON `error` key under a 200 |
| An MCP gateway's `GET /health` returned 200 `{"status":"ok"}` | Every proxied upstream failed on a real call: one with "fetch failed", one with "dial tcp 192.0.2.10:8787: no route to host". The upstream registrations still pointed at an address that had been retired weeks earlier | One real `tools/call` per upstream; assert on the result, not on the gateway |
| An LLM gateway listed an email MCP server as `healthy` with all 19 tools present | Every call returned `unauthorized_client`. Health and `tools/list` never touch the upstream credential | One `tools/call` that exercises the credential; assert `isError` is false |
| A local inference server answered PONG | Worker-sized prompts (about 30k tokens) failed with a backpressure error from the accelerator's memory cap | A request at the real size, streamed |
| A gated site "returns something" | For an unauthenticated client the healthy answer is a 302 to the identity provider's login. A page that "Failed to fetch" in the browser was an expired session, not an outage | `http-evidence.py <url> --expect-redirect <login host>`; run app checks against the origin, not through the gate |

## Exit codes

| Proxy said | Truth | The real check |
|---|---|---|
| A server launcher exited 0, the port listened, the process was healthy | The shipped launch script had started the server with authentication disabled, because a path variable was empty inside a `param()` default | Run the shipped command verbatim, then a negative test: an unauthenticated client must be refused |
| SSH to a remote host exited 0 | The connection was held for a browser approval for two minutes and no command ran | Echo a sentinel and look for it in the output |
| A nightly refresh's steps all exited 0 and stamped "fresh" | Four steps re-rendered frozen input; the dashboard claimed "today" on 9-day-old data | Stamp only when the watched input's hash changed since the last stamp |
| `cmd 2>&1 \| tail` exited 0 | That is `tail`'s exit code; `cmd` had crashed | `cmd > log 2>&1; echo "exit=$?"` or `${PIPESTATUS[0]}` |
| A sync script printed "pushed / Done" | The push had failed; the script forced the exit code to 0 before printing | Compare `git ls-remote origin` with the local HEAD |
| A hook runner's every entry point exits 0 | By design (fail open). A rule with a bad regex printed to stderr and counted as "no match", so a rule could be dead for weeks | Pipe-test and read the printed JSON verdict: `scripts/hook-pipe-test.py` |
| A workflow engine returned 200 and "execution success" for a webhook | The webhook node had no outgoing connection; nothing ran | Dump the execution's run data and check that the nodes you expect actually appear |

## Empty results and negatives

| Proxy said | Truth | The real check |
|---|---|---|
| A backgrounded recursive grep wrote an empty file: "zero references to module X" | The search was killed mid-walk; two such modules existed | Check the search process's own exit status, and probe for a token you know is present |
| An exact-path check found no such application | It was installed under a folder with a space in its name | Glob with wildcards; on an indexed filesystem query the index, after a positive control |
| A filename index returned nothing for a whole drive | That drive was not in the index | Positive control first; a scoped walk when the index does not cover the location |
| `find` over a folder returned nothing | The folder was a junction the shell's `find` does not traverse | Walk the real path, or use the platform's native tool |
| A grep for the known-bad strings was clean | The same fabricated claims were still there in other words | Grep the number or identifier, then read the document against the source |
| An index said a packet held no such document | Pages 1 to 7 were the document | Open the pages. Render scanned PDFs and read them |
| A `page=N` scrape saved 450 rows | 30 unique rows; the route ignored `page=` and returned page 1 every time | Check id uniqueness on any paginated pull |

## Caches and fallbacks (LLM gateways)

| Proxy said | Truth | The real check |
|---|---|---|
| A smoke test passed in 0.0 s | The gateway answered from its response cache: the same prompt twice came back in 0.41 s and then 0.027 s, same response id, with a cache-key header on the second | Body `"cache": {"no-cache": true}` plus a nonce the reply must echo; reject any reply carrying a cache-key header |
| A model group answered 200 | A fallback model answered for a dead primary | `"disable_fallbacks": true` (or the equivalent on your gateway) |
| 200 from a reasoning model | `content` was null. With `max_tokens 16` the reply had `finish_reason=length`, `reasoning_tokens=16` and no text, because the whole budget went to thinking | Give 400+ tokens and assert on the content (nonce echo) |
| `/v1/models` lists the model | Listed is not working: one key returned 402 (billing), one 403 ("API blocked"), one 429 for an entire night | A real no-cache call per group |
| A vision model returned 200 | Empty reply because `format: json` had been set on a vision request the backend could not fill | Assert on content |

## Measurement and parsing

| Proxy said | Truth | The real check |
|---|---|---|
| A classifier `case` printed "config opened OK" | The tool had said "Incorrect password", an outcome the script never enumerated; the catch-all defaulted to success | Enumerate good and bad strings; the fallback is UNKNOWN and prints the raw output |
| `grep -c $'\r'` reported 219 | The file had zero CR bytes (that grep counts lines, and the pattern matched every line) | `tr -cd '\r' \| wc -c` |
| 16 workers did 45.9 units/s in one volley | Sustained, 12 workers timed out and throughput fell to 2.7/s | Continuous load for 150 s or more |
| A concurrency probe passed | The probe used a bare client per call; the shipped code shared one HTTP session across threads and hung | Test the shipped code path, not a re-implementation |
| An 8-way test at 5k context said the accelerator was fine | At the real 100k to 175k context it was 3 to 4x slower | Deep AND concurrent, at the depth you actually run |
| A quick Python probe "verified" a parser written in another language | It was a separate implementation; a wrong key in the shipped parser would have passed | Run the shipped artifact |
| A clean build: "built and verified" | Compiles is not runs is not correct; four code paths had never executed | Say which of the three you actually have |
| A subagent's summary claimed the join key was present | It was missing from the data | Check the artifact, not the report |
| A live comparison showed a 3.3x win | Another job was saturating the same link during the control arm | Stop competing work before measuring, or the control is wrong |

## How to use this file

When a signal looks like a row in the first column, do the third column before you report. When you hit a new one, add a row: proxy, truth, real check. Keep the numbers; drop the names.
