# Curating and Verifying a Large Dirty Governed Worktree

Use this when a user explicitly authorizes preserving an existing broad worktree rather than committing only the newest edit.

## Safe sequence

1. Capture branch, upstream, divergence, `git status --porcelain=v1 -z`, tracked diff stats, and untracked file sizes.
2. Classify every path as:
   - intended source/test/docs,
   - durable project governance or reviewed team knowledge,
   - generated/runtime state,
   - machine-specific export,
   - unrelated artifact,
   - credential-bearing or ambiguous.
3. Add precise ignore rules for recurring local state. Do not use `git add -A` before this classification.
4. Remove only clearly generated duplicates or scratch files covered by the user's curation authorization. Preserve ambiguous files unstaged.
5. Stage explicit paths, then inspect `git diff --cached --stat`, `--name-status`, `--check`, and a complete secret scan over a diff written to disk. Tool stdout limits can silently truncate a large diff, so never scan only the displayed terminal output.
6. Verify test collection and a narrow changed-surface slice before expensive validation. Missing declared dependencies should be installed from the repository's requirement files; add genuinely required but undeclared test/runtime dependencies to the appropriate manifest.
7. **Run an early independent staged-diff review before the full suite.** Fan out three read-only tracks when the diff is broad: (a) security/authority boundaries, (b) logic/integration consumers, and (c) curation/machine-specific state. Reviewers should inspect `git diff --cached` directly and return exact file/line blockers. This catches unsafe task principals, ambiguous broker POSTs, dangling imports, stale consumers, and generated history before spending minutes on a full test run.
8. Fix every blocking review finding and rerun the owning focused tests. If the review changes the staged diff materially, repeat the relevant review track; an old verdict does not cover new code.
9. **Freeze the final candidate before final review.** Write the complete staged diff to disk, record a SHA-256 (or staged tree ID), and tell reviewers that exact identifier. Do not keep editing while final reviewers are running. Any staged change after dispatch—even a test-only or lint-only change—invalidates the final verdict: restage, recompute the identifier, rerun the affected gates, and dispatch a fresh final review. An in-flight review is not a concurrency lane for more implementation.
10. Run the full suite only after collection, focused tests, and the early review are clean enough to justify it. Record collection errors, behavioral failures, skips, wrapper/process failures, and infrastructure termination separately.
11. If the full suite exposes baseline contract drift, fix it only when the current source clearly establishes the intended contract. Examples: stale lane counts, fixture hashes bound to a changed score surface, or docs still asserting retired topology. Never weaken an authority gate merely to turn tests green. Tests that require absent ignored/generated historical artifacts must use an explicit skip guard or hermetic fixture; the production validator should continue to fail closed when evidence is missing.
12. Regenerate the staged inventory, rerun `git diff --cached --check`, secret/machine-path scans, compile/lint gates, and a final independent review of the actual to-be-committed diff.
13. Split the final verified state into coherent commits, push, and verify the remote SHA/CI. Keep unrelated assets in a separate asset-only commit or leave them unstaged. Do not claim success until the remote receipt exists.

## Isolating concurrent tracked edits without losing them

A long verification/review session may overlap with an operator, watcher, or another agent that edits tracked files after the candidate was staged. Do not silently mix those edits into the release, and do not restore them from `HEAD`.

1. List tracked unstaged paths with `git diff --name-only` and classify them against the explicit intended-path set.
2. Stage only the intended repair paths and confirm those paths no longer have a worktree-only delta.
3. Preserve the remaining tracked concurrent edits with a named `git stash push --keep-index -m "preserve concurrent edits before release"`. Omit `--include-untracked` when large unrelated assets should remain outside the stash.
4. Confirm the working tree now represents the staged candidate plus only deliberately excluded untracked paths; run final tests against this isolated state.
5. Record the stash name. After the verified commits are pushed, reapply it deliberately and resolve any conflicts against the new commits. Never drop the stash until the concurrent work is recovered or explicitly rejected.

This technique isolates the candidate while keeping the index intact, but it does not make an in-flight review valid after staged edits. Restaging still requires a new candidate identifier and affected re-review.

## Static-check and entrypoint pitfalls

- Build lint input from staged paths and filter by the linter's language before invoking it. For Ruff, pass only staged `*.py` files; a shell filter that accidentally forwards `.gitignore`, JSON, batch, or PowerShell files creates thousands of meaningless parser errors.
- Large staged-diff secret scans must write the complete diff to disk and inspect the file. Tool stdout can truncate while still returning exit zero. Scan added lines separately for credentials, personal usernames, absolute machine paths, privileged task principals, and dangerous authority markers; distinguish deliberate traversal-test fixtures such as `C:/outside/...` from production paths.
- In-process pytest often modifies `sys.path` through `conftest.py`, masking import failures in real CLI entrypoints. When a deploy-layer module imports a repository-level shared module, run representative subprocess entrypoints (`python deploy/<cli>.py ...`, wrapper scripts, and `--help`) with the exact scheduled/installed interpreter. A full suite failure concentrated in subprocess CLIs is usually an entrypoint bootstrap defect, not dozens of independent feature regressions.
- When splitting commits from generated path lists, inventory with `git diff --name-status --no-renames` (or equivalent status data), not only rename-aware `--name-only`: a rename may display only the destination and leave the source deletion unstaged. Generate NUL-delimited pathspec files directly; newline lists created on Windows can carry `\r` into `xargs` and produce false `pathspec ...? did not match` failures. After every commit, require `git status --short` to contain only explicitly excluded paths.
- Treat pre-commit as a mutating gate. Run it on the frozen candidate before final review, inspect any auto-fixes, restage intentionally, and rerun focused tests. Do not silently use `--no-verify` as the release path. If the checked-in hook policy is impossible against the repository's documented baseline (for example a whole-tree formatter on an unformatted legacy tree), align the hook to the smallest already-governed enforceable baseline, update its contract test, and obtain a clean hook run; do not broaden cleanup inside a safety release.
- If another agent/watcher is actively changing tracked files, do not run tests and pre-commit in parallel against the moving worktree. Preserve concurrent deltas in named stashes, obtain a tracked-clean candidate, then run gates serially. A hook's temporary stash protects its own process, but a parallel pytest can still observe unrelated writes.

