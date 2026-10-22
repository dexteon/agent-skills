# KV cache, VRAM and unified-memory math

How to size an inference server's memory before you quote "it fits" or "it needs N GB". The recipe is in SKILL.md Method 4; this file holds the detail and the measured tables that calibrate it. `scripts/kv_math.py` does the arithmetic.

## 1. Read the architecture, never assume it

Everything below starts from numbers in the model's GGUF header (or the equivalent config.json for other formats):

| Key | Meaning |
|---|---|
| `block_count` | total transformer layers (can include an extra speculative/MTP layer) |
| `attention.head_count_kv` | KV heads per layer (GQA: fewer than query heads). Can be a per-layer array with zeros for layers that hold no KV |
| `attention.key_length`, `attention.value_length` | head dimensions for K and V (often equal; some models differ) |
| `full_attention_interval` | hybrid models: only every Nth layer has a growing KV cache; the other layers hold a small constant recurrent state |
| `context_length` | trained context, not a memory limit |

A hybrid model carries KV on only `block_count // interval` layers. Getting this wrong is the single biggest sizing error: a 27B hybrid model (64 blocks, interval 4) was once costed as 64 KV layers at 256 KB/token instead of 16 at 64 KB/token, a 4x error. `kv_math.py gguf` reads the header from the first 16 MB of the file, so a remote model can be sized without downloading it:

```bash
ssh some-host 'head -c 16000000 /path/to/model.gguf' > hdr.gguf
python scripts/kv_math.py gguf hdr.gguf --cache q8_0 --ctx 262144 --slots 2
```

## 2. The KV floor

```
bytes per token = KV_layers x 2 (K and V) x kv_heads x head_dim x bytes_per_element
per slot        = bytes per token x context per slot
```

Bytes per element by cache type: f16/bf16 2.0, q8_0 34/32, q5_1 24/32, q5_0 22/32, q4_1 20/32, q4_0 18/32.

Worked floors (`kv_math.py kv`):

| Architecture | Cache | Bytes/token | Per 262,144-token slot |
|---|---|---|---|
| 27B hybrid: 64 layers, interval 4 (16 KV layers), 4 KV heads, head_dim 256 | f16 | 65,536 | 16,384 MiB |
| same | q4_0 | 18,432 | 4,608 MiB (3,456 MiB at 196,608) |
| 35B MoE hybrid: 40 layers, interval 4 (10 KV layers), 2 KV heads, head_dim 256 | q8_0 | 10,880 | 2,720 MiB |
| 35B MoE hybrid variant: 41 blocks (one MTP), interval 4, 2 KV heads, head_dim 256 | q4_0 | 5,760 | 1,440 MiB |
| dense GQA: 48 layers, 8 KV heads, head_dim 128 | f16 | 196,608 | 49,152 MiB |

The floor is a shortlist tool. Measured per-slot cost has run 15 to 25 percent above it because compute buffers and recurrent state also scale with slots and context.

## 3. Measure two configs and fit

Load the model at two or more total-context values and record used memory after load. Fit `used = base + per_token x total_ctx`. The slope is per TOTAL token (summed over all slots), not per slot.

Measured: a 27B hybrid model (Q5-class weights, 19,282 MiB; 888 MiB vision projector; q8_0 KV) on a 48 GB card with 48,402 MiB free before load:

| slots x ctx | total ctx | used MiB | free MiB |
|---|---|---|---|
| 1 x 262,144 | 262,144 | 29,868 | 18,536 |
| 2 x 262,144 | 524,288 | 40,082 | 8,322 |
| 4 x 131,072 | 524,288 | 40,126 | 8,278 |
| 6 x 106,496 | 638,976 | 44,632 | 3,772 |
| 5 x 131,072 | 655,360 | 45,140 | 3,264 |
| 6 x 114,688 | 688,128 | 46,472 | 1,932 |
| 6 x 122,880 | 737,280 | 48,312 | 92 (loads, unsafe) |
| 3 x 262,144 | 786,432 | OOM | - |

Fit over the seven loaded rows: `used = 19,699 + 0.03889 x total_ctx` MiB, worst residual 84 MiB, about 40 MiB per 1,024 total tokens. Three confirmations:

| Config | Predicted | Measured | Where |
|---|---|---|---|
| 6 x 114,688 (live swap) | 46,472 | 46,492 | same card |
| 2 x 262,144 (revert) | 40,082 | 40,188 | same card |
| 3 x 262,144 | about 50,296 | 50,059 of 81,920 | an 80 GB card of a different GPU generation |

What broke the first estimate: the compute buffer was about 3,600 MiB (not the 2,048 MiB margin inherited from another model) and did not shrink with `--ubatch-size` (3,745 MiB at 1024, 3,574 at 512). Real per-slot cost at 262,144 was 10,214 MiB against 8,336 to 8,704 MiB from config arithmetic.

