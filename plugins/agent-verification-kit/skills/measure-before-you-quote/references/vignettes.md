# Measurement failures, with the true value

Every row here is a real incident from operating LLM inference, embedding pipelines, rented GPUs and container hosts. Names, hosts and dates are stripped; the numbers are kept because the size of each error is the lesson. None of it is live state. Use it to recognise the shape of a mistake before you repeat it.

## 1. Cheap proxies that lied

| Cheap proxy said | Real workload said | Why the proxy lied |
|---|---|---|
| Single-stream HTTP range request: 4.5 MB/s, "the 24 GB model needs about 90 min" | Parallel multi-connection download: about 103 MB/s, 23x faster | One TCP stream on a long-haul link is window-limited |
| Inference server `prompt_per_second = 43` on a 32-token prompt, reported as "a weak card" | 3,700 tok/s on a real 33k-token prompt | At 32 tokens the figure is per-request overhead |
| Repeated synthetic sentence: 26 to 30 chunks/s through an embedding API | Real documents: 6 to 7 chunks/s | Near-duplicate inputs hit caches and tokenize cheaply |
| 16 workers, one burst: 45.9 chunks/s | Production: `ReadTimeout`, collapsed to 2.7 chunks/s | APIs allow a burst, then throttle |
| Encoding B "3.3x faster" than encoding A | Zero change in production | The control arm ran while a live job saturated the same link |
| 8-way test at 5k context: previous-generation card at 87% of the reference card | Real sessions at 100k to 175k context: 3 to 4x worse, about 4 tok/s per stream | Only deep plus concurrent shows the KV-bandwidth cost |
| Decode "130 tok/s single-stream" at near-zero context | 6 to 15 tok/s per stream with 4 deep sessions live | Same depth trap on a different box |
| A tiny PING/PONG health probe passed on a Metal-backed server | `BackpressureError` (23.8 GB requested against a 23.1 GB cap) on about 30k-token worker prompts | A tiny probe never touches the memory ceiling |

The serialization diagnostic: an embedding API did 26 to 30 chunks/s uncontended while the pipeline using it managed 7.3, because extraction and network calls ran in lockstep. A producer/consumer with a bounded queue in the pipeline's own code fixed it, with no change to the API. When the pipeline is far slower than its slowest component measured alone, the bottleneck is your own serialization.

## 2. Windows that were too short, or the wrong shape

| Quoted | Window or proxy | True |
|---|---|---|
| 59 chunks/s | 26 s | 19.7 to 24.0 sustained over full work cycles |
| 36.6 chunks/s | 42 s | same |
| "retries are accelerating" | three notification pings | no change in retry rate |
| "GPU idle" (10%) | one `nvidia-smi` sample | about 86% over six samples |
| 20 to 37 tok/s | a dashboard's rolling average that divided by wall-clock time including idle gaps | 128 tok/s from the server's own timings |
| 6.3 vs 55.7 tok/s "on identical configs" | first request after a restart vs warm | the first request pays CUDA context init; discard 2 warm-ups |
| 924 tok/s "aggregate" | summed `predicted_per_second` across requests on a 2-slot box | total tokens divided by wall-clock only |
| "download still running" | process alive | the file sat at exactly 19,348 MB for 45 s: stalled, not slow |
| "6th request was not refused" (rate-limit proof failed) | six requests straddled a 10-minute bucket boundary (`epoch // 600`) | the test window itself was wrong; the proof now waits for a fresh bucket when under 90 s remain |
| "CPU 100%" every 20 s | Windows `Win32_Processor.LoadPercentage`, a 1 s snapshot that reads 100% whenever one core is busy | a foreground workload used about half the CPU; the sampler's own process enumeration added load |

The 26 s and 42 s mistakes happened three sessions in a row while a written rule already said "state the window". That is why the checklist in SKILL.md is mechanical: it has to work when the number is already on screen and the right measurement would take another minute.

**Billing is a rate too.** Three prices for one rented GPU disagreed in the same afternoon: the listing's `$0.18327/hr`, the console's `$0.192/hr`, and a clean 10-minute credit delta of `$0.1865/hr`. A 2-minute sample taken while a download was billing read `$0.2514/hr`. Measure credit delta over at least 10 minutes with nothing downloading.

