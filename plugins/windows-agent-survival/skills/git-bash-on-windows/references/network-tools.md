# Running nmap from Git Bash on Windows

Generic notes for using nmap on a Windows host through Git Bash. This covers only the
tool mechanics: the driver, privileges, flag forms, and which invocation survives the
MSYS layer. Choosing targets and interpreting results are out of scope.

## Npcap is required

nmap on Windows needs the Npcap packet-capture driver installed. Without it, raw-packet
and interface operations fail. Install Npcap first; a plain `nmap --version` runs
without it, but a raw scan will not.

## Raw scans need elevation

A raw scan (SYN scan, `-sS`) needs an Administrator shell. From a non-elevated agent
shell it fails on privilege. A TCP connect scan (`-sT --unprivileged`) runs without
elevation and is the gentler choice. To run an elevated scan, launch an elevated child
process that the human approves:

```powershell
Start-Process pwsh -Verb RunAs -ArgumentList `
  '-NoProfile','-ExecutionPolicy','Bypass','-File','C:/Users/<you>/scratch/scan.ps1'
```

The elevated window runs independently of your shell; you see it spawn but not its live
output, so write results to a file and read them back.

## Interface flag: -e, not -i

On Windows nmap builds, `-e <interface>` selects the interface and binds the raw
socket. `-i` means input-file mode, so `-i eth0` fails with an input-file error
("Failed to open input file eth0"). List interfaces first:

```bash
nmap --iflist
```

Then pass the chosen interface with `-e`.

## Path conversion mangles native nmap arguments

Because nmap is a native Windows exe, MSYS path conversion can rewrite its arguments
(interface names and flags that look like paths) before nmap sees them. The reliable
way to pass native arguments is to put the full command in a `.bat` with native paths
and run that batch, so nmap receives its arguments unmangled:

```bash
cmd //c "C:/Users/<you>/scratch/run_scan.bat"
```

Alternatively, prefix a single command with `MSYS_NO_PATHCONV=1` to stop the rewrite.
As always, verify the scan produced the output file you expected rather than trusting
the exit code.
