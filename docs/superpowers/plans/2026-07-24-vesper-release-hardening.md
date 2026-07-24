# Vesper Release Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a recoverable Windows release of the Vesper Quant Factory with migration, failure, safety, packaging, legal, smoke, soak, storage, and Tkinter-parity evidence sufficient to pass milestone M6.

**Architecture:** Plan 06 adds a release boundary around the completed Plan 01–05 product: Python owns schema migration, reconciliation, deterministic release simulations, and safety/storage audits; Rust owns bounded sidecar restart and cached read-only recovery; Tauri packages the React host and a PyInstaller `onedir` sidecar into one Windows NSIS installer. Release reports are machine-readable version-1 JSON, and one aggregate gate refuses a release if a required report, legal artifact, migration fixture, smoke result, or parity decision is absent or invalid.

**Tech Stack:** Python 3.11, stdlib SQLite, pytest, PyInstaller 6.21.0 `onedir`, Tauri 2, Rust stable MSVC, React 19, TypeScript, Vite, Vitest, React Testing Library, pnpm, NSIS, PowerShell 7, Syft 1.44.0, CycloneDX JSON 1.7, GitHub Actions Windows runners.

## Global Constraints

- Before any code edit, follow `AGENTS.md`: load matching skills, query the canonical checkout's `.codegraph` index for every symbol/file to be changed, and read `SKILLS/CODE.md` plus `SKILLS/EXAMPLES.md`.
- The current planning checkout has no `.codegraph`; implementation must run in the canonical Windows checkout with a current index or stop before editing code.
- Plan 06 starts only after Plans 01–05 are implemented in dependency order and milestone gates M1, M2, M3, M4, and M5 all pass.
- The sidecar API protocol remains version `1`; the first-release database
  schema is `3`, with released upgrade fixtures for schemas `1`, `2`, and `3`.
  Additions may not rename frozen fields, states, commands, receipt semantics,
  or authority rules.
- Sidecar startup continues to use `VESPER_FACTORY_SESSION_TOKEN`,
  `VESPER_FACTORY_HOME`, loopback-only binding, and exactly one
  `VESPER_FACTORY_READY {"protocol":1,"port":54321,"pid":1234,"schema":3}`
  line after migrations complete.
- Factory state remains under `%LOCALAPPDATA%\Vesper\Factory\`; SQLite uses WAL and foreign keys, and destructive migrations create a timestamped consistent database backup before the migration transaction.
- A sidecar health failure freezes mutations; at most three supervised restart attempts are allowed in a rolling five-minute window, after which the host enters read-only recovery.
- A factory-wide stop disables dispatch and paper effects atomically, allows at most 15 seconds for graceful worker shutdown, interrupts survivors, and requires explicit local-UI resume.
- Codex and Hermes remain separately installed/authenticated optional runtimes; either or both may be unavailable without preventing Vesper from launching or exposing read-only/local non-runtime features.
- The release target is `x86_64-pc-windows-msvc`, Tauri NSIS, current-user installation, and no release publication or code signing. MSI, ARM64, signing credentials, remote publication, and deployment need separate authority.
- The packaged UI must not require a user-installed Python, Node, Rust, Codex, or Hermes merely to launch.
- Keep `scripts/dashboard.py`, `vesper/dashboard/`, and their tests operational. This plan never removes, disables, renames, or redirects the Tkinter dashboard.
- Even complete replacement-parity evidence only makes a separate removal review eligible; removing Tkinter requires a new exact-scope approval.
- Do not edit `config/`, `vesper/risk.py`, `vesper/execution.py`, scheduler code, `vesper/data/massive/`, `vesper/data/model_research/`, active model artifacts, broker credentials, provider credentials, or risk/trading parameters.
- Massive data is read-only. Alpaca is paper-only and remains disabled without an active human-reviewed P2 envelope; an ambiguous paper effect is never retried automatically.
- Receipt-referenced evidence, manifests, and candidate artifacts remain pinned. Cleanup may remove only unreferenced temporary files, expired disposable worktrees, and bounded terminal-log tails.
- Use generated UUID4 identifiers with the roadmap's stable prefixes, RFC 3339 UTC timestamps ending in `Z`, canonical compact/sorted UTF-8 JSON, and SHA-256 hashes.
- Use test-first changes, deterministic assertions, one focused commit per task, `python -m py_compile` for changed Python modules, and the roadmap's full Python/Rust/frontend verification commands before M6.

---

## Dependencies and Acceptance Gates

Plan 06 consumes only frozen or explicitly published predecessor contracts. Before Task 1, record the exact predecessor commit IDs in the Plan 06 execution log and prove:

- **Plan 01 / M1:** schema `1`, the version-1 HTTP API, command idempotency, ordered events, authoritative receipts, stop/resume, lease reconciliation, and the development sidecar entry `scripts/factory.py` pass.
- **Plan 02 / M2:** the Tauri host can start the development sidecar, cache a redacted `FactorySnapshotV1`, render Mission Control, operate tray/background/quit, and render degraded/read-only state.
- **Plan 03 / M3:** `AgentAdapter`, exact probe-to-launch path reuse, the
  headless `NEXT` dispatch supervisor, fresh read-only reviewer isolation, fake
  Codex/Hermes executables, PTY interruption/termination, task packet
  injection, and truthful session exit recording pass.
- **Plan 04 / M4:** database schema `2`, paper-envelope effect-time validation,
  `AMBIGUOUS` outcomes, independent evaluation, replay/lineage, resource
  reservations, analytics, and integrated review pass.
- **Plan 05 / M5:** database schema `3`, episodes, FTS context, canaries,
  bounded code acceptance, rollback, and Memory state pass without changing
  the frozen authority boundary.
- **Shared files:** serialize edits after the final Plan 05 commit. Re-run the shared type/API contract suite before changing `scripts/factory.py`, sidecar supervision, snapshot types, Tauri configuration, or CI.

If a release test proves a predecessor contract is false, stop Plan 06, reopen the owning milestone gate, correct that plan's implementation with its own test and commit, then rebase Plan 06. Do not add a release-only bypass or reinterpret a frozen state.

### Additive Plan 06 release contracts

`FactorySnapshotV1.factory` gains one optional additive object:

```json
{
  "version": 7,
  "mode": "PAUSED",
  "health": "HEALTHY",
  "recovery": {
    "protocol": 1,
    "startup_reason": "ABNORMAL_SHUTDOWN",
    "reconciliation": "COMPLETE",
    "interrupted_attempt_ids": ["atm_00000000-0000-4000-8000-000000000001"],
    "revoked_lease_ids": ["rsv_00000000-0000-4000-8000-000000000002"],
    "revoked_runtime_grant_count": 1,
    "restart_attempts_in_window": 0,
    "restart_window_seconds": 300,
    "read_only_reason": null
  }
}
```

Exact added values are:

```python
FactoryHealthV1 = Literal[
    "HEALTHY", "DEGRADED", "RECOVERING", "READ_ONLY_RECOVERY",
]
StartupReasonV1 = Literal[
    "CLEAN_START", "ABNORMAL_SHUTDOWN", "MIGRATION_FAILED",
    "RESTART_BUDGET_EXHAUSTED",
]
ReconciliationStateV1 = Literal["NOT_REQUIRED", "RUNNING", "COMPLETE", "FAILED"]
```

The release report envelope is:

```json
{
  "protocol": 1,
  "gate": "migration-every-version",
  "status": "PASS",
  "started_at": "2026-07-24T12:00:00Z",
  "finished_at": "2026-07-24T12:00:10Z",
  "source_commit": "40 lowercase hexadecimal characters",
  "artifacts": [],
  "metrics": {},
  "failures": []
}
```

`status` is exactly `PASS` or `FAIL`. A report with missing keys, a different protocol, a non-current commit, or a non-empty `failures` array cannot satisfy M6.

## File and Responsibility Map

| Path | Responsibility |
|---|---|
| `vesper/factory/release/migrations.py` | Released-schema catalog, consistent backups, transactional migration runner |
| `vesper/factory/release/startup.py` | Migration-before-bind, abnormal-start reconciliation, forced paused mode |
| `vesper/factory/release/storage_audit.py` | Pinned/reclaimable storage and projected-reserve audit |
| `scripts/factory.py` | Invoke Plan 06 startup preparation before binding or printing readiness |
| `tests/release/support/sidecar.py` | Black-box sidecar process/client fixture using the frozen HTTP boundary |
| `tests/factory/release/` | Python migration, reconciliation, safety, storage, and simulation tests |
| `apps/desktop/src-tauri/src/sidecar/restart_budget.rs` | Rolling five-minute restart accounting and decision logic |
| `apps/desktop/src-tauri/src/sidecar/snapshot_cache.rs` | Atomic redacted snapshot cache for read-only recovery |
| `apps/desktop/src-tauri/src/sidecar/supervisor.rs` | Freeze, restart, and read-only recovery integration |
| `apps/desktop/src/recovery/RecoveryBanner.tsx` | Recovery status and guarded local resume UI |
| `apps/desktop/src/recovery/types.ts` | Exact frontend recovery types |
| `scripts/release/simulate_factory.py` | Seeded 100-task/fault simulation and report |
| `scripts/release/check_resources.py` | Resource/storage audit CLI and report |
| `packaging/pyinstaller/vesper_factory.spec` | Reproducible PyInstaller `onedir` sidecar definition |
| `packaging/requirements-build.txt` | Pinned Windows build-only Python dependency |
| `scripts/release/build_sidecar.ps1` | Build and verify the sidecar directory |
| `packaging/legal-policy.json` | Allowed/prohibited license and provenance rules |
| `packaging/borrowed-source.json` | Exact provenance for copied source; empty when no source was copied |
| `scripts/release/generate_legal.py` | Notices, license texts, provenance, and component coverage |
| `scripts/release/install_syft.ps1` | Version/checksum-verified Syft acquisition |
| `apps/desktop/src-tauri/tauri.windows.conf.json` | NSIS target and bundled sidecar/legal resources |
| `scripts/release/build_windows.ps1` | Ordered sidecar, frontend, Rust, legal, SBOM, and NSIS build |
| `scripts/release/smoke_windows.ps1` | Install, launch, unavailable-runtime, forced-kill, paused-restart, and uninstall smoke |
| `.github/workflows/release-hardening-windows.yml` | PR package gate plus manual/scheduled eight-hour soak |
| `packaging/soak-policy.json` | Exact duration and resource acceptance limits |
| `apps/desktop/src-tauri/tests/eight_hour_soak.rs` | Shared-host/sidecar/PTY/event/restart soak |
| `scripts/release/run_soak.ps1` | Eight-hour Windows soak driver and report validator |
| `packaging/tkinter-parity.json` | Complete legacy capability/evidence matrix |
| `docs/release/tkinter-replacement-parity.md` | Evidence-backed retain/removal-review decision |
| `packaging/release-gates.json` | M6 required reports and artifact checks |
| `scripts/release/verify_m6.py` | Aggregate M6 verifier |

Generated installers and transient build output remain under ignored `build/` and `dist/`. Machine-readable gate reports are written under `release/reports/`; legal notices, provenance, and the SBOM are written under `release/legal/`, `release/provenance/`, and `release/sbom/` and are committed when dependencies change.

### Task 1: Transactional Migration Backup Contract

**Files:**
- Create: `vesper/factory/release/__init__.py`
- Create: `vesper/factory/release/migrations.py`
- Create: `packaging/schema-releases.json`
- Create: `tests/factory/release/test_migration_backups.py`

**Interfaces:**
- Consumes: the ordered Plan 01/04/05 migrations for database schemas `1`, `2`,
  and `3`, WAL mode, foreign keys, and startup ownership.
- Produces: `MigrationStep`, `MigrationReportV1`, `RELEASED_SCHEMA_VERSIONS`, `CURRENT_SCHEMA`, and `migrate_database(db_path, backup_dir, steps, now)`.
- Invariant: current production registry is schema `3` with no Plan 06 product
  version bump; the destructive-backup test uses an in-test synthetic `3 → 4`
  step and does not register or ship schema `4`.

- [ ] **Step 1: Write the failing backup and rollback tests**

```python
# tests/factory/release/test_migration_backups.py
from datetime import datetime, timezone
import sqlite3

import pytest

from vesper.factory.release.migrations import MigrationStep, migrate_database

NOW = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)


