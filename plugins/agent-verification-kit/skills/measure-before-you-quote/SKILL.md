---
name: measure-before-you-quote
description: "Measure before you quote a number. Load this before stating a rate, a utilization, an ETA, \"how much VRAM\", \"will it fit\", \"is X faster than Y\", \"what does this cost\", a capacity or slot projection, a benchmark result, or \"X caused Y\". It holds seven measurement recipes (real workload, stated window, matched null, KV-cache and VRAM math, cost per unit of work, container metrics, one-mechanism-explains-all), scripts that do the arithmetic, and anonymized incidents showing the size of each mistake."
license: MIT
version: 0.1.0
---
# Measure before you quote

The expensive mistakes in capacity, cost and performance work are rarely bad code. They are confident numbers taken from the wrong measurement: a 26 second window, a 32-token prompt, one `nvidia-smi` sample, a before/after pair with no control, a memory figure that included something that had already been unloaded. Each one looked authoritative, and someone planned around it.

Knowing the rules does not stop this. The mistakes happen when a number is already on screen and the correct measurement would take another 60 seconds, so the cheap number gets spoken. The checklist below is mechanical so that it works without judgement.

## When to load this

You are about to say a rate, a percentage, an ETA, a memory or slot projection, a cost comparison, a benchmark result, or "X caused Y". If the job is instead pass/fail acceptance, live-failure triage, or a health check, this skill is a supporting reference, not the driver.

## Terms

| Term | Meaning here |
|---|---|
| Slot | One concurrent sequence an inference server holds (`--parallel N` in llama.cpp). Each slot owns a share of the total context. |
| KV cache | The per-token key and value tensors kept for every slot. It is what grows with context. |
| Prefill / decode | Prefill processes the prompt (thousands of tok/s); decode generates output one token at a time. They compete for the same compute. |
| Hybrid model | Only every Nth layer (`full_attention_interval`) carries a growing KV cache; the others hold a small constant recurrent state. |
| Work cycle | The time for a pipeline to finish one full round, for example `WORKERS x BATCH` items. |
| Window | The time span a rate was measured over. Always stated with the number. |
| Control arm | The same measurement under identical conditions except the variable under test. |
| Matched null | What the statistic looks like when the effect is absent: same inputs, same window lengths, same regime, random timing. |
| Block bootstrap | Resampling contiguous runs of rows so overlapping observations are not counted as independent. |
| Cost per work | Money to finish a fixed job, as opposed to money per hour. |
| Time multiplier | How many times longer a candidate takes than a reference for the same work, measured at real depth (1.0 = reference). |

## The pre-quote checklist

Before any sentence that contains a rate, a utilization, an ETA, a memory projection, a cost or a causal claim:

- [ ] **Window stated?** Say it: "over 180 s, 6 intervals". If the window is shorter than one work cycle, or an oscillating gauge has fewer than about 5 samples, do not say the number. Say "measuring, N seconds" and go take it.
- [ ] **Real workload?** Real data, real size, real depth, real concurrency, competing work stopped.
- [ ] **Cumulative or instantaneous?** Decide which one you are quoting before you compute it.
- [ ] **Control or null?** For any "A differs from B" or "the signal works", the same-condition control arm exists and the interval excludes zero.
- [ ] **Components named?** For any memory figure, list what is inside it before projecting from it.
- [ ] **Every observation explained?** Including the things that did NOT break, and the size of each change.
- [ ] **Already wrong once?** If an earlier estimate for this job was wrong, say so plainly and withhold the next one until it survives a real measurement. Nobody objects to "I don't know yet"; they object to numbers that keep changing.

## Method 1: measure the real workload, not a micro-probe

1. Name the workload and its real size: prompt tokens, context depth, concurrency, file size, document mix.
2. Feed real inputs. Sample from the actual corpus, dump them to a file, and feed that same file to every arm of a comparison.
3. Sustain the load for at least 150 s. A single volley measures the burst allowance, not the sustained rate.
4. Stop competing work on the same resource, or the control arm is wrong.
5. For inference, trust the server's own per-request timings, discard at least 2 warm-up requests after a restart, then take repeats.
6. When the pipeline is far slower than its slowest component measured alone, the bottleneck is your own serialization, not the dependency.

