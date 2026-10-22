#!/usr/bin/env python3
"""Moving-block bootstrap confidence interval for a mean, or for a mean
difference against a matched null. Read-only: reads one CSV, prints numbers.
Pure standard library.

Why this exists: a symmetric outcome distribution over 167 events was once
read as "the signal is a coin flip". Bootstrapped, the asymmetry was -0.002
with a 95% CI of [-0.296, +0.271]: no verdict either way was supportable.
The right test (forward outcomes against matched random timings, block
bootstrap because the outcome windows overlapped) reversed the conclusion.
Pair every point estimate with an interval, and block-resample when
observations overlap in time.

Usage
  python block_bootstrap.py --demo
  python block_bootstrap.py --csv data.csv --col diff --block 4
  python block_bootstrap.py --csv data.csv --col signal_ret --null-col random_ret --block 12

  --col       the measured series (rows in time order)
  --null-col  outcomes of the matched null (same inputs, same window lengths,
              same regime, random timing). Rows with an empty value are skipped.
  --block     block length in rows. Set it to the overlap: if each row's
              outcome window spans 12 steps and rows are 1 step apart, use 12.
              Treating overlapping rows as independent narrows the CI falsely.
  --demo      run on a built-in synthetic series (200 rows of autocorrelated
              noise plus a small true effect) and show how the plain bootstrap
              (block 1) claims a finding that the block bootstrap withholds.
"""
import argparse
import csv
import random
import statistics


def load(path, col):
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            v = (row.get(col) or "").strip()
            if v:
                out.append(float(v))
    return out


def block_resample_mean(xs, block, rng):
    n = len(xs)
    if block <= 1:
        return statistics.fmean(rng.choice(xs) for _ in range(n))
    starts = n - block + 1
    picked = []
    while len(picked) < n:
        s = rng.randrange(starts)
        picked.extend(xs[s:s + block])
    return statistics.fmean(picked[:n])


def bootstrap(xs, ys, block, iters, conf, seed):
    rng = random.Random(seed)
    point = statistics.fmean(xs) - (statistics.fmean(ys) if ys else 0.0)
    boots = []
    for _ in range(iters):
        m = block_resample_mean(xs, block, rng)
        if ys is not None:
            m -= block_resample_mean(ys, block, rng)
        boots.append(m)
    boots.sort()
    lo_i = int((1 - conf) / 2 * iters)
    hi_i = int((1 + conf) / 2 * iters) - 1
    below = sum(1 for b in boots if b <= 0) / iters
    return point, boots[lo_i], boots[hi_i], below


def report(label, xs, ys, block, iters, conf, seed, null_label=None):
    point, lo, hi, below = bootstrap(xs, ys, block, iters, conf, seed)
    print(f"rows: {len(xs)}" + (f" vs null {len(ys)}" if ys else "") +
          f"; block {block}; effective independent n ~ {len(xs) // max(block, 1)}")
    print(f"{label} = {point:+.4f}")
    print(f"{conf:.0%} CI (moving-block bootstrap, {iters} iters, seed {seed}): [{lo:+.4f}, {hi:+.4f}]")
    print(f"share of bootstrap estimates <= 0: {below:.3f}")
    if lo <= 0 <= hi:
        print("VERDICT: the interval contains 0. This statistic supports NO directional claim. "
              "Say so, and name the test that could falsify the claim.")
    else:
        side = "above" if lo > 0 else "below"
        print(f"VERDICT: the interval is entirely {side} 0. If this cut was chosen after looking at "
              "the data, or is one of several horizons tested, label it hypothesis-generating.")


def synthetic_series(n, overlap, effect, seed):
    """Autocorrelated noise: each row is the mean of `overlap` underlying
    steps, so neighbouring rows share most of their inputs (like rolling
    forward-return windows). A small constant `effect` is added."""
    rng = random.Random(seed)
    steps = [rng.gauss(0, 1) for _ in range(n + overlap)]
    return [statistics.fmean(steps[i:i + overlap]) + effect for i in range(n)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", help="CSV file with a header row; rows in time order")
    ap.add_argument("--col", help="column holding the measured series")
    ap.add_argument("--null-col", help="column holding the matched-null series")
    ap.add_argument("--block", type=int, default=1, help="block length in rows (default 1 = plain bootstrap)")
    ap.add_argument("--iters", type=int, default=5000, help="bootstrap iterations (default 5000)")
    ap.add_argument("--conf", type=float, default=0.95, help="confidence level (default 0.95)")
    ap.add_argument("--seed", type=int, default=12345, help="random seed (default 12345)")
    ap.add_argument("--demo", action="store_true", help="run on a built-in synthetic series")
    a = ap.parse_args()

    if a.demo:
        n, overlap, effect = 200, 12, 0.05
        xs = synthetic_series(n, overlap, effect, a.seed)
        print(f"DEMO: {n} rows, each the mean of {overlap} overlapping steps, true effect {effect:+.2f}")
        print()
        print("--- plain bootstrap (block 1): treats overlapping rows as independent ---")
        report("mean(demo)", xs, None, 1, a.iters, a.conf, a.seed)
        print()
        print(f"--- block bootstrap (block {overlap} = the overlap) ---")
        report("mean(demo)", xs, None, overlap, a.iters, a.conf, a.seed)
        print()
        print("The plain interval is too narrow because it counts each overlapping row as new "
              "evidence. The block interval is the honest one.")
        return

    if not (a.csv and a.col):
        ap.error("--csv and --col are required unless --demo is given")
    xs = load(a.csv, a.col)
    ys = load(a.csv, a.null_col) if a.null_col else None
    if len(xs) < max(10, 2 * a.block):
        raise SystemExit(f"only {len(xs)} rows in {a.col}: too few for block {a.block}")
    if ys is not None and len(ys) < max(10, 2 * a.block):
        raise SystemExit(f"only {len(ys)} rows in {a.null_col}")
    if a.block > len(xs) // 2:
        raise SystemExit("block is more than half the series: the bootstrap has nothing to resample")

    label = f"mean({a.col})" + (f" - mean({a.null_col})" if ys else "")
    report(label, xs, ys, a.block, a.iters, a.conf, a.seed)


if __name__ == "__main__":
    main()
