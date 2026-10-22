---
name: everything-search
description: "Find files by name on Windows in under a second with voidtools Everything's CLI (es.exe) instead of a slow recursive walk. Load this before any find, Get-ChildItem -Recurse, or ** glob over a drive, a home folder or a big tree, and whenever someone asks 'where is X', 'find all *.ext', 'do we have a file called', or 'list the biggest / newest files under'. Covers the flags that silently return nothing."
license: MIT
version: 0.1.0
---
# Everything search: ask the index, do not walk the disk

[Everything](https://www.voidtools.com/) keeps a live index of every file and folder name on the machine's NTFS volumes. Its command line client `es.exe` answers "where is this file" across whole drives in well under a second. A recursive `find`, `Get-ChildItem -Recurse` or a `**` glob over a drive root takes minutes, floods the tool output, and can time out the call. On a Windows box that has Everything, query the index first.

## When to use it

- Locating a file or folder by name, extension or name fragment when you do not know the folder: a config, a `*.sqlite`, a log, a script someone mentioned.
- Counting or listing files by extension, size or date across a big tree.
- Any time you are about to walk a drive root, `C:\Users\<you>`, or a top-level project folder.

Do not use it for **file contents**. The index holds names, sizes, dates and attributes only. `es.exe -r "TOKEN"` finds files whose *name* matches TOKEN, never files that contain it. Use ripgrep (`rg`) or your content-search tool for that. A small folder you already know is also fine to list directly.

## Setup

Two binaries ship with Everything and only one is scriptable:

| Binary | Role |
|---|---|
| `es.exe` (separate "ES" download from voidtools) | Command line client. Prints results to stdout. Script against this. |
| `Everything.exe` / `Everything64.exe` | The GUI and the indexing service. Its `-search`, `-regex`, `-path` flags drive the GUI window and return nothing to a caller. Only its non-search flags (`-rescan`, `-update`, `-create-file-list`) are useful from a script. |

Put `es.exe` somewhere fixed (this skill uses `C:\tools\es.exe`) and keep Everything running. The helper script in `scripts/` reads `ES_PATH` and `ES_INSTANCE` from the environment so you can point it anywhere.

## The command

```bash
C:/tools/es.exe -instance 1.5a -n 50 -path "C:/Projects" "*.yaml"
```

```powershell
& C:\tools\es.exe -instance 1.5a -n 50 -path "C:\Projects" "*.yaml"
```

Flags that matter:

- **`-instance 1.5a`**: required on every call when the installed Everything is the 1.5 alpha (service name `Everything (1.5a)`). Without it `es.exe` prints `Error 8: Everything IPC window not found. Please make sure Everything is running.` and exits 8, even though Everything is running. Everything 1.4 uses no instance name, so drop the flag there. Check with `es.exe -instance 1.5a -get-everything-version`.
- **`-path <dir>`** scopes the search to a subtree. Forward slashes work from any shell and avoid the `"C:\"` trailing-backslash quoting mess in Git Bash.
- **`-p` is not a scope flag.** It is `-match-path`: the search terms match the *full path*, so `-p "C:/Windows" system32` returns every file *under* System32, not files named system32 (33,015 rows vs 841 on one machine). Use `-path` for scoping.
- `-n <num>` limits rows. `-get-result-count` prints only the count. `-r <regex>` switches to regex. `-sort date-modified-descending` puts newest first. `-csv -size -dm` adds size and date columns; `-date-format 1` gives ISO 8601.
- Everything's own search syntax works inside the terms: `file:` (files only), `folder:`, `ext:py;ps1`, `"size:>1gb"`, `dm:today`, `dm:last7days`, `!node_modules\` (exclude a folder). Quote anything with `>` or `<` or your shell treats it as a redirect. Full list in [references/query-syntax.md](references/query-syntax.md).
- **Do not use `/a-d` or `/ad` from Git Bash.** MSYS rewrites a leading `/` argument into a path and the query returns 0 rows with no error (the same query from PowerShell returns the real count). Use `file:` or `folder:` instead; they work in every shell.

Examples:

```bash
C:/tools/es.exe -instance 1.5a "settings.json"                                  # anywhere on the box
C:/tools/es.exe -instance 1.5a -n 20 -r "\.sqlite$"                             # regex on the name
C:/tools/es.exe -instance 1.5a -get-result-count -path "C:/Projects" "*.yaml"   # count only
C:/tools/es.exe -instance 1.5a -n 10 -path "D:/" file: "size:>2gb"              # big files
C:/tools/es.exe -instance 1.5a -n 10 -sort date-modified-descending -path "C:/Projects" "*.log"
C:/tools/es.exe -instance 1.5a -path "C:/Projects" "*.py" "!node_modules\\" "!.venv\\"
```

## An empty result is not proof

`es.exe` exits 0 with no output when nothing matches, and it exits 0 with no output when the query is broken in a way it does not detect (wrong `-path` spelling, an MSYS-mangled argument, a drive that is not indexed). So zero rows means "check the query", never "the file does not exist".

Before trusting an empty result, run the same flags against a file you know is there (a **positive control**):

```bash
C:/tools/es.exe -instance 1.5a -n 1 -path "C:/Windows" notepad.exe
```

It must print `C:\Windows\notepad.exe`. If it does not, the call is broken (missing `-instance`, Everything stopped, wrong `ES_PATH`) and you fall back to a scoped walk. Terms are substrings, so an unscoped `es.exe` also matches `windres.exe`; scope or anchor with regex when the name is short.

## When to fall back to a walk

- `es.exe` errors, or the positive control returns nothing.
- The path is not indexed. Network shares (UNC paths, mapped drives) and FAT or exFAT removable media are only in the index if someone added them as indexed folders in Everything's options. Assume a share is not indexed until a positive control on that share succeeds.
- You need file contents (use `rg`) or per-file processing as you go.
- The machine has no `es.exe` (Linux, macOS, a VM without Everything).

A scoped walk is fine when it is scoped: `Get-ChildItem -Recurse -Filter *.yaml C:\Projects\one-repo` over one repo is seconds, not minutes.

## Helper script

`scripts/es_find.py` wraps the command: it reads `ES_PATH` (default `C:\tools\es.exe`) and `ES_INSTANCE` (default `1.5a`, set it empty for Everything 1.4), runs a positive control first, and only then runs your query, so a broken setup fails loudly instead of returning a quiet empty list.

```bash
python scripts/es_find.py --path "C:/Projects" "*.yaml"
python scripts/es_find.py --count --path "C:/Projects" "*.yaml"
python scripts/es_find.py --newest 10 --path "C:/Projects" "*.log"
python scripts/es_find.py --help
```

```powershell
$env:ES_INSTANCE = ""            # Everything 1.4: no instance name
python scripts\es_find.py --path "C:\Projects" "*.yaml"
```

Exit codes: 0 found, 1 no match (control passed), 2 control failed or es.exe missing.

## Agent hook idea

Agents keep reaching for the walk out of habit. A PreToolUse hook on your shell tool can catch that: when the command text matches `find <drive-or-home> -name`, `Get-ChildItem -Recurse` without a narrow `-Path`, `ls -R` on a drive root, or a `**` glob over a drive, the hook prints a one-line suggestion with the equivalent `es.exe -instance 1.5a -path ... "<pattern>"` command and lets the original command run. Suggest, never block: the walk is still right for unindexed shares and content searches. The hook needs no state and reads only the command string, so it is a few lines of Python or PowerShell on stdin.

## Checklist before you say "the file does not exist"

1. Query used `-path`, not `-p`, and included `-instance` if Everything is 1.5a.
2. No `/a-d` style argument from Git Bash.
3. Positive control on the same drive returned the known file.
4. The drive or share is actually indexed.
5. If any of those failed, run a scoped walk and say which tool found nothing.

---
Part of [agent-skills](https://github.com/dexteon/agent-skills) by [CyberAutomations](https://cyberautomations.com).