## Windows/Hermes Python shadowing diagnostic

A project interpreter can still inherit the parent agent's `PYTHONPATH`. This can make a repository import such as `cli` resolve to the agent application's `cli.py`, or make tests pass/fail differently by order.

Diagnose with the project interpreter:

```bash
.venv/Scripts/python.exe -c "import os,sys,importlib.util; print(os.environ.get('PYTHONPATH')); print(*sys.path, sep='\\n'); print(importlib.util.find_spec('cli'))"
```

If an external agent path precedes repository package roots, run repository verification with an intentionally clean inherited path:

```bash
PYTHONPATH= .venv/Scripts/python.exe -m pytest ...
```

The repository's `tests/conftest.py` must then add every intentional package root explicitly (for example both the repo root and `deploy/`). This is a test-isolation fix, not a permanent claim that external tooling is broken.

## Full-suite interpreter-state poisoning

When tests pass alone but later native-library tests fail only in the full-suite order—with duplicate registration errors, internal C-extension assertions, or a clean pytest summary followed by a process crash—look for tests that mutate process-global import state. A direct `sys.modules.pop("torch", None)` (or equivalent for TensorFlow, NumPy, plugin registries, logging globals, or environment variables) can remove the Python module while native registrations remain loaded; importing it again may double-register operators and corrupt teardown.

Reproduce with the suspected mutator test immediately followed by one failing consumer. Fix test isolation rather than production code: use `monkeypatch.delitem(sys.modules, name, raising=False)`, `monkeypatch.setenv`, or a fixture with explicit restoration so pytest restores original state. Then run the pair in that order, the affected native-library slice, and the full suite. Treat a normal behavioral summary plus exit 139 as non-green until the process itself exits zero.

## Portable logout-safe Windows tasks

Never run mutable, user-writable repository code as `SYSTEM` or another more-privileged principal. A Task Scheduler definition that combines `S-1-5-18`/highest privilege with a writable checkout is a local privilege-escalation boundary: anyone who can edit the wrapper or imported Python gains that principal on the next run.

For a user-owned unattended pipeline, use a tracked XML **template** with placeholders for the task principal and deployment root plus `RunLevel=LeastPrivilege`. Choose logon type from the workload: S4U is acceptable only for strictly local work that needs no authenticated HTTPS, network share, user-bound secret, or bearer/header credential. For network-capable work, use a purpose-built service identity or password logon with secure interactive registration (for example `schtasks /RP "*"`); never place the password in XML, Git, logs, summaries, or command arguments. Render from an elevated tracked installer, XML-escape substituted values, and do not commit a personal SID, account name, or absolute checkout path. Parse both template and rendered XML before registration.

Do not register any stored-credential task against a mutable development checkout or writable virtual environment. Deploy a reviewed immutable runtime snapshot: code, interpreter, launcher, and secrets writable only by the intended principal, SYSTEM, and Administrators, with explicitly separate writable log/data/artifact directories. The installer must audit effective ACLs and fail closed on unexpected write/modify/delete/ownership rights; do not "harden" an active development checkout merely to force installation. Derive wrapper roots from the installed launcher location rather than hardcoding `D:\...`, force deterministic encoding, and propagate the real child exit code. Never turn a failed command green merely because a same-date receipt exists; validate receipt status and provenance or preserve the failure.

If a machine-owned task genuinely requires a service account, move executable code to an administrator-owned, non-user-writable install directory and separately review update permissions before granting that principal. `SYSTEM` is not a portability shortcut.

Registration may require administrator authority. Prove the real OS path after import:

- rendered principal, logon type, and least required run level,
- exact task action, dynamic wrapper root, and working directory,
- non-interactive/logout-safe behavior,
- battery settings and `StartWhenAvailable`,
- manual trigger completion,
- fresh `Last Result: 0`,
- generated receipts/logs with validated PASS status,
- then one natural logged-out scheduled run where practical.

Keep an existing redundant scheduler enabled until the replacement is installed and verified. Afterward, retain one primary and one idempotent recovery path; pause uncontrolled duplicate production authority.

## Reporting rule

If verification uncovers failures, say the work is not commit-safe and continue repairing. Do not convert partial focused passes into a claim that the broad worktree is verified.