Shapes of the mistake (full table in `references/vignettes.md` section 1): a 32-token prompt reported 43 tok/s prefill where a real 33k prompt did 3,700; a single-stream download test said "90 minutes" where a parallel pull took 4; a repeated synthetic sentence embedded at 26 to 30 chunks/s where real documents did 6 to 7; an 8-way test at 5k context rated a card at 87% of the reference where real 100k to 175k sessions ran 3 to 4x slower; a tiny PING health probe passed on a server that threw a memory backpressure error on every 30k-token request.

## Method 2: state the measurement window

1. Find the work cycle. A window shorter than one cycle catches a batch draining and misses the refill stall, so it is systematically optimistic.
2. Sample a durable progress counter (file size, a counter in a state file, a DB row count), not a log. Silence in a log reads as healthy; a counter that does not move is a stall.
3. Take at least 5 intervals for anything that oscillates (GPU util, CPU load, queue depth).
4. Report the window with the number, and say whether it is cumulative or instantaneous.
5. Treat "unchanged" as its own state. Stalled is not slow. Before calling a stall, rule out a counter that is only flushed less often than your interval.
6. Exclude idle. A rolling average that divides by wall-clock time including gaps between turns under-reports.
7. Never sum per-request rates across concurrent requests. Only total tokens divided by wall-clock elapsed is honest.
8. Billing is a rate too. Price a rented box from a credit delta over at least 10 minutes with nothing downloading.

```bash
python scripts/rate_window.py --demo --interval 0.5 --samples 13 --cycle-sec 1.5 --unit items   # no infrastructure needed
python scripts/rate_window.py --file ./downloads/model.bin --interval 10 --samples 7 --unit bytes
python scripts/rate_window.py --json-file ./state.json --key totals.done --interval 30 --samples 7 --cycle-sec 120 --unit chunks
```

The sampler prints every interval, flags stalls and resets, and refuses to call a number quotable when the window is shorter than a cycle, has fewer than 5 intervals, or contains unexplained zero-progress gaps. Vignettes: 59 chunks/s from a 26 s window where the sustained rate was 19.7 to 24.0; one GPU sample at 10% where six averaged 86%; two "identical" runs at 6.3 and 55.7 tok/s because the first paid CUDA init; a rate-limit proof that failed because six requests straddled a 10-minute bucket boundary.

## Method 3: build the null before asserting

1. Before saying "A differs from B", run the control arm: A against A and B against B under the same conditions. If the control shows the same "difference", there is no finding.
2. Before saying "the signal works" or "the signal is noise", define the matched null: same inputs, same window lengths, same regime, random timing. In a rising series every entry looks smart and every exit looks early; the null removes the drift.
3. Pair every point estimate with an interval. Where observations overlap in time, use a block bootstrap with the block set to the overlap, and report the effective independent n, not the row count.
4. Name the test that could falsify the claim, and run that one. A statistic that cannot come out the other way proves nothing.
5. Count the tests. Five horizons with three significant is a different claim from one pre-registered horizon. If the cut was chosen after seeing the data, label it hypothesis-generating.
6. For a before/after on a live system, re-enumerate the top consumers in both samples and confirm the delta belongs to the thing you touched (Method 6).
7. When a check overturns something already said, correct it plainly and keep the correction visible.

```bash
python scripts/block_bootstrap.py --demo                                   # plain vs block CI on synthetic overlapping data
python scripts/block_bootstrap.py --csv results.csv --col signal --null-col random --block 12
```

Vignettes: a symmetric outcome distribution over 167 events was called "a coin flip"; bootstrapped, the 95% CI was [-0.296, +0.271], which supports no verdict, and the right test (forward outcomes against matched random timings) found a real effect at one horizon and none at the horizon actually used. Two embedding vectors at 0.9998 cosine were called "different encodings"; with a control, all pairings measured 1.0000000000. A 4-bit vs 6-bit quantization comparison with a proper control showed 0.9877: a real 1.2% drift, which is why quantizations are never mixed in one collection.

