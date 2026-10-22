#!/usr/bin/env python3
"""Sample a progress counter over a stated window and report the rate honestly.

Read-only. It reads a file size, a numeric value inside a JSON file, or a
numeric value inside a JSON HTTP response. With --ssh it reads the file on a
remote host over `ssh -o BatchMode=yes`. It never writes, restarts or kills
anything.

Why this exists: rates quoted from short windows are wrong again and again.
A 26 second window once said 59 items/s when the sustained rate over full
work cycles was 19.7 to 24.0. One `nvidia-smi` sample read 10% while six
samples averaged about 86%. This script makes the window explicit, prints
every interval, and separates STALLED from SLOW from NOT YET QUOTABLE.

Sources (pick one)
  --file PATH                 byte size of a growing file (download, log, DB)
  --json-file PATH --key a.b  a numeric value inside a JSON file
  --url URL --key a.b         a numeric value inside a JSON HTTP response (GET)
  --demo                      a built-in simulated counter (needs nothing)
  add --ssh HOST to read --file / --json-file on a remote host

Examples
  # built-in demo: a counter that advances in batches, so you can see the
  # partial-stall note and the window verdict without any infrastructure.
  # The first run is withheld (stalls seen, no cycle stated); the second
  # states the cycle and a window of 4 cycles, and is quotable.
  python rate_window.py --demo --interval 0.5 --samples 9 --unit items
  python rate_window.py --demo --interval 0.5 --samples 13 --cycle-sec 1.5 --unit items

  # a download growing on local disk, one sample every 10 s, 7 samples
  python rate_window.py --file ./downloads/model.bin --interval 10 --samples 7 --unit bytes

  # a worker pool whose state file holds {"totals": {"done": N}}; the work
  # cycle (WORKERS x BATCH) takes about 120 s, so the verdict is withheld
  # until the window is at least that long
  python rate_window.py --json-file ./state.json --key totals.done --interval 30 --samples 7 --cycle-sec 120 --unit chunks

  # same counter on a remote host (quote "~/..." paths; some shells rewrite
  # absolute remote paths before Python sees them)
  python rate_window.py --ssh build-box --json-file "~/jobs/state.json" --key totals.done --interval 30 --samples 7
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.request

DEMO_RATE_PER_S = 50.0      # true underlying rate of the simulated counter
DEMO_FLUSH_EVERY_S = 1.5    # the counter is only "flushed" this often


def dig(obj, key):
    for part in key.split("."):
        if isinstance(obj, list):
            obj = obj[int(part)]
        else:
            obj = obj[part]
    return float(obj)


def ssh_out(host, remote_cmd):
    out = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, remote_cmd],
        capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError(f"ssh {host} failed rc={out.returncode}: {out.stderr.strip()[:200]}")
    return out.stdout


def remote_path(p):
    # Expand ~ on the remote side so the caller can quote "~/x" safely.
    if p.startswith("~/"):
        return '"$HOME/' + p[2:].replace('"', '') + '"'
    return "'" + p.replace("'", "") + "'"


def read_value(a, t0):
    if a.demo:
        # A counter that grows at DEMO_RATE_PER_S but is written out only every
        # DEMO_FLUSH_EVERY_S seconds. Short windows see stalls that are not stalls.
        elapsed = time.time() - t0
        flushed = int(elapsed // DEMO_FLUSH_EVERY_S) * DEMO_FLUSH_EVERY_S
        return float(int(flushed * DEMO_RATE_PER_S))
    if a.file:
        if a.ssh:
            return float(ssh_out(a.ssh, f"wc -c < {remote_path(a.file)}").strip())
        import os
        return float(os.path.getsize(a.file))
    if a.json_file:
        if a.ssh:
            text = ssh_out(a.ssh, f"cat {remote_path(a.json_file)}")
        else:
            with open(a.json_file, encoding="utf-8") as fh:
                text = fh.read()
        return dig(json.loads(text), a.key)
    req = urllib.request.Request(a.url, headers=dict(h.split(":", 1) for h in a.header or []))
    with urllib.request.urlopen(req, timeout=15) as r:
        return dig(json.loads(r.read().decode("utf-8")), a.key)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="path of a growing file; its byte size is the counter")
    src.add_argument("--json-file", help="path of a JSON file holding the counter (needs --key)")
    src.add_argument("--url", help="HTTP URL returning JSON that holds the counter (needs --key)")
    src.add_argument("--demo", action="store_true", help="use a built-in simulated counter")
    ap.add_argument("--key", help="dotted path to the counter in the JSON, e.g. totals.done")
    ap.add_argument("--header", action="append", help="HTTP header 'Name: value' (url mode)")
    ap.add_argument("--ssh", help="read --file / --json-file on this ssh host")
    ap.add_argument("--interval", type=float, default=10.0, help="seconds between samples (default 10)")
    ap.add_argument("--samples", type=int, default=7, help="number of samples; intervals = samples-1 (default 7)")
    ap.add_argument("--cycle-sec", type=float,
                    help="length of one full work cycle (e.g. WORKERS x BATCH time); "
                         "the verdict is withheld if the window is shorter")
    ap.add_argument("--unit", default="units", help="label for the counter (default 'units')")
    a = ap.parse_args()
    if (a.json_file or a.url) and not a.key:
        ap.error("--key is required with --json-file or --url")
    if a.ssh and (a.url or a.demo):
        ap.error("--ssh applies to --file or --json-file only")
    if a.samples < 2:
        ap.error("need at least 2 samples")

    t0 = time.time()
    rows = []
    for i in range(a.samples):
        t = time.time()
        try:
            v = read_value(a, t0)
        except Exception as e:
            print(f"sample {i}: READ FAILED: {e}")
            v = None
        rows.append((t, v))
        stamp = time.strftime("%H:%M:%S", time.localtime(t))
        if v is None:
            pass
        elif len(rows) > 1 and rows[-2][1] is not None:
            dt = t - rows[-2][0]
            d = v - rows[-2][1]
            flag = "  STALL" if d == 0 else ("  RESET?" if d < 0 else "")
            print(f"{stamp}  {v:>16,.0f}  +{d:>12,.0f} in {dt:5.1f}s = {d / dt:>12,.2f} {a.unit}/s{flag}")
        else:
            print(f"{stamp}  {v:>16,.0f}  (first sample)")
        if i < a.samples - 1:
            time.sleep(a.interval)

    good = [(t, v) for t, v in rows if v is not None]
    if len(good) < 2:
        sys.exit("fewer than 2 readable samples: no rate can be stated")
    window = good[-1][0] - good[0][0]
    deltas = [(good[i][1] - good[i - 1][1], good[i][0] - good[i - 1][0]) for i in range(1, len(good))]
    rates = [d / dt for d, dt in deltas if dt > 0]
    stalls = sum(1 for d, _ in deltas if d == 0)
    resets = sum(1 for d, _ in deltas if d < 0)
    overall = (good[-1][1] - good[0][1]) / window if window > 0 else 0.0

    print()
    print(f"WINDOW: {window:.0f} s, {len(deltas)} intervals of ~{a.interval:g} s")
    print(f"sustained rate over the window: {overall:,.2f} {a.unit}/s")
    if rates:
        print(f"interval rates: min {min(rates):,.2f}  median {statistics.median(rates):,.2f}  max {max(rates):,.2f}")
    # Window checks come BEFORE the stall verdict: a counter that is flushed or
    # batched once per cycle looks frozen in any window shorter than that cycle.
    short = []
    if len(deltas) < 5:
        short.append(f"only {len(deltas)} intervals (< 5)")
    if a.cycle_sec and window < a.cycle_sec:
        short.append(f"window {window:.0f} s is shorter than one work cycle ({a.cycle_sec:g} s)")
    if stalls == len(deltas):
        if short:
            cyc = (f", shorter than one cycle ({a.cycle_sec:g} s)"
                   if a.cycle_sec and window < a.cycle_sec else "")
            print(f"VERDICT: NOT QUOTABLE (no movement seen in {window:.0f} s{cyc}): "
                  + "; ".join(short) + ". Not yet a stall: take a window of at least one full cycle "
                  "and 5 intervals before calling it stalled.")
            return
        print("VERDICT: STALLED. The counter did not move in any interval. Stalled is not slow: "
              "check the process by effect (port open, CPU, children) before calling it healthy. "
              "First rule out a counter that is only flushed to disk less often than your window.")
        return
    if resets:
        print(f"WARNING: {resets} interval(s) went backwards: counter reset or wrong key. Do not quote a rate.")
    if stalls:
        print(f"NOTE: {stalls} interval(s) with zero progress (partial stalls or batch refill gaps).")
        if not a.cycle_sec:
            short.append(f"{stalls} zero-progress interval(s) and no --cycle-sec given: the counter "
                         "may be flushed in batches; find the cycle length and pass --cycle-sec")
    nz = [r for r in rates if r > 0]
    if len(nz) >= 2 and max(nz) / min(nz) > 3:
        short.append("interval rates vary more than 3x (oscillating; widen the window)")
    if short:
        print("VERDICT: NOT QUOTABLE YET: " + "; ".join(short) + ". Say 'measuring' and take a longer window.")
    else:
        print(f"VERDICT: quotable as '{overall:,.2f} {a.unit}/s sustained over {window:.0f} s'.")
    if a.demo:
        print(f"(demo: the true rate is {DEMO_RATE_PER_S:g} {a.unit}/s, flushed every {DEMO_FLUSH_EVERY_S:g} s; "
              "any single interval shorter than the flush period is wrong by construction)")


if __name__ == "__main__":
    main()
