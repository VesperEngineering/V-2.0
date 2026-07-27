# Verification Techniques for Repo Hygiene & Test Audits

Reusable runbooks distilled from a whole-repo dead-file + test-failure audit. Read-only unless stated.

## 1. Baseline A/B: classify pre-existing vs. introduced failures (uncommitted tree)

When a working tree carries someone's uncommitted changes and tests fail, decide "did this tree break it?" empirically — run the failing loop against the committed baseline.

```bash
git stash push -u -m "<label>"        # -u includes untracked; ignore harmless
                                      # "failed to remove <dir>: Permission denied"
<run the exact failing loop>          # now at committed HEAD
git stash pop                         # restore
```

- If pop says **"The stash entry is kept in case you need it again"**, the pop APPLIED but kept a copy. Verify before dropping: `git diff --name-only --diff-filter=U` (empty = no conflicts), `git diff stash@{0} --stat` (empty = tree matches), re-run a focused loop to prove restored work intact, then `git stash drop stash@{0}`.
- **Verdict:** failures identical at baseline AND in the tree → pre-existing, not introduced. New ones → introduced.

## 2. Windows pytest TMPDIR trap (Vesper-scale repos)

Two distinct failure modes, one fix:

- Default Windows temp (`C:\Users\<u>\AppData\Local\Temp\pytest-of-<u>`) can hold a **stale lock** → `PermissionError: [WinError 5] Access is denied` during collection. Not a code bug.
- Pointing TMPDIR into the **repo** (e.g. `D:\repo\.pytest_run`) breaks tests that assert system-temp is **outside** the repo (`os.path.relpath` cross-mount, or `rel()` outside-path checks) → false failures.

**Fix:** use a temp dir on the **same drive as the repo but outside the repo root**.

```bash
mkdir -p /d/pytest_tmp
export TMPDIR="D:\\pytest_tmp" TEMP="D:\\pytest_tmp" TMP="D:\\pytest_tmp"
python -m pytest tests/ -p no:cacheprovider ...
rm -rf /d/pytest_tmp
```

A test that "fails" only under a redirected TMPDIR is an environment artifact — re-run under the correct temp before counting it real.

## 3. Desktop `.lnk` launch verification (Tkinter apps, read-only)

Prove a shortcut launches correctly without a full manual QA pass:

```powershell
# Launch through the actual .lnk
Invoke-Item "C:\Users\<u>\Desktop\APP.lnk"; Start-Sleep 8
# Inspect the process: correct pythonw + args, has a window, responding
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
  Where-Object { $_.CommandLine -match 'app.module' } |
  ForEach-Object { Get-Process -Id $_.ProcessId } |
  Select-Object Id, MainWindowTitle, MainWindowHandle, Responding, @{n='Threads';e={$_.Threads.Count}}
```

- A live window has a non-zero `MainWindowHandle`, a real `MainWindowTitle`, `Responding=True`, and >1 thread. A process that is alive but `Handle=0` / 1 thread failed to map a window (often a non-interactive-shell display issue, not an app bug).
- **Visual confirmation** (no white scrollbars / no console): bring to front via `SetForegroundWindow`, capture the screen with `System.Drawing.Graphics.CopyFromScreen`, and read the PNG. A Tkinter app launched via `pythonw.exe` should show no console window.
- **Cleanup:** kill only the PID(s) you launched (`Stop-Process -Id <pid>`); leave any pre-existing user instance alone. Verify the user's own instance survives if there was one.

## 4. Reference-count scan in one pass (large repos)

Per-file × per-file grep times out. Concatenate each reference class into one big string, build ONE alternation regex over all stems (longest first), single pass, subtract self-occurrences. See `scripts/repo_hygiene_scan.py` for the production implementation (uses `git ls-files`, dotted-path import gate, noisy-stem guard, orphaned-pyc + junk + version-chain finders).

## 5. False-positive discipline

Every "dead" verdict needs the exact import statement grep + a check for `RETIRED.md` / retirement tests / external scheduler paths / explicit registries / dynamic loaders. When a sub-agent returns a dead-file list, spot-check its highest-confidence entries before trusting any — a single confirmed false positive (e.g. flagging a just-created installer) means the whole list needs re-vetting.
