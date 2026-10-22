#!/usr/bin/env python3
"""Run Hermes kanban boards one after another: unblock the next board's gate
when the previous board is complete.

Designed as a no-agent cron job (``hermes cron create "20m" --name chain-x
--no-agent --script chain_boards.py --deliver local``). ``--script`` takes no
arguments, so the chain lives in a JSON file beside the script
(``chain_boards.json``) unless ``--config`` says otherwise:

    {
      "boards": [
        {"slug": "phase-1"},
        {"slug": "phase-2", "gate": "t_1a2b3c4d"},
        {"slug": "phase-3", "gate": "t_5e6f7a8b"}
      ]
    }

Each board after the first names its gate task (created blocked, with the rest
of that board linked behind it via --parent). Each run:

  1. reads ``hermes kanban --board <slug> stats --json`` per board and calls a
     board complete when by_status has zero triage, todo, scheduled, ready,
     running, blocked and review (there is no "total" key; done >= total is the
     wrong test because a triage or blocked card never advances);
  2. for each consecutive pair, unblocks the next gate when the previous board
     is complete and the gate is still blocked (idempotent);
  3. prints ``CONTINUE <active boards>`` or ``DONE``.

Exit codes: 0 ran, 2 config missing or hermes not found. Every hermes failure
is printed and the run continues, so one bad board does not hide the others.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import List, Optional

ACTIVE_STATUSES = ("triage", "todo", "scheduled", "ready", "running", "blocked", "review")


def run(hermes: str, args: List[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run([hermes, "kanban", *args], capture_output=True, text=True, timeout=timeout)


def board_active(hermes: str, slug: str, timeout: int) -> Optional[dict]:
    """Return {status: count} for active statuses, or None when stats could not be read."""
    r = run(hermes, ["--board", slug, "stats", "--json"], timeout)
    if r.returncode != 0:
        print(f"WARN {slug}: stats rc={r.returncode}: {(r.stderr or r.stdout).strip().splitlines()[-1:]}")
        return None
    try:
        by_status = json.loads(r.stdout)["by_status"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"WARN {slug}: unreadable stats JSON ({e})")
        return None
    return {s: int(by_status.get(s, 0) or 0) for s in ACTIVE_STATUSES}


def gate_status(hermes: str, slug: str, gate: str, timeout: int) -> Optional[str]:
    r = run(hermes, ["--board", slug, "show", gate, "--json"], timeout)
    if r.returncode != 0:
        print(f"WARN {slug}: show {gate} rc={r.returncode}")
        return None
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None
    task = data.get("task") if isinstance(data, dict) and isinstance(data.get("task"), dict) else data
    return str(task.get("status")) if isinstance(task, dict) and task.get("status") else None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n", 1)[1])
    default_cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chain_boards.json")
    ap.add_argument("--config", default=default_cfg, help=f"chain JSON (default: {default_cfg})")
    ap.add_argument("--hermes", default="hermes", help="hermes executable (default: hermes on PATH)")
    ap.add_argument("--dry-run", action="store_true", help="report what would be unblocked, change nothing")
    ap.add_argument("--timeout", type=int, default=60, help="seconds per hermes call (default 60)")
    args = ap.parse_args(argv)

    try:
        with open(args.config, encoding="utf-8") as f:
            boards = json.load(f)["boards"]
        slugs = [b["slug"] for b in boards]
        if len(boards) < 2:
            raise ValueError("need at least two boards")
        for b in boards[1:]:
            if not b.get("gate"):
                raise ValueError(f"board {b.get('slug')!r} has no gate task id")
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
        print(f"bad config {args.config}: {e}", file=sys.stderr)
        return 2
    if shutil.which(args.hermes) is None:
        print(f"hermes executable not found: {args.hermes}", file=sys.stderr)
        return 2

    active = {}
    for slug in slugs:
        counts = board_active(args.hermes, slug, args.timeout)
        active[slug] = None if counts is None else sum(counts.values())

    for prev, nxt in zip(boards, boards[1:]):
        prev_slug, nxt_slug, gate = prev["slug"], nxt["slug"], nxt["gate"]
        if active.get(prev_slug) != 0:
            continue  # previous board still active or unreadable
        status = gate_status(args.hermes, nxt_slug, gate, args.timeout)
        if status not in ("blocked", "scheduled"):
            continue  # already released, or unreadable: do nothing
        if args.dry_run:
            print(f"WOULD UNBLOCK {nxt_slug}:{gate} (previous board {prev_slug} complete)")
            continue
        r = run(args.hermes, ["--board", nxt_slug, "unblock", "--reason", f"chain: {prev_slug} complete", gate], args.timeout)
        if r.returncode == 0:
            print(f"UNBLOCKED {nxt_slug}:{gate} (previous board {prev_slug} complete)")
            run(args.hermes, ["--board", nxt_slug, "dispatch"], args.timeout)
            active[nxt_slug] = (active.get(nxt_slug) or 0) + 1
        else:
            print(f"WARN {nxt_slug}: unblock {gate} rc={r.returncode}: {(r.stderr or r.stdout).strip().splitlines()[-1:]}")

    still = [s for s in slugs if active.get(s) is None or active[s] > 0]
    if not still:
        print("DONE")
    else:
        print("CONTINUE " + " ".join(f"{s}:{'?' if active[s] is None else active[s]}" for s in still))
    return 0


if __name__ == "__main__":
    sys.exit(main())
