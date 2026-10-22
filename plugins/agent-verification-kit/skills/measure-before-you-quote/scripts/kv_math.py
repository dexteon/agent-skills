#!/usr/bin/env python3
"""KV-cache and VRAM sizing math for llama.cpp-style inference servers.
Read-only: it computes, and in `gguf` mode it reads a model file header.
It never loads a model, never touches a GPU, never calls a server. No
dependencies beyond the standard library.

Subcommands
  kv     KV bytes per token from architecture numbers, plus per-slot size.
  gguf   Same, but read the architecture numbers from a GGUF file header
         (a truncated copy of the first ~16 MB of the file is enough).
  fit    Least-squares fit of measured (total_ctx, used_MiB) points:
         used = base + per_token * total_ctx. Predicts new configs.
  slots  How many slots of a given context fit in the free memory.

The arithmetic gives the KV FLOOR. Measured per-slot cost has come in 15 to
25 percent higher (compute buffers and recurrent state scale with slots
too). Use `kv` to shortlist, then measure two configs and use `fit`.

Examples (architecture numbers are typical of public open-weight models)
  # a 27B hybrid model: 64 layers, full attention on every 4th, 4 KV heads,
  # head_dim 256, q4_0 cache, one 196,608-token slot
  python kv_math.py kv --layers 64 --full-attn-interval 4 --kv-heads 4 --head-dim 256 --cache q4_0 --ctx 196608

  # a 35B mixture-of-experts hybrid: 40 layers, interval 4, 2 KV heads,
  # head_dim 256, q8_0 cache, 4 slots of 262,144
  python kv_math.py kv --layers 40 --full-attn-interval 4 --kv-heads 2 --head-dim 256 --cache q8_0 --ctx 262144 --slots 4

  # a dense GQA model with no hybrid layers: 48 layers, 8 KV heads, head_dim 128
  python kv_math.py kv --layers 48 --kv-heads 8 --head-dim 128 --cache f16 --ctx 32768 --slots 8

  # fit three real loads of one model and predict a fourth on a 48 GB card
  python kv_math.py fit --point 262144:29868 --point 524288:40082 --point 688128:46472 --predict 786432 --free 48402

  # how many 262,144-token slots fit once base and slope are known
  python kv_math.py slots --free 48402 --base 19699 --per-token 0.03889 --ctx 262144

  # read the header of a local GGUF (or of a 16 MB head -c chunk of one)
  python kv_math.py gguf ./model.gguf --cache q8_0 --ctx 262144 --slots 2
"""
import argparse
import sys

# Bytes per element for llama.cpp KV cache types (block size 32 for the quants).
CACHE_BYTES = {
    "f32": 4.0,
    "f16": 2.0,
    "bf16": 2.0,
    "q8_0": 34 / 32,    # 32 int8 + one f16 scale
    "q5_1": 24 / 32,
    "q5_0": 22 / 32,
    "q4_1": 20 / 32,
    "q4_0": 18 / 32,    # 16 bytes of nibbles + one f16 scale
    "iq4_nl": 18 / 32,
}
MIB = 1024 * 1024


def kv_bytes_per_token(full_layers, kv_heads, k_dim, v_dim, cache_k, cache_v):
    """K and V for every full-attention layer. Linear/SSM layers hold a
    constant recurrent state instead and are not counted here."""
    k = full_layers * kv_heads * k_dim * CACHE_BYTES[cache_k]
    v = full_layers * kv_heads * v_dim * CACHE_BYTES[cache_v]
    return k + v


def report_kv(full_layers, total_layers, kv_heads, k_dim, v_dim, cache_k, cache_v,
              ctx, slots, recurrent_mib):
    bpt = kv_bytes_per_token(full_layers, kv_heads, k_dim, v_dim, cache_k, cache_v)
    print(f"layers: {total_layers} total, {full_layers} carry a growing KV cache")
    print(f"kv_heads={kv_heads} k_dim={k_dim} v_dim={v_dim} cache K={cache_k} V={cache_v}")
    print(f"KV per token: {bpt:,.0f} bytes ({bpt / 1024:.1f} KiB)")
    if ctx:
        per_slot = bpt * ctx / MIB + recurrent_mib
        print(f"KV per slot at ctx {ctx:,}: {per_slot:,.0f} MiB"
              + (f" (incl. {recurrent_mib} MiB recurrent state)" if recurrent_mib else ""))
        if slots:
            print(f"KV for {slots} slots x {ctx:,} = {slots * ctx:,} total tokens: "
                  f"{per_slot * slots:,.0f} MiB")
            print(f"llama.cpp flags: --ctx-size {slots * ctx} --parallel {slots} "
                  "(ctx-size is DIVIDED across --parallel slots)")
    print("NOTE: this is the KV floor. Measured per-slot cost has run 15-25% higher; "
          "measure two configs and use `fit` before renting or reconfiguring.")


