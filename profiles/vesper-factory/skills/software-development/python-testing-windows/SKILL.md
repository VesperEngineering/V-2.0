---
name: python-testing-windows
description: Run Python test suites (pytest) reliably on Windows / git-bash — avoid false failures from temp-dir mount mismatches, in-repo temp placement, and stale pytest lock dirs. Use whenever a pytest run on Windows fails or errors in a way that smells environmental (mount mismatch, temp path, scandir permission) rather than a real code bug.
---

# Python Testing on Windows

Running pytest on Windows (especially from git-bash/MSYS on a multi-drive
machine) has environment traps that produce FALSE failures and FALSE errors.
Rule these out in Phase-1 of any debugging before concluding the code or the
test is broken.

## The three temp-dir traps

### 1. `TMPDIR` on an MSYS path → tmp on the WRONG mount

`TMPDIR=/tmp/...` (any MSYS-style path) from git-bash puts pytest's `tmp_path`
on the shell mount (e.g. `C:`) while the repo is on another drive (e.g. `D:`).
Tests doing `os.path.relpath(tmp, "D:/repo")` or asserting a canonical/absolute
path then fail with `ValueError: path is on mount 'C:', start on mount 'D:'` —
a FALSE failure, not a code bug.

**Fix:** set the temp vars to a NATIVE path on the SAME drive as the repo, and
set ALL THREE (Windows Python honors `TEMP`/`TMP`, not just `TMPDIR`):
```bash
export TMPDIR="D:\\pytest_tmp" TEMP="D:\\pytest_tmp" TMP="D:\\pytest_tmp"
```

### 2. `TMPDIR` INSIDE the repo → breaks "external temp path" tests

Pointing temp inside the repo tree (e.g. `D:\repo\.pytest_run`) breaks tests
that expect system temp to be OUTSIDE the repo (they compute a relative path
and expect it to stay absolute). Another FALSE failure.

**Fix:** temp dir must be outside the repo tree entirely.

### 3. Stale `pytest-of-<user>` lock dir → `PermissionError [WinError 5]`

A leftover `C:\Users\<user>\AppData\Local\Temp\pytest-of-<user>` from a crashed
or killed prior run makes collection fail with
`PermissionError: Access is denied` in `os.scandir`. Environment lock, not code.

**Fix:** delete the stale dir, or just redirect temp vars per trap #1 —
redirecting sidesteps the locked dir entirely. When changing environment variables is undesirable, an explicit accessible external `--basetemp` can also bypass pytest's locked default `pytest-of-<user>` root; run the full suite with that explicit path and report the path used.

## Rule of thumb

When a Windows pytest failure smells environmental (mount mismatch, temp-path,
scandir permission), FIX the TEMP/TMP/TMPDIR placement and re-run BEFORE
concluding the code or test is broken. One native path, repo's drive, outside
the repo tree. Add `-p no:cacheprovider` to keep `.pytest_cache` out of the repo.

### Basetemp preflight

`pytest --basetemp=<path>` can fail with `FileNotFoundError` when its parent
folder is absent, even though pytest creates the final basetemp itself. Before
every isolated run, create a fresh external root and child path explicitly,
then set all three temp variables to the root:

```bash
mkdir -p 'D:/pytest_tmp_<slice>/run'
export TMPDIR='D:\\pytest_tmp_<slice>'
export TEMP='D:\\pytest_tmp_<slice>'
export TMP='D:\\pytest_tmp_<slice>'
python -m pytest <targets> -p no:cacheprovider \
  --basetemp='D:\\pytest_tmp_<slice>\\run'
```

If a run failed solely because that parent was absent, use a **new** external
root and rerun. Report the setup-only attempt separately from the final
behavioral result; do not repair project source for this condition.

### SQLite temporary fixtures: close in the child, clean in the parent

On Windows, SQLite files can remain locked until the Python process that opened them exits. In particular, `with sqlite3.connect(path) as connection:` commits or rolls back but does **not** itself close the connection. A verification helper that creates a temporary SQLite fixture and then deletes its `TemporaryDirectory` in the same process can therefore report a cleanup `PermissionError` even after its assertions passed.