## 3. Claims made without a null

- **The coin-flip that was not.** A symmetric outcome distribution over 167 events (median favourable excursion +0.81 vs unfavourable -0.89, in normalised units) was reported as "the signal is a coin flip". That statistic measures where to place a cutoff; it never was an edge test. Bootstrapped, the asymmetry was -0.002 with a 95% CI of [-0.296, +0.271], so it supported no verdict at all. The right instrument, forward outcomes against matched random timings with a block bootstrap (blocks set to the overlap of the outcome windows), reversed the finding: a real effect from about 12 h out and none at the 4 h horizon the system actually acted on. "No effect, stop" and "wrong horizon, change the hold" are opposite recommendations. An outside reviewer flagged it first.
- **The encodings that "differed".** Two embedding vectors at 0.9998 cosine were reported as "plain and base64 request encodings produce different vectors". They came from separate requests under concurrent load, with no control. Plain-vs-plain, base64-vs-base64 and plain-vs-base64 all measured 1.0000000000. Base64 is bit-exact; the 0.0002 was run-to-run noise under load.
- **A real difference with a proper control.** 4-bit vs 6-bit quantizations of the same embedding model on identical text measured 0.9877 mean cosine (about 1.2% drift) against a useful discriminative range of about 0.50. That is why quantizations are never mixed inside one vector collection.
- **The 3.3x encoding win** in section 1 is also a null failure: the control arm ran under different load from the test arm.

## 4. Memory numbers quoted from the wrong components

- **OOM by 166 MiB.** The first deploy of 3 slots x 262,144 tokens of a 27B hybrid model on a 48 GB card OOMed. The estimate kept a 2,048 MiB margin inherited from a different model; this model's compute buffer alone was about 3,600 MiB and did not shrink with `--ubatch-size` (3,745 MiB at 1024, 3,574 at 512). Config arithmetic said 8.3 to 8.7 GiB per slot; measured was 10,214 MiB. Seven real loads settled it in 15 minutes. See `kv-cache-and-vram.md` for the fit.
- **Equal total context, equal memory.** 2 x 262,144 and 4 x 131,072 measured 40,082 and 40,126 MiB. Size by total tokens, not slot count.
- **The fit crossed GPU generations.** 3 x 262,144 predicted about 50,300 MiB (impossible on the 48 GB card). On an 80 GB datacenter card the same config measured 50,059 MiB, within 240 MiB.
- **VRAM headroom is not speed headroom.** With 3 slots busy on the 80 GB card, GPU utilization was 100% while 31,861 MiB sat free. Two decoding slots ran at 0.57 tok/s each while the third prefilled 22K tokens at about 1,150 tok/s. A 4th slot fits by memory and would only divide saturated compute.
- **Lazy allocation OOM.** A 9-slot config loaded and printed READY with 561 MiB free, then died on the first real request (`cudaMalloc(&cublas_workspaces[...])`). 8 slots with 3,209 MiB free served 8 concurrent requests. Hence the 2 GiB post-load floor and concurrent validation.
- **Corrected 4x by reading the header.** An early note assumed a 27B model had 64 full-attention layers: 256 KB/token, 12 GB at 196,608 context, "256K fp16 = 64 GB". The GGUF header said 64 blocks with `full_attention_interval 4`, so 16 KV layers: 64 KB/token at f16 and 18 KB at q4_0, about 3.4 GiB at 196,608. Context was never the memory problem on that model; weights (about 22 GB) and other resident models were.
- **A stale component.** "256K context plus the embedding job will not fit" was concluded from a 47 GB wired-memory reading on a 64 GB unified-memory box. That 47 GB included an 8 GB embedding model and several small models, plus idle GPU buffers the OS later reclaimed. After the unload it read 31 GB, and stayed 31 GB after a 28,618-token fill (on that build the KV is allocated at load, so wired memory does not grow as context fills).
- **The binding constraint moved.** With an embedding job sharing the GPU, the 27B's prefill was 24.9 tok/s and decode 4.2; with the GPU free, 539 and 13.7. Separately, system RAM bound before the GPU memory cap did: swap reached 4.9 GB at 47 GB wired, and with both big jobs resident, free memory hit 0.1 GB and swap went from 4.4 to 10.8 GB in four minutes.

