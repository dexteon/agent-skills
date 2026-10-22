# Cost per unit of work on rented GPUs (optional: marketplace-specific)

This section applies when you rent GPUs by the hour from a marketplace (Vast.ai is the one these numbers come from; the method transfers to any metered host). Skip it if your compute is owned or flat-rate.

## 1. Rank by job cost, never by $/hr

```
cost = usd_hr x (work_hours x time_mult + setup_min / 60) + download_gb x usd_per_tb / 1000
```

- `time_mult`: how many times longer the candidate takes than your reference card for the same work, measured at the real context depth and concurrency. Shallow tests hide it: one card measured 87% of the reference at 5k context and 3 to 4x slower at 100k to 175k.
- `setup_min`: minutes billed before useful work. Model download, plus a source build (about 30 minutes for a CUDA inference server) when no prebuilt binary matches the box.
- `usd_per_tb`: inbound bandwidth price. It varies about 10,000x between hosts ($0.004/TB vs $40/TB seen in one week) and the headline hourly price excludes it.
- Disk adds about $0.03/hr per 60 GB over the quoted rate, and a stopped box still bills disk.

The measured inversion, 10 hours of reference-card work:

| Card | $/hr | time x | job cost |
|---|---|---|---|
| 48 GB current-gen workstation (reference) | 0.537 | 1.0 | $5.37 |
| 24 GB current-gen consumer | 0.535 | 1.15 | $6.15 |
| 48 GB two generations old | 0.253 | 3.2 | $8.10 |
| 48 GB one generation old | 0.446 | 2.3 | $10.26 |

`python scripts/cost_per_work.py --work-hours 10 --offer "A:0.537:1.0" --offer "B:0.535:1.15" --offer "C:0.253:3.2" --offer "D:0.446:2.3"` reproduces it.

## 2. Prebuilt binaries and when they do not help

If you keep a cache of prebuilt server binaries keyed by GPU architecture (sm80, sm86, sm89, sm90, sm120 and so on), a cache hit normally removes the build from `setup_min`. Two ways a hit still fails on the box, each costing a 30-minute source build:

- the tarball was built against a different CUDA major version than the host image (unresolved `libcudart.so.12` on a CUDA 13 image);
- the tarball was built with native CPU tuning on an AVX-512 host and the offer runs a CPU without it (SIGILL at startup).

Key the cache by architecture, CUDA major and CPU feature level, or add `setup_min` whenever the offer's CUDA version or CPU differs from what the tarball was built on. Keep the ranking script's list of cached architectures in sync with the cache; a stale list charges some offers for a build they no longer need.

## 3. Filter in the query, verify on the instance

Filter the search itself rather than reading the list by eye. Field names below are Vast.ai's; find the equivalents on another marketplace.

| Filter | Incident behind it |
|---|---|
| `gpu_frac=1` | a "cheap 48 GB" datacenter card was a quarter share, benchmark score 5.4 vs 88.9 for a whole card. `gpu_frac` is the share of the machine, so a whole card on a 3-card host shows 0.333 with a whole-card score; check the benchmark on the created instance |
| `compute_cap>=800` | two-generations-old cards ran 100k to 175k-context sessions at about 4 tok/s per stream |
| `inet_down>=4000`, then a pre-flight download of at least 15 MB/s | a host advertising 622 Mbps delivered about 5 MB/s and turned a 55-second pull into 80 minutes; good hosts did 65 to 470 MB/s |
| `duration>2` (days) | a 20 h job on an 8 h host dies |
| `reliability>0.98` | the query field is `reliability`; a similarly named display field is not a query field (check `search offers --help`) |
| `verified=true`, `rentable=true` | obvious once forgotten |
| exclude mining SKUs by name | one was listed at 65,536 MiB with 8 GB usable, and won the cost ranking on paper twice; enforce a minimum compute capability in code |
| fold in `internet_down_cost_per_tb` | one 24.4 GB pull registered as 28.63 GB billed at $40/TB: $1.118, about 6 hours of that box's rental |

After create, verify on the instance: the card share, the benchmark score against the whole-card value, and a pre-flight download. If the download is under 15 MB/s, the default is to destroy the box and state the burn per hour. Offer IDs churn in minutes, so re-verify right before `create`.

## 4. Price the all-in rate from a credit delta

Three prices for one box disagreed in an afternoon: the listing's $0.18327/hr, the console's $0.192/hr, and a clean 10-minute credit delta of $0.1865/hr. A 2-minute sample taken while a download was billing read $0.2514/hr. Measure credit delta over at least 10 minutes with nothing downloading.

## 5. Renting spends money

State the burn rate and get an explicit go before creating an instance, and state it again whenever the next step waits on a human; idle boxes bill. Bid survival on a spot market (how far over the floor to bid) is a separate question with its own measurement: on a contested night even 2.5x the floor lost.
