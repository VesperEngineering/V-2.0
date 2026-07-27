# WSL2 Memory Accounting for Active ML Research

## Purpose

Use this reference when Windows Task Manager shows high `VmmemWSL` memory during or after a WSL2 training run. Diagnose before changing limits or killing the VM.

## Key Model

- `VmmemWSL` is the aggregate Windows process for the WSL VM, not one Python program.
- Its working set includes Linux process RSS, kernel/runtime overhead, filesystem page cache, shared memory, and every active WSL distribution/process.
- `.wslconfig` `memory=<size>` is a **maximum**, not an up-front reservation.
- Linux `free` reports cache as reclaimable and therefore may show large `available` memory while Windows still attributes several GiB to `VmmemWSL`.
- Python/PyTorch allocators can retain released arenas for reuse. This is normal unless the process or VM working set grows monotonically across completed experiments.
- `autoMemoryReclaim=gradual` is deliberately non-aggressive: it reclaims cache over time and should not interrupt active data loading/training. It does not reclaim a live process heap.
- `vmIdleTimeout=-1` keeps WSL alive indefinitely when otherwise idle, so its warm cache can persist after an experiment.

## Safe Evidence Collection

Run these read-only probes from the Windows/MSYS shell:

```bash
python -c "import psutil; p=psutil.Process(<VMMEM_PID>); m=p.memory_info(); h=psutil.virtual_memory(); print(f'vmmem RSS={m.rss/2**30:.2f} GiB'); print(f'host available={h.available/2**30:.2f} GiB ({h.percent:.0f}% used)')"

wsl.exe -e sh -lc "free -h; grep -E 'MemAvailable|Cached|SReclaimable|Shmem' /proc/meminfo; ps -eo pid,etime,pcpu,pmem,rss,comm,args --sort=-rss | head -15"

wsl.exe -e sh -lc "nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>/dev/null || true; nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null || true"
```

Interpret the result as a ledger:

```text
Vmmem working set
≈ active training RSS + page cache + WSL/kernel overhead + other WSL services
```

The values need not match exactly because Windows and Linux sample/account memory differently.

## Decision Rules

**Normal:** An active `train.py`/Python worker has substantial RSS and CPU/GPU activity; WSL cache remains warm; host still has several GiB available; `VmmemWSL` eventually drops between runs or under pressure.

**Investigate:** `VmmemWSL` repeatedly rises across completed runs, no large Linux process/cache explains it, Windows begins paging/freezing, or WSL hits its configured cap/OOMs.

**Do not casually reclaim memory during a run.** `wsl --shutdown` kills all WSL workloads, including the research worker, Codex, and local servers. Linux `drop_caches` reduces future I/O performance and does not release private Python/PyTorch allocations.

For a workstation-responsiveness policy, decide explicitly between:
- a lower WSL `memory=` ceiling (protects Windows; raises experiment OOM risk),
- the current `gradual` reclaim (best default for iterative research), or
- a finite `vmIdleTimeout` (allows shutdown after all WSL work is truly idle).

Apply `.wslconfig` changes only during a planned stop/restart, then verify the effective guest limit with `free -h`.
