# Process control on Windows from an agent shell

Finding, inspecting, and killing processes is full of quiet traps on the Git Bash
layer. Every block is marked with its shell.

## Kill only by a captured PID

Never kill by a command-line match. A filter like `*server.py*` or `*node*` matches
many unrelated processes, and a generic entry filename (for example `server.py`) is
shared by all sorts of tools. Killing by match has taken down unrelated live services.

Capture the PID when you start the process, and stop only that id:

```powershell
$p = Start-Process -WindowStyle Hidden -FilePath "python" `
  -ArgumentList '"C:/Users/<you>/scratch/job.py"' -PassThru
$p.Id | Out-File "C:/Users/<you>/scratch/job.pid"
# later, stop exactly that process
Stop-Process -Id (Get-Content "C:/Users/<you>/scratch/job.pid")
```

If a PID is genuinely unavailable, print the full match list and confirm before killing
anything. Never kill a browser from a script: ask the human to close it.

## Finding a process is the same trap in reverse

`pgrep -f foo` and `ps -ef | grep foo` match the searching shell's own command line.
A process that is actually dead looks alive, with a new PID on each check (the grep
itself). Verify a service by its effect, not by a cmdline match:

```bash
netstat -ano | grep :8080     # is the port actually listening?
# then map the listening PID to its command line in PowerShell
```

```powershell
Get-CimInstance Win32_Process -Filter "ProcessId = 1234" |
  Select-Object ProcessId, CommandLine | Format-List
```

## Why ps/ss miss detached processes, and what to use

Git Bash `ps` enumerates MSYS processes; a Windows process launched detached (through
`Start-Process` or a redirect) may not appear, and `ss -tlnp` often returns nothing for
it. Use Windows tooling:

- Port to PID: `netstat -ano | grep :PORT`
- PID to command line: `Get-CimInstance Win32_Process` (prefer this over `tasklist`,
  whose `/FI` arguments get mangled by path conversion through bash, and over
  `Get-Process`, which does not show the command line).

## taskkill flag form

`taskkill` wants slash-flags, which bash rewrites. Use the doubled-slash form and never
silence its stderr:

```bash
taskkill //F //PID 1234        # //F and //PID reach taskkill as /F /PID
```

A single-slash `taskkill /F /PID` through bash can become a mangled path argument and
fail with "Invalid argument/option". If you redirect that failure to the null device,
the kill fails silently while the script reports success. Echo the result instead.

## Elevation

System-level PowerShell cmdlets (`Set-NetIPInterface`, `Register-ScheduledTask` as
SYSTEM, `auditpol /set`) return "Access is denied" from a non-elevated agent shell.
Either ask the human to run it in an elevated terminal, or launch an elevated child
that does the work and writes its result to a file you can read back:

```powershell
Start-Process pwsh -Verb RunAs -ArgumentList `
  '-NoProfile','-ExecutionPolicy','Bypass','-File','C:/Users/<you>/scratch/task.ps1'
```
