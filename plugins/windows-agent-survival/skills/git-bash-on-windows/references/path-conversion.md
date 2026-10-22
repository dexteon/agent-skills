# MSYS path conversion and native path forms

Git Bash (MSYS2) rewrites arguments that look like POSIX paths into Windows paths
before the target program runs. This helps native tools and breaks slash-flags. Every
command block below is marked with its shell.

## Verified behavior on a Windows host

```bash
cmd //c echo /c/foo
# -> C:/foo            the /c/foo argument was rewritten to a Windows path
MSYS_NO_PATHCONV=1 cmd //c echo /c/foo
# -> '/foo' is not recognized ...   conversion is suppressed, cmd sees /c then /foo
cmd //c echo //F //PID
# -> /F /PID           a doubled leading slash collapses to one and is NOT rewritten
```

The doubled-slash collapse is why a Windows tool that wants `/F /PID` is written
`//F //PID` through bash.

## The two ways to pass slash-flags to Windows tools

Windows tools (`taskkill`, `schtasks`, `sc`, `net`, `reg`, `wmic`) take flags that
begin with a slash. Through bash you need one of:

```bash
# A) suppress conversion for this one command
MSYS_NO_PATHCONV=1 schtasks /Query /TN "MyTask" /V /FO LIST

# B) double every leading slash
taskkill //F //PID 1234
```

Do not combine them. With `MSYS_NO_PATHCONV=1` set, a doubled slash reaches the program
literally (`//F`), which it rejects. Also never silence the tool's own stderr (do not
redirect to the null device): a mangled-flag failure then looks like success while
nothing happened. Echo the result.

## Backslashes in CLI arguments disappear

Bash consumes backslashes in an unquoted or weakly quoted argument. A path like
`--out C:\logs\run.db` arrives with the backslashes stripped, so the tool happily
creates a relative file with a mashed name instead of erroring. The run "succeeds," the
expected file never exists, and the report is wrong.

```bash
# wrong: backslashes eaten
mytool --out C:\logs\run.db
# right: forward-slash Windows path, then verify
mytool --out C:/logs/run.db
ls -l C:/logs/run.db   # confirm before reporting the artifact as produced
```

## Native tools want forward-slash Windows paths

`git`, `node`, `python`, `gh`, `openssl` are native Windows executables. They want a
forward-slash Windows path, like `C:/Users/<you>/project`. A POSIX `/c/Users/...` path
can fail for a native exe with a "cannot find" error, even though the bash `cd` builtin
accepts the same string.

The sharpest version of this: `$HOME` in Git Bash expands to `/c/Users/<you>`. Handing
that to a native tool can corrupt it (a duplicated drive segment, module not found).

```bash
# wrong: $HOME expands to a POSIX form a native tool mishandles
node "$HOME/tools/app.js"
# right: literal forward-slash Windows path
node "C:/Users/<you>/tools/app.js"
```

Rule of thumb: the bash `cd` builtin and bash's own `find`/`ls` accept POSIX
(`/c/...`, `$HOME`) forms; native executables want the literal `C:/...` forward-slash
form. If one path form fails for a native tool, switch to the literal `C:/...` form
rather than retrying the same string.

## schtasks through bash

`schtasks /delete /tn "T" /f` becomes `schtasks C:/Program Files/Git/delete ...` under
path conversion and fails with "Invalid argument/option". Use `MSYS_NO_PATHCONV=1`, or
the PowerShell equivalent:

```powershell
Unregister-ScheduledTask -TaskName "T" -Confirm:$false
```
