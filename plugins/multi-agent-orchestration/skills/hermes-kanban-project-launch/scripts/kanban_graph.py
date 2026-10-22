#!/usr/bin/env python3
"""Create a dependency-linked task graph on a Hermes kanban board, parents first.

Reads a JSON spec, creates cards in topological order with ``hermes kanban
--board <slug> create ... --json``, captures each card's id, and passes parent
ids with ``--parent`` so children start in ``todo`` and promote when their
parents finish. A child whose parent failed to create is skipped with a clear
message instead of failing quietly with ``unknown parent task(s)``.

Spec format (graph.json):

    {
      "defaults": {"workspace": "dir:/path/to/project", "priority": 0},
      "tasks": [
        {"key": "research", "title": "Research options", "assignee": "researcher",
         "body": "What to compare and where to write it"},
        {"key": "impl", "title": "Implement", "assignee": "engineer",
         "parents": ["research"], "goal": true, "goal_max_turns": 100},
        {"key": "review", "title": "Full code review", "assignee": "reviewer",
         "parents": ["impl"], "priority": 5}
      ]
    }

Per-task keys: key (required, unique), title (required), assignee, body,
parents (list of keys), priority (int), workspace, goal (bool), goal_max_turns,
model, provider, max_runtime, skills (list), max_retries.

Examples:
    python kanban_graph.py --board my-project graph.json --dry-run
    python kanban_graph.py --board my-project graph.json --ids-out ids.json

Exit codes: 0 all created, 1 some cards failed or were skipped, 2 bad spec.
No dependencies beyond Python 3.8 and a ``hermes`` on PATH (or --hermes).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from typing import Dict, List, Optional

ID_RE = re.compile(r"\bt_[0-9a-f]{8}\b")


def topo_order(tasks: List[dict]) -> List[dict]:
    by_key = {t["key"]: t for t in tasks}
    done: List[str] = []
    seen = set()
    visiting = set()

    def visit(key: str) -> None:
        if key in seen:
            return
        if key in visiting:
            raise ValueError(f"dependency cycle through {key!r}")
        visiting.add(key)
        for parent in by_key[key].get("parents") or []:
            if parent not in by_key:
                raise ValueError(f"task {key!r} names unknown parent {parent!r}")
            visit(parent)
        visiting.discard(key)
        seen.add(key)
        done.append(key)

    for t in tasks:
        visit(t["key"])
    return [by_key[k] for k in done]


def build_cmd(hermes: str, board: str, task: dict, defaults: dict, parent_ids: List[str]) -> List[str]:
    get = lambda k, d=None: task.get(k, defaults.get(k, d))  # noqa: E731
    cmd = [hermes, "kanban", "--board", board, "create", task["title"], "--json"]
    if get("assignee"):
        cmd += ["--assignee", str(get("assignee"))]
    if get("body"):
        cmd += ["--body", str(get("body"))]
    if get("priority") is not None:
        cmd += ["--priority", str(int(get("priority")))]
    if get("workspace"):
        cmd += ["--workspace", str(get("workspace"))]
    if get("goal"):
        cmd += ["--goal"]
        if get("goal_max_turns"):
            cmd += ["--goal-max-turns", str(int(get("goal_max_turns")))]
    if get("model"):
        cmd += ["--model", str(get("model"))]
        if get("provider"):
            cmd += ["--provider", str(get("provider"))]
    if get("max_runtime"):
        cmd += ["--max-runtime", str(get("max_runtime"))]
    if get("max_retries") is not None:
        cmd += ["--max-retries", str(int(get("max_retries")))]
    for skill in get("skills") or []:
        cmd += ["--skill", str(skill)]
    for pid in parent_ids:
        cmd += ["--parent", pid]
    return cmd


def parse_id(stdout: str) -> Optional[str]:
    text = stdout.strip()
    try:
        data = json.loads(text)
        for key in ("id", "task_id"):
            if isinstance(data, dict) and data.get(key):
                return str(data[key])
    except json.JSONDecodeError:
        pass
    m = ID_RE.search(text)
    return m.group(0) if m else None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n", 1)[1])
    ap.add_argument("spec", help="JSON spec file (see format above)")
    ap.add_argument("--board", required=True, help="board slug; passed as --board on every call")
    ap.add_argument("--hermes", default="hermes", help="hermes executable (default: hermes on PATH)")
    ap.add_argument("--dry-run", action="store_true", help="print the commands, create nothing")
    ap.add_argument("--ids-out", help="write the key -> id map to this JSON file")
    ap.add_argument("--timeout", type=int, default=60, help="seconds per hermes call (default 60)")
    args = ap.parse_args(argv)

    try:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
        tasks = spec["tasks"]
        defaults = spec.get("defaults") or {}
        keys = [t["key"] for t in tasks]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate task keys")
        for t in tasks:
            if not t.get("title"):
                raise ValueError(f"task {t.get('key')!r} has no title")
        ordered = topo_order(tasks)
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
        print(f"bad spec: {e}", file=sys.stderr)
        return 2

    if not args.dry_run and shutil.which(args.hermes) is None:
        print(f"hermes executable not found: {args.hermes}", file=sys.stderr)
        return 2

    ids: Dict[str, str] = {}
    failed: List[str] = []
    for task in ordered:
        parents = task.get("parents") or []
        missing = [p for p in parents if p not in ids]
        if missing:
            print(f"SKIP {task['key']}: parent(s) not created: {', '.join(missing)}")
            failed.append(task["key"])
            continue
        cmd = build_cmd(args.hermes, args.board, task, defaults, [ids[p] for p in parents])
        if args.dry_run:
            print(" ".join(json.dumps(c) if " " in c else c for c in cmd))
            ids[task["key"]] = f"<id:{task['key']}>"
            continue
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            print(f"FAIL {task['key']}: hermes timed out after {args.timeout}s")
            failed.append(task["key"])
            continue
        tid = parse_id(r.stdout) if r.returncode == 0 else None
        if not tid:
            err = (r.stderr or r.stdout).strip().splitlines()
            print(f"FAIL {task['key']}: rc={r.returncode} {err[-1] if err else '(no output)'}")
            failed.append(task["key"])
            continue
        ids[task["key"]] = tid
        print(f"OK   {task['key']} -> {tid}" + (f" (parents: {', '.join(ids[p] for p in parents)})" if parents else ""))

    if args.ids_out and not args.dry_run:
        with open(args.ids_out, "w", encoding="utf-8") as f:
            json.dump(ids, f, indent=2)
        print(f"ids written to {args.ids_out}")
    if failed:
        print(f"{len(failed)} card(s) failed or skipped: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"{len(ids)} card(s) {'planned' if args.dry_run else 'created'} on board {args.board}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
