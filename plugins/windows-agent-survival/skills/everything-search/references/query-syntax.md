# es.exe flags and Everything search syntax

Everything is the index and GUI from voidtools; `es.exe` is the separate command line client ("ES"). The flags below are from `es.exe -h` on ES 1.1.0.30 against Everything 1.5.0.1391. The search terms use Everything's own syntax, so anything you can type into the GUI search box works as a term on the command line.

## Connection

| Flag | Meaning |
|---|---|
| `-instance <name>` | Talk to a named Everything instance. The 1.5 alpha installs as instance `1.5a`, so every call needs `-instance 1.5a` or you get `Error 8: Everything IPC window not found` (exit code 8). Everything 1.4 has no instance name; omit the flag. |
| `-get-everything-version` | Print the version of the running Everything service. Good first probe. |
| `-version` | Print the ES client version. |

## Scope

| Flag | Meaning |
|---|---|
| `-path <dir>` | Match only inside this folder tree. This is the scope flag. Forward slashes are fine. |
| `-parent <dir>` | Match only direct children of this folder (no recursion). |
| `-parent-path <dir>` | Match inside the parent of the given path. |
| `-p`, `-match-path` | Not a scope flag. Makes the terms match the full path and name, so a term hits every file under any folder whose path contains it. |

## Matching

| Flag | Meaning |
|---|---|
| `-r <regex>`, `-regex` | Regex on the name (or the full path with `-p`). Anchor with `^` and `$` for exact names. |
| `-i`, `-case` | Case sensitive. Default is case insensitive. |
| `-w`, `-whole-word` | Whole words only. |
| `-a`, `-diacritics` | Match diacritical marks. |

## Limits and sorting

| Flag | Meaning |
|---|---|
| `-n <num>`, `-max-results` | Show at most this many rows. Always set it on a broad query. |
| `-o <offset>` | Start at this offset (paging). |
| `-get-result-count` | Print only the number of matches. |
| `-sort <key>[-ascending|-descending]` | Keys: `name`, `path`, `size`, `extension`, `date-created`, `date-modified`, `date-accessed`, `attributes`, `run-count`, `date-recently-changed`, `date-run`. Example: `-sort date-modified-descending`. |
| `-s` | Sort by full path. |

## Output columns and formats

| Flag | Meaning |
|---|---|
| `-size`, `-dm`, `-dc`, `-da`, `-ext`, `-attribs` | Add the size, date modified, created, accessed, extension or attributes column. |
| `-name`, `-path-column`, `-full-path-and-name` | Choose the name columns. |
| `-csv`, `-tsv`, `-txt`, `-efu`, `-m3u`, `-m3u8` | Output format. `-csv` with `-size -dm` is the easiest to parse. |
| `-size-format <n>` | 0 auto, 1 bytes, 2 KB, 3 MB. |
| `-date-format <n>` | 0 auto, 1 ISO 8601, 2 FILETIME, 3 ISO 8601 UTC. |
| `-export-csv <file>`, `-export-txt <file>` | Write results to a file instead of stdout. |

## DIR style switches (avoid from Git Bash)

`/ad` (folders only), `/a-d` (files only), `/a[RHSDAVNTPLCOIE]` attribute filters, `/on` `/os` `/od` sorts. These work from PowerShell and cmd. From Git Bash, MSYS rewrites a leading `/` argument into a Windows path and the query silently returns 0 rows. Use the search-syntax equivalents below instead; they work from every shell.

## Everything search syntax inside the terms

Terms are substring matches on the name unless a modifier says otherwise. Multiple terms are ANDed. Quote any term that contains `>`, `<`, `|` or spaces, or the shell eats it. Every term below was run against a live Everything 1.5.0.1391 index while writing this page.

| Term | Meaning |
|---|---|
| `file:` | Files only (replaces `/a-d`). |
| `folder:` | Folders only (replaces `/ad`). |
| `ext:py;ps1` | By extension, semicolon separated. |
| `*.log` | Wildcard on the whole name. `*` any run, `?` one character. |
| `"size:>1gb"` | Size filter. Units `kb`, `mb`, `gb`. Ranges `size:100mb..1gb`. Also `size:empty`, `size:large`. |
| `dm:today` | Date modified. Also `dm:yesterday`, `dm:last7days`, `dm:lastmonth`, `dm:2026`, `dm:2026-10`, `"dm:>2026-10-01"`. |
| `dc:`, `da:` | Date created, date accessed, same forms. |
| `!node_modules\` | Exclude anything with this path component (the trailing backslash means "folder"). Chain several. |
| `parent:C:\x` | Direct children of a folder (same as `-parent`). |
| `path:` | Match against the path (same as `-p`). |
| `regex:` | Regex for one term (same as `-r`). |
| `case:` | Case sensitive for one term. |
| `wholeword:` | Whole word for one term. |
| `a|b` | OR, with no spaces around the bar. Group with `< >`: `"<notepad.exe|calc.exe>" ext:exe`. Written as `a | b` with spaces it returns 0 rows from every shell. |
| `attrib:H` | Attribute filter (H hidden, S system, R read only, D directory). |
| `empty:` | Empty folders. |
| `dupe:` | Files whose name appears more than once in the index. |

## Combinations that come up

```bash
# newest 10 logs in a tree, with dates
es.exe -instance 1.5a -n 10 -sort date-modified-descending -dm -date-format 1 -path "C:/Projects" "*.log"

# everything over 2 GB on one drive
es.exe -instance 1.5a -n 20 -sort size-descending -size -path "D:/" file: "size:>2gb"

# python files in a repo, skipping virtualenvs and node_modules
es.exe -instance 1.5a -path "C:/Projects/app" ext:py "!.venv\\" "!node_modules\\"

# exact filename, anywhere, regex anchored
es.exe -instance 1.5a -r "^settings\.json$"

# how many sqlite files were touched today
es.exe -instance 1.5a -get-result-count "*.sqlite" dm:today
```

## What the index does not hold

- File contents. Use ripgrep.
- Anything on a volume that is not indexed: network shares, mapped drives, FAT or exFAT media, unless the owner added them as indexed folders in Everything's options. A positive control on that volume tells you.
- Changes that happened in the last moment on a folder being indexed from scratch; NTFS volumes update live, added folders rescan on a schedule.