**Robust pattern:** use an explicit `connection.close()` for fixture setup. When exercising code under test that may retain a SQLite handle, create the fixture directory in a parent process, run the temporary verifier as a child process, then remove that directory only after the child exits. This preserves a real behavioral verdict and guarantees cleanup without masking a passing assertion behind a Windows file-handle error.

### `--basetemp` does not contain fixed-root application writes

External temp variables isolate pytest-owned fixtures and cache only. Tests and
subprocesses can still write paths derived from application constants such as
`ROOT / "artifacts"`, generated assets, or repository-local databases. Before
claiming that a broad run was isolated, inspect failure/output paths and the
source worktree for fixed-root writers.

When such writers exist, run the complete broad command in an external,
Git-aware disposable snapshot of the exact dirty candidate. Build it from
exact `HEAD` plus the tracked diff and untracked candidate files, but then
raw-copy every candidate path from the source worktree and compare SHA-256:
Windows checkout/apply filters can normalize CRLF/LF even when `git apply`
succeeds. Preserve deletions, give the snapshot only copied bounded fixtures,
run pytest with a separate external basetemp, and compare candidate paths plus
source evidence/Git fingerprints after the run. Treat an earlier in-worktree
run as diagnostic rather than admissible; do not delete unknown ignored files.
The detailed recipe is in the `evidence-artifact-integrity` skill at
`references/dirty-candidate-disposable-test-snapshot.md`.

## Cross-test lifecycle crash isolation

When a broad suite aborts while two focused files each pass alone, treat it as a potential cross-test lifecycle or subprocess-cleanup defect rather than attributing it to the latest feature immediately.

1. Preserve the aborted full-suite output and verify external-temp cleanup from outside its leaf before any retry.
2. Run the changed feature's focused file and the suspected asynchronous/UI file alone, each with a fresh native external temp root.
3. Run the remainder with `--ignore=<suspected-file>` using the same interpreter. This distinguishes a failing feature from an interaction that leaves worker threads or subprocesses alive across tests.
4. If the split commands are green but the combined run remains unstable, inspect the asynchronous test's lifecycle (`join`, stop signal, subprocess ownership) and fix the leak with a dedicated regression. Do not call the full suite green until the declared combined command passes.

### GUI-refresh repair pattern

For a Tkinter view whose background snapshot loader calls a CLI, fix both the production lifecycle and test isolation:

- Retain the active loader thread plus a `threading.Event` cancellation signal.
- Pass that signal into the snapshot reader and its CLI helper. Use `subprocess.Popen` with bounded `communicate(timeout=...)` polling; when cancellation or deadline fires, terminate the child, drain it, and raise an explicit cancellation/timeout error.
- In `close()`, set the event, join the retained loader thread with a bounded wait, then cancel Tk `after()` callbacks and destroy widgets.
- UI layout/selection tests must monkeypatch the snapshot reader **before** invoking the UI button; never let those tests call the real CLI.
- Add a regression whose fake snapshot blocks until the cancellation event is set, then assert `close()` returns with the loader thread no longer alive.

This pattern separates a real lifecycle defect from a Windows runtime symptom and prevents later tests from inheriting subprocess pipe-reader threads.

## Verification-evidence traps (Hermes tool wrapper)

