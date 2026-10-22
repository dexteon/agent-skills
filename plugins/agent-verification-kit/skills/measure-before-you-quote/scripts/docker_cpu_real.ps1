# docker_cpu_real.ps1: read `docker stats` CPU correctly. Read-only.
# It runs `docker info`, `docker stats --no-stream` and `docker inspect` only.
# It never starts, stops, updates or recreates a container.
#
# Why: docker stats CPUPerc is a percentage of ONE CPU, not of the machine.
# A photo-indexing container once read 200.79% and was blamed for host lag.
# Its compose cap was cpus: "2.0", so 200.79% meant "sitting exactly at its
# own 2-core cap", about 6% of a 32-thread host. The healthiest reading possible.
#
# Two denominators, two different questions:
#   share of Docker's VM   = cores_used / (docker info NCPU)
#                            (on Docker Desktop this is the VM's CPU count, often
#                             smaller than the host's)
#   share of the host      = cores_used / host logical processors
# And one more that decides "hog or healthy":
#   share of its own cap   = cores_used / (NanoCpus / 1e9)  (0 = uncapped)
#
# Usage (PowerShell 5.1 or 7, Docker CLI on PATH):
#   powershell -NoProfile -File docker_cpu_real.ps1                 # 3 snapshots, top 15
#   powershell -NoProfile -File docker_cpu_real.ps1 -Samples 5 -Top 10
#   pwsh -NoProfile -File docker_cpu_real.ps1 -Help
param(
    [int]$Samples = 3,
    [int]$Top = 15,
    [switch]$Help
)
if ($Help) {
    Get-Content $PSCommandPath | Select-Object -First 21 | ForEach-Object { $_ -replace '^# ?', '' }
    exit 0
}
$ErrorActionPreference = 'Stop'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "docker CLI not found on PATH"
    exit 1
}

$ncpu = [int](docker info --format '{{.NCPU}}')
$hostLP = [Environment]::ProcessorCount
Write-Output ("Docker VM CPUs (docker info NCPU): {0}   host logical processors: {1}" -f $ncpu, $hostLP)
Write-Output ("Taking {0} snapshot(s) of docker stats (each one is itself a ~1-2 s sample)..." -f $Samples)

$byName = @{}
for ($i = 0; $i -lt $Samples; $i++) {
    $lines = docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}'
    foreach ($l in $lines) {
        $p = $l.Split('|')
        if ($p.Count -lt 3) { continue }
        $pct = [double]($p[1].TrimEnd('%'))
        if (-not $byName.ContainsKey($p[0])) { $byName[$p[0]] = @{ cpu = @(); mem = $p[2] } }
        $byName[$p[0]].cpu += $pct
        $byName[$p[0]].mem = $p[2]
    }
}

if ($byName.Count -eq 0) {
    Write-Output "No running containers reported by docker stats."
    exit 0
}

$rows = foreach ($name in $byName.Keys) {
    $vals = $byName[$name].cpu | Sort-Object
    $med = $vals[[int][math]::Floor(($vals.Count - 1) / 2)]
    $insp = (docker inspect $name --format '{{.HostConfig.NanoCpus}} {{.HostConfig.CpuQuota}} {{.HostConfig.CpuPeriod}}').Split(' ')
    $nano = [double]$insp[0]; $quota = [double]$insp[1]; $period = [double]$insp[2]
    $cap = 0.0
    if ($nano -gt 0) { $cap = $nano / 1e9 } elseif ($quota -gt 0 -and $period -gt 0) { $cap = $quota / $period }
    $cores = $med / 100.0
    $ofCap = if ($cap -gt 0) { '{0,6:N0}%' -f (100 * $cores / $cap) } else { 'uncapped' }
    $flag = ''
    if ($cap -gt 0 -and $cores -ge 0.9 * $cap) { $flag = 'AT OWN CAP (limit working; not a host problem)' }
    [pscustomobject]@{
        Container      = $name
        'CPUPerc med'  = ('{0:N1}%' -f $med)
        'min-max'      = ('{0:N1}-{1:N1}' -f $vals[0], $vals[-1])
        Cores          = [math]::Round($cores, 2)
        'of DockerVM'  = ('{0:N1}%' -f (100 * $cores / $ncpu))
        'of host'      = ('{0:N1}%' -f (100 * $cores / $hostLP))
        'cap cores'    = $(if ($cap -gt 0) { $cap } else { '-' })
        'of cap'       = $ofCap
        Mem            = $byName[$name].mem
        Note           = $flag
        _sort          = $med
    }
}
$rows | Sort-Object _sort -Descending | Select-Object -First $Top -Property * -ExcludeProperty _sort | Format-Table -AutoSize | Out-String -Width 220
Write-Output "Before blaming a container: a value near its own cap is the cap working. If a host metric"
Write-Output "moved after you touched something, re-list the top consumers and confirm the delta is yours."