def cmd_kv(a):
    if a.full_attn_interval:
        full = a.layers // a.full_attn_interval
    else:
        full = a.full_layers if a.full_layers else a.layers
    v_dim = a.v_dim or a.head_dim
    report_kv(full, a.layers, a.kv_heads, a.head_dim, v_dim, a.cache_k or a.cache,
              a.cache_v or a.cache, a.ctx, a.slots, a.recurrent_mib)


def read_gguf_kv(path):
    """Parse only the GGUF key/value header (v2/v3). No dependencies, reads
    nothing past the header, and works on a truncated chunk of the file, so a
    remote model can be sized from `ssh host 'head -c 16000000 FILE' > hdr.gguf`."""
    import struct
    scalar = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?",
              10: "Q", 11: "q", 12: "d"}
    with open(path, "rb") as fh:
        if fh.read(4) != b"GGUF":
            sys.exit(f"{path}: not a GGUF file (no GGUF magic)")
        version, = struct.unpack("<I", fh.read(4))
        if version < 2:
            sys.exit(f"{path}: GGUF v{version} is too old for this parser")
        _n_tensors, n_kv = struct.unpack("<QQ", fh.read(16))

        def need(n):
            b = fh.read(n)
            if len(b) < n:
                raise EOFError
            return b

        def rstr():
            n, = struct.unpack("<Q", need(8))
            return need(n).decode("utf-8", "replace")

        def rval(t):
            if t == 8:
                return rstr()
            if t == 9:
                at, = struct.unpack("<I", need(4))
                n, = struct.unpack("<Q", need(8))
                vals = [rval(at) for _ in range(n)]
                return vals if n <= 512 else None   # skip vocab-sized arrays
            fmt = "<" + scalar[t]
            return struct.unpack(fmt, need(struct.calcsize(fmt)))[0]

        out = {}
        try:
            for _ in range(n_kv):
                k = rstr()
                t, = struct.unpack("<I", need(4))
                out[k] = rval(t)
        except EOFError:
            print(f"(header continues past the end of {path}; parsed {len(out)} of {n_kv} keys. "
                  "Fetch more bytes if a key below is missing.)")
        return out