A second model, the 35B MoE hybrid at q8_0 KV: measured 0.01282 MiB/token (3,360 MiB per 262,144 slot) against a 2,720 MiB floor; predictions from the measured rate landed within 100 to 240 MiB. Weights 25,036 MiB plus about 3,285 MiB per slot at Q5-class quantization.

```bash
python scripts/kv_math.py fit --point 262144:29868 --point 524288:40082 --point 688128:46472 --predict 786432 --free 48402
python scripts/kv_math.py slots --free 48402 --base 19699 --per-token 0.03889 --ctx 262144
```

## 4. Rules that came out of the measurements

1. **Size by total context, not slot count.** 2 x 262,144 and 4 x 131,072 measured 40,082 and 40,126 MiB. In llama.cpp `--ctx-size` is divided across `--parallel` slots, so `--ctx-size` must equal slots x per-slot context or every session silently gets a fraction.
2. **Keep at least 2 GiB free after load on CUDA.** cuBLAS allocates its workspace lazily on the first real matmul. A 9-slot config loaded with 561 MiB free, printed READY, and died on the first request; 8 slots with 3,209 MiB free served 8 concurrent requests.
3. **Validate with concurrency, not a single request.** Fill every slot and run a prefill at the same time before declaring a config good.
4. **Slots must cover concurrent callers plus auxiliary callers** (title generation, compaction, health probes that carry a prompt). Fewer slots means LRU eviction and a full re-prefill of someone's history. Re-prefill seconds is about context tokens divided by measured prefill tok/s: at 864 tok/s cold on a 100K history, about 121 s.
5. **Memory headroom is not compute headroom.** With 3 slots busy on an 80 GB card, GPU util was 100% while 31,861 MiB sat free; two decoding slots ran at 0.57 tok/s each while the third prefilled 22K tokens at about 1,150 tok/s. A 4th slot fits by memory and only divides saturated compute. After sizing by memory, measure per-stream decode with every slot busy and a concurrent prefill running.
6. **Multi-GPU:** the compute buffer is duplicated per card; lower the micro-batch (`-ub` from 2048 toward 256) before lowering context. 2 x 24 GB cards settled 7 x 196,608 at 43,407 of 49,152 MiB with `-ub 256`.
7. **Size a prompt cache against the container's cgroup limit** (`/sys/fs/cgroup/memory.max`), not against `free`.
8. **Name the components of any memory number before projecting from it**, and re-measure after each load or unload.

## 5. Unified memory (Apple silicon and similar)

On a unified-memory box the GPU's share is "wired" memory under a cap (`sysctl iogpu.wired_limit_mb` on macOS). Three traps measured on a 64 GB box with a 56,000 MB cap:

- **Stale components.** A 47 GB wired reading was used to conclude "256K context will not fit alongside the embedding job". It included an 8 GB embedding model, several small models, and idle GPU buffers the OS later reclaimed. After unloading, 31 GB; still 31 GB after a 28,618-token fill, because on that build the KV is allocated at load.
- **System RAM binds before the wired cap.** Swap reached 4.9 GB at 47 GB wired; with two large jobs resident, free memory hit 0.1 GB and swap went from 4.4 to 10.8 GB in four minutes.
- **Contention, not memory, was the binding constraint.** With an embedding job on the GPU the 27B did 24.9 tok/s prefill and 4.2 decode; with the GPU free, 539 and 13.7. The discriminating experiment was "pause the other job, change nothing else".

Read-only commands for the live picture:

```bash
# any CUDA box
nvidia-smi --query-gpu=memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader
# macOS unified memory: cap, wired GB, swap
sysctl -n iogpu.wired_limit_mb
echo "wired GB: $(echo "scale=1; $(vm_stat | grep 'wired down' | tr -dc 0-9) * 16384 / 1000000000" | bc)"
sysctl -n vm.swapusage
# llama.cpp server: slot state (never hit an endpoint that counts as activity on a model-swapping proxy;
# it refreshes the idle timer and can cold-load a model)
curl -s http://127.0.0.1:PORT/slots
```

## 6. Speed at depth (for the time multiplier in cost per work)

| Measurement | Value |
|---|---|
| Decode, 48 GB one-generation-old card, near-zero context | 128 tok/s solo; about 63 per stream at 2 to 4 concurrent |
| Decode at depth (4 deep sessions, 344K KV live) | 6 to 15 tok/s per stream |
| Prefill, same card | 3,700 tok/s at 33k; 2,500 at 132k; 1,756 at 253k |
| Two-generations-old vs current, 8-way | decode near parity (about 87%); prefill at 135 to 152k depth 1,428 vs 2,560 tok/s (about 56%) |
| 35B MoE hybrid on unified memory | decode 110 tok/s short, 97 at 28K, 63 at 100K; cold 100K prefill 864 tok/s |

Any speed number without its context depth and concurrency is a different measurement from the one you need.
