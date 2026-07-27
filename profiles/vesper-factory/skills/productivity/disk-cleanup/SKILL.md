---
name: disk-cleanup
description: Analyze disk usage and safely free space on Windows. Identify space hogs, clear caches, and reclaim GBs without risk.
---

# Disk Cleanup (Windows)

## Trigger

User asks about disk space, "why is my drive full", "what's taking up space", "clean up C drive", "free up space", or similar.

## Core Principle

On Windows with git-bash/MSYS, **NEVER use `du` for large directory scans** — it's pathologically slow (60s+ timeouts). Use **Python `os.scandir` with recursive `get_dir_size()`** via `execute_code` instead. It's 10-50x faster.

## Approach

### Phase 1: Top-level scan

Get the big picture first. Scan all top-level directories on the drive:

```python
import os

def get_dir_size(path):
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat().st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += get_dir_size(entry.path)
            except (PermissionError, OSError):
                pass
    except (PermissionError, OSError):
        pass
    return total
```

Use `execute_code` with a generous timeout (300-600s) for full-drive scans.

### Phase 2: Drill into large directories

For any directory >5 GB, scan its immediate children to identify sub-hogs:

```python
def get_immediate_subdirs(path):
    results = []
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            size = get_dir_size(entry.path)
            results.append((size, entry.path))
    results.sort(reverse=True)
    return results
```

### Phase 3: Classify and act

Present findings in three tiers:

| Tier | Meaning | Action |
|------|---------|--------|
| 🟢 Safe to delete | Caches, temp files, recordings | Delete immediately |
| 🟡 Shrinkable | VHDs, old envs, game installs | Compact or move |
| 🔴 Leave alone | System files, apps, user data | Don't touch |

## Safe-to-Delete Targets (Windows)

These are always safe — they regenerate on demand:

| Cache | Command | Typical Saving |
|-------|---------|---------------|
| pip | `pip cache purge` | 1-10 GB |
| uv | `uv cache clean` | 1-5 GB |
| NuGet | `dotnet nuget locals all --clear` | 1-3 GB |
| npm | `npm cache clean --force` | 0.5-3 GB |
| npm npx/prebuild leftovers | After confirming they are cache-only, remove `%LOCALAPPDATA%/npm-cache/_npx` and `_prebuilds` | 0.1-3 GB |
| Temp files | `rm -rf $LOCALAPPDATA/Temp/*` | 0.5-3 GB |
| .cache (user) | `rm -rf ~/.cache/*` | 0.5-2 GB |

Also check for these common large dirs:
- `.gemini/antigravity/browser_recordings/` — Gemini CLI recordings
- `.codex/archived_sessions/` — Codex CLI old sessions
- `AppData/Local/pip/` — pip wheel cache
- `AppData/Local/uv/cache/` — uv cache

## Shrinkable Targets

- **WSL2 VHDs**: First inventory `ext4.vhdx` files and verify `wsl -l -v` reports every distribution stopped. Run `wsl --shutdown`, then use an **elevated Administrator PowerShell** to compact each disk: `Optimize-VHD -Path <path>\ext4.vhdx -Mode Full`. Record VHD sizes and C: free space before and after; compaction may reclaim little or nothing when the virtual disk has few free blocks.
  - Newer WSL exposes `wsl --manage <distro> --set-sparse true`. Never add `--allow-unsafe` when WSL warns sparse-VHD support is disabled due to potential data corruption; use the elevated `Optimize-VHD` route instead.
  - To relocate an active distro off C:, run `wsl --shutdown`, then `wsl --manage <distro> --move <new-empty-directory>` on a volume with sufficient free space. Treat any move error—especially `MoveDistro/E_ACCESSDENIED`—as **ambiguous**, not as a failed no-op: do not retry or delete anything. First inventory source/destination VHDX files and inspect the distro's `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Lxss\\{GUID}` registration. A move can physically relocate the VHDX while leaving `BasePath` at the old location. Only after confirming the destination VHDX exists, repair that one `BasePath` value, then verify `wsl -d <distro> -- /bin/true` and shut the distro down again. Never delete a leftover VHDX that is not mapped to a verified active distro—classify it first with a read-only `wsl --mount <vhdx> --vhd --options ro`, unmount it, and obtain the user's explicit disposition.
  - Do not delete, permanently detach, or resize WSL VHDs as a disk-cleanup shortcut.
- **pagefile.sys**: If RAM > 32 GB, reduce to 4-8 GB fixed via System Properties → Performance → Advanced → Virtual Memory
- **hiberfil.sys**: If you never hibernate, `powercfg -h off` frees RAM × 0.75
- **WinSxS**: `DISM /online /Cleanup-Image /StartComponentCleanup` (administrator)

## Pitfalls

- `du` on git-bash/Windows is unusably slow — never use it for directories larger than a few GB
- `execute_code` can time out waiting for user consent; if blocked, fall back to individual `terminal` calls targeting one directory each
- Windows `dir /s` is also slow and hard to parse — Python `os.scandir` is the reliable method
- Some files (pagefile.sys, hiberfil.sys) show as 0 bytes to `os.scandir` — check with `dir /a` or `df` instead

## Presentation

Always present results as a table with GB sizes, sorted largest-first. Group by category (Games, System, Programs, User Profile). End with ranked "biggest wins" list if the user wants to free more space.

See `references/windows-caches.md` for the full cache-location catalog.