def cmd_gguf(a):
    f = read_gguf_kv(a.path)

    def get(key, default=None):
        v = f.get(key)
        return default if v is None else v

    arch = get("general.architecture")
    if not arch:
        sys.exit("no general.architecture key; not a model GGUF?")
    p = arch + "."
    if get(p + "block_count") is None:
        sys.exit(f"arch {arch!r} has no {p}block_count key: not a text LLM "
                 "(vision projector, embedder or other). Nothing to size.")
    layers = int(get(p + "block_count"))
    heads = get(p + "attention.head_count")
    kvh = get(p + "attention.head_count_kv", heads)
    emb = get(p + "embedding_length")
    interval = get(p + "full_attention_interval")
    ctx_train = get(p + "context_length")
    if isinstance(heads, list):
        heads_n = max(heads)
    else:
        heads_n = heads
    k_dim = get(p + "attention.key_length") or (int(emb) // int(heads_n))
    v_dim = get(p + "attention.value_length") or k_dim

    if isinstance(kvh, list):
        nonzero = [h for h in kvh if h]
        full = len(nonzero)
        kv_heads = max(nonzero) if nonzero else 0
        src = "per-layer head_count_kv array (zero = no KV)"
    elif interval:
        full = layers // int(interval)
        kv_heads = int(kvh)
        src = f"full_attention_interval={interval}"
    else:
        full = layers
        kv_heads = int(kvh)
        src = "no interval key: every layer is full attention"

    print(f"file: {a.path}")
    print(f"arch: {arch}  context_length (trained): {ctx_train}  layer rule: {src}")
    report_kv(full, layers, kv_heads, int(k_dim), int(v_dim), a.cache_k or a.cache,
              a.cache_v or a.cache, a.ctx or (int(ctx_train) if ctx_train else None),
              a.slots, a.recurrent_mib)


def parse_point(s):
    try:
        ctx, mib = s.split(":")
        return float(ctx), float(mib)
    except ValueError:
        raise argparse.ArgumentTypeError("point must be TOTAL_CTX:USED_MIB, e.g. 524288:40082")


def cmd_fit(a):
    pts = a.point
    if len(pts) < 2:
        sys.exit("need at least two measured points (one point cannot separate base from slope)")
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    if sxx == 0:
        sys.exit("all points have the same total ctx; vary total context between measurements")
    slope = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx
    base = my - slope * mx
    print(f"fit over {n} points: used_MiB = {base:,.0f} + {slope:.5f} * total_ctx")
    print(f"  = {slope * 1024:.1f} MiB per 1,024 TOTAL context tokens (summed over all slots)")
    print("residuals (measured - fitted):")
    worst = 0.0
    for c, m in pts:
        res = m - (base + slope * c)
        worst = max(worst, abs(res))
        print(f"  total_ctx {c:>10,.0f}  measured {m:>9,.0f}  fitted {base + slope * c:>9,.0f}  {res:+7,.0f}")
    print(f"worst residual: {worst:,.0f} MiB")
    for c in a.predict or []:
        pred = base + slope * c
        line = f"predict total_ctx {c:,.0f}: {pred:,.0f} MiB"
        if a.free:
            left = a.free - pred
            verdict = "FITS" if left >= a.floor else ("TIGHT (below floor)" if left > 0 else "OOM")
            line += f"  free after load {left:,.0f} MiB -> {verdict} (floor {a.floor} MiB)"
        print(line)
    if a.free:
        print(f"floor = post-load free VRAM to keep for lazy allocations (cuBLAS workspace "
              f"on CUDA). A server that loaded with 561 MiB free died on its first real "
              f"request; keep >= 2048.")


def cmd_slots(a):
    usable = a.free - a.floor - a.base
    if usable <= 0:
        print(f"nothing fits: free {a.free} - floor {a.floor} - base {a.base} = {usable} MiB")
        return
    per_slot = a.per_token * a.ctx
    n = int(usable // per_slot)
    print(f"per slot at ctx {a.ctx:,}: {per_slot:,.0f} MiB; usable {usable:,.0f} MiB")
    print(f"max slots: {n}  (leaves {usable - n * per_slot + a.floor:,.0f} MiB free after load)")
    print("Then: slots must be >= concurrent callers PLUS auxiliary callers (title generation, "
          "compaction), or LRU eviction re-prefills a whole history. VRAM headroom is not "
          "compute headroom: check per-stream decode with all slots busy.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def cache_args(p):
        p.add_argument("--cache", default="q8_0", choices=sorted(CACHE_BYTES),
                       help="KV cache type for both K and V (default q8_0)")
        p.add_argument("--cache-k", choices=sorted(CACHE_BYTES), help="override K cache type")
        p.add_argument("--cache-v", choices=sorted(CACHE_BYTES), help="override V cache type")
        p.add_argument("--ctx", type=int, help="context per slot")
        p.add_argument("--slots", type=int, help="number of slots (--parallel)")
        p.add_argument("--recurrent-mib", type=float, default=0.0,
                       help="constant per-slot recurrent state of linear layers, MiB")

    k = sub.add_parser("kv", help="KV floor from architecture numbers")
    k.add_argument("--layers", type=int, required=True, help="block_count")
    k.add_argument("--full-attn-interval", type=int,
                   help="hybrid models: every Nth layer is full attention (often 4)")
    k.add_argument("--full-layers", type=int, help="explicit count of full-attention layers")
    k.add_argument("--kv-heads", type=int, required=True, help="attention.head_count_kv")
    k.add_argument("--head-dim", type=int, required=True, help="key_length")
    k.add_argument("--v-dim", type=int, help="value_length if different from head-dim")
    cache_args(k)
    k.set_defaults(fn=cmd_kv)

    g = sub.add_parser("gguf", help="KV floor from a GGUF header")
    g.add_argument("path", help="GGUF file, or a truncated head of one")
    cache_args(g)
    g.set_defaults(fn=cmd_gguf)

    f = sub.add_parser("fit", help="fit measured loads and predict")
    f.add_argument("--point", type=parse_point, action="append", required=True,
                   help="TOTAL_CTX:USED_MIB from a real load (repeat, >= 2)")
    f.add_argument("--predict", type=float, action="append", help="total ctx to predict")
    f.add_argument("--free", type=float, help="free MiB before load (not total VRAM)")
    f.add_argument("--floor", type=float, default=2048.0, help="MiB to keep free after load (default 2048)")
    f.set_defaults(fn=cmd_fit)

    s = sub.add_parser("slots", help="slots that fit in free memory")
    s.add_argument("--free", type=float, required=True, help="free MiB before load")
    s.add_argument("--base", type=float, required=True, help="fitted base MiB")
    s.add_argument("--per-token", type=float, required=True, help="fitted MiB per total token")
    s.add_argument("--ctx", type=int, required=True, help="context per slot")
    s.add_argument("--floor", type=float, default=2048.0, help="MiB to keep free after load (default 2048)")
    s.set_defaults(fn=cmd_slots)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
