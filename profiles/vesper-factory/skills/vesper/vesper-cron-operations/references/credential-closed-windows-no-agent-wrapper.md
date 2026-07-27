# Credential-closed Windows no-agent research wrapper

Use this pattern for a local, research-only Hermes cron tick that must call project Python and audited Kanban CLI operations without inheriting broker/provider credentials.

## Executable and release identity

- Invoke the project interpreter, Git, Hermes, and OS termination utility by absolute path; never rely on `PATH` or `PATHEXT`.
- Pin and verify every enforcement executable's SHA-256 before use, including timeout/kill tools. A tool upgrade becomes a visible HOLD until the reviewed identity is refreshed.
- Determine what each pinned executable actually binds. A small Python console launcher usually imports mutable package source and `site-packages`; hashing the launcher and interpreter does **not** bind `hermes_cli`, project imports, native wheels, or dependencies. Include those runtime artifacts—or a complete immutable environment image/lock with verified installation hashes—in release identity.
- Verify a canonical release manifest *before* starting the project Python target. It must bind the scheduler wrapper itself, every runtime-imported source/config file, the dependency lock/environment identity, and the expected release commit. A clean-worktree check inside the target is too late to prevent execution of a replaced wrapper/target, and a different clean commit is not automatically an approved release.
- Persist wrapper, release-manifest, source, protocol, schedule-definition, interpreter, and dependency-lock hashes in activation evidence.
- Prefer a dedicated evidence-root virtual environment over a mutable shared project environment. Pin the actual artifact-producing versions, hash the venv interpreter, run dependency consistency checks, and point the wrapper at that interpreter.
- Prove the lock is the producing environment rather than trusting remembered pins: rebuild a representative immutable artifact in a new generation and compare physical bytes. When decoded tables match but Parquet hashes differ, inspect footer metadata such as `created_by`; a PyArrow-version-only footer difference diagnoses lock drift, not data drift. Update the lock to the proven producing stack and require a byte-identical rebuild before scheduling.
- Regenerate the release manifest only after formatting and all runtime-source edits finish. Any later runtime, wrapper, interpreter, or dependency-lock change invalidates prior staged-diff reviews and requires a fresh exact-digest review.

## Hermes credential closure with shared Kanban

`--ignore-user-config` skips behavioral `config.yaml`, but Hermes startup may still load `.env`, `.op.env`, external secret sources, and machine-global managed scope *before* subcommand dispatch. Managed scope can also reintroduce `PATH`. Environment filtering and an empty `HERMES_HOME` are therefore insufficient unless the pinned Hermes bootstrap has an earlier, verified no-env/no-secrets mode.

For Kanban-only subprocesses:

1. Set `HERMES_HOME` to a dedicated empty, non-symlink scheduler directory whose **immediate parent is named `profiles`** (for example, `<evidence-root>/profiles/research-cron`). Hermes treats that shape as an explicit profile and does not follow the user's sticky `active_profile` into the credential-bearing default profile.
2. Reject `.env`, `.op.env`, `config.yaml`, `auth.json`, secret-source configuration, plugin state, or any other credential/config state in that directory.
3. Inspect the pinned Hermes bootstrap implementation, not only CLI help. Verify project fallback env files are absent and machine-managed/external secret loaders cannot run. If the general Hermes CLI has no pre-bootstrap credential-closed mode, do not claim closure: use a pinned Kanban-only entrypoint that does not invoke global environment/secret loading, or patch and release such a mode first.
4. In a separate child process, redirect every managed/secret source to a synthetic temp root containing sentinel credential names and a sentinel `PATH`; prove none appear after bootstrap. Print booleans/names only, never real credential values.
5. Set `HERMES_KANBAN_DB` to the exact canonical board database and `HERMES_KANBAN_BOARD` to the approved slug. Also set `HERMES_KANBAN_HOME` to the **shared Hermes root** that contains `kanban/boards`, not to `<root>/kanban`; the latter becomes `<root>/kanban/kanban/boards` during named-board existence checks. This preserves shared-board access without selecting the default credential profile.
6. Pass `HERMES_IGNORE_USER_CONFIG=1` and `--ignore-user-config` as defense in depth.
7. Supply a minimal environment: Windows system roots, dedicated temp paths, UTF-8 settings, explicit Kanban variables, and bounded CPU thread variables. Omit `APPDATA`, `LOCALAPPDATA`, provider keys, broker keys, `PATH`, and `PATHEXT`. Current Hermes evaluates a `Path.home()` fallback eagerly inside dotenv loading even when `HERMES_HOME` is set, so on Windows provide **sanitized** `HOME` and `USERPROFILE` values that point to the same empty scheduler profile; never forward the user's real home values.
8. Run one live read-only `hermes kanban ... show --json` probe with this exact environment before permitting writes. A process exit code of zero is not enough: Hermes can report a missing board on stderr and emit empty stdout, so require parseable JSON bound to the expected task/board.

Kanban writes still use the supported CLI with fixed argv. Direct SQLite remains read-only audit only.

## Hard timeout and output bounds

`subprocess.run(capture_output=True)` followed by a length check is not a hard output cap: memory is already unbounded. Stream stdout/stderr concurrently into fixed-size buffers. On overflow, terminate the child tree and emit a small truthful HELD result without replaying partial output.

On Windows, prefer a Job Object with kill-on-close and assign the child before it can spawn descendants. A new process group plus absolute, hash-pinned `taskkill.exe /PID <pid> /T /F` is only a fallback: descendants can detach, and taskkill can fail or time out. Always keep a verified direct `kill()` fallback, bounded final waits, and a terminal HELD/FAIL path that cannot return while the direct child is still alive.

## Exactly-one and external-effect closure

- Use a process-lifetime kernel lock (`msvcrt.locking` on Windows; `flock` on POSIX), not lock-file existence or timestamp/PID-only stale reclamation. The lock file may persist while the kernel ownership does not.
- Acquire the singleton before queue selection, data/feature materialization, or any expensive/publishing prework, and hold one coherent ownership generation through local terminal publication plus external-effect reconciliation. A lock only around the evaluator still permits overlapping ticks.
- Model external publication as a replayable outbox. A receipt can survive a failed comment; the next tick must reconcile that exact missing effect before selecting later work. Verify the complete read-back body/hash, not marker-substring presence.
- Inject crashes after terminal receipt, ledger append, champion/summary publication, active-marker cleanup, and Kanban publication. Replay must finish all missing downstream effects; test baseline rejection/no-champion explicitly.
- Normalize Windows workspace paths with canonical real-path handling plus `normpath` + `normcase`, and evaluate owner/claim lease liveness separately. A stale matching path must not block forever, and a live owner with incomplete path metadata must not be ignored.
- Require an explicit runnable activation-status allowlist. Do not treat every non-`done`/non-`archived` card—including blocked, review, cancelled, or stale-running—as permission to execute.
- Treat a busy race as explicit `IDLE` or `HELD`, never as permission to start a second experiment.
- Verify one experiment maximum per tick both in the wrapper's fixed argv and inside the lifecycle.

## Release gate

Do not install recurrence until: supervised canary succeeds; exact source/release is clean and committed; focused and adversarial tests pass against an external export of the exact staged index; an independent reviewer returns a complete parseable `passed=true` verdict against that exact digest; and inventory proves no conflicting executor fingerprint. Require a schedule-definition artifact that binds job ID, command/args, worktree, cadence/window, no-agent mode, wrapper/release/executable hashes, overlap policy, prior-job disposition, and scoped rollback steps. Its absence is a release-blocking failure, not an optional evidence omission.