# Reading Docker and Windows metrics correctly (optional: platform-specific)

This section applies when the thing you are measuring runs in Docker, especially Docker Desktop on Windows, or when you are reading Windows host memory. The general rule it illustrates (know the denominator before you quote a percentage) applies everywhere.

## 1. `docker stats` CPU is a percentage of one CPU

`CPUPerc` is per core: 200% means two cores' worth. Convert to cores by dividing by 100, then pick the denominator that matches the question:

| Question | Denominator |
|---|---|
| share of Docker's VM (Docker Desktop, WSL2 or HyperKit) | `docker info --format '{{.NCPU}}'` |
| share of the physical machine | host logical processors (`[Environment]::ProcessorCount` on Windows, `nproc` elsewhere) |
| hog or healthy | the container's own cap: `docker inspect <c> --format '{{.HostConfig.NanoCpus}}'` divided by 1e9 (0 = uncapped), or `CpuQuota / CpuPeriod` |

A container sitting near its own cap is the limit working, not a host problem. Go templates have no arithmetic (`{{div}}` fails), so divide in the shell.

Incident: a photo-indexing container read `200.79%` and was blamed for lagging the machine. Its compose file had `cpus: "2.0"`, so it sat exactly at its 2-core cap, about 6.3% of a 32-thread host. The healthiest possible reading.

`scripts/docker_cpu_real.ps1` takes N `docker stats` snapshots (each is itself a 1 to 2 s sample), reports the median per container, and prints all three shares plus an "AT OWN CAP" flag:

```powershell
powershell -NoProfile -File scripts\docker_cpu_real.ps1 -Samples 5 -Top 10
```

The same arithmetic in a POSIX shell:

```bash
NCPU=$(docker info --format '{{.NCPU}}')
docker stats --no-stream --format '{{.Name}} {{.CPUPerc}}' | while read -r name pct; do
  cores=$(echo "${pct%\%} / 100" | bc -l)
  cap=$(docker inspect "$name" --format '{{.HostConfig.NanoCpus}}')
  printf '%-30s %.2f cores  %.1f%% of VM  cap %s\n' "$name" "$cores" "$(echo "100 * $cores / $NCPU" | bc -l)" "$([ "$cap" = 0 ] && echo uncapped || echo "$(echo "$cap / 1000000000" | bc -l)")"
done
```

## 2. Windows memory pressure is commit charge, not free RAM

The stutter signature on one host was 129.1 of 135.9 GB committed (95%) with 11.4 GB in memory compression, while the box still reported 39.5 GB "free".

```powershell
$m = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
'{0:N1} / {1:N1} GB committed ({2}%)' -f ($m.CommittedBytes/1GB), ($m.CommitLimit/1GB), $m.PercentCommittedBytesInUse
Get-Process | Sort-Object PagedMemorySize64 -Descending | Select-Object -First 8 Id, ProcessName, @{n='CommitGB';e={[math]::Round($_.PagedMemorySize64/1GB,2)}}
```

## 3. Re-list the consumers before taking credit for a delta

A 31.6 GB commit-charge drop was credited to stopping that 2.4 GiB container. A virtual machine holding 28.5 GB had exited on its own between the two samples. The magnitude alone should have rejected the claim. When a host metric moves after you act, enumerate the top consumers in both samples; if something in the "before" list is missing from "after" and you did not stop it, subtract it first.

## 4. Windows CPU snapshots

`Win32_Processor.LoadPercentage` is a 1-second snapshot that reads 100% whenever one core is busy. A sampler built on it alerted "cpu 100%" every 20 s while a foreground workload used about half the CPU, and the sampler's own full process enumeration added load. Use `Win32_PerfFormattedData_PerfOS_Processor` (`PercentProcessorTime` on `Name='_Total'`) over several samples, or Performance Counters, and keep the sampler cheaper than the thing it watches.