## Method 4: KV cache, VRAM and unified-memory math

1. **Read the architecture, do not assume it.** From the GGUF header: `block_count`, `attention.head_count_kv`, `attention.key_length`, `attention.value_length`, `full_attention_interval` if present. A hybrid model carries KV on only `block_count // interval` layers. One 27B model was costed 4x too high by assuming all 64 layers carried KV when only 16 did.
2. **Compute the KV floor:** bytes per token = KV layers x 2 x KV heads x head_dim x bytes per element (f16 = 2, q8_0 = 34/32, q4_0 = 18/32). Per slot = that x context per slot.
3. **Measure two or more real configs** at different total context and fit `used = base + per_token x total_ctx`. The arithmetic is right about the KV and blind to compute buffers. Measured per-slot cost has run 15 to 25 percent above the floor.
4. **Size by total context, not slot count.** 2 x 262,144 and 4 x 131,072 measured 40,082 and 40,126 MiB. In llama.cpp `--ctx-size` is divided across `--parallel`.
5. **Keep at least 2 GiB free after load on CUDA.** cuBLAS allocates its workspace lazily on the first real matmul; a server that loaded with 561 MiB free printed READY and died on request one.
6. **Slots must cover concurrent callers plus auxiliary callers** (title generation, compaction). Fewer slots means LRU eviction and a full re-prefill: about context tokens divided by measured prefill tok/s.
7. **Memory headroom is not compute headroom.** After sizing by memory, measure per-stream decode with every slot busy and a concurrent prefill running. Three busy slots once showed 100% GPU with 31,861 MiB free and 0.57 tok/s per decoding stream.
8. **Name the components of any memory number** before projecting from it, and re-measure after each load or unload. A 47 GB unified-memory reading that blocked a config included 8 GB of a model that was no longer needed and idle buffers the OS later reclaimed; after unload it read 31 GB.

```bash
python scripts/kv_math.py kv --layers 64 --full-attn-interval 4 --kv-heads 4 --head-dim 256 --cache q4_0 --ctx 196608
python scripts/kv_math.py gguf ./model.gguf --cache q8_0 --ctx 262144 --slots 2     # a 16 MB head -c chunk of the file is enough
python scripts/kv_math.py fit --point 262144:29868 --point 524288:40082 --point 688128:46472 --predict 786432 --free 48402
python scripts/kv_math.py slots --free 48402 --base 19699 --per-token 0.03889 --ctx 262144
```

The measured fit tables, the OOM-by-166-MiB story, and the unified-memory traps are in `references/kv-cache-and-vram.md`.

## Method 5: cost per unit of work, not per hour

1. Pick a reference card and measure each candidate's time multiplier at the real depth and concurrency (Method 1). Headline speeds and shallow tests mislead.
2. Rank by job cost: `cost = $/hr x (work_hours x time_mult + setup_min/60) + download_GB x $/TB / 1000`.
3. Fold in setup: download time, plus a source build when no prebuilt binary matches the box's GPU architecture, CUDA major version and CPU features.
4. Fold in bandwidth. Inbound bandwidth price varies about 10,000x between hosts and the hourly rate excludes it; one 24 GB pull cost $1.118, six hours of that box's rental.
5. Filter the search query itself (whole card, compute capability, inbound bandwidth, rental duration, reliability; exclude mining SKUs), then verify on the created instance (card share, benchmark score, pre-flight download speed).
6. Renting spends money: state the burn rate and get an explicit go first, and restate it whenever the next step waits on a human.

```bash
python scripts/cost_per_work.py --work-hours 10 --offer "48GB workstation:0.537:1.0" --offer "24GB consumer:0.535:1.15" --offer "48GB two gens old:0.253:3.2" --offer "48GB one gen old:0.446:2.3"
```

That run reproduces the measured inversion: the two cheapest cards per hour ($0.253 and $0.446) were the two most expensive per job ($8.10 and $10.26) against $5.37 for the reference. Marketplace-specific filters and incidents are in `references/rented-gpu-cost.md` (optional).

## Method 6: know the denominator (containers and hosts)

