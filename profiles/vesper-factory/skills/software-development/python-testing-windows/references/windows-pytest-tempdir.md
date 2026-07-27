# Windows Pytest Temp-Dir Traps — Condensed Reference

Root cause of repeated FALSE pytest failures/errors on Windows git-bash
multi-drive setups. Fix environment before debugging code.

| # | Trap | Symptom | Fix |
|---|------|---------|-----|
| 1 | `TMPDIR=/tmp/...` (MSYS path) → tmp on wrong mount | `ValueError: path is on mount 'C:', start on mount 'D:'` on `os.path.relpath`/abs-path asserts | `export TMPDIR="D:\\pytest_tmp" TEMP="D:\\pytest_tmp" TMP="D:\\pytest_tmp"` (native path, repo's drive) |
| 2 | `TMPDIR` inside repo tree | "external temp path" tests fail — relative path expected to stay absolute | temp dir OUTSIDE repo tree |
| 3 | Stale `pytest-of-<user>` lock dir | `PermissionError [WinError 5]` in `os.scandir` at collection | `rm -rf "$LOCALAPPDATA/Temp/pytest-of-$USER"` OR redirect temp vars (sidesteps it) |

## Notes
- Set ALL THREE of `TMPDIR` / `TEMP` / `TMP` — Windows Python honors `TEMP`/`TMP`, not just `TMPDIR`.
- Add `-p no:cacheprovider` to keep `.pytest_cache` out of the repo.
- Re-run a single failing test after fixing temp placement; if it passes, the failure was the harness, not the code.
- A failure that appears ONLY under one temp/mount config = environment artifact. A failure that reproduces across configs = real.