def _schema_three(path):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE ledger (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO ledger(value) VALUES ('authoritative')")
        conn.execute("PRAGMA user_version = 3")


def test_destructive_step_creates_consistent_timestamped_backup(tmp_path):
    db_path = tmp_path / "factory.db"
    backup_dir = tmp_path / "backups"
    _schema_three(db_path)

    step = MigrationStep(
        from_schema=3,
        to_schema=4,
        name="drop_ledger",
        destructive=True,
        statements=("DROP TABLE ledger",),
    )
    report = migrate_database(db_path, backup_dir, (step,), now=lambda: NOW)

    assert report.from_schema == 3
    assert report.to_schema == 4
    assert report.backup_path == (
        backup_dir / "factory.schema-0003.20260724T120000000000Z.bak"
    )
    with sqlite3.connect(report.backup_path) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 3
        assert backup.execute("SELECT value FROM ledger").fetchone()[0] == "authoritative"


def test_failed_migration_rolls_back_database_but_retains_backup(tmp_path):
    db_path = tmp_path / "factory.db"
    backup_dir = tmp_path / "backups"
    _schema_three(db_path)
    step = MigrationStep(
        from_schema=3,
        to_schema=4,
        name="invalid_destructive_step",
        destructive=True,
        statements=("DROP TABLE ledger", "ALTER TABLE missing_table RENAME TO never"),
    )

    with pytest.raises(sqlite3.OperationalError):
        migrate_database(db_path, backup_dir, (step,), now=lambda: NOW)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        assert conn.execute("SELECT value FROM ledger").fetchone()[0] == "authoritative"
    assert len(list(backup_dir.glob("*.bak"))) == 1
```

- [ ] **Step 2: Run the focused test and verify red**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan06-migration-red-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/release/test_migration_backups.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'vesper.factory.release'`.

- [ ] **Step 3: Add the released-schema manifest and minimal migration runner**

`packaging/schema-releases.json`:

```json
{
  "protocol": 1,
  "current_schema": 3,
  "released": [
    {
      "schema": 1,
      "fixture": "tests/factory/release/fixtures/schema_v1.sql",
      "minimum_sidecar_protocol": 1
    },
    {
      "schema": 2,
      "fixture": "tests/factory/release/fixtures/schema_v2.sql",
      "minimum_sidecar_protocol": 1
    },
    {
      "schema": 3,
      "fixture": "tests/factory/release/fixtures/schema_v3.sql",
      "minimum_sidecar_protocol": 1
    }
  ]
}
```

Core implementation:

```python
# vesper/factory/release/migrations.py
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

CURRENT_SCHEMA = 3
RELEASED_SCHEMA_VERSIONS = (1, 2, 3)


@dataclass(frozen=True)
class MigrationStep:
    from_schema: int
    to_schema: int
    name: str
    destructive: bool
    statements: Sequence[str]


@dataclass(frozen=True)
class MigrationReportV1:
    protocol: int
    from_schema: int
    to_schema: int
    applied: Sequence[str]
    backup_path: Path | None


def _timestamp(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    return utc.strftime("%Y%m%dT%H%M%S%fZ")


def _consistent_backup(source: sqlite3.Connection, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source.execute("PRAGMA wal_checkpoint(FULL)")
    with sqlite3.connect(target) as backup:
        source.backup(backup)
        if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("migration backup failed SQLite integrity_check")


def _pending_steps(
    current: int,
    steps: Sequence[MigrationStep],
) -> Sequence[MigrationStep]:
    ordered = tuple(sorted(steps, key=lambda step: step.from_schema))
    pending: list[MigrationStep] = []
    cursor = current
    for step in ordered:
        if step.from_schema < cursor:
            continue
        if step.from_schema != cursor:
            raise RuntimeError(f"migration path breaks at schema {cursor}")
        pending.append(step)
        cursor = step.to_schema
    return tuple(pending)


def migrate_database(
    db_path: Path,
    backup_dir: Path,
    steps: Sequence[MigrationStep],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> MigrationReportV1:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        pending = _pending_steps(current, steps)
        backup_path = None
        if any(step.destructive for step in pending):
            backup_path = backup_dir / (
                f"factory.schema-{current:04d}.{_timestamp(now())}.bak"
            )
            _consistent_backup(conn, backup_path)

        conn.execute("BEGIN IMMEDIATE")
        try:
            for step in pending:
                for statement in step.statements:
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {step.to_schema:d}")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("migration failed SQLite foreign_key_check")
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("migration failed SQLite integrity_check")
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    return MigrationReportV1(
        protocol=1,
        from_schema=current,
        to_schema=pending[-1].to_schema if pending else current,
        applied=tuple(step.name for step in pending),
        backup_path=backup_path,
    )
```

The production `steps` registry contains the exact additive `1 → 2` research
and `2 → 3` learning migrations already owned by Plans 04 and 05; Plan 06 does
not copy or reinterpret their SQL. It adapts the registered migration objects
from `vesper.factory.migrations` into this backup/reporting wrapper and asserts
their stored checksums. Any future schema release must add a contiguous step, a
released fixture, and its expected backup behavior in one commit.

- [ ] **Step 4: Run focused tests and Python compilation**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan06-migration-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/release/test_migration_backups.py -q \
  --basetemp="$TMPROOT/pytest"
.venv/Scripts/python.exe -m py_compile vesper/factory/release/migrations.py
```

Expected: `2 passed`; `py_compile` exits `0`.

- [ ] **Step 5: Inspect and commit**

```bash
git diff --check
git diff --stat
git diff -- vesper/factory/release/migrations.py packaging/schema-releases.json tests/factory/release/test_migration_backups.py
git add vesper/factory/release/__init__.py vesper/factory/release/migrations.py packaging/schema-releases.json tests/factory/release/test_migration_backups.py
git commit -m "feat: add release migration backups"
```

### Task 2: Every-Released-Version Startup Matrix

**Files:**
- Create: `tests/release/support/__init__.py`
- Create: `tests/release/support/sidecar.py`
- Create: `scripts/release/capture_schema_fixture.py`
- Create: `tests/factory/release/fixtures/schema_v1.sql`
- Create: `tests/factory/release/fixtures/schema_v2.sql`
- Create: `tests/factory/release/fixtures/schema_v3.sql`
- Create: `tests/factory/release/test_every_released_schema.py`
- Create: `vesper/factory/release/startup.py`
- Modify: `scripts/factory.py`

**Interfaces:**
- Consumes: the exact no-argument development sidecar startup in `scripts/factory.py`, frozen readiness line, bearer-authenticated `/v1/health` and `/v1/snapshot`, and Task 1's `migrate_database`.
- Produces: `prepare_startup(factory_home: Path, now: Callable[[], datetime]) -> StartupPreparationV1` and black-box `SidecarProcess`.
- `SidecarProcess.start()` migrates any released fixture and returns
  `ReadyV1(protocol=1, port, pid, schema=3)` without logging either token.

- [ ] **Step 1: Write the failing manifest/fixture matrix test**

```python
# tests/factory/release/test_every_released_schema.py
import json
from pathlib import Path

import pytest

from tests.release.support.sidecar import SidecarProcess, restore_sql_fixture

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = json.loads((ROOT / "packaging/schema-releases.json").read_text("utf-8"))


@pytest.mark.parametrize("release", MANIFEST["released"], ids=lambda item: f"schema-{item['schema']}")
def test_sidecar_starts_from_every_released_schema(tmp_path, release):
    factory_home = tmp_path / "Factory"
    factory_home.mkdir()
    restore_sql_fixture(ROOT / release["fixture"], factory_home / "factory.db")

    with SidecarProcess.start(factory_home) as sidecar:
        health = sidecar.get_json("/v1/health")
        snapshot = sidecar.get_json("/v1/snapshot")

    assert health["protocol"] == 1
    assert health["schema"] == MANIFEST["current_schema"] == 3
    assert snapshot["protocol"] == 1
    assert snapshot["factory"]["mode"] == "PAUSED"
    assert sidecar.ready.schema == 3


def test_manifest_lists_every_fixture_once():
    versions = [item["schema"] for item in MANIFEST["released"]]
    assert versions == list(range(1, MANIFEST["current_schema"] + 1))
    for item in MANIFEST["released"]:
        assert (ROOT / item["fixture"]).is_file()
```

- [ ] **Step 2: Run the matrix test and verify red**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan06-schema-red-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/release/test_every_released_schema.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection because `tests.release.support.sidecar` does not exist.

- [ ] **Step 3: Implement the black-box process fixture and startup preparation**

The process fixture must:

1. Generate independent 32-byte URL-safe session tokens.
2. set only `VESPER_FACTORY_SESSION_TOKEN` and the supplied absolute `VESPER_FACTORY_HOME`;
3. run `.venv/Scripts/python.exe scripts/factory.py` from repository root;
4. accept only the frozen readiness prefix and exact `ReadyV1` keys;
5. reject a second stdout line before readiness;
6. send bearer-authenticated requests with `urllib.request`;
7. terminate the process tree on context exit; and
8. retain bounded stdout/stderr tails with token replacement.

Exact public signatures are
`SidecarProcess.start(factory_home: Path, timeout_seconds: float = 20.0) -> SidecarProcess`,
`get_json(path: str) -> dict[str, object]`, and
`post_command(kind: str, payload: dict[str, object], expected_version: int, idempotency_key: str) -> dict[str, object]`.
Its immutable `ReadyV1` fields are `protocol: int`, `port: int`, `pid: int`, and
`schema: int`; the process fixture does not import private factory modules or
mutate SQLite.

`vesper/factory/release/startup.py` adds:

```python
@dataclass(frozen=True)
class StartupPreparationV1:
    protocol: int
    schema: int
    migration: MigrationReportV1
    backup_paths: Sequence[Path]


def prepare_startup(
    factory_home: Path,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> StartupPreparationV1:
    factory_home.mkdir(parents=True, exist_ok=True)
    db_path = factory_home / "factory.db"
    if not db_path.is_file():
        raise RuntimeError("Plan 01 schema initialization must run before release migration")
    migration = migrate_database(
        db_path=db_path,
        backup_dir=factory_home / "backups",
        steps=PRODUCTION_MIGRATIONS,
        now=now,
    )
    if migration.to_schema != CURRENT_SCHEMA:
        raise RuntimeError(
            f"factory schema {migration.to_schema} does not match sidecar schema {CURRENT_SCHEMA}"
        )
    return StartupPreparationV1(
        protocol=1,
        schema=CURRENT_SCHEMA,
        migration=migration,
        backup_paths=(migration.backup_path,) if migration.backup_path else (),
    )
```

Move no workflow logic into this wrapper. `scripts/factory.py` reads and
validates both required environment variables, runs Plan 01's existing
fresh-database schema-`1` initializer when `factory.db` is absent, calls
`prepare_startup`, and only then binds a socket. It passes
`StartupPreparationV1.schema` to the existing readiness encoder.

- [ ] **Step 4: Capture and review deterministic schema fixtures `1..3`**

`scripts/release/capture_schema_fixture.py` applies the registered production
migrations only through the requested target version, opens the database
read-only, runs `PRAGMA integrity_check`, and writes `Connection.iterdump()`
output with LF endings and a final newline. It never starts the normal sidecar,
because normal startup must always migrate to current schema `3`.

Run:

```bash
for schema in 1 2 3; do
  PYTHONPATH=. .venv/Scripts/python.exe scripts/release/capture_schema_fixture.py \
    --schema "$schema" \
    --output "tests/factory/release/fixtures/schema_v${schema}.sql"
done
git diff -- tests/factory/release/fixtures/schema_v1.sql \
  tests/factory/release/fixtures/schema_v2.sql \
  tests/factory/release/fixtures/schema_v3.sql
```

Expected: every capture exits `0`; each output begins with
`BEGIN TRANSACTION;`, contains its exact migration prefix and matching
`PRAGMA user_version`, contains no token/credential rows, and ends with
`COMMIT;`.

- [ ] **Step 5: Run matrix, migration, and compile checks**

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan06-schema-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/release/test_migration_backups.py \
  tests/factory/release/test_every_released_schema.py -q \
  --basetemp="$TMPROOT/pytest"
.venv/Scripts/python.exe -m py_compile \
  vesper/factory/release/startup.py \
  scripts/release/capture_schema_fixture.py \
  scripts/factory.py
```

Expected: all focused tests PASS; each compile exits `0`. Verify fixtures `1`
and `2` upgrade to `3`, fixture `3` is an identity startup, and each readiness
line reports protocol `1` plus schema `3`.

- [ ] **Step 6: Inspect and commit**

```bash
git diff --check
git diff --stat
git diff -- scripts/factory.py vesper/factory/release/startup.py tests/factory/release/test_every_released_schema.py
git add scripts/factory.py scripts/release/capture_schema_fixture.py vesper/factory/release/startup.py tests/release/support/__init__.py tests/release/support/sidecar.py tests/factory/release/fixtures/schema_v1.sql tests/factory/release/fixtures/schema_v2.sql tests/factory/release/fixtures/schema_v3.sql tests/factory/release/test_every_released_schema.py
git commit -m "test: verify every released factory schema"
```

### Task 3: Abnormal Startup Reconciliation and Paused Restart

**Files:**
- Create: `tests/factory/release/test_paused_restart.py`
- Modify: `vesper/factory/release/startup.py`
- Modify: `vesper/factory/reconciliation.py`
- Modify: `scripts/factory.py`
- Modify: `tests/release/support/sidecar.py`

**Interfaces:**
- Consumes: Plan 01's one-transaction reconciliation primitive, append-only receipts/events, lease/runtime-grant revocation, and `factory.resume` command; Plan 03's session exit bookkeeping.
- Produces: `RecoveryStatusV1`, the additive `FactorySnapshotV1.factory.recovery` object, and `SidecarProcess.kill_tree()`.
- Reconciliation never decides that an interrupted attempt succeeded and never creates a retry or successor.

- [ ] **Step 1: Write the forced-kill black-box test**

```python
# tests/factory/release/test_paused_restart.py
from tests.release.support.scenarios import admitted_running_attempt
from tests.release.support.sidecar import SidecarProcess


def test_forced_kill_restarts_paused_and_reconciles_once(tmp_path):
    factory_home = tmp_path / "Factory"
    first = SidecarProcess.start(factory_home)
    scenario = admitted_running_attempt(first, runtime="CODEX")
    first.kill_tree()

    with SidecarProcess.start(factory_home) as restarted:
        snapshot = restarted.get_json("/v1/snapshot")
        recovery = snapshot["factory"]["recovery"]

        assert snapshot["factory"]["mode"] == "PAUSED"
        assert snapshot["factory"]["health"] == "HEALTHY"
        assert recovery == {
            "protocol": 1,
            "startup_reason": "ABNORMAL_SHUTDOWN",
            "reconciliation": "COMPLETE",
            "interrupted_attempt_ids": [scenario.attempt_id],
            "revoked_lease_ids": [scenario.lease_id],
            "revoked_runtime_grant_count": 1,
            "restart_attempts_in_window": 0,
            "restart_window_seconds": 300,
            "read_only_reason": None,
        }
        attempt = next(item for item in snapshot["attempts"] if item["attempt_id"] == scenario.attempt_id)
        task = next(item for item in snapshot["tasks"] if item["task_id"] == scenario.task_id)
        assert attempt["outcome"] == "INTERRUPTED"
        assert task["state"] == "INTERRUPTED"

        receipts = restarted.receipts_for(scenario.attempt_id, kind="attempt.interrupted")
        assert len(receipts) == 1
        assert restarted.post_command(
            "factory.resume", {}, snapshot["factory"]["version"], "resume-after-review"
        )["ok"] is True

    with SidecarProcess.start(factory_home) as second_restart:
        assert len(
            second_restart.receipts_for(scenario.attempt_id, kind="attempt.interrupted")
        ) == 1
```

Add companion tests in the same file:

- an `EVALUATING` attempt is interrupted and not accepted;
- an `AMBIGUOUS` attempt remains `AMBIGUOUS`;
- no worker grant or MCP tool can invoke `factory.resume`;
- dispatch before explicit resume returns `TRANSITION_DENIED`; and
- a clean explicit quit does not create interruption receipts.

- [ ] **Step 2: Run the focused test and verify red**

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan06-restart-red-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/release/test_paused_restart.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL because `factory.recovery` is absent or startup does not remain `PAUSED`. If reconciliation itself is absent, reopen M1 before continuing.

- [ ] **Step 3: Add the exact recovery status and startup ordering**

```python
# vesper/factory/release/startup.py
@dataclass(frozen=True)
class RecoveryStatusV1:
    protocol: int
    startup_reason: str
    reconciliation: str
    interrupted_attempt_ids: Sequence[str]
    revoked_lease_ids: Sequence[str]
    revoked_runtime_grant_count: int
    restart_attempts_in_window: int
    restart_window_seconds: int
    read_only_reason: str | None


def reconcile_abnormal_startup(
    reconciler: StartupReconciler,
    *,
    unclean_shutdown: bool,
) -> RecoveryStatusV1:
    if not unclean_shutdown:
        return RecoveryStatusV1(
            protocol=1,
            startup_reason="CLEAN_START",
            reconciliation="NOT_REQUIRED",
            interrupted_attempt_ids=(),
            revoked_lease_ids=(),
            revoked_runtime_grant_count=0,
            restart_attempts_in_window=0,
            restart_window_seconds=300,
            read_only_reason=None,
        )
    result = reconciler.reconcile_and_pause(reason="ABNORMAL_SHUTDOWN")
    return RecoveryStatusV1(
        protocol=1,
        startup_reason="ABNORMAL_SHUTDOWN",
        reconciliation="COMPLETE",
        interrupted_attempt_ids=tuple(sorted(result.interrupted_attempt_ids)),
        revoked_lease_ids=tuple(sorted(result.revoked_lease_ids)),
        revoked_runtime_grant_count=result.revoked_runtime_grant_count,
        restart_attempts_in_window=0,
        restart_window_seconds=300,
        read_only_reason=None,
    )
```

`StartupReconciler.reconcile_and_pause(reason)` must execute these effects in one SQLite transaction and in this order:

1. persist factory mode `PAUSED` and disable dispatch/paper effects;
2. mark active `RUNNING`/`EVALUATING` attempts and tasks `INTERRUPTED`;
3. preserve existing `AMBIGUOUS` outcomes;
4. revoke active leases and runtime grants;
5. mark active sessions interrupted with their observed exit information;
6. append one `attempt.interrupted` receipt per newly interrupted attempt;
7. append ordered reconciliation events; and
8. append one `factory.reconciled` receipt carrying sorted affected IDs.

Idempotency is keyed by the prior process/startup epoch plus attempt ID. Running reconciliation again appends no second interruption receipt. `scripts/factory.py` completes migration, reconciliation, and forced pause before binding and before printing readiness.

- [ ] **Step 4: Run restart, kernel reconciliation, and compile checks**

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan06-restart-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/release/test_paused_restart.py \
  tests/factory -q \
  --basetemp="$TMPROOT/pytest"
.venv/Scripts/python.exe -m py_compile \
  vesper/factory/release/startup.py \
  vesper/factory/reconciliation.py \
  scripts/factory.py
```

Expected: all focused and M1 reconciliation tests PASS; compilation exits `0`; no test observes an automatic resume, automatic retry, or duplicated interruption receipt.

- [ ] **Step 5: Inspect and commit**

```bash
git diff --check
git diff --stat
git diff -- vesper/factory/release/startup.py vesper/factory/reconciliation.py scripts/factory.py tests/factory/release/test_paused_restart.py
git add vesper/factory/release/startup.py vesper/factory/reconciliation.py scripts/factory.py tests/release/support/sidecar.py tests/factory/release/test_paused_restart.py
git commit -m "feat: reconcile crashes into paused startup"
```

### Task 4: Bounded Sidecar Restart and Read-Only Recovery

**Files:**
- Create: `apps/desktop/src-tauri/src/sidecar/restart_budget.rs`
- Create: `apps/desktop/src-tauri/src/sidecar/snapshot_cache.rs`
- Modify: `apps/desktop/src-tauri/src/sidecar/mod.rs`
- Modify: `apps/desktop/src-tauri/src/sidecar/supervisor.rs`
- Create: `apps/desktop/src/recovery/types.ts`
- Create: `apps/desktop/src/recovery/RecoveryBanner.tsx`
- Create: `apps/desktop/src/recovery/RecoveryBanner.test.tsx`
- Modify: `apps/desktop/src/App.tsx`

**Interfaces:**
- Consumes: Plan 02's `SidecarSupervisor`, snapshot/event proxy, application mode store, and mutation-command dispatch.
- Produces: `RestartBudget`, `RestartDecision`, `SnapshotCache`, `RecoveryStatusV1`, and `RecoveryBannerProps`.
- Mutation freeze starts on the first health failure and ends only after a healthy readiness/health/snapshot sequence plus explicit operator resume.

- [ ] **Step 1: Write failing Rust restart-budget and cache tests**

```rust
// apps/desktop/src-tauri/src/sidecar/restart_budget.rs
#[cfg(test)]
mod tests {
    use super::{RestartBudget, RestartDecision};
    use std::time::{Duration, Instant};

    #[test]
    fn fourth_failure_inside_five_minutes_enters_read_only_recovery() {
        let start = Instant::now();
        let mut budget = RestartBudget::new(3, Duration::from_secs(300));

        assert_eq!(
            budget.record_failure(start),
            RestartDecision::RestartAfter(Duration::from_secs(1))
        );
        assert_eq!(
            budget.record_failure(start + Duration::from_secs(60)),
            RestartDecision::RestartAfter(Duration::from_secs(2))
        );
        assert_eq!(
            budget.record_failure(start + Duration::from_secs(120)),
            RestartDecision::RestartAfter(Duration::from_secs(4))
        );
        assert_eq!(
            budget.record_failure(start + Duration::from_secs(180)),
            RestartDecision::EnterReadOnlyRecovery
        );
    }

    #[test]
    fn failures_age_out_of_the_rolling_window() {
        let start = Instant::now();
        let mut budget = RestartBudget::new(3, Duration::from_secs(300));
        let _first = budget.record_failure(start);

        assert_eq!(
            budget.record_failure(start + Duration::from_secs(301)),
            RestartDecision::RestartAfter(Duration::from_secs(1))
        );
        assert_eq!(budget.attempts_in_window(), 1);
    }
}
```

Add `snapshot_cache.rs` tests that write sequences `41` then `42`, reject sequence `40`, simulate an interrupted temporary-file write, and prove `load()` still returns the complete redacted sequence-`42` snapshot.

- [ ] **Step 2: Run focused Rust tests and verify red**

```powershell
Set-Location apps/desktop/src-tauri
cargo test sidecar::restart_budget sidecar::snapshot_cache
```

Expected: compilation FAIL because both modules and types are absent.

- [ ] **Step 3: Implement exact restart decisions and atomic snapshot cache**

```rust
// apps/desktop/src-tauri/src/sidecar/restart_budget.rs
use std::collections::VecDeque;
use std::time::{Duration, Instant};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RestartDecision {
    RestartAfter(Duration),
    EnterReadOnlyRecovery,
}

#[derive(Debug)]
pub struct RestartBudget {
    max_attempts: usize,
    window: Duration,
    failures: VecDeque<Instant>,
}

impl RestartBudget {
    pub fn new(max_attempts: usize, window: Duration) -> Self {
        Self {
            max_attempts,
            window,
            failures: VecDeque::new(),
        }
    }

    pub fn record_failure(&mut self, now: Instant) -> RestartDecision {
        while self
            .failures
            .front()
            .is_some_and(|oldest| now.duration_since(*oldest) > self.window)
        {
            self.failures.pop_front();
        }
        if self.failures.len() >= self.max_attempts {
            return RestartDecision::EnterReadOnlyRecovery;
        }
        self.failures.push_back(now);
        let delay = 1_u64 << (self.failures.len() - 1);
        RestartDecision::RestartAfter(Duration::from_secs(delay))
    }

    pub fn attempts_in_window(&self) -> usize {
        self.failures.len()
    }
}
```

`SnapshotCache` writes canonical JSON to
`%LOCALAPPDATA%\Vesper\Factory\recovery\last-snapshot-v1.json.tmp`, calls
`sync_all`, atomically renames it to `last-snapshot-v1.json`, and fsyncs the
parent directory where Windows permits. It accepts only protocol `1`, a
sequence greater than or equal to the cached sequence, and values that have
already passed the shared redactor. It stores no session token, worker token,
credential, or terminal body.

Integrate the supervisor state sequence exactly:

```text
Healthy
  -> first failed health/readiness: Degraded + mutations frozen
  -> RestartAfter(1s), RestartAfter(2s), RestartAfter(4s)
  -> healthy readiness + /v1/health + fresh snapshot: PausedHealthy
  -> fourth failure inside 300s: ReadOnlyRecovery using SnapshotCache
```

No restart path invokes `factory.resume`. A schema/protocol mismatch counts as
a failure, and a sidecar that prints a malformed readiness line is terminated
before retry.

- [ ] **Step 4: Write the recovery component test and verify red**

```tsx
// apps/desktop/src/recovery/RecoveryBanner.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { RecoveryBanner } from "./RecoveryBanner";

it("shows cached read-only state and offers no resume mutation", () => {
  const onResume = vi.fn();
  const onExportRecoveryDetails = vi.fn().mockResolvedValue(undefined);
  render(
    <RecoveryBanner
      mode="PAUSED"
      health="READ_ONLY_RECOVERY"
      status={{
        protocol: 1,
        startupReason: "RESTART_BUDGET_EXHAUSTED",
        reconciliation: "FAILED",
        interruptedAttemptIds: [],
        revokedLeaseIds: [],
        revokedRuntimeGrantCount: 0,
        restartAttemptsInWindow: 3,
        restartWindowSeconds: 300,
        readOnlyReason: "Sidecar failed more than three times in five minutes.",
      }}
      onResume={onResume}
      onExportRecoveryDetails={onExportRecoveryDetails}
    />,
  );

  expect(screen.getByRole("status")).toHaveTextContent("Read-only recovery");
  expect(screen.queryByRole("button", { name: "Resume factory" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Export recovery details" }));
  expect(onResume).not.toHaveBeenCalled();
  expect(onExportRecoveryDetails).toHaveBeenCalledOnce();
});
```

Run:

```powershell
Set-Location apps/desktop
pnpm test --run src/recovery/RecoveryBanner.test.tsx
```

Expected: FAIL because `RecoveryBanner` does not exist.

- [ ] **Step 5: Implement typed recovery rendering and mutation freeze**

```ts
// apps/desktop/src/recovery/types.ts
export type FactoryHealthV1 =
  | "HEALTHY"
  | "DEGRADED"
  | "RECOVERING"
  | "READ_ONLY_RECOVERY";
export type StartupReasonV1 =
  | "CLEAN_START"
  | "ABNORMAL_SHUTDOWN"
  | "MIGRATION_FAILED"
  | "RESTART_BUDGET_EXHAUSTED";
export type ReconciliationStateV1 =
  | "NOT_REQUIRED"
  | "RUNNING"
  | "COMPLETE"
  | "FAILED";

export interface RecoveryStatusV1 {
  protocol: 1;
  startupReason: StartupReasonV1;
  reconciliation: ReconciliationStateV1;
  interruptedAttemptIds: string[];
  revokedLeaseIds: string[];
  revokedRuntimeGrantCount: number;
  restartAttemptsInWindow: number;
  restartWindowSeconds: 300;
  readOnlyReason: string | null;
}

export interface RecoveryBannerProps {
  mode: "RUNNING" | "PAUSED" | "STOPPED";
  health: FactoryHealthV1;
  status: RecoveryStatusV1;
  onResume: () => Promise<void>;
  onExportRecoveryDetails: () => Promise<void>;
}
```

`RecoveryBanner` renders `role="status"`, exact restart count/window, affected
attempts, factual reason, and an export-recovery-details action. It renders
`Resume factory` only when health is `HEALTHY`, mode is `PAUSED`, and
reconciliation is `COMPLETE` or `NOT_REQUIRED`. `App.tsx` disables every
mutating command while health is not `HEALTHY`; board, dossier, evidence,
cached snapshot, and recovery export stay readable.

- [ ] **Step 6: Run focused and subsystem checks**

```powershell
Set-Location apps/desktop
pnpm test --run src/recovery/RecoveryBanner.test.tsx
pnpm test --run
pnpm build
Set-Location src-tauri
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test sidecar
```

Expected: all commands exit `0`; the fourth in-window failure yields
`READ_ONLY_RECOVERY`; no mutation or automatic resume occurs.

- [ ] **Step 7: Inspect and commit**

```bash
git diff --check
git diff --stat
git diff -- apps/desktop/src-tauri/src/sidecar apps/desktop/src/recovery apps/desktop/src/App.tsx
git add apps/desktop/src-tauri/src/sidecar/restart_budget.rs apps/desktop/src-tauri/src/sidecar/snapshot_cache.rs apps/desktop/src-tauri/src/sidecar/mod.rs apps/desktop/src-tauri/src/sidecar/supervisor.rs apps/desktop/src/recovery/types.ts apps/desktop/src/recovery/RecoveryBanner.tsx apps/desktop/src/recovery/RecoveryBanner.test.tsx apps/desktop/src/App.tsx
git commit -m "feat: bound sidecar recovery attempts"
```

### Task 5: Deterministic Failure Injection and 100-Task Simulation

**Files:**
- Create: `tests/release/support/scenarios.py`
- Create: `tests/release/support/faults.py`
- Create: `tests/factory/release/fixtures/fault-plan-v1.json`
- Create: `scripts/release/simulate_factory.py`
- Create: `tests/factory/release/test_failure_injection.py`
- Create: `tests/factory/release/test_100_task_simulation.py`

**Interfaces:**
- Consumes: frozen `/v1/commands` idempotency, ordered events, Plan 03 fake runtimes, Plan 01 reconciliation, and Task 4 restart policy.
- Produces: `FaultPlanV1`, `SimulationReportV1`, and the CLI `simulate_factory.py --tasks 100 --concurrency 4 --seed 20260724 --fault-plan tests/factory/release/fixtures/fault-plan-v1.json --report release/reports/100-task-simulation-v1.json`.
- The harness uses disposable factory homes and fake paper/runtime adapters only; it cannot reach Massive, Alpaca, credentials, or protected paths.

- [ ] **Step 1: Add the exact seeded fault plan and failing report assertion**

`tests/factory/release/fixtures/fault-plan-v1.json`:

```json
{
  "protocol": 1,
  "seed": 20260724,
  "task_count": 100,
  "concurrency": 4,
  "duplicate_command_tasks": [7, 43, 88],
  "runtime_exit_tasks": [13, 47, 79],
  "lease_expiry_tasks": [23, 61],
  "sidecar_exit_after_completed_task": 50
}
```

```python
# tests/factory/release/test_100_task_simulation.py
from pathlib import Path

from scripts.release.simulate_factory import run_simulation


def test_seeded_one_hundred_task_simulation_has_exact_invariants(tmp_path):
    root = Path(__file__).resolve().parents[3]
    report = run_simulation(
        factory_home=tmp_path / "Factory",
        fault_plan_path=root / "tests/factory/release/fixtures/fault-plan-v1.json",
        source_commit="0123456789abcdef0123456789abcdef01234567",
    )

    assert report["status"] == "PASS"
    assert report["metrics"] == {
        "task_count": 100,
        "completed_task_count": 100,
        "attempt_count": 105,
        "interrupted_attempt_count": 5,
        "authoritative_completion_receipt_count": 100,
        "idempotent_replay_count": 3,
        "idempotency_conflict_count": 0,
        "sidecar_restart_count": 1,
        "active_lease_count": 0,
        "active_runtime_grant_count": 0,
        "event_sequence_contiguous": True,
        "sqlite_integrity_check": "ok",
        "sqlite_foreign_key_violation_count": 0,
    }
    assert report["failures"] == []
```

- [ ] **Step 2: Run the simulation test and verify red**

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan06-simulation-red-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/release/test_100_task_simulation.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection because `scripts.release.simulate_factory` is absent.

- [ ] **Step 3: Implement the release-only fault harness and report schema**

```python
# tests/release/support/faults.py
@dataclass(frozen=True)
class FaultPlanV1:
    protocol: int
    seed: int
    task_count: int
    concurrency: int
    duplicate_command_tasks: Sequence[int]
    runtime_exit_tasks: Sequence[int]
    lease_expiry_tasks: Sequence[int]
    sidecar_exit_after_completed_task: int


class DeterministicFaults:
    def __init__(self, plan: FaultPlanV1):
        self.plan = plan

    def duplicate_response_for(self, ordinal: int) -> bool:
        return ordinal in self.plan.duplicate_command_tasks

    def runtime_exit_for(self, ordinal: int) -> bool:
        return ordinal in self.plan.runtime_exit_tasks

    def expire_lease_for(self, ordinal: int) -> bool:
        return ordinal in self.plan.lease_expiry_tasks
```

`run_simulation` performs this exact deterministic sequence:

1. create one admitted local-compute campaign with no paper authority;
2. create 100 tasks numbered `001` through `100`;
3. dispatch at most four fake-runtime tasks concurrently;
4. replay the same canonical command/idempotency key after a simulated dropped
   response for tasks 7, 43, and 88;
5. force runtime exit for tasks 13, 47, and 79, reconcile each as interrupted,
   and create one explicit retry attempt;
6. expire leases for tasks 23 and 61, reconcile evidence before creating one
   explicit retry attempt;
7. kill/restart the sidecar after task 50 completes and explicitly resume after
   successful reconciliation;
8. finish all retries through fresh independent fake evaluators;
9. query all events in pages of 500 and prove contiguous unique sequences;
10. run SQLite integrity/foreign-key checks and prove no active lease/grant; and
11. atomically write the version-1 release report.

The script returns exit `0` only for `status: PASS`; all mismatches are factual
strings in `failures` and return exit `1`.

- [ ] **Step 4: Add the focused failure matrix**

`tests/factory/release/test_failure_injection.py` contains six separate tests:

| Fault | Required result |
|---|---|
| SQLite writer lock | command fails with stable `DATABASE_BUSY`; no partial transition/receipt |
| dropped command response | identical replay returns original result; one effect |
| fake runtime exit | session/attempt become `INTERRUPTED`; no success receipt |
| sidecar process exit | paused reconciliation precedes explicit resume |
| torn snapshot-cache write | last complete cached snapshot remains readable |
| projected disk reserve breach | artifact-producing dispatch is blocked before file creation |

Use fake clocks and temporary paths; do not use wall-clock sleeps or fill a real
disk.

- [ ] **Step 5: Run the simulation and failure matrix**

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan06-simulation-green-$$"
REPORT="$TMPROOT/100-task-report.json"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/release/test_failure_injection.py \
  tests/factory/release/test_100_task_simulation.py -q \
  --basetemp="$TMPROOT/pytest"
PYTHONPATH=. .venv/Scripts/python.exe scripts/release/simulate_factory.py \
  --factory-home "$TMPROOT/Factory" \
  --tasks 100 \
  --concurrency 4 \
  --seed 20260724 \
  --fault-plan tests/factory/release/fixtures/fault-plan-v1.json \
  --report "$REPORT"
.venv/Scripts/python.exe -m py_compile scripts/release/simulate_factory.py tests/release/support/faults.py
```

Expected: all focused tests PASS; CLI prints
`PASS 100 tasks, 105 attempts, 5 interrupted, 3 idempotent replays, 1 sidecar restart`;
report status is `PASS`; compilation exits `0`.

- [ ] **Step 6: Inspect and commit**

```bash
git diff --check
git diff --stat
git diff -- scripts/release/simulate_factory.py tests/factory/release tests/release/support
git add tests/release/support/scenarios.py tests/release/support/faults.py tests/factory/release/fixtures/fault-plan-v1.json scripts/release/simulate_factory.py tests/factory/release/test_failure_injection.py tests/factory/release/test_100_task_simulation.py
git commit -m "test: simulate one hundred faulted tasks"
```

### Task 6: Codex and Hermes Unavailable Degradation

**Files:**
- Create: `apps/desktop/src-tauri/tests/unavailable_runtimes.rs`
- Create: `apps/desktop/src/runtime/RuntimeHealthPanel.test.tsx`
- Modify: `apps/desktop/src/runtime/types.ts`
- Modify: `apps/desktop/src/runtime/RuntimeHealthPanel.tsx`
- Create: `tests/factory/release/test_runtime_unavailable.py`

**Interfaces:**
- Consumes: Plan 03 `AgentAdapter::probe`, exact resolved-path launch contract,
  headless dispatch supervisor, adapter status snapshot, and Plan 02
  Settings/runtime-health UI.
- Produces: `RuntimeAvailabilityV1`, stable explicit-start
  `RUNTIME_UNAVAILABLE` behavior, and bounded no-runtime background idling.

```ts
export interface RuntimeAvailabilityV1 {
  protocol: 1;
  runtime: "CODEX" | "HERMES";
  status: "AVAILABLE" | "BLOCKED";
  resolvedPath: string | null;
  version: string | null;
  probedAt: string;
  failureReason: string | null;
  remediation: string | null;
}
```

- [ ] **Step 1: Write failing Rust and frontend degradation tests**

The Rust integration test starts the host with:

```text
configured Codex path = absent
configured Hermes path = absent
PATH = an empty temporary directory
Windows application aliases = empty fake resolver
```

It asserts both probes return `BLOCKED`, neither has a resolved path/version,
the host still reaches window-ready with factory health `HEALTHY`, and a queued
`READY` task creates no attempt while the headless dispatcher backs off rather
than spinning.

```tsx
// apps/desktop/src/runtime/RuntimeHealthPanel.test.tsx
it("keeps factory views usable when both optional runtimes are blocked", () => {
  render(
    <RuntimeHealthPanel
      runtimes={[
        {
          protocol: 1,
          runtime: "CODEX",
          status: "BLOCKED",
          resolvedPath: null,
          version: null,
          probedAt: "2026-07-24T12:00:00Z",
          failureReason: "Executable not found.",
          remediation: "Install Codex or choose its absolute executable path.",
        },
        {
          protocol: 1,
          runtime: "HERMES",
          status: "BLOCKED",
          resolvedPath: null,
          version: null,
          probedAt: "2026-07-24T12:00:00Z",
          failureReason: "Executable not found.",
          remediation: "Install Hermes or choose its absolute executable path.",
        },
      ]}
    />,
  );

  expect(screen.getByTestId("runtime-CODEX")).toHaveTextContent("Blocked");
  expect(screen.getByTestId("runtime-HERMES")).toHaveTextContent("Blocked");
});
```

- [ ] **Step 2: Run focused tests and verify red**

```powershell
Set-Location apps/desktop/src-tauri
cargo test --test unavailable_runtimes
Set-Location ..
pnpm test --run src/runtime/RuntimeHealthPanel.test.tsx
```

Expected: Rust test target or frontend test FAIL because the exact release
contract is not implemented.

- [ ] **Step 3: Implement stable blocked status without global degradation**

Map probe errors to `RuntimeAvailabilityV1` once, and make the launcher consume
the same stored probe object. A runtime-backed task receives:

```json
{
  "ok": false,
  "error": {
    "code": "RUNTIME_UNAVAILABLE",
    "message": "Codex is unavailable.",
    "details": {
      "runtime": "CODEX",
      "resolved_path": null,
      "remediation": "Install Codex or choose its absolute executable path."
    }
  }
}
```

For an explicit `TASK` start, the task remains `READY` and one deduplicated
attention item records the unavailable runtime; no attempt/grant is created.
For background `NEXT`, the supervisor sends an empty capability list, receives
`204`, and backs off to five seconds without mutating cards. Factory health
does not become `DEGRADED`; Research history, Evidence, Memory, Models,
Settings, cached state, and local exports remain usable. Never synthesize a
version or launch through a different path.

- [ ] **Step 4: Add and run the Python command-boundary test**

`tests/factory/release/test_runtime_unavailable.py` sends a runtime launch
result with code `RUNTIME_UNAVAILABLE` through the frozen command boundary and
asserts task `READY`, no attempt/grant or success receipt, one attention item,
and no change to factory health. The Rust test observes at least two bounded
idle intervals and asserts no busy loop, token issuance, or process launch.

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan06-runtime-unavailable-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/release/test_runtime_unavailable.py -q \
  --basetemp="$TMPROOT/pytest"
cd apps/desktop
pnpm test --run src/runtime/RuntimeHealthPanel.test.tsx
cd src-tauri
cargo test --test unavailable_runtimes
```

Expected: all focused tests PASS, with no contradictory available/launch state.

- [ ] **Step 5: Inspect and commit**

```bash
git diff --check
git diff --stat
git diff -- apps/desktop/src/runtime apps/desktop/src-tauri/tests/unavailable_runtimes.rs tests/factory/release/test_runtime_unavailable.py
git add apps/desktop/src-tauri/tests/unavailable_runtimes.rs apps/desktop/src/runtime/types.ts apps/desktop/src/runtime/RuntimeHealthPanel.tsx apps/desktop/src/runtime/RuntimeHealthPanel.test.tsx tests/factory/release/test_runtime_unavailable.py
git commit -m "test: degrade cleanly without agent runtimes"
```

### Task 7: Global-Stop and Paper-Ambiguity Safety Gates

**Files:**
- Create: `vesper/factory/release/safety_audit.py`
- Create: `tests/factory/release/test_global_stop_safety.py`
- Create: `tests/factory/release/test_paper_ambiguity_safety.py`

**Interfaces:**
- Consumes: Plan 01 factory-stop transaction/receipt, Plan 03 process-tree controls, Plan 04 P2 envelope/effect ledger, and frozen `AMBIGUOUS` outcome.
- Produces: `SafetyAuditV1` and `audit_safety(snapshot, receipts, paper_effects)`.

```python
@dataclass(frozen=True)
class SafetyAuditV1:
    protocol: int
    authoritative_stop_receipt_count: int
    active_lease_count: int
    active_runtime_grant_count: int
    enabled_paper_authority_count: int
    ambiguous_effect_count: int
    automatic_retry_after_ambiguity_count: int
    violations: Sequence[str]
```

- [ ] **Step 1: Write the failing global-stop scenario**

```python
# tests/factory/release/test_global_stop_safety.py
def test_global_stop_revokes_paper_and_terminates_survivor_at_fifteen_seconds(
    running_factory,
    fake_clock,
):
    cooperative = running_factory.start_worker(stop_behavior="cooperative")
    hanging = running_factory.start_worker(stop_behavior="hang")
    running_factory.activate_paper_envelope(account_id="paper-release-test")

    result = running_factory.stop_factory(idempotency_key="release-stop-1")
    assert result["ok"] is True
    assert running_factory.dispatch_enabled() is False
    assert running_factory.paper_submission_enabled() is False
    assert cooperative.graceful_stop_requested is True
    assert hanging.terminate_requested is False

    fake_clock.advance(seconds=15)
    running_factory.run_due_actions()

    assert hanging.terminate_requested is True
    audit = running_factory.safety_audit()
    assert audit.violations == ()
    assert audit.authoritative_stop_receipt_count == 1
    assert audit.active_lease_count == 0
    assert audit.active_runtime_grant_count == 0
    assert audit.enabled_paper_authority_count == 0
```

Add assertions that a repeated stop idempotency key returns the same result,
a different stop key while already stopped creates no second authoritative
stop receipt, and worker/evaluator/MCP identities cannot resume.

- [ ] **Step 2: Write the failing paper-ambiguity scenario**

```python
# tests/factory/release/test_paper_ambiguity_safety.py
def test_accepted_then_timed_out_paper_effect_is_ambiguous_and_never_retried(
    paper_factory,
):
    paper_factory.adapter.accept_then_timeout(client_order_id="vesper-paper-0001")

    result = paper_factory.submit_order(client_order_id="vesper-paper-0001")

    assert result["outcome"] == "AMBIGUOUS"
    assert paper_factory.adapter.calls == ["vesper-paper-0001"]
    assert paper_factory.paper_submission_enabled() is False
    assert paper_factory.candidate_stage() == "PAPER"
    assert paper_factory.attention_items() == [
        {
            "severity": "HIGH",
            "reason": "Paper effect status is ambiguous.",
            "allowed_actions": ["RECONCILE_WITH_PROVIDER", "STOP_CAMPAIGN"],
        }
    ]
    retry = paper_factory.submit_order(client_order_id="vesper-paper-0001")
    assert retry["error"]["code"] == "PAPER_EFFECT_AMBIGUOUS"
    assert paper_factory.adapter.calls == ["vesper-paper-0001"]
```

- [ ] **Step 3: Run both safety tests and verify red**

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan06-safety-red-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/release/test_global_stop_safety.py \
  tests/factory/release/test_paper_ambiguity_safety.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL because `safety_audit` and the release scenario fixtures are
absent. A failure in stop/paper product semantics reopens M1 or M4.

- [ ] **Step 4: Implement the pure ledger auditor and scenario adapters**

`audit_safety` reads snapshots/receipts/effect records without mutation. It
adds a violation for:

- stop receipt count other than one after a stop;
- any active lease/grant or enabled paper authority after stop settlement;
- a completed/verified receipt for an interrupted stop survivor;
- an automatic retry, successor, or candidate advancement after ambiguity;
- more than one provider call for the ambiguous client-order ID; or
- missing HIGH/CRITICAL attention for an ambiguous paper effect.

Keep product corrections in the owning Plan 01/03/04 modules; the release
auditor remains read-only.

- [ ] **Step 5: Run safety and predecessor suites**

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan06-safety-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/release/test_global_stop_safety.py \
  tests/factory/release/test_paper_ambiguity_safety.py \
  tests/factory -q \
  --basetemp="$TMPROOT/pytest"
.venv/Scripts/python.exe -m py_compile vesper/factory/release/safety_audit.py
```

Expected: all tests PASS; stop settles at the 15-second boundary; paper call
count remains one; compilation exits `0`.

- [ ] **Step 6: Inspect and commit**

```bash
git diff --check
git diff --stat
git diff -- vesper/factory/release/safety_audit.py tests/factory/release/test_global_stop_safety.py tests/factory/release/test_paper_ambiguity_safety.py
git add vesper/factory/release/safety_audit.py tests/factory/release/test_global_stop_safety.py tests/factory/release/test_paper_ambiguity_safety.py
git commit -m "test: enforce factory stop and paper ambiguity"
```

### Task 8: Resource and Storage Release Checks

**Files:**
- Create: `vesper/factory/release/storage_audit.py`
- Create: `scripts/release/check_resources.py`
- Create: `tests/factory/release/test_storage_audit.py`
- Create: `tests/factory/release/test_resource_audit.py`

**Interfaces:**
- Consumes: frozen campaign/global ceilings, authoritative evidence references, terminal retention, resource reservations, and storage cleanup candidates.
- Produces: `ResourceAuditV1`, `StorageAuditV1`, `audit_resources`, `audit_storage`, and `release/reports/resource-storage-v1.json`.
- The audit has no delete operation. Existing cleanup executes only paths returned as `reclaimable_paths`.

- [ ] **Step 1: Write failing projected-reserve and pinned-evidence tests**

```python
# tests/factory/release/test_storage_audit.py
from pathlib import Path

from vesper.factory.release.storage_audit import audit_storage


def test_projected_artifact_growth_blocks_before_disk_reserve(tmp_path):
    report = audit_storage(
        factory_home=tmp_path,
        free_bytes=11 * 1024**3,
        projected_growth_bytes=2 * 1024**3,
        warning_free_bytes=12 * 1024**3,
        minimum_free_disk_reserve_bytes=10 * 1024**3,
        referenced_paths=frozenset(),
    )

    assert report.warning is True
    assert report.artifact_dispatch_allowed is False
    assert report.projected_free_bytes == 9 * 1024**3
    assert report.reason == "Projected artifact growth would cross the disk reserve."


def test_receipt_referenced_evidence_is_never_reclaimable(tmp_path):
    evidence = tmp_path / "evidence" / "run.json"
    temporary = tmp_path / "worktrees" / "expired" / "scratch.tmp"
    evidence.parent.mkdir(parents=True)
    temporary.parent.mkdir(parents=True)
    evidence.write_text("authoritative", encoding="utf-8")
    temporary.write_text("unreferenced", encoding="utf-8")

    report = audit_storage(
        factory_home=tmp_path,
        free_bytes=20 * 1024**3,
        projected_growth_bytes=0,
        warning_free_bytes=12 * 1024**3,
        minimum_free_disk_reserve_bytes=10 * 1024**3,
        referenced_paths=frozenset({evidence.resolve()}),
    )

    assert report.pinned_paths == (evidence.resolve(),)
    assert report.reclaimable_paths == (temporary.resolve(),)
```

- [ ] **Step 2: Run focused tests and verify red**

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan06-storage-red-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/release/test_storage_audit.py \
  tests/factory/release/test_resource_audit.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection because `storage_audit` does not exist.

- [ ] **Step 3: Implement exact audit records and conservative classification**

```python
# vesper/factory/release/storage_audit.py
@dataclass(frozen=True)
class StorageAuditV1:
    protocol: int
    free_bytes: int
    projected_growth_bytes: int
    projected_free_bytes: int
    warning_free_bytes: int
    minimum_free_disk_reserve_bytes: int
    pinned_bytes: int
    reclaimable_bytes: int
    pinned_paths: Sequence[Path]
    reclaimable_paths: Sequence[Path]
    warning: bool
    artifact_dispatch_allowed: bool
    reason: str | None


@dataclass(frozen=True)
class ResourceAuditV1:
    protocol: int
    concurrent_workers: int
    total_attempts: int
    aggregate_wall_seconds: float
    cpu_percent: float
    gpu_workers: int
    memory_bytes: int
    artifact_growth_bytes: int
    retained_terminal_bytes: int
    violations: Sequence[str]
```

`audit_storage` resolves every path and rejects anything outside
`factory_home`. It classifies as reclaimable only:

- files under an explicitly expired disposable worktree;
- terminal bytes older than the configured retained tail; or
- files under the factory temporary directory with no receipt/evidence/hash
  reference.

Anything under `evidence/` or `manifests/`, any candidate artifact, any
database/backup/WAL file, and any referenced path is pinned. Unknown files are
pinned. `artifact_dispatch_allowed` is false exactly when
`free_bytes - projected_growth_bytes < minimum_free_disk_reserve_bytes`.

`audit_resources` compares measured values to the already frozen campaign and
global ceilings and reports field-specific violations; it neither changes a
budget nor grants paid/GPU authority.

- [ ] **Step 4: Implement and run the report CLI**

`scripts/release/check_resources.py` accepts:

```text
--factory-home <absolute path>
--snapshot <FactorySnapshotV1 JSON>
--receipts <receipt export JSON>
--report release/reports/resource-storage-v1.json
```

It obtains free space with `shutil.disk_usage`, computes pinned/reclaimable
bytes, invokes both audits, runs SQLite integrity/foreign-key checks, writes
the standard release envelope atomically, and exits `1` on any violation.

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan06-storage-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/release/test_storage_audit.py \
  tests/factory/release/test_resource_audit.py -q \
  --basetemp="$TMPROOT/pytest"
.venv/Scripts/python.exe -m py_compile \
  vesper/factory/release/storage_audit.py \
  scripts/release/check_resources.py
```

Expected: all focused tests PASS; compilation exits `0`; the fixture reports
pinned and reclaimable storage separately and blocks before crossing reserve.

- [ ] **Step 5: Inspect and commit**

```bash
git diff --check
git diff --stat
git diff -- vesper/factory/release/storage_audit.py scripts/release/check_resources.py tests/factory/release/test_storage_audit.py tests/factory/release/test_resource_audit.py
git add vesper/factory/release/storage_audit.py scripts/release/check_resources.py tests/factory/release/test_storage_audit.py tests/factory/release/test_resource_audit.py
git commit -m "feat: audit release resource and storage bounds"
```

### Task 9: PyInstaller `onedir` Factory Sidecar

**Files:**
- Create: `packaging/requirements-build.txt`
- Create: `packaging/pyinstaller/vesper_factory.spec`
- Create: `scripts/release/build_sidecar.ps1`
- Create: `scripts/release/verify_sidecar_bundle.py`
- Create: `tests/release/test_pyinstaller_contract.py`

**Interfaces:**
- Consumes: `scripts/factory.py`, API protocol `1`, database schema `3`,
  default capability templates in `vesper/factory/templates/`, and policy
  schemas in `vesper/factory/schemas/`.
- Produces: `build/release/sidecar/vesper-factory/vesper-factory.exe` plus its `_internal/` directory.
- The executable accepts the same two required environment variables and emits the same readiness line as the development sidecar.

- [ ] **Step 1: Write the failing packaging contract test**

```python
# tests/release/test_pyinstaller_contract.py
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_sidecar_spec_is_onedir_and_build_tool_is_pinned():
    spec = (ROOT / "packaging/pyinstaller/vesper_factory.spec").read_text("utf-8")
    requirements = (ROOT / "packaging/requirements-build.txt").read_text("utf-8")

    assert "exclude_binaries=True" in spec
    assert "COLLECT(" in spec
    assert "contents_directory=\"_internal\"" in spec
    assert "scripts\" / \"factory.py\"" in spec
    assert requirements.splitlines() == ["pyinstaller==6.21.0"]
```

- [ ] **Step 2: Run the contract test and verify red**

```bash
PYTHONPATH=. .venv/Scripts/python.exe -m pytest \
  tests/release/test_pyinstaller_contract.py -q
```

Expected: FAIL with `FileNotFoundError` for the spec or build requirements.

- [ ] **Step 3: Add the pinned requirement and complete `onedir` spec**

`packaging/requirements-build.txt`:

```text
pyinstaller==6.21.0
```

`packaging/pyinstaller/vesper_factory.spec`:

```python
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parents[1]
required_data = (
    (ROOT / "vesper" / "factory" / "templates", "vesper/factory/templates"),
    (ROOT / "vesper" / "factory" / "schemas", "vesper/factory/schemas"),
    (ROOT / "packaging" / "schema-releases.json", "packaging"),
)
missing = [str(source) for source, _target in required_data if not source.exists()]
if missing:
    raise SystemExit("missing required sidecar data: " + ", ".join(missing))

mcp_datas, mcp_binaries, mcp_hiddenimports = collect_all("mcp")
a = Analysis(
    [str(ROOT / "scripts" / "factory.py")],
    pathex=[str(ROOT)],
    binaries=mcp_binaries,
    datas=[(str(source), target) for source, target in required_data] + mcp_datas,
    hiddenimports=mcp_hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="vesper-factory",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    contents_directory="_internal",
)
collection = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="vesper-factory",
)
```

- [ ] **Step 4: Add the Windows builder and packaged-process verifier**

`scripts/release/build_sidecar.ps1` has parameters
`-Python .venv\Scripts\python.exe` and
`-OutputRoot build\release\sidecar`, fails outside Windows x64, installs only
`packaging/requirements-build.txt`, and runs:

```powershell
& $Python -m PyInstaller `
  --noconfirm `
  --clean `
  --distpath $OutputRoot `
  --workpath build\pyinstaller `
  packaging\pyinstaller\vesper_factory.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
& $Python scripts\release\verify_sidecar_bundle.py `
  --sidecar-dir "$OutputRoot\vesper-factory"
if ($LASTEXITCODE -ne 0) { throw "Bundled sidecar verification failed" }
```

`verify_sidecar_bundle.py` creates a temporary factory home, supplies a fresh
32-byte token, launches only `vesper-factory.exe`, validates one protocol/schema
`1` readiness line, calls authenticated `/v1/health`, verifies loopback binding,
and terminates the process tree. It fails if `_internal/` is missing, if a
token appears in output, or if launch needs `python.exe` from `PATH`.

- [ ] **Step 5: Build on Windows and verify green**

```powershell
.\scripts\release\build_sidecar.ps1
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe -m pytest tests\release\test_pyinstaller_contract.py -q
```

Expected: `1 passed`; verifier prints
`PASS bundled sidecar protocol=1 schema=3 loopback=true`; the output is a
directory, not a one-file executable.

- [ ] **Step 6: Inspect and commit**

```bash
git diff --check
git diff --stat
git diff -- packaging/requirements-build.txt packaging/pyinstaller scripts/release/build_sidecar.ps1 scripts/release/verify_sidecar_bundle.py tests/release/test_pyinstaller_contract.py
git add packaging/requirements-build.txt packaging/pyinstaller/vesper_factory.spec scripts/release/build_sidecar.ps1 scripts/release/verify_sidecar_bundle.py tests/release/test_pyinstaller_contract.py
git commit -m "build: package factory sidecar on Windows"
```

### Task 10: Third-Party Notices, SBOM, and License Provenance

**Files:**
- Create: `packaging/legal-policy.json`
- Create: `packaging/borrowed-source.json`
- Create: `scripts/release/install_syft.ps1`
- Create: `scripts/release/generate_legal.py`
- Create: `scripts/release/verify_legal.py`
- Create: `tests/release/test_legal_gate.py`
- Generate: `release/legal/THIRD_PARTY_NOTICES.txt`
- Generate: `release/legal/licenses/`
- Generate: `release/provenance/license-provenance.json`
- Generate: `release/sbom/vesper.cdx.json`

**Interfaces:**
- Consumes: Python environment metadata, `pnpm-lock.yaml`, `Cargo.lock`, the built sidecar directory, and any exact copied-source entries.
- Produces: CycloneDX JSON `specVersion: "1.7"`, sorted notices/license texts, and `LicenseProvenanceV1`.
- Every SBOM component must resolve to name, version, package URL, source URL/revision, SPDX expression, and a SHA-256-addressed license text.

- [ ] **Step 1: Write failing legal-policy tests**

```python
# tests/release/test_legal_gate.py
from pathlib import Path

from scripts.release.verify_legal import verify_legal


def test_unknown_or_agpl_component_blocks_release(tmp_path):
    result = verify_legal(
        components=[
            {
                "name": "unknown-package",
                "version": "1.0.0",
                "purl": "pkg:generic/unknown-package@1.0.0",
                "source_url": "https://example.invalid/unknown-package",
                "source_revision": "sha256:0123456789abcdef",
                "license_expression": "NOASSERTION",
                "license_text_sha256": None,
            },
            {
                "name": "copied-agent",
                "version": "1.0.0",
                "purl": "pkg:generic/copied-agent@1.0.0",
                "source_url": "https://example.invalid/copied-agent",
                "source_revision": "commit:0123456789abcdef",
                "license_expression": "AGPL-3.0-only",
                "license_text_sha256": "sha256:0123456789abcdef",
            },
        ],
        policy_path=Path("packaging/legal-policy.json"),
    )

    assert result.status == "FAIL"
    assert result.violations == (
        "unknown-package@1.0.0 has no resolved license.",
        "unknown-package@1.0.0 has no license text.",
        "copied-agent@1.0.0 uses prohibited AGPL-3.0-only.",
    )
```

- [ ] **Step 2: Run the legal test and verify red**

```bash
PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/release/test_legal_gate.py -q
```

Expected: FAIL because `verify_legal` or `legal-policy.json` is absent.

- [ ] **Step 3: Add exact policy and copied-source ledger**

`packaging/legal-policy.json`:

```json
{
  "protocol": 1,
  "cyclonedx_spec_version": "1.7",
  "syft_version": "1.44.0",
  "prohibited_license_expression_prefixes": ["AGPL-"],
  "unresolved_license_expressions": ["NOASSERTION", "LicenseRef-Unknown"],
  "required_component_fields": [
    "name",
    "version",
    "purl",
    "source_url",
    "source_revision",
    "license_expression",
    "license_text_sha256"
  ]
}
```

`packaging/borrowed-source.json`:

```json
{
  "protocol": 1,
  "entries": []
}
```

An empty ledger asserts no external source was copied. If implementation reused
source, that same commit must add its upstream URL, immutable commit, local
paths, SPDX license, retained notice path, and local tests; conceptual
references do not get entries.

- [ ] **Step 4: Implement deterministic legal generation and verification**

`install_syft.ps1` downloads exactly Syft `1.44.0` Windows amd64 zip and its
official checksum file from the matching immutable release, compares
`Get-FileHash -Algorithm SHA256`, and expands `syft.exe` only after equality.

`generate_legal.py`:

1. inventories Python distributions from `.venv`, Node production packages
   from `pnpm-lock.yaml`, Rust packages from `cargo metadata --locked`, and
   `packaging/borrowed-source.json`;
2. resolves source revision from lockfile checksum, package integrity, or Git
   commit without network guessing;
3. copies each discovered license file to
   `release/legal/licenses/<sha256>.txt`;
4. writes sorted `THIRD_PARTY_NOTICES.txt` and
   `license-provenance.json`;
5. runs
   `syft dir:build/release/stage -o cyclonedx-json=release/sbom/vesper.cdx.json`;
6. merges lockfile inventory components into the CycloneDX document and joins
   every component to provenance by package URL;
7. writes `release/reports/legal-provenance-v1.json` using the standard release
   envelope; and
8. exits `1` on unknown license, missing text/source/revision, prohibited AGPL,
   or an unlisted copied-source path.

Exact provenance component:

```json
{
  "name": "package-name",
  "version": "1.2.3",
  "purl": "pkg:ecosystem/package-name@1.2.3",
  "source_url": "https://upstream.example/package-name",
  "source_revision": "sha256:0123456789abcdef",
  "license_expression": "MIT",
  "license_text_sha256": "sha256:0123456789abcdef",
  "notice_path": "release/legal/licenses/0123456789abcdef.txt"
}
```

- [ ] **Step 5: Generate artifacts and verify green**

```powershell
.\scripts\release\install_syft.ps1 -Destination build\tools\syft
$env:PATH = "$(Resolve-Path build\tools\syft);$env:PATH"
.\.venv\Scripts\python.exe scripts\release\generate_legal.py `
  --stage build\release\stage `
  --output-root release
.\.venv\Scripts\python.exe scripts\release\verify_legal.py `
  --sbom release\sbom\vesper.cdx.json `
  --provenance release\provenance\license-provenance.json `
  --notices release\legal\THIRD_PARTY_NOTICES.txt
.\.venv\Scripts\python.exe -m pytest tests\release\test_legal_gate.py -q
```

Expected: verifier prints `PASS legal provenance covers every SBOM component`;
test passes; generated JSON is canonical and contains no unresolved/prohibited
license.

- [ ] **Step 6: Inspect and commit**

```bash
git diff --check
git diff --stat
git diff -- packaging/legal-policy.json packaging/borrowed-source.json scripts/release release/legal release/provenance release/sbom tests/release/test_legal_gate.py
git add packaging/legal-policy.json packaging/borrowed-source.json scripts/release/install_syft.ps1 scripts/release/generate_legal.py scripts/release/verify_legal.py tests/release/test_legal_gate.py release/legal release/provenance release/sbom
git commit -m "build: add notices sbom and license provenance"
```

### Task 11: Tauri Windows Package, Install Smoke, and CI

**Files:**
- Create: `apps/desktop/src-tauri/tauri.windows.conf.json`
- Create: `apps/desktop/src-tauri/src/sidecar/paths.rs`
- Create: `apps/desktop/src-tauri/src/release_health.rs`
- Modify: `apps/desktop/src-tauri/src/sidecar/mod.rs`
- Modify: `apps/desktop/src-tauri/src/sidecar/supervisor.rs`
- Modify: `apps/desktop/src-tauri/src/lib.rs`
- Create: `scripts/release/build_windows.ps1`
- Create: `scripts/release/smoke_windows.ps1`
- Create: `tests/release/test_windows_package_contract.py`
- Create: `.github/workflows/release-hardening-windows.yml`

**Interfaces:**
- Consumes: Tasks 9–10 artifacts, Plan 02 Tauri shell, and Task 4 supervisor/cache.
- Produces: an NSIS setup executable under
  `apps/desktop/src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/`
  and `release/reports/windows-package-smoke-v1.json`.
- `release_health.rs` atomically writes redacted
  `%LOCALAPPDATA%\Vesper\Factory\logs\host-health-v1.json`.

Exact host health shape:

```json
{
  "protocol": 1,
  "window_ready": true,
  "app_version": "0.1.0",
  "sidecar": {"health": "HEALTHY", "schema": 1, "pid": 1234},
  "factory": {
    "mode": "PAUSED",
    "health": "HEALTHY",
    "reconciliation": "COMPLETE"
  },
  "adapters": {
    "CODEX": {"status": "BLOCKED", "failure_reason": "Executable not found."},
    "HERMES": {"status": "BLOCKED", "failure_reason": "Executable not found."}
  }
}
```

- [ ] **Step 1: Write the failing package-config contract**

```python
# tests/release/test_windows_package_contract.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_windows_bundle_is_nsis_with_sidecar_and_legal_resources():
    config = json.loads(
        (ROOT / "apps/desktop/src-tauri/tauri.windows.conf.json").read_text("utf-8")
    )
    bundle = config["bundle"]
    assert bundle["targets"] == ["nsis"]
    assert bundle["resources"] == {
        "../../../build/release/sidecar/vesper-factory/": "sidecar/",
        "../../../release/legal/": "legal/",
        "../../../release/provenance/license-provenance.json": "provenance/license-provenance.json",
        "../../../release/sbom/vesper.cdx.json": "sbom/vesper.cdx.json",
    }
    assert bundle["windows"]["nsis"]["installMode"] == "currentUser"
```

- [ ] **Step 2: Run the contract and verify red**

```bash
PYTHONPATH=. .venv/Scripts/python.exe -m pytest \
  tests/release/test_windows_package_contract.py -q
```

Expected: FAIL because `tauri.windows.conf.json` is absent.

- [ ] **Step 3: Add exact Windows Tauri configuration and resource resolution**

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "bundle": {
    "active": true,
    "targets": ["nsis"],
    "resources": {
      "../../../build/release/sidecar/vesper-factory/": "sidecar/",
      "../../../release/legal/": "legal/",
      "../../../release/provenance/license-provenance.json": "provenance/license-provenance.json",
      "../../../release/sbom/vesper.cdx.json": "sbom/vesper.cdx.json"
    },
    "windows": {
      "webviewInstallMode": {
        "type": "downloadBootstrapper",
        "silent": true
      },
      "nsis": {
        "installMode": "currentUser",
        "languages": ["English"],
        "displayLanguageSelector": false
      }
    }
  }
}
```

`paths.rs` resolves `BaseDirectory::Resource/sidecar/vesper-factory.exe`,
requires sibling `_internal/`, canonicalizes both under the resource directory,
and returns:

```rust
pub struct BundledSidecar {
    pub executable: PathBuf,
    pub working_directory: PathBuf,
}

pub fn resolve_bundled_sidecar<R: Runtime>(
    app: &AppHandle<R>,
) -> Result<BundledSidecar, SidecarPathError>;
```

The supervisor launches exactly `BundledSidecar.executable` with
`working_directory`, never searches `PATH`, and keeps development-path
selection separate.

- [ ] **Step 4: Implement ordered build and disposable-profile smoke**

`build_windows.ps1` runs, in order:

```powershell
.\scripts\release\build_sidecar.ps1
pnpm --dir apps\desktop install --frozen-lockfile
pnpm --dir apps\desktop lint
pnpm --dir apps\desktop test --run
pnpm --dir apps\desktop build
cargo test --manifest-path apps\desktop\src-tauri\Cargo.toml
cargo build `
  --manifest-path apps\desktop\src-tauri\Cargo.toml `
  --release `
  --target x86_64-pc-windows-msvc
New-Item -ItemType Directory -Force build\release\stage | Out-Null
Copy-Item -Recurse -Force `
  build\release\sidecar\vesper-factory `
  build\release\stage\sidecar
Copy-Item -Force `
  apps\desktop\src-tauri\target\x86_64-pc-windows-msvc\release\vesper.exe `
  build\release\stage\vesper.exe
.\.venv\Scripts\python.exe scripts\release\generate_legal.py `
  --stage build\release\stage `
  --output-root release
pnpm --dir apps\desktop tauri build -- `
  --target x86_64-pc-windows-msvc `
  --bundles nsis
```

`smoke_windows.ps1` refuses a non-CI profile unless passed
`-DisposableProfileConfirmed`, then:

1. silently installs the one generated `*-setup.exe`;
2. creates a sentinel under `%LOCALAPPDATA%\Vesper\Factory\evidence\`;
3. launches with a restricted `PATH` containing no Codex/Hermes;
4. waits at most 60 seconds for `host-health-v1.json`;
5. asserts native window ready, sidecar schema `3`, both adapters `BLOCKED`,
   and no new `chrome.exe`, `firefox.exe`, or user-facing `msedge.exe`;
6. creates a disposable fake Codex `.cmd`, configures that exact path, admits
   and resumes one no-write fixture card, hides the window to the tray, and
   proves the headless `NEXT` supervisor launches it and injects one packet
   without terminal input;
7. kills the app process tree to inject abnormal termination;
8. relaunches and asserts `PAUSED` plus reconciliation `COMPLETE`;
9. kills the test process tree, silently uninstalls through the registered
   uninstall command, and proves installed binaries are gone; and
10. proves the factory evidence sentinel remains; and
11. runs `scripts/release/check_resources.py` against the smoke factory state
    to write `release/reports/resource-storage-v1.json`.

It writes the standard `windows-package-smoke` report and returns `1` for any
failed assertion.

- [ ] **Step 5: Add exact Windows CI jobs**

`.github/workflows/release-hardening-windows.yml` contains:

```yaml
name: release-hardening-windows

on:
  pull_request:
  workflow_dispatch:
    inputs:
      run_eight_hour_soak:
        description: Run the full eight-hour soak
        required: true
        default: false
        type: boolean
  schedule:
    - cron: "0 4 * * 0"

jobs:
  package-smoke:
    runs-on: windows-2025
    timeout-minutes: 120
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - uses: pnpm/action-setup@v4
        with:
          version: "10"
      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: x86_64-pc-windows-msvc
      - shell: pwsh
        run: |
          python -m venv .venv
          .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r packaging\requirements-build.txt
          pnpm --dir apps\desktop install --frozen-lockfile
          .\scripts\release\build_windows.ps1
          .\scripts\release\smoke_windows.ps1 -DisposableProfileConfirmed
      - uses: actions/upload-artifact@v4
        with:
          name: vesper-windows-release-evidence
          path: |
            apps/desktop/src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/*-setup.exe
            release/reports/*.json
            release/legal/
            release/provenance/
            release/sbom/

  eight-hour-soak:
    if: github.event_name == 'schedule' || inputs.run_eight_hour_soak
    runs-on: windows-2025
    timeout-minutes: 540
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - uses: pnpm/action-setup@v4
        with:
          version: "10"
      - uses: dtolnay/rust-toolchain@stable
      - shell: pwsh
        run: |
          python -m venv .venv
          .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r packaging\requirements-build.txt
          pnpm --dir apps\desktop install --frozen-lockfile
          .\scripts\release\build_sidecar.ps1
          .\scripts\release\run_soak.ps1
```

- [ ] **Step 6: Run manual Windows package/smoke green**

From a disposable Windows test profile:

```powershell
$ErrorActionPreference = "Stop"
Set-Location C:\src\vesper-v2
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r packaging\requirements-build.txt
corepack enable
pnpm --dir apps\desktop install --frozen-lockfile
.\scripts\release\build_windows.ps1
.\scripts\release\smoke_windows.ps1 -DisposableProfileConfirmed
```

Expected: NSIS build exits `0`; smoke report is `PASS`; app launches without
Python/Node/Rust/Codex/Hermes; forced restart is paused; uninstall removes
binaries and preserves factory evidence.

- [ ] **Step 7: Inspect and commit**

```bash
git diff --check
git diff --stat
git diff -- apps/desktop/src-tauri scripts/release/build_windows.ps1 scripts/release/smoke_windows.ps1 tests/release/test_windows_package_contract.py .github/workflows/release-hardening-windows.yml
git add apps/desktop/src-tauri/tauri.windows.conf.json apps/desktop/src-tauri/src/sidecar/paths.rs apps/desktop/src-tauri/src/sidecar/mod.rs apps/desktop/src-tauri/src/sidecar/supervisor.rs apps/desktop/src-tauri/src/release_health.rs apps/desktop/src-tauri/src/lib.rs scripts/release/build_windows.ps1 scripts/release/smoke_windows.ps1 tests/release/test_windows_package_contract.py .github/workflows/release-hardening-windows.yml
git commit -m "build: add Windows installer and smoke gate"
```

### Task 12: Eight-Hour Soak, Tkinter Parity Decision, and M6 Gate

**Files:**
- Create: `packaging/soak-policy.json`
- Create: `apps/desktop/src-tauri/tests/eight_hour_soak.rs`
- Create: `scripts/release/run_soak.ps1`
- Create: `tests/release/test_soak_report.py`
- Create: `packaging/tkinter-parity.json`
- Create: `scripts/release/render_tkinter_parity.py`
- Create: `docs/release/tkinter-replacement-parity.md`
- Create: `packaging/release-gates.json`
- Create: `scripts/release/verify_m6.py`
- Create: `tests/release/test_m6_gate.py`

**Interfaces:**
- Consumes: Tasks 1–11 reports/artifacts and all M1–M5 suites.
- Produces: `SoakReportV1`, a complete parity matrix with decision
  `RETAIN_TKINTER`, and `release/reports/m6-release-v1.json`.
- The soak uses the production supervisor, packaged sidecar, fake CLIs, public
  sidecar API, and disposable factory state.

- [ ] **Step 1: Write failing soak-report and M6 tests**

```python
# tests/release/test_soak_report.py
def test_soak_policy_is_exactly_eight_hours():
    policy = json.loads(Path("packaging/soak-policy.json").read_text("utf-8"))
    assert policy["duration_seconds"] == 28800
    assert policy["idle_phase_seconds"] == 1800
    assert policy["running_phase_seconds"] == 27000
    assert policy["sidecar_kill_seconds"] == [7200, 14400, 21600]


# tests/release/test_m6_gate.py
def test_tkinter_removal_is_never_authorized_by_plan_six():
    parity = json.loads(Path("packaging/tkinter-parity.json").read_text("utf-8"))
    assert parity["decision"] == "RETAIN_TKINTER"
    assert parity["removal_authorized"] is False
    assert parity["separate_removal_approval_required"] is True
```

- [ ] **Step 2: Run focused tests and verify red**

```bash
PYTHONPATH=. .venv/Scripts/python.exe -m pytest \
  tests/release/test_soak_report.py \
  tests/release/test_m6_gate.py -q
```

Expected: FAIL because soak/parity policy files are absent.

- [ ] **Step 3: Add exact eight-hour policy and ignored Rust soak**

`packaging/soak-policy.json`:

```json
{
  "protocol": 1,
  "duration_seconds": 28800,
  "idle_phase_seconds": 1800,
  "running_phase_seconds": 27000,
  "event_poll_interval_ms": 250,
  "task_interval_seconds": 60,
  "terminal_bytes_per_second": 1024,
  "sidecar_kill_seconds": [7200, 14400, 21600],
  "maximum_ending_rss_delta_bytes": 268435456,
  "maximum_handle_delta": 64,
  "maximum_idle_cpu_percent_of_one_core": 5.0,
  "maximum_wal_bytes_after_checkpoint": 16777216,
  "maximum_unreferenced_storage_growth_bytes": 67108864
}
```

`eight_hour_soak.rs` is marked `#[ignore = "eight-hour release gate"]` and:

- idles for 1,800 seconds while polling every 250 ms;
- runs one fake task per minute for 27,000 seconds with bounded terminal output;
- kills the sidecar at elapsed seconds 7,200, 14,400, and 21,600;
- verifies paused reconciliation and performs explicit harness-operator resume;
- checks event contiguity, receipts, leases/grants, SQLite integrity/foreign
  keys, restart count, RSS, handles, CPU, WAL, logs, and storage; and
- atomically writes `release/reports/eight-hour-soak-v1.json`.

Three kills spaced two hours apart must produce three successful supervised
restarts, no read-only recovery, three interrupted attempts at most, and no
blind duplicate.

- [ ] **Step 4: Add the complete Tkinter evidence matrix and retain decision**

`packaging/tkinter-parity.json` contains these exact capability IDs:

```json
{
  "protocol": 1,
  "decision": "RETAIN_TKINTER",
  "removal_authorized": false,
  "separate_removal_approval_required": true,
  "capabilities": [
    "launch",
    "engine_and_circuit_breaker_status",
    "account_and_risk_metrics",
    "positions",
    "signals_and_orders",
    "train_model_action_and_log",
    "backtest_action_and_log",
    "model_run_history_and_test_action",
    "backtest_evidence",
    "live_team_worker_state",
    "live_team_selected_output_and_redaction"
  ],
  "legacy_files": [
    "scripts/dashboard.py",
    "vesper/dashboard/app.py",
    "vesper/dashboard/backtest_evidence.py",
    "vesper/dashboard/model_runs.py",
    "vesper/dashboard/worker_monitor.py"
  ],
  "legacy_tests": [
    "tests/test_dashboard_backtest_evidence.py",
    "tests/test_dashboard_model_runs.py",
    "tests/test_dashboard_worker_monitor.py"
  ]
}
```

`render_tkinter_parity.py` runs the three legacy test files, records replacement
evidence by capability from committed frontend/Rust tests and smoke reports,
and writes `docs/release/tkinter-replacement-parity.md`. Missing replacement
evidence is recorded as `NOT VERIFIED`, never inferred. The document always
states:

```text
Decision: RETAIN_TKINTER
Removal authorized by Plan 06: no
Separate exact-scope approval required: yes
```

If every capability is verified, the document may state
`Eligible for separate removal review: yes`; it still does not authorize an
edit to the Tkinter paths.

- [ ] **Step 5: Add aggregate gate manifest and verifier**

`packaging/release-gates.json` requires:

```json
{
  "protocol": 1,
  "gates": [
    {
      "id": "migration-every-version",
      "mode": "run",
      "command": [".venv/Scripts/python.exe", "-m", "pytest", "tests/factory/release/test_migration_backups.py", "tests/factory/release/test_every_released_schema.py", "-q"],
      "report": "release/reports/migration-every-version-v1.json"
    },
    {
      "id": "forced-kill-recovery",
      "mode": "run",
      "command": [".venv/Scripts/python.exe", "-m", "pytest", "tests/factory/release/test_paused_restart.py", "-q"],
      "report": "release/reports/forced-kill-recovery-v1.json"
    },
    {
      "id": "failure-injection",
      "mode": "run",
      "command": [".venv/Scripts/python.exe", "-m", "pytest", "tests/factory/release/test_failure_injection.py", "tests/factory/release/test_global_stop_safety.py", "tests/factory/release/test_paper_ambiguity_safety.py", "-q"],
      "report": "release/reports/failure-injection-v1.json"
    },
    {
      "id": "100-task-simulation",
      "mode": "run",
      "command": [".venv/Scripts/python.exe", "scripts/release/simulate_factory.py", "--factory-home", "build/release/gates/simulation/Factory", "--tasks", "100", "--concurrency", "4", "--seed", "20260724", "--fault-plan", "tests/factory/release/fixtures/fault-plan-v1.json", "--report", "release/reports/100-task-simulation-v1.json"],
      "report": "release/reports/100-task-simulation-v1.json"
    },
    {
      "id": "legal-provenance",
      "mode": "run",
      "command": [".venv/Scripts/python.exe", "scripts/release/verify_legal.py", "--sbom", "release/sbom/vesper.cdx.json", "--provenance", "release/provenance/license-provenance.json", "--notices", "release/legal/THIRD_PARTY_NOTICES.txt", "--report", "release/reports/legal-provenance-v1.json"],
      "report": "release/reports/legal-provenance-v1.json"
    },
    {
      "id": "tkinter-parity",
      "mode": "run",
      "command": [".venv/Scripts/python.exe", "scripts/release/render_tkinter_parity.py", "--matrix", "packaging/tkinter-parity.json", "--output", "docs/release/tkinter-replacement-parity.md", "--report", "release/reports/tkinter-parity-v1.json"],
      "report": "release/reports/tkinter-parity-v1.json"
    },
    {
      "id": "resource-storage",
      "mode": "consume",
      "command": [],
      "report": "release/reports/resource-storage-v1.json"
    },
    {
      "id": "windows-package-smoke",
      "mode": "consume",
      "command": [],
      "report": "release/reports/windows-package-smoke-v1.json"
    },
    {
      "id": "eight-hour-soak",
      "mode": "consume",
      "command": [],
      "report": "release/reports/eight-hour-soak-v1.json"
    }
  ],
  "artifacts": [
    "release/legal/THIRD_PARTY_NOTICES.txt",
    "release/provenance/license-provenance.json",
    "release/sbom/vesper.cdx.json",
    "docs/release/tkinter-replacement-parity.md"
  ],
  "required_protocol": 1,
  "required_schema": 1
}
```

`verify_m6.py --run` executes each `mode: run` command without a shell, wraps a
pytest command's exit/output in its named standard report, and consumes reports
written directly by release scripts. It validates every report against the
current 40-character Git commit, requires `PASS`, rejects non-empty failures,
validates all artifact hashes, runs `PRAGMA integrity_check` and
`PRAGMA foreign_key_check` on the smoke database, requires the NSIS installer
and `onedir` sidecar, and requires the parity retain decision. It writes
`m6-release-v1.json` and never signs, publishes, deploys, or removes Tkinter.

- [ ] **Step 6: Run the eight-hour Windows soak**

`scripts/release/run_soak.ps1` executes:

```powershell
$env:VESPER_SIDECAR_DIR = (Resolve-Path build\release\sidecar\vesper-factory)
$env:VESPER_SOAK_POLICY = (Resolve-Path packaging\soak-policy.json)
cargo test `
  --manifest-path apps\desktop\src-tauri\Cargo.toml `
  --release `
  --test eight_hour_soak `
  -- `
  --ignored `
  --nocapture
if ($LASTEXITCODE -ne 0) { throw "Eight-hour soak failed" }
.\.venv\Scripts\python.exe -m pytest tests\release\test_soak_report.py -q
if ($LASTEXITCODE -ne 0) { throw "Soak report validation failed" }
```

Expected after 28,800 seconds: report `PASS`; three bounded restarts; no
read-only recovery, state corruption, event gap/duplicate, leaked lease/grant,
resource/storage violation, or unreconciled attempt.

- [ ] **Step 7: Render parity evidence and run the final M6 gate**

```powershell
.\.venv\Scripts\python.exe scripts\release\render_tkinter_parity.py `
  --matrix packaging\tkinter-parity.json `
  --output docs\release\tkinter-replacement-parity.md `
  --report release\reports\tkinter-parity-v1.json
.\.venv\Scripts\python.exe scripts\release\verify_m6.py `
  --run `
  --gates packaging\release-gates.json `
  --reports release\reports `
  --output release\reports\m6-release-v1.json
```

Expected: parity document says `RETAIN_TKINTER`; M6 prints
`PASS protocol=1 schema=3 release hardening gates complete`.

- [ ] **Step 8: Run complete manual Windows verification**

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = (Get-Location).Path
$tempRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-m6"
New-Item -ItemType Directory -Force $tempRoot | Out-Null
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTEST_ADDOPTS = ""
$env:TMPDIR = $tempRoot
$env:TEMP = $tempRoot
$env:TMP = $tempRoot
.\.venv\Scripts\python.exe -m pytest -q --basetemp "$tempRoot\pytest"
Set-Location apps\desktop
pnpm lint
pnpm test --run
pnpm build
Set-Location src-tauri
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test
Set-Location ..\..\..
.\scripts\release\build_windows.ps1
.\scripts\release\smoke_windows.ps1 -DisposableProfileConfirmed
.\scripts\release\run_soak.ps1
.\.venv\Scripts\python.exe scripts\release\verify_m6.py `
  --run `
  --gates packaging\release-gates.json `
  --reports release\reports `
  --output release\reports\m6-release-v1.json
```

Expected: every command exits `0`. Signing, publishing, deployment, live
trading, active-model replacement, and Tkinter removal remain unapproved.

- [ ] **Step 9: Inspect and commit**

```bash
git diff --check
git diff --stat
git diff -- packaging/soak-policy.json apps/desktop/src-tauri/tests/eight_hour_soak.rs scripts/release/run_soak.ps1 packaging/tkinter-parity.json scripts/release/render_tkinter_parity.py docs/release/tkinter-replacement-parity.md packaging/release-gates.json scripts/release/verify_m6.py tests/release/test_soak_report.py tests/release/test_m6_gate.py
git add packaging/soak-policy.json apps/desktop/src-tauri/tests/eight_hour_soak.rs scripts/release/run_soak.ps1 tests/release/test_soak_report.py packaging/tkinter-parity.json scripts/release/render_tkinter_parity.py docs/release/tkinter-replacement-parity.md packaging/release-gates.json scripts/release/verify_m6.py tests/release/test_m6_gate.py
git commit -m "test: complete release hardening gates"
```

## M6 Acceptance Checklist

- [ ] M1–M5 predecessor commits and passing gate evidence are recorded.
- [ ] Every released schema fixture `1..3` starts and upgrades to current
      schema `3`.
- [ ] Destructive migration backup/rollback tests pass.
- [ ] Forced termination reconciles once and restarts paused.
- [ ] Four sidecar failures inside five minutes enter cached read-only recovery.
- [ ] Failure matrix and deterministic 100-task simulation pass.
- [ ] Codex/Hermes-unavailable launch remains usable and truthful.
- [ ] A packaged fixture card dispatches from the tray with React unmounted,
      while zero available runtimes idle with bounded backoff and no attempt.
- [ ] Global stop and ambiguous paper-effect safety tests pass.
- [ ] Pinned/reclaimable storage and hard resource ceilings pass.
- [ ] PyInstaller `onedir`, legal provenance, notices, and CycloneDX SBOM pass.
- [ ] NSIS install/launch/forced-restart/uninstall smoke passes without a browser.
- [ ] Eight-hour idle/running soak passes its resource and storage policy.
- [ ] Tkinter parity evidence is complete and decision remains `RETAIN_TKINTER`.
- [ ] Full Python, frontend, Rust, package, smoke, and aggregate M6 commands pass.

Plan 06 is complete only when `release/reports/m6-release-v1.json` is `PASS` for
the current commit. Any subsequent code/dependency/package change invalidates
that report and requires rerunning the affected gate plus aggregate M6.
