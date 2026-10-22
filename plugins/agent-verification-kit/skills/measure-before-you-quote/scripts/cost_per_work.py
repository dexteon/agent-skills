#!/usr/bin/env python3
"""Rank rented GPU (or any metered compute) offers by the cost to FINISH a
fixed job, not by $/hr. Read-only: pure arithmetic over numbers you pass in.
It never calls a marketplace API.

    cost = usd_hr * (work_hours * time_mult + setup_min / 60)
         + download_gb * usd_per_tb / 1000

  usd_hr       all-in hourly rate (rental plus disk). Best source: a credit
               delta measured over at least 10 minutes with no download in
               flight. Listed prices, console prices and measured prices for
               one box have disagreed by 5% in one afternoon.
  time_mult    how much longer this card takes than your reference card for
               the SAME work, measured at the real depth and concurrency
               (1.0 = reference; 2.3 = takes 2.3x as long). Shallow tests
               hide this: one card measured 87% of the reference at 5k
               context and 3 to 4x slower at 100k to 175k.
  setup_min    minutes billed before useful work: model download time, plus
               a source build (about 30 min for a CUDA inference server) when
               no prebuilt binary matches the box's GPU architecture, CUDA
               major version and CPU instruction set.
  download_gb  bytes pulled onto the box (model plus any projector).
  usd_per_tb   the host's inbound bandwidth price. It can vary 10,000x
               between hosts and the headline $/hr does not include it.

Offer format: NAME:USD_HR:TIME_MULT[:SETUP_MIN[:DOWNLOAD_GB:USD_PER_TB]]

Example (a measured inversion: 10 h of work on the reference card)
  python cost_per_work.py --work-hours 10 \\
    --offer "48GB workstation card:0.537:1.0" --offer "24GB consumer card:0.535:1.15" \\
    --offer "48GB previous-gen card:0.253:3.2" --offer "48GB older pro card:0.446:2.3"

  The two cheapest per hour come out as the two most expensive per job.

Example with setup and bandwidth
  python cost_per_work.py --work-hours 10 \\
    --offer "cached build, cheap egress:0.50:1.0:5:25:0.004" \\
    --offer "source build, dear egress:0.45:1.0:35:25:40"
"""
import argparse


def parse_offer(s):
    parts = s.split(":")
    if len(parts) not in (3, 4, 6):
        raise argparse.ArgumentTypeError(
            "offer must be NAME:USD_HR:TIME_MULT[:SETUP_MIN[:DOWNLOAD_GB:USD_PER_TB]]")
    name = parts[0]
    try:
        nums = [float(x) for x in parts[1:]]
    except ValueError:
        raise argparse.ArgumentTypeError(f"non-numeric field in offer {s!r}")
    usd_hr, mult = nums[0], nums[1]
    setup = nums[2] if len(nums) >= 3 else 0.0
    dl_gb, per_tb = (nums[3], nums[4]) if len(nums) == 5 else (0.0, 0.0)
    return dict(name=name, usd_hr=usd_hr, mult=mult, setup=setup, dl_gb=dl_gb, per_tb=per_tb)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work-hours", type=float, required=True,
                    help="hours the job takes on the reference card (time_mult 1.0)")
    ap.add_argument("--offer", type=parse_offer, action="append", required=True,
                    help="NAME:USD_HR:TIME_MULT[:SETUP_MIN[:DOWNLOAD_GB:USD_PER_TB]] (repeat)")
    a = ap.parse_args()

    rows = []
    for o in a.offer:
        hours = a.work_hours * o["mult"] + o["setup"] / 60.0
        bw = o["dl_gb"] * o["per_tb"] / 1000.0
        cost = o["usd_hr"] * hours + bw
        rows.append((cost, hours, bw, o))
    rows.sort(key=lambda r: r[0])
    cheapest_hr = min(o["usd_hr"] for o in a.offer)

    print(f"{'rank':<5}{'offer':<30}{'$/hr':>8}{'time x':>8}{'hours':>8}{'bandwidth $':>13}{'JOB COST $':>12}")
    for i, (cost, hours, bw, o) in enumerate(rows, 1):
        tag = "  <- cheapest per hour" if o["usd_hr"] == cheapest_hr else ""
        print(f"{i:<5}{o['name']:<30}{o['usd_hr']:>8.3f}{o['mult']:>8.2f}{hours:>8.1f}{bw:>13.2f}{cost:>12.2f}{tag}")
    best = rows[0]
    print()
    print(f"Cheapest to finish: {best[3]['name']} at ${best[0]:.2f}.")
    print("Before renting: filter in the search query (whole card, compute capability, inbound "
          "bandwidth, max rental duration, reliability), exclude mining cards by name, then verify "
          "the CREATED instance (card share, benchmark score, pre-flight download speed).")


if __name__ == "__main__":
    main()
