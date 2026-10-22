---
name: git-bash-on-windows
description: "Load when an AI coding agent (Claude Code, Hermes, or any other) runs shell commands on Windows through Git Bash or MSYS2, with PowerShell alongside. Triggers: Windows, Git Bash, MSYS, MSYS2, PowerShell, pwsh, path mangling, 'command not found', exit code looks wrong, command fake-succeeded, process won't die, background job died, heredoc broke, backslash disappeared."
license: MIT
version: 0.1.0
---

# Git Bash on Windows: survival guide for coding agents

You are an agent running shell commands on Windows. Your "bash" is Git Bash (MSYS2),
a POSIX layer bolted onto Windows. Most traps here do not throw an error. They let a
command look like it succeeded while it quietly did the wrong thing, and your "done"
report is then wrong. This guide names each trap with its symptom, its cause, and a
copy-pasteable fix. Mark every command block with its shell (```bash or ```powershell).

Read the Top traps table before your first command on a Windows host.

## Top traps (read first)

| # | Symptom | Cause | Fix |
|---|---------|-------|-----|
| 1 | An arg like `/c/foo` or `/FI` turns into `C:/foo` on the way to a program | MSYS rewrites anything that looks like a POSIX path | Prefix `MSYS_NO_PATHCONV=1`, or double the slash (`//FI`) |
| 2 | `cd /d somedir` fails with `cd: too many arguments` | `/d` is a cmd.exe flag, not a bash one | Use `git -C DIR`, `make -C DIR`, `npm --prefix DIR`; or `cd DIR` with no `/d` |
| 3 | A CLI arg like `--out C:\logs\x.db` makes a weirdly named relative file | Bash eats the backslashes before the program sees them | Pass forward-slash paths: `--out C:/logs/x.db`, then confirm the file exists |
| 4 | A pipeline "fails" (exit 1) though the real work succeeded | Exit code is the LAST stage; `grep -c` with 0 matches is exit 1 | Check the real stage's result; do not let `|| echo` mask failures |
| 5 | A Python heredoc writes a corrupt file from `"C:\\foo"` | The Bash tool strips one backslash level, so `\\f` arrives as `\f` | Build backslashes with `chr(92)`, or write the script with your editor tool |
| 6 | A 3 line edit shows as a whole-file diff | CRLF file read as LF and written back as LF | Preserve line endings; write with `newline="\r\n"` on a CRLF file |
| 7 | `str.replace(...)` patch "succeeds" but the file is unchanged | `replace` is a no-op when the pattern is absent | Put `assert old in text` next to every replace, or use an editor tool |
| 8 | A `.ps1` scheduled task or script silently exits 1 | `#Requires -Version 7.0` under `powershell.exe` (5.1) refuses to run | Run it with `pwsh` (7.x), or drop the `#Requires` if PS7 is not needed |
| 9 | You kill a PID by name and take down an unrelated service | A common entry filename (for example `server.py`) matches many processes | Capture the PID when you start it; kill only that PID |
| 10 | A background job dies the moment the call returns | `nohup ... &` from an agent shell is tied to the call | Launch detached with `Start-Process -WindowStyle Hidden` and redirect output |

## Path conversion (MSYS rewriting your arguments)

MSYS tries to be helpful: any argument that looks like a POSIX path gets rewritten to a
Windows path before the target program sees it. This is great for native tools and
terrible for flags that start with a slash.

Verified on this host:

```bash
cmd //c echo /c/foo
# prints: C:/foo      (the /c/foo argument was rewritten)
MSYS_NO_PATHCONV=1 cmd //c echo /c/foo
# the rewrite is suppressed
cmd //c echo //F //PID
# prints: /F /PID     (a doubled leading slash collapses to one, no rewrite)
```

So a Windows tool that wants slash-flags (`taskkill /F /PID`, `schtasks /Query`,
`sc`, `net`) gets mangled when you type the single-slash form through bash. Two fixes:

```bash
# Option A: suppress conversion for this command
MSYS_NO_PATHCONV=1 schtasks /Query /TN "MyTask" /V /FO LIST
# Option B: double every leading slash so bash leaves it alone
taskkill //F //PID 1234
```

Do NOT mix them (do not write `MSYS_NO_PATHCONV=1 taskkill //F`): with conversion off,
the doubled slash reaches the program literally. Pick one.

Native tools (`git`, `node`, `python`, `gh`) want forward-slash Windows paths, like
`C:/Users/<you>/project`. A POSIX `/c/Users/...` path can fail for a native exe even
though the bash `cd` builtin accepts it. See `references/path-conversion.md` for the
full set, including the `$HOME` to `/c/Users/<you>` expansion that corrupts a native
module path.

## Exit codes and silent fake-success

- A pipeline reports the exit code of its LAST stage. `something | grep -c foo` that
  finds nothing exits 1 even though `something` ran fine. Judge success by the real
  work, not the tail of the pipe.
- A `cmd || echo fallback` can leave the result's exit code as the `echo` (0). The
  command failed; the status says success. Avoid wrapping a command whose status you
  care about in `|| echo`.
- `curl -o file URL` can write a 0 byte file on this layer while `curl URL > file`
  works. After any download, check `wc -c file` before you trust it.
- Verify the artifact, not the status. After a build, install, or clone, confirm the
  durable thing exists on disk (`ls`, `test -f`). An exit code of 0 means "did not
  crash," not "produced what I expected."