- **Windows Python cannot open MSYS paths.** From git-bash, `python /c/Users/.../script.py`
  fails with `can't open file 'C:\\c\\Users\\...'` — the interpreter is native Windows and
  does not resolve MSYS mount paths, it just prefixes `C:\`. Pass the Windows-style path
  (`python "C:/Users/.../script.py"`) even though the shell itself accepts `/c/...`.

- **Temporary verifier scripts need native arguments and an explicit import root.** Creating an ad-hoc verifier with
  `tempfile.NamedTemporaryFile(prefix="hermes-verify-", suffix=".py", delete=False)` is
  portable, but passing git-bash `$PWD` into that Windows Python script is not. Convert the
  repository argument first (`REPO=$(cygpath -w "$PWD")`), pass `"$REPO"`, preserve the
  verifier exit code, and remove both the script and its isolated basetemp on every path.
  A failed first attempt must still clean its generated script before retrying. Because Python
  sets `sys.path[0]` to the external script directory, a verifier importing project modules
  must either receive the native repository path and execute `sys.path.insert(0, repo_path)`,
  or launch a project-local module instead; its shell working directory alone is not enough.

- **Piping pytest through `| tail` records exit 15 as a FAILED run.** The
  terminal wrapper sees the pipeline exit status, and a pytest run that printed
  `N passed` can be logged as `exit 15` (SIGTERM-ish artifact of the pipe/head
  closing early), flipping verification_evidence to "failed". When the harness
  demands a clean recorded exit code, run pytest WITHOUT a trailing pipe (or
  redirect full output to a file and `tail` the file). pytest's own summary
  line is the truth; the wrapper's exit code is only as good as the last pipe
  stage.
- **System Python (uv-managed cpython) ships without `tzdata`.**
  `ZoneInfo("America/New_York")` raises `ZoneInfoNotFoundError` there while the
  same code passes under the repo venv. Fix: `uv pip install tzdata` into that
  interpreter, or run the script under the project venv that has it. Symptom is
  import-time failure of any module that constructs a ZoneInfo at module scope —
  it looks like a code bug in the module but is interpreter-local.

## Bind the exact Python review environment and gates

Independent review must name the project interpreter, external Windows temp paths, exact test targets, and exact lint selectors. Do not let a reviewer substitute system Python or replace a scoped critical lint gate with unrestricted historical style debt. Keep review scratch outside the worktree and recheck candidate/diff identity before the verdict.

**Reviewer-environment false HOLDs.** A full-suite HOLD whose only evidence is missing-dependency import failures under system `python` (for example `ModuleNotFoundError: yfinance` while the project `.venv` has it) is an environment-selection defect, not a candidate defect. Before accepting or acting on that verdict: verify the reviewer's `sys.executable` and `pip`-level dependency presence, verify the frozen candidate identity is unchanged, then re-run (or re-dispatch) the full-suite gate with the explicit project interpreter. An initial HOLD of that shape gets exactly one bounded environment-bound re-verification; do not patch project source to satisfy the wrong interpreter.

If a test calls Git (`git rev-parse`, `git status`, blob/tree reads), a plain `git archive` export is not a sufficient scratch checkout: it has exact files but no `.git` metadata, so the test can fail during setup with exit 128. Use an external detached clone/worktree-equivalent at the exact commit, or initialize the external export with access to the source object store and check out the exact SHA. Verify external `HEAD`, tree ID, and clean status before rerunning. Classify the archive-only failure as setup evidence, use a fresh basetemp for the rerun, and do not patch product source to accommodate missing review metadata.

See `references/windows-pytest-tempdir.md` for the condensed trap list.

## Embedded Tcl/Tk discovery in Python environments

A Windows project venv can import `tkinter` while failing at `tk.Tk()` because its embedded interpreter cannot locate the matching Tcl/Tk *script* directories. Do not skip GUI tests or point at an arbitrary system Tcl installation: Tcl patch-level mismatches can fail at runtime.

1. Reproduce with both `TCL_LIBRARY` and `TK_LIBRARY` unset, using the project interpreter.
2. Derive the matching script root from `Path(tkinter.__file__).resolve()` rather than hard-coding a user or Python-install path. **Do not trust `pyvenv.cfg`'s `home` field for this:** uv-managed environments can expose a distinct patch-versioned runtime directory at import time. Locate `tcl/tcl8.6/init.tcl` and `tcl/tk8.6/tk.tcl` under the runtime that actually supplied `tkinter`, and require both marker files before setting either variable.
3. When an initial full-suite Tk failure names a stale or different runtime path, run one isolated, fresh-process tight GUI test with the same project interpreter and external native `TEMP`/`TMP`/`TMPDIR` before editing application bootstrap. If it passes, retry the complete suite once with a fresh external basetemp; classify the initial failure as process/environment resolution instability only if that declared full command then passes.
4. In application bootstrap before creating the first `tk.Tk()`, set each variable only when its existing value does not contain its marker file. Preserve a valid operator-provided setting.
5. Add a regression that starts with both variables unset and asserts the application resolves directories containing `init.tcl` and `tk.tcl`; run the full suite in that same unset environment.

This is a process-local runtime discovery repair, not a system-wide environment or dependency change. It makes GUI tests and the native application use the Tcl/Tk scripts matching the active Python runtime.

## Binary-safe immutable artifact writes

On Windows, a descriptor opened with `os.open(..., os.O_WRONLY)` can translate
`\n` to `\r\n` unless binary mode is explicit. This makes an immediate replay
of identical JSON look like an immutable mutation and breaks byte/hash binding.
For receipt, ledger, and content-addressed artifact helpers, include
`getattr(os, "O_BINARY", 0)` in the open flags, write bytes, `fsync`, and add a
regression asserting `path.read_bytes() == encoded_bytes` before testing replay.
Do not hide this by normalizing newlines during validation—the persisted bytes
are the evidence contract. See `references/windows-binary-artifacts.md` for the
portable helper and reproduction recipe.

## Canonical tracked-text hashes across Git worktrees

Do not apply the immutable-artifact rule blindly to tracked source/input text when Git checkout filters can produce LF in one Windows worktree and CRLF in another. If source identity must survive that conversion, the contract and receipt must explicitly declare the canonicalization profile; every preparer, finalizer, unattended runner, and reviewer must use the same semantics. Persisted receipts, ledgers, candidates, and other evidence artifacts remain exact raw-byte-bound.

See `references/canonical-text-hashing.md` for the contract shape, helper, regressions, and independent-review recipe.

## Cleanup-safe pytest command structure

Do not combine `set -e` with post-test cleanup that appears later in the same shell body. If pytest exits nonzero, `set -e` aborts before cleanup, leaving the external basetemp behind and obscuring whether the cleanup gate was satisfied.

Use one of these patterns instead:

```bash
set +e
python -m pytest ... --basetemp="$ROOT/pytest"
test_status=$?
set -e
cd /outside/the/temp/leaf
rm -rf "$ROOT"
cleanup_status=$?
test ! -e "$ROOT" || cleanup_status=1
(( test_status == 0 && cleanup_status == 0 ))
```

or install an `EXIT` trap before pytest and separately preserve both statuses. A failed or setup-only test attempt still requires verified cleanup. Never let an earlier behavioral status mask a cleanup failure.

When selecting focused targets, derive filenames from the repository rather than guessing a conventional name such as `test_signals.py`. If the first command names a nonexistent test, classify that attempt as reviewer setup error, clean its temp root, discover the actual tracked tests, and rerun with a fresh root. Do not count the setup-only attempt against the candidate.

## Verifying a "green suite" claim

- Run the FULL suite with the correct temp placement before declaring green.
- Distinguish a real failure from an environment artifact by re-running the
  failing test alone after fixing temp placement — if it then passes, it was
  the harness, not the code.
- A failure that appears only under a specific temp/mount config is an
  environment artifact; a failure that reproduces across configs is real.
- **Acceptance-gate rule:** when the review contract requires a green full
  suite (or says that an unexecutable test is blocking), do not convert an
  attributable interpreter/GUI/environment failure into a pass. Report the
  focused target result separately, report the full suite as **not admissibly
  green**, retain the diagnostic cause, and HOLD until the required command can
  run green in its declared review environment. This is distinct from assigning
  code blame; it preserves fail-closed acceptance evidence.
- If a first broad run aborts unexpectedly, inspect the failure and retry once
  from a fresh external `--basetemp`. Report both attempts and use the cleanest
  completed run as evidence; never hide an incomplete first run.

See `references/windows-pytest-tempdir.md` for the condensed trap list.

## Cross-platform optional-module collection

When native Windows collection fails on a Unix-only optional module such as `_curses`, do not patch unrelated product code or call the changed slice broken. Verify platform-neutral changed tests natively with the explicit `src/` import root, run the complete suite in the project's declared WSL/Linux environment, and preserve the native limitation as a separate portability fact. Cleanup may require a fresh post-pytest process after the command returns. See `references/cross-platform-optional-module-collection.md` for the classification and two-layer verification recipe.