## 5. Cost per hour vs cost per job

For the same 10 hours of reference-card work (`scripts/cost_per_work.py` reproduces it):

| Card (described, not named) | $/hr | time multiplier | job cost |
|---|---|---|---|
| 48 GB current-gen workstation card (reference) | 0.537 | 1.0 | $5.37 |
| 24 GB current-gen consumer card | 0.535 | 1.15 | $6.15 |
| 48 GB two-generations-old card | 0.253 | 3.2 | $8.10 |
| 48 GB one-generation-old card | 0.446 | 2.3 | $10.26 |

The two cheapest per hour were the two most expensive per job. The same inversion held for embedding boxes: a $0.061/hr 12 GB card cost more per job than a $0.108/hr 12 GB card of the next tier.

- **Advertised bandwidth is a claim.** A host advertising 622 Mbps delivered about 5 MB/s and turned a 55-second model pull into 80 minutes. Good hosts did 65 to 470 MB/s.
- **Bandwidth is billed.** One 24.4 GB pull registered as 28.63 GB billed at $40/TB and took $1.118 off the credit, about 6 hours of that box's rental. Another host charged $0.004/TB for the same pull.
- **Fractional cards.** A "cheap 48 GB" datacenter card was a quarter share (`gpu_frac 0.25`) with a benchmark score of 5.4 against 88.9 for a whole card. Another offer at `gpu_frac 0.333` was a whole card on a 3-card host, score 54.47. The fraction describes the machine; the benchmark describes the card.
- **Mining cards.** A mining-only SKU was listed at 65,536 MiB and has 8 GB of usable memory. It won cost-per-work rankings on paper twice.

## 6. Container and host metrics read with the wrong denominator

- A container read `200.79%` CPU and was blamed for lagging the machine. Its compose file had `cpus: "2.0"`, so 200.79% meant it sat exactly at its own 2-core cap, about 6.3% of the 32-thread host. That was the healthiest possible reading.
- Same session: a 31.6 GB commit-charge drop was credited to stopping that container. It held 2.4 GiB. A virtual machine holding 28.5 GB had exited on its own between the two samples. The magnitude alone should have rejected the claim.
- The stutter signature on that host was 129.1 of 135.9 GB committed (95%) with 11.4 GB in memory compression, while the box still reported 39.5 GB "free". Windows memory pressure shows in commit charge, not free RAM.

## 7. One mechanism must explain every observation

| Tempting mechanism | Observation it could not explain | Mechanism that explained everything |
|---|---|---|
| "sshd auth hang" on one host; "HTTP endpoints are fine" | the SSH known-hosts file held three different host keys for that address; the HTTP endpoints had broken on the same schedule, unprobed | the whole host was moving to a new address; the per-service diagnosis cached a wrong cause for two days and leaked a dead address into three client configs |
| another sshd fault on the same host | the host answered ping while every service hung | kernel-level OOM loop (a crawler fork storm, about 311 forks, 19 GB); ICMP is answered in the kernel, every service needs userspace memory |
| embedding throughput "dictated by GPU contention" (13 vs 50 chunks/s, "proven" at 100% util) | in one of the slow periods the GPU sat at 0% and 34 C, which contention cannot produce | server config and network: prompt-cache thrashing (disabling the cache took it from 2.6 to 15.1 chunks/s), decimal JSON vectors on a collapsed uplink (base64 is 4x smaller), too-small per-slot context |
| 31.6 GB commit drop "because the container stopped" | the container held 2.4 GiB | a 28.5 GB VM exited on its own between samples |

The same hypothesis can be wrong on one box and right on another. "GPU contention" was wrong for the rented embedding box above and right for the unified-memory box in section 4, where the discriminating experiment (pause the embedding job, change nothing else) moved prefill from 24.9 to 539 tok/s. Run the experiment; do not carry the verdict over.