## Heredocs, backslashes, and writing files

Prefer your editor or write tool for any file whose bytes must land exactly. Heredocs
fail in several quiet ways on this stack.

- The Bash tool strips one level of backslash before bash runs. Inside a
  `python - <<'PY'` block, `"C:\\foo"` arrives as `"C:\foo"`, and Python reads `\f` as
  a form-feed, `\b` as a backspace. Verified: `python -c 'print(repr("D:\\bin"))'`
  prints `'D:\x08in'` (the `\b` became a backspace). You usually get only a
  `SyntaxWarning: invalid escape sequence`, and the file is already corrupt. Fix: build
  separators with `chr(92)` and join, or write the script to a file with your editor
  tool and run the file.
- An apostrophe inside a `<<'EOF'` body can abort the shell with
  `unexpected EOF while looking for matching '`.
- A large `cat > file <<'EOF'` can be refused by a pre-tool hook while a plain
  `echo > file` to the same path is allowed. The content never lands.

Two patch-safety rules that save silent no-ops:

- `str.replace(old, new)` does nothing when `old` is absent, then your script prints
  its success line and writes the file unchanged. Put `assert old in text` next to
  every replace, or use an editor tool that fails loudly on a missing match.
- Editing a CRLF file with an LF-only tool rewrites every line. Text-mode reads
  normalize to LF; writing back without `newline="\r\n"` persists LF, so a three-line
  change shows as a full-file diff and a diff-scanning gate flags pre-existing content
  as new. Keep the original's endings; check `git diff --numstat` shows only your lines.

## PowerShell next to Git Bash

- `powershell` is Windows PowerShell 5.1; `pwsh` is PowerShell 7.x. Verified on this
  host: 5.1 and 7.6.7 both present. A script with `#Requires -Version 7.0` run under
  `powershell.exe` refuses silently and the caller sees only exit 1. Check the first
  lines (`head -5 script.ps1 | grep -i requires`) and use `pwsh` for 7.x scripts.
- `$`-prefixed tokens (`$_`, `$env:FOO`, `$Matches`) in an inline
  `powershell -Command "..."` get eaten by bash first and the command fails to parse.
  Write any variable-heavy PowerShell to a `.ps1` file and run it:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "C:/Users/<you>/scratch/diag.ps1"
```

- When an agent hands a human a one-line command, state the shell. A `!`-style
  one-liner has run under PowerShell when a POSIX form was meant, failing at `export`.
  PowerShell also evaluates any `$( ... )` before the rest runs, so a command that
  prompts inside `$( )` can execute and then have its result discarded. Prefer a form
  valid in both shells, or label it and use that shell's syntax
  (`$env:X = "v"; cmd` for PowerShell).

## Process control

- Kill by a PID you captured at launch, never by a command-line match. A filter like
  `CommandLine -like '*server.py*'` matches many unrelated processes, and `server.py`
  is a very common entry filename. Record the PID when you spawn the process and stop
  only that id.
- Reading is the same trap: `pgrep -f foo` and `ps | grep foo` match the searching
  shell's own command line, so a dead process looks alive with a fresh PID each check.
  Verify by effect (a port open, a log growing), not by a cmdline match.
- Git Bash `ps` and `ss` often do not show detached Windows processes. Use
  `netstat -ano | grep :PORT` for port to PID, then PowerShell
  `Get-CimInstance Win32_Process` for the command line. Prefer `Get-CimInstance` over
  `tasklist` under bash: `tasklist /FI` arguments get mangled by path conversion.
- Never kill a browser process from a script. Ask the human to close it.

Full command forms, the daemon-discovery pattern, and the `taskkill //F` detail are in
`references/process-control.md`.

## Background jobs

`nohup cmd &` launched from an agent shell dies when the tool call returns. Launch a
long job detached, from PowerShell, with redirected output, and capture its PID:

```powershell
$p = Start-Process -WindowStyle Hidden -FilePath "python" `
  -ArgumentList '"C:/Users/<you>/scratch/job.py"' `
  -RedirectStandardOutput "C:/Users/<you>/scratch/job.out" `
  -RedirectStandardError  "C:/Users/<you>/scratch/job.err" -PassThru
$p.Id | Out-File "C:/Users/<you>/scratch/job.pid"
```

Then monitor a progress counter, not a log grep. A hung job writes no log lines, and
silence reads as healthy. A full-screen TUI will redraw over your console and force a
manual interrupt, so always pass the tool's no-UI flag (for example `--no-ui`) when one
exists.

## When a tool keeps failing, stop

If a tool returns the same failure across repeated calls, do not keep firing it, and do
not fan it out in parallel to "try harder." One failure means investigate the cause and
retry once; two or more means the tool or its setup is broken, so switch engines or fix
the setup. Probe one cheap case before a batch. See `references/loop-prevention.md`.

## Network tools (nmap from Git Bash)

nmap needs the Npcap driver installed on Windows, and a raw scan needs an elevated
(Administrator) shell. On Windows builds, `-e <interface>` selects the interface;
`-i` means input-file mode, so `-i eth0` fails with an input-file error. Path
conversion also mangles native nmap arguments through bash. See
`references/network-tools.md`.

---
Part of [agent-skills](https://github.com/dexteon/agent-skills) by [CyberAutomations](https://cyberautomations.com).