1. `docker stats` CPU is a percentage of one CPU. Convert to cores (`/100`).
2. Divide by the right denominator for the question: Docker VM CPUs (`docker info --format '{{.NCPU}}'`) for share of the VM, host logical processors for share of the machine.
3. Read the container's own cap first (`docker inspect <c> --format '{{.HostConfig.NanoCpus}}'`, divide by 1e9; 0 = uncapped). A container sitting at its cap is the limit working, not a host problem. A container at "200.79%" with `cpus: "2.0"` was the healthiest reading possible, about 6% of a 32-thread host.
4. Windows memory pressure shows in commit charge, not free RAM (95% committed with 39.5 GB "free" was a stuttering box).
5. When a metric moves after you act, re-list the top consumers in both samples. A 31.6 GB drop credited to stopping a 2.4 GiB container was a 28.5 GB VM exiting on its own.

```powershell
powershell -NoProfile -File scripts\docker_cpu_real.ps1 -Samples 5 -Top 10
```

Platform detail and a POSIX equivalent are in `references/docker-and-windows-metrics.md` (optional).

## Method 7: one mechanism must explain every observation

1. Write an observation ledger before naming a cause: what broke, what still works, what did NOT happen, the timing, the size of each change.
2. List every candidate mechanism. For each, mark every observation as explained, contradicted, or silent.
3. Reject any mechanism that contradicts an observation, however well it explains the headline symptom. Check magnitude, not just direction.
4. Where two mechanisms survive, design the discriminating experiment: one change for which they predict different numbers. Write both predictions down first.
5. A note that says BROKEN, or names a cause, is an observation from the past. Re-probe it before you build on it.

Vignettes (table in `references/vignettes.md` section 7): an "sshd hang" that was a host changing its address, diagnosed per-service for two days while every other endpoint had failed on the same schedule; a host that "answered ping" while every service hung, because ICMP is answered in the kernel and the box was in an OOM loop; a "GPU contention" verdict that could not explain a slow period at 0% GPU and 34 C. The same hypothesis was wrong on one box and right on another; the discriminating experiment (pause the other job, change nothing else) moved prefill from 24.9 to 539 tok/s there. Run the experiment; do not carry the verdict over.

## Reporting a number

- Lead with the net position, then the number, then its window: "Sustained 21 chunks/s over 6 minutes (full cycles); ETA about 3 h".
- Use numbers for odds and margins ("fits with 8.2 GB free", "OOM by 166 MiB"), not adjectives.
- When a check overturns something you said, write the correction where the original claim lives, visibly.

## Files in this skill

| File | What it does |
|---|---|
| `scripts/rate_window.py` | Samples a counter (file size, JSON file key, JSON URL key; local or over ssh), prints every interval, flags stalls and resets, withholds a verdict when the window is too short. `--demo` needs nothing. |
| `scripts/kv_math.py` | KV floor from architecture numbers or a GGUF header (standard library only), least-squares fit of measured loads, slot count from free memory. |
| `scripts/cost_per_work.py` | Ranks offers by job cost including setup time and bandwidth. |
| `scripts/block_bootstrap.py` | Moving-block bootstrap CI of a mean or of a mean minus a matched null; verdict when the CI contains 0. `--demo` shows plain vs block. |
| `scripts/docker_cpu_real.ps1` | `docker stats` over N snapshots, converted to cores, share of Docker VM, share of host, share of own cap. PowerShell 5.1 or 7. |
| `references/vignettes.md` | Every incident behind the methods, anonymized, with the quoted number and the true one. |
| `references/kv-cache-and-vram.md` | Architecture keys, worked floors, measured fit tables, unified-memory traps, speed at depth. |
| `references/rented-gpu-cost.md` | Optional: marketplace filters, prebuilt-binary traps, bandwidth billing. |
| `references/docker-and-windows-metrics.md` | Optional: container denominators, Windows commit charge, CPU snapshot traps. |

All scripts are read-only and dependency-free (Python 3 standard library; the `.ps1` needs only the Docker CLI).

---
Part of [agent-skills](https://github.com/dexteon/agent-skills) by [CyberAutomations](https://cyberautomations.com).
