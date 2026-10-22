#!/usr/bin/env python3
"""Find files by name with voidtools Everything (es.exe), with a positive control first.

A bare es.exe call exits 0 with no output both when nothing matches and when the
call is broken (missing -instance, wrong path, unindexed drive). This wrapper
runs a probe for a file that must exist before it runs your query, so a broken
setup fails loudly instead of returning a quiet empty list.

Environment:
  ES_PATH       path to es.exe            (default C:\\tools\\es.exe)
  ES_INSTANCE   Everything instance name  (default 1.5a; set to "" for Everything 1.4)
  ES_CONTROL    positive-control query    (default: notepad.exe under C:/Windows)

Exit codes: 0 found, 1 no match (control passed), 2 control failed or es.exe missing.

Examples:
  python es_find.py --path "C:/Projects" "*.yaml"
  python es_find.py --count --path "C:/Projects" "*.yaml"
  python es_find.py --newest 10 --path "C:/Projects" "*.log"
  python es_find.py --regex "^settings\\.json$"
"""
import argparse
import os
import shutil
import subprocess
import sys

DEFAULT_ES = r"C:\tools\es.exe"
DEFAULT_INSTANCE = "1.5a"
CONTROL_PATH = "C:/Windows"
CONTROL_TERM = "notepad.exe"


def es_binary():
    p = os.environ.get("ES_PATH", "").strip() or DEFAULT_ES
    if os.path.isfile(p):
        return p
    found = shutil.which("es.exe") or shutil.which("es")
    if found:
        return found
    sys.stderr.write(
        f"es_find: es.exe not found at {p} and not on PATH. "
        "Install ES from voidtools and set ES_PATH.\n"
    )
    sys.exit(2)


def base_args(es):
    args = [es]
    inst = os.environ.get("ES_INSTANCE", DEFAULT_INSTANCE)
    if inst.strip():
        args += ["-instance", inst.strip()]
    return args


def run(args):
    try:
        cp = subprocess.run(args, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return 124, "", "es.exe timed out after 60 s"
    return cp.returncode, cp.stdout, cp.stderr


def positive_control(es):
    """Prove the index answers before trusting an empty result."""
    custom = os.environ.get("ES_CONTROL", "").strip()
    if custom:
        args = base_args(es) + ["-n", "1"] + custom.split()
    else:
        args = base_args(es) + ["-n", "1", "-path", CONTROL_PATH, CONTROL_TERM]
    rc, out, err = run(args)
    if rc != 0 or not out.strip():
        sys.stderr.write("es_find: positive control FAILED, not trusting any result.\n")
        sys.stderr.write(f"  command: {' '.join(args)}\n")
        if err.strip():
            sys.stderr.write(f"  stderr: {err.strip()}\n")
        elif not out.strip():
            sys.stderr.write("  es.exe printed nothing. Check ES_INSTANCE (1.5a vs empty), "
                             "that Everything is running, and that the control drive is indexed.\n")
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("terms", nargs="*", help="Everything search terms (name substrings, *.ext, ext:, size:, dm:, !folder\\)")
    ap.add_argument("--path", help="scope to this folder tree (es.exe -path, never -p)")
    ap.add_argument("--regex", help="regex on the file name (es.exe -r)")
    ap.add_argument("-n", "--max", type=int, default=50, help="max rows (default 50)")
    ap.add_argument("--count", action="store_true", help="print only the match count")
    ap.add_argument("--newest", type=int, metavar="N", help="N newest by date modified, with dates")
    ap.add_argument("--largest", type=int, metavar="N", help="N largest, with sizes")
    ap.add_argument("--files-only", action="store_true", help="add file: (skip folders)")
    ap.add_argument("--no-control", action="store_true", help="skip the positive control (not recommended)")
    ap.add_argument("--show-command", action="store_true", help="print the es.exe command line to stderr")
    a = ap.parse_args()

    if not a.terms and not a.regex:
        ap.error("give at least one search term or --regex")

    es = es_binary()
    if not a.no_control:
        positive_control(es)

    args = base_args(es)
    if a.count:
        args.append("-get-result-count")
    else:
        limit = a.newest or a.largest or a.max
        args += ["-n", str(limit)]
    if a.newest:
        args += ["-sort", "date-modified-descending", "-dm", "-date-format", "1"]
    if a.largest:
        args += ["-sort", "size-descending", "-size"]
    if a.path:
        args += ["-path", a.path]
    if a.regex:
        args += ["-r", a.regex]
    if a.files_only:
        args.append("file:")
    args += a.terms

    if a.show_command:
        sys.stderr.write("es_find: " + " ".join(args) + "\n")

    rc, out, err = run(args)
    if rc != 0:
        sys.stderr.write(err.strip() or f"es.exe exited {rc}\n")
        sys.exit(2)
    sys.stdout.write(out)
    if a.count:
        sys.exit(0 if out.strip() not in ("", "0") else 1)
    sys.exit(0 if out.strip() else 1)


if __name__ == "__main__":
    main()
