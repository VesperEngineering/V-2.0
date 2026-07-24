# Vesper Factory Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python-owned Vesper factory kernel so an admitted campaign can create bounded cards, select eligible author/reviewer work for autonomous dispatch, issue task-scoped worker grants, durably coordinate attempts and evidence, recover safely, and expose the frozen schema `1`, loopback API, CLI, and seven MCP tools.

**Architecture:** New modules under `vesper.factory` own all workflow truth and use short SQLite transactions against `%LOCALAPPDATA%\Vesper\Factory\factory.db` in WAL mode. Starlette mounts authenticated `/v1` routes and one stateless FastMCP streamable-HTTP application; `scripts/factory.py` is the development/diagnostic entry point, while Rust remains responsible for native process and PTY concerns. Every mutation flows through one service transaction that appends ordered events and immutable receipts without storing raw session or worker tokens.

**Tech Stack:** Python 3.11, stdlib `sqlite3`, `mcp[cli]==1.28.1`, Starlette and uvicorn supplied by that pinned SDK, pytest, SHA-256, canonical JSON, RFC 3339 UTC.

## Global Constraints

- Before any code edit, follow `AGENTS.md`: load matching skills, query the repository `.codegraph` index for every symbol/file to be changed, and read `SKILLS/CODE.md` plus `SKILLS/EXAMPLES.md`.
- The current local clone does not contain `.codegraph`. Implementation must run from the canonical Windows checkout where the index exists, or stop and refresh/create the required index before editing code.
- Do not edit `config/`, `vesper/risk.py`, `vesper/execution.py`, scheduler code, `vesper/data/massive/`, `vesper/data/model_research/`, active model artifacts, or any file outside the write set named in this plan.
- Massive data is read-only. Alpaca effects, live trading, paid compute, active-model replacement, remote push, deployment, and protected-path changes remain denied.
- Keep the current Python engine and Tkinter dashboard operational; `vesper.factory` is additive and must not import or mutate trading, risk, execution, scheduler, dashboard, data, or model modules.
- Use Python 3.11-compatible syntax, test-first changes, surgical diffs, deterministic assertions, temporary factory homes/databases, and one focused commit per task.
- Add exactly `mcp[cli]==1.28.1` to `requirements.txt`; do not add a second web framework, ORM, migration framework, queue, or configuration package.
- Use generated UUID4 identifiers with stable prefixes `cmp_`, `cnd_`, `tsk_`, `atm_`, `rcp_`, `evt_`, `wrk_`, `ses_`, `evd_`, `lsn_`, `att_`, and `rsv_`. The frozen command response additionally requires `cmd_`; lease IDs are canonical hyphenated UUID4 strings.
- Store UTC timestamps as RFC 3339 strings ending in `Z`. Store flexible payloads as canonical UTF-8 JSON with sorted keys, compact separators, `ensure_ascii=False`, and `allow_nan=False`; hash canonical bytes with SHA-256 and render hashes as `sha256:<64 lowercase hex>`.
- Never store or emit raw sidecar session tokens, raw worker tokens, broker/provider credentials, CLI credentials, authorization headers, or unrestricted terminal output in SQLite, receipts, events, logs, snapshots, or error details.
- Every state transition, receipt append, resource activation/release, grant mutation, and corresponding event append is one `BEGIN IMMEDIATE` transaction. Service helpers accept an open connection and never commit independently.
- Schema `1` is a creation-only migration from an empty database. Plan 06 owns destructive-migration backup and release recovery; this plan must reject a database whose `PRAGMA user_version` exceeds `1`.
- Candidate evaluation, candidate progression, research scoring, runtime binary probing or process launch, physical worktree creation, PTY/log capture, paper effects, learning/routing, desktop UI, packaging, and deployment are out of scope. Python does own deterministic dispatch eligibility and atomic grant claims; Rust performs the resulting process launch in Plan 03. Schema/API fields needed by downstream plans must return truthful empty or inactive values rather than simulated product behavior.

---

## Dependencies and Acceptance Gates

- **Earlier implementation-plan dependency:** none. Plan 01 is the root of the delivery graph.
- **Authoritative inputs:** `docs/superpowers/specs/2026-07-24-vesper-quant-factory-design.md`, `docs/superpowers/plans/2026-07-24-vesper-quant-factory-roadmap.md`, and the existing lifecycle contract in `reports/platform_gap_lifecycle_contract_v1.md`.
- **Plan 02 / Plan 03 entry gate:** schema `1`, the exact `/v1` and `/mcp` contracts, the `TASK`/`NEXT` dispatch-grant contract, and `tests/factory/sidecar_fixture.py` must be committed and green. Plans 02 and 03 must consume these interfaces without renaming fields or reinterpreting states.
- **Plan 04 entry dependency supplied here:** durable attempt, evidence, receipt, run-manifest, worker/session, and runtime-grant paths. This plan does not produce evaluator or candidate behavior.
- **M1 Kernel acceptance gate:** a CLI can initialize factory ceilings, admit a campaign, transition a card, acquire and reconcile a lease, append evidence/receipts, use every structured worker tool, stop/resume the factory, and replay ordered events from temporary SQLite state.
- **Repository gate:** the existing Python suite remains green, every changed Python file compiles, `git diff --check` is clean, and no protected path is modified.

## Frozen Kernel Contracts

These names and values are schema/API version `1`. Downstream plans may extend them additively but may not rename fields, reinterpret states, or bypass guards.

```python
from typing import Literal

CampaignStatus = Literal["DRAFT", "ADMITTED", "PAUSED", "STOPPED", "CLOSED"]
CandidateStage = Literal[
    "ADMISSION", "RESEARCH", "EVALUATION", "SHADOW",
    "PAPER", "LIVE_APPROVAL_REQUIRED", "ARCHIVED",
]
TaskState = Literal[
    "BACKLOG", "READY", "RUNNING", "EVALUATING", "COMPLETED",
    "BLOCKED", "INTERRUPTED", "CANCELED",
]
AttemptOutcome = Literal[
    "VERIFIED", "REJECTED", "FAILED", "BLOCKED",
    "INCONCLUSIVE", "INTERRUPTED", "AMBIGUOUS",
]
AttentionSeverity = Literal["INFO", "WARNING", "HIGH", "CRITICAL"]
FactoryMode = Literal["RUNNING", "PAUSED", "STOPPED"]
FactoryHealth = Literal[
    "HEALTHY", "DEGRADED", "RECOVERING", "READ_ONLY_RECOVERY",
]
WorkflowStage = Literal[
    "ADMISSION", "CONTRACT", "IMPLEMENT", "TRAIN", "BACKTEST", "REVIEW", "NEXT",
]
AttemptKind = Literal["AUTHOR", "EVALUATOR", "RECONCILER"]
RuntimeName = Literal["codex", "hermes", "fake"]
CapabilityTemplate = Literal[
    "Quant Research", "Data Engineering", "ML Systems",
    "Portfolio Evaluation", "Risk Review", "Development",
    "Independent Evaluator",
]
```

The task transition graph is:

```text
BACKLOG -> READY | CANCELED
READY -> RUNNING (runtime-grant service only) | BLOCKED | CANCELED
RUNNING -> EVALUATING (evidence-seal service only) | BLOCKED | INTERRUPTED | CANCELED
EVALUATING -> COMPLETED (authoritative-verdict service only) | BLOCKED | INTERRUPTED | CANCELED
BLOCKED -> READY (explicit resolution with guards) | CANCELED
INTERRUPTED -> BLOCKED (reconciliation) | CANCELED
COMPLETED and CANCELED are terminal
```

`RUNNING` requires one active lease and immutable attempt. `COMPLETED` requires an `evaluation.verdict` receipt with `outcome="VERIFIED"`, `authority="independent-evaluator-v1"`, matching contract/input hashes, and registered evidence. No generic transition endpoint may synthesize either state.

## Planned File Map

| Path | Responsibility |
|---|---|
| `vesper/factory/__init__.py` | Export only stable kernel entry points and schema/protocol constants |
| `vesper/factory/errors.py` | Stable policy/validation error codes and HTTP status mapping |
| `vesper/factory/foundation.py` | Canonical JSON, hashes, UUID4 IDs, UTC, secret-key rejection |
| `vesper/factory/paths.py` | `%LOCALAPPDATA%`/override resolution and app-data directory layout |
| `vesper/factory/contracts.py` | Version-1 `TypedDict`/literal contracts and deterministic validation |
| `vesper/factory/database.py` | SQLite connection policy and transaction helper |
| `vesper/factory/migrations.py` | Complete schema-1 SQL and migration runner |
| `vesper/factory/journal.py` | Append-only events and receipts |
| `vesper/factory/evidence.py` | Immutable content-addressed evidence and run-manifest validation |
| `vesper/factory/campaigns.py` | Global-limit initialization, frozen campaign admission, task-graph admission |
| `vesper/factory/tasks.py` | Tasks, dependencies, guarded state changes, follow-up cards |
| `vesper/factory/attention.py` | Deduplicated actionable attention items |
| `vesper/factory/resources.py` | Reservations, collisions, budget checks, measured usage |
| `vesper/factory/attempts.py` | Attempts, workers, sessions, leases, heartbeat, sealing, reconciliation |
| `vesper/factory/control.py` | Factory stop/resume and startup-paused behavior |
| `vesper/factory/commands.py` | Idempotent command envelope/dispatch |
| `vesper/factory/snapshot.py` | `FactorySnapshotV1` and ordered event pages |
| `vesper/factory/kernel.py` | Transaction-owning façade used by CLI, HTTP, and MCP |
| `vesper/factory/dispatch.py` | Deterministic `TASK`/`NEXT` eligibility, ordering, and runtime selection |
| `vesper/factory/grants.py` | One-time worker grants, digest validation, request authority context |
| `vesper/factory/mcp_server.py` | Exactly seven task-scoped FastMCP tools |
| `vesper/factory/api.py` | Starlette `/v1` routes, auth middleware, error envelopes, MCP mount |
| `vesper/factory/server.py` | Loopback socket binding, readiness line, uvicorn lifecycle |
| `vesper/factory/cli.py` | Deterministic JSON CLI commands |
| `scripts/factory.py` | Repository-root launcher matching existing script style |
| `tests/factory/` | Temporary-database unit, contract, integration, API, MCP, CLI, and M1 tests |
| `requirements.txt` | Pin `mcp[cli]==1.28.1` |

### Task 1: Canonical Foundation, App-Data Paths, and Dependency Pin

**Files:**
- Create: `vesper/factory/__init__.py`
- Create: `vesper/factory/errors.py`
- Create: `vesper/factory/foundation.py`
- Create: `vesper/factory/paths.py`
- Create: `tests/factory/test_foundation.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `PROTOCOL_VERSION = 1`, `SCHEMA_VERSION = 1`.
- Produces: `FactoryError(code: str, message: str, http_status: int = 400, details: Mapping[str, object] | None = None)`.
- Produces: `new_id(kind: IdKind) -> str`, `new_lease_id() -> str`.
- Produces: `format_utc(value: datetime) -> str`, `parse_utc(value: str) -> datetime`, `utc_now() -> datetime`.
- Produces: `canonical_json_bytes(value: object) -> bytes`, `canonical_json(value: object) -> str`, `canonical_hash(value: object) -> str`, `sha256_file(path: Path) -> str`, `assert_secret_free(value: object) -> None`.
- Produces: `FactoryPaths.from_home(home: Path) -> FactoryPaths`, `FactoryPaths.resolve(env: Mapping[str, str]) -> FactoryPaths`, and `FactoryPaths.create() -> None`.
- Consumed by: every subsequent task.

- [ ] **Step 1: Add failing foundation tests and the exact dependency assertion**

```python
# tests/factory/test_foundation.py
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import pytest

from vesper.factory.errors import FactoryError
from vesper.factory.foundation import (
    canonical_hash,
    canonical_json_bytes,
    format_utc,
    new_id,
    new_lease_id,
    parse_utc,
)
from vesper.factory.paths import FactoryPaths


def test_factory_dependency_and_canonical_values(tmp_path: Path) -> None:
    assert metadata.version("mcp") == "1.28.1"
    assert canonical_json_bytes({"é": 1, "a": [True, None]}) == (
        b'{"a":[true,null],"\xc3\xa9":1}'
    )
    assert canonical_hash({"b": 2, "a": 1}) == (
        "sha256:43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"
    )
    assert format_utc(datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)) == (
        "2026-07-24T12:00:00Z"
    )
    assert parse_utc("2026-07-24T12:00:00Z") == datetime(
        2026, 7, 24, 12, 0, tzinfo=timezone.utc
    )
    assert new_id("task").startswith("tsk_")
    assert len(new_lease_id()) == 36

    paths = FactoryPaths.from_home((tmp_path / "factory").resolve())
    paths.create()
    assert paths.database == paths.home / "factory.db"
    assert paths.evidence.is_dir()
    assert paths.logs.is_dir()
    assert paths.manifests.is_dir()
    assert paths.worktrees.is_dir()


def test_paths_and_canonicalization_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(FactoryError, match="absolute"):
        FactoryPaths.from_home(Path("relative"))
    with pytest.raises(FactoryError, match="RFC 3339"):
        parse_utc("2026-07-24T12:00:00+00:00")
    with pytest.raises(FactoryError, match="secret"):
        canonical_json_bytes({"worker_token": "forbidden"})
    with pytest.raises(FactoryError, match="finite"):
        canonical_json_bytes({"score": float("nan")})
```

- [ ] **Step 2: Run the focused test and verify red**

Run from Git Bash:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_foundation.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'vesper.factory'` (and, before installing requirements, the environment may also report that `mcp` is absent).

- [ ] **Step 3: Add the pin and implement the foundation exactly**

Append this exact direct dependency to `requirements.txt` and preserve every existing line:

```text
mcp[cli]==1.28.1
```

Implement the core values as follows:

```python
# vesper/factory/errors.py
from collections.abc import Mapping


class FactoryError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 400,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = dict(details or {})

    def body(self) -> dict[str, object]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }
```

```python
# vesper/factory/foundation.py
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from vesper.factory.errors import FactoryError

IdKind = Literal[
    "campaign", "candidate", "task", "attempt", "receipt", "event",
    "worker", "session", "evidence", "lesson", "attention",
    "reservation", "command",
]
ID_PREFIXES: dict[IdKind, str] = {
    "campaign": "cmp_",
    "candidate": "cnd_",
    "task": "tsk_",
    "attempt": "atm_",
    "receipt": "rcp_",
    "event": "evt_",
    "worker": "wrk_",
    "session": "ses_",
    "evidence": "evd_",
    "lesson": "lsn_",
    "attention": "att_",
    "reservation": "rsv_",
    "command": "cmd_",
}
SECRET_KEYS = {
    "authorization", "api_key", "apikey", "password", "secret",
    "session_token", "token", "worker_token",
}


def new_id(kind: IdKind) -> str:
    return f"{ID_PREFIXES[kind]}{uuid.uuid4().hex}"


def new_lease_id() -> str:
    return str(uuid.uuid4())


def assert_secret_free(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in SECRET_KEYS or normalized.endswith("_token"):
                raise FactoryError(
                    "SECRET_FIELD_DENIED",
                    f"Potential secret field is not durable: {path}.{key}",
                )
            assert_secret_free(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_secret_free(child, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise FactoryError("NONFINITE_JSON", "Canonical JSON numbers must be finite.")


def canonical_json_bytes(value: object) -> bytes:
    assert_secret_free(value)
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise FactoryError("INVALID_JSON", "Value is not canonical JSON.") from exc
    return rendered.encode("utf-8")


def canonical_json(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def canonical_hash(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FactoryError("INVALID_TIME", "UTC time must be timezone-aware.")
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise FactoryError("INVALID_TIME", "Time must be RFC 3339 UTC ending in Z.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FactoryError("INVALID_TIME", "Time must be RFC 3339 UTC ending in Z.") from exc
    if format_utc(parsed) != value:
        raise FactoryError("INVALID_TIME", "Time must use whole-second RFC 3339 UTC.")
    return parsed


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
```

```python
# vesper/factory/paths.py
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from vesper.factory.errors import FactoryError


@dataclass(frozen=True)
class FactoryPaths:
    home: Path
    database: Path
    evidence: Path
    logs: Path
    manifests: Path
    worktrees: Path

    @classmethod
    def from_home(cls, home: Path) -> "FactoryPaths":
        if not home.is_absolute():
            raise FactoryError("INVALID_FACTORY_HOME", "Factory home must be absolute.")
        normalized = home.resolve(strict=False)
        return cls(
            home=normalized,
            database=normalized / "factory.db",
            evidence=normalized / "evidence",
            logs=normalized / "logs",
            manifests=normalized / "manifests",
            worktrees=normalized / "worktrees",
        )

    @classmethod
    def resolve(cls, env: Mapping[str, str]) -> "FactoryPaths":
        override = env.get("VESPER_FACTORY_HOME")
        if override:
            return cls.from_home(Path(override))
        local_app_data = env.get("LOCALAPPDATA")
        if not local_app_data:
            raise FactoryError(
                "FACTORY_HOME_REQUIRED",
                "Set VESPER_FACTORY_HOME or run on Windows with LOCALAPPDATA.",
            )
        return cls.from_home(Path(local_app_data) / "Vesper" / "Factory")

    def create(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        for directory in (self.evidence, self.logs, self.manifests, self.worktrees):
            directory.mkdir(parents=True, exist_ok=True)
```

`vesper/factory/__init__.py` must export only `PROTOCOL_VERSION`, `SCHEMA_VERSION`, `FactoryKernel`, and `FactoryPaths`; import `FactoryKernel` only after Task 9 creates it, so Tasks 1-8 export the two constants and `FactoryPaths`.

- [ ] **Step 4: Install requirements and verify green**

Run:

```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_foundation.py -q
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile vesper/factory/__init__.py vesper/factory/errors.py vesper/factory/foundation.py vesper/factory/paths.py
```

Expected: dependency installation succeeds, pytest reports `2 passed`, and compilation exits `0`.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt vesper/factory/__init__.py vesper/factory/errors.py vesper/factory/foundation.py vesper/factory/paths.py tests/factory/test_foundation.py
git commit -m "feat(factory): add canonical kernel foundation"
```

### Task 2: SQLite WAL Database and Schema-1 Migration

**Files:**
- Create: `vesper/factory/database.py`
- Create: `vesper/factory/migrations.py`
- Create: `tests/factory/conftest.py`
- Create: `tests/factory/test_database.py`

**Interfaces:**
- Consumes: `FactoryPaths`, `format_utc()`, `canonical_hash()`, `FactoryError`.
- Produces: `Database(path: Path)`, `Database.connect() -> ContextManager[sqlite3.Connection]`, and `Database.transaction() -> ContextManager[sqlite3.Connection]`.
- Produces: immutable
  `Migration(version: int, name: str, sql: str)`, `SCHEMA_V1`,
  `MIGRATIONS = (Migration(1, "factory-kernel-v1", SCHEMA_V1),)`,
  `CURRENT_SCHEMA`, and
  `migrate(database, now, target_version: int | None = None) -> None`.
- Invariant: every connection sets `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`, and `row_factory=sqlite3.Row`.
- Invariant: schema `1` contains only kernel-owned records; `FactorySnapshotV1.candidates` remains an empty list until the research plan adds candidate storage.

- [ ] **Step 1: Write the failing migration tests**

```python
# tests/factory/test_database.py
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.factory.database import Database
from vesper.factory.migrations import migrate


EXPECTED_TABLES = {
    "schema_migrations", "factory_config", "factory_state", "campaigns",
    "tasks", "task_dependencies", "workers", "sessions", "attempts",
    "leases", "runtime_grants", "evidence", "attempt_evidence", "receipts",
    "events", "attention_items", "resource_reservations", "budget_usage",
    "command_results",
}


def test_schema_one_uses_wal_foreign_keys_and_paused_start(tmp_path: Path) -> None:
    database = Database(tmp_path / "factory.db")
    migrate(
        database,
        datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
        target_version=1,
    )

    with database.connect() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert EXPECTED_TABLES <= tables
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        state = connection.execute(
            "SELECT mode, dispatch_enabled, paper_enabled FROM factory_state"
        ).fetchone()
        assert dict(state) == {
            "mode": "PAUSED",
            "dispatch_enabled": 0,
            "paper_enabled": 0,
        }


def test_append_only_schema_triggers_reject_mutation(tmp_path: Path) -> None:
    database = Database(tmp_path / "factory.db")
    migrate(
        database,
        datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
        target_version=1,
    )
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO events(
                event_id, kind, aggregate_type, aggregate_id, occurred_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("evt_" + "1" * 32, "test.created", "test", "one",
             "2026-07-24T12:00:00Z", "{}"),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with database.transaction() as connection:
            connection.execute("DELETE FROM events")


def test_newer_database_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "factory.db"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version = 2")
    connection.close()
    with pytest.raises(Exception, match="newer"):
        migrate(
            Database(path),
            datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
            target_version=1,
        )
```

- [ ] **Step 2: Run the migration test and verify red**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_database.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'vesper.factory.database'`.

- [ ] **Step 3: Implement the connection/transaction policy**

```python
# vesper/factory/database.py
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=5.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = self._open()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()
```

- [ ] **Step 4: Implement the complete schema-1 contract**

`SCHEMA_V1` must execute the following exact DDL. Checks are database backstops; service validation still returns stable `FactoryError` codes before a constraint failure.

```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE factory_config (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    protocol INTEGER NOT NULL CHECK (protocol = 1),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    global_budget_json TEXT,
    global_budget_hash TEXT,
    configured_at TEXT,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE factory_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    mode TEXT NOT NULL CHECK (mode IN ('RUNNING', 'PAUSED', 'STOPPED')),
    health TEXT NOT NULL CHECK (
        health IN ('HEALTHY', 'DEGRADED', 'RECOVERING', 'READ_ONLY_RECOVERY')
    ),
    dispatch_enabled INTEGER NOT NULL CHECK (dispatch_enabled IN (0, 1)),
    paper_enabled INTEGER NOT NULL CHECK (paper_enabled = 0),
    startup_reconciled_at TEXT,
    last_stop_receipt_id TEXT,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE campaigns (
    campaign_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (
        status IN ('DRAFT', 'ADMITTED', 'PAUSED', 'STOPPED', 'CLOSED')
    ),
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    contract_json TEXT NOT NULL,
    contract_hash TEXT NOT NULL,
    budget_json TEXT NOT NULL,
    budget_hash TEXT NOT NULL,
    approval_reference TEXT NOT NULL,
    admitted_at TEXT NOT NULL,
    closed_at TEXT,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    parent_task_id TEXT REFERENCES tasks(task_id),
    state TEXT NOT NULL CHECK (
        state IN (
            'BACKLOG', 'READY', 'RUNNING', 'EVALUATING', 'COMPLETED',
            'BLOCKED', 'INTERRUPTED', 'CANCELED'
        )
    ),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    workflow_stage TEXT NOT NULL CHECK (
        workflow_stage IN (
            'ADMISSION', 'CONTRACT', 'IMPLEMENT', 'TRAIN',
            'BACKTEST', 'REVIEW', 'NEXT'
        )
    ),
    work_kind TEXT NOT NULL,
    capability_template TEXT NOT NULL,
    contract_json TEXT NOT NULL,
    contract_hash TEXT NOT NULL,
    max_attempts INTEGER NOT NULL CHECK (max_attempts > 0),
    requires_run_manifest INTEGER NOT NULL CHECK (requires_run_manifest IN (0, 1)),
    current_attempt_id TEXT REFERENCES attempts(attempt_id)
        DEFERRABLE INITIALLY DEFERRED,
    state_details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE workers (
    worker_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    capability_template TEXT NOT NULL,
    template_version INTEGER NOT NULL CHECK (template_version > 0),
    runtime TEXT NOT NULL CHECK (runtime IN ('codex', 'hermes', 'fake')),
    model TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('ACTIVE', 'ENDED')),
    created_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL UNIQUE REFERENCES workers(worker_id),
    attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(attempt_id)
        DEFERRABLE INITIALLY DEFERRED,
    runtime TEXT NOT NULL CHECK (runtime IN ('codex', 'hermes', 'fake')),
    state TEXT NOT NULL CHECK (
        state IN (
            'GRANTED', 'RUNNING', 'STOP_REQUESTED', 'EXITED',
            'INTERRUPTED', 'REVOKED'
        )
    ),
    bounded_log_path TEXT,
    exit_json TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE attempts (
    attempt_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    worker_id TEXT NOT NULL UNIQUE REFERENCES workers(worker_id),
    session_id TEXT NOT NULL UNIQUE REFERENCES sessions(session_id)
        DEFERRABLE INITIALLY DEFERRED,
    attempt_kind TEXT NOT NULL CHECK (
        attempt_kind IN ('AUTHOR', 'EVALUATOR', 'RECONCILER')
    ),
    retry_of_attempt_id TEXT REFERENCES attempts(attempt_id),
    review_of_attempt_id TEXT REFERENCES attempts(attempt_id),
    status TEXT NOT NULL CHECK (
        status IN ('ACTIVE', 'EVIDENCE_SEALED', 'RECONCILING', 'FINISHED')
    ),
    outcome TEXT CHECK (
        outcome IS NULL OR outcome IN (
            'VERIFIED', 'REJECTED', 'FAILED', 'BLOCKED',
            'INCONCLUSIVE', 'INTERRUPTED', 'AMBIGUOUS'
        )
    ),
    runtime TEXT NOT NULL CHECK (runtime IN ('codex', 'hermes', 'fake')),
    model TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    contract_hash TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    started_at TEXT NOT NULL,
    wall_deadline_at TEXT NOT NULL,
    ended_at TEXT,
    sealed_at TEXT,
    reconciliation_receipt_id TEXT REFERENCES receipts(receipt_id)
        DEFERRABLE INITIALLY DEFERRED,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE leases (
    lease_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(attempt_id),
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    worker_id TEXT NOT NULL UNIQUE REFERENCES workers(worker_id),
    status TEXT NOT NULL CHECK (
        status IN ('ACTIVE', 'RELEASED', 'REVOKED', 'EXPIRED')
    ),
    issued_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    released_at TEXT,
    revoked_at TEXT,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX leases_one_active_task
ON leases(task_id) WHERE status = 'ACTIVE';

CREATE TABLE runtime_grants (
    session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),
    idempotency_key TEXT NOT NULL UNIQUE,
    input_hash TEXT NOT NULL,
    token_digest TEXT NOT NULL UNIQUE,
    worker_id TEXT NOT NULL REFERENCES workers(worker_id),
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
    lease_id TEXT NOT NULL REFERENCES leases(lease_id),
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE TABLE evidence (
    evidence_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
    purpose TEXT NOT NULL,
    source_path TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    manifest_id TEXT REFERENCES evidence(evidence_id),
    created_at TEXT NOT NULL,
    UNIQUE (attempt_id, purpose, sha256)
);

CREATE TABLE receipts (
    receipt_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    authority TEXT NOT NULL,
    outcome TEXT CHECK (
        outcome IS NULL OR outcome IN (
            'VERIFIED', 'REJECTED', 'FAILED', 'BLOCKED',
            'INCONCLUSIVE', 'INTERRUPTED', 'AMBIGUOUS'
        )
    ),
    contract_hash TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    manifest_id TEXT REFERENCES evidence(evidence_id),
    supersedes_receipt_id TEXT REFERENCES receipts(receipt_id),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE attempt_evidence (
    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
    sealed_at TEXT,
    PRIMARY KEY (attempt_id, evidence_id)
);

CREATE TABLE task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    depends_on_task_id TEXT NOT NULL REFERENCES tasks(task_id),
    required_receipt_kind TEXT NOT NULL,
    satisfied_by_receipt_id TEXT REFERENCES receipts(receipt_id),
    created_at TEXT NOT NULL,
    PRIMARY KEY (task_id, depends_on_task_id),
    CHECK (task_id <> depends_on_task_id)
);

CREATE TABLE events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE attention_items (
    attention_id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (
        severity IN ('INFO', 'WARNING', 'HIGH', 'CRITICAL')
    ),
    kind TEXT NOT NULL,
    campaign_id TEXT REFERENCES campaigns(campaign_id),
    task_id TEXT REFERENCES tasks(task_id),
    attempt_id TEXT REFERENCES attempts(attempt_id),
    factual_reason TEXT NOT NULL,
    receipt_ids_json TEXT NOT NULL,
    allowed_actions_json TEXT NOT NULL,
    blocks_progress INTEGER NOT NULL CHECK (blocks_progress IN (0, 1)),
    occurrence_count INTEGER NOT NULL CHECK (occurrence_count > 0),
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX attention_one_open_dedupe
ON attention_items(dedupe_key) WHERE status = 'OPEN';

CREATE TABLE resource_reservations (
    reservation_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    attempt_id TEXT REFERENCES attempts(attempt_id),
    resource_type TEXT NOT NULL CHECK (
        resource_type IN (
            'FILE', 'ARTIFACT', 'DATASET', 'COMPUTE', 'GPU', 'PAPER_ACCOUNT'
        )
    ),
    resource_key TEXT NOT NULL,
    access_mode TEXT NOT NULL CHECK (
        access_mode IN ('READ', 'WRITE', 'EXCLUSIVE', 'BOUNDED')
    ),
    amount INTEGER NOT NULL CHECK (amount >= 0),
    unit TEXT NOT NULL CHECK (
        unit IN ('COUNT', 'BYTES', 'PERCENT', 'SLOT')
    ),
    status TEXT NOT NULL CHECK (
        status IN ('PLANNED', 'ACTIVE', 'RELEASED', 'BLOCKED')
    ),
    created_at TEXT NOT NULL,
    activated_at TEXT,
    released_at TEXT
);

CREATE INDEX reservations_active_lookup
ON resource_reservations(resource_type, resource_key)
WHERE status = 'ACTIVE';

CREATE TABLE budget_usage (
    attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id),
    wall_seconds INTEGER NOT NULL DEFAULT 0 CHECK (wall_seconds >= 0),
    peak_cpu_percent INTEGER NOT NULL DEFAULT 0 CHECK (peak_cpu_percent >= 0),
    peak_memory_bytes INTEGER NOT NULL DEFAULT 0 CHECK (peak_memory_bytes >= 0),
    artifact_bytes INTEGER NOT NULL DEFAULT 0 CHECK (artifact_bytes >= 0),
    terminal_bytes INTEGER NOT NULL DEFAULT 0 CHECK (terminal_bytes >= 0),
    updated_at TEXT NOT NULL
);

CREATE TABLE command_results (
    command_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    input_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    result_json TEXT NOT NULL,
    http_status INTEGER NOT NULL,
    last_event_sequence INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TRIGGER factory_budget_frozen
BEFORE UPDATE OF global_budget_json, global_budget_hash ON factory_config
WHEN OLD.global_budget_hash IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'factory global budget is frozen');
END;

CREATE TRIGGER campaign_contract_frozen
BEFORE UPDATE OF
    title, objective, contract_json, contract_hash,
    budget_json, budget_hash, approval_reference
ON campaigns
BEGIN
    SELECT RAISE(ABORT, 'campaign contract is frozen');
END;

CREATE TRIGGER task_contract_frozen
BEFORE UPDATE OF
    campaign_id, parent_task_id, title, description, workflow_stage,
    work_kind, capability_template, contract_json, contract_hash,
    max_attempts, requires_run_manifest
ON tasks
BEGIN
    SELECT RAISE(ABORT, 'task contract is frozen');
END;

CREATE TRIGGER attempt_identity_frozen
BEFORE UPDATE OF
    task_id, worker_id, session_id, attempt_kind, retry_of_attempt_id,
    runtime, model, worktree_path, contract_hash, input_hash, started_at,
    wall_deadline_at
ON attempts
BEGIN
    SELECT RAISE(ABORT, 'attempt identity is frozen');
END;

CREATE TRIGGER evidence_no_update BEFORE UPDATE ON evidence
BEGIN SELECT RAISE(ABORT, 'evidence is append-only'); END;
CREATE TRIGGER evidence_no_delete BEFORE DELETE ON evidence
BEGIN SELECT RAISE(ABORT, 'evidence is append-only'); END;
CREATE TRIGGER receipts_no_update BEFORE UPDATE ON receipts
BEGIN SELECT RAISE(ABORT, 'receipts are append-only'); END;
CREATE TRIGGER receipts_no_delete BEFORE DELETE ON receipts
BEGIN SELECT RAISE(ABORT, 'receipts are append-only'); END;
CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER commands_no_update BEFORE UPDATE ON command_results
BEGIN SELECT RAISE(ABORT, 'command results are append-only'); END;
CREATE TRIGGER commands_no_delete BEFORE DELETE ON command_results
BEGIN SELECT RAISE(ABORT, 'command results are append-only'); END;
```

The migration runner must:

1. Create the database parent directory.
2. Open/configure WAL before beginning migration.
3. Validate that `MIGRATIONS` is contiguous from `1`, names are unique, and
   each stored checksum matches `canonical_hash(migration.sql)`.
4. Resolve `target_version` to `CURRENT_SCHEMA` when omitted; reject targets
   outside `1..CURRENT_SCHEMA` and reject `user_version > target_version` with
   `FactoryError("SCHEMA_TOO_NEW", ..., 503)`.
5. Return without rewriting anything when `user_version == target_version`,
   after checking every applied migration checksum.
6. Apply each missing migration in its own `BEGIN IMMEDIATE` transaction,
   recording its version/name/checksum and changing `PRAGMA user_version` only
   after its SQL and version-specific initialization succeed.
7. For version `0`, execute all schema-1 DDL above, then insert singleton rows:

```python
timestamp = format_utc(now)
connection.execute(
    """
    INSERT INTO factory_config(
        singleton, protocol, schema_version, updated_at
    ) VALUES (1, 1, 1, ?)
    """,
    (timestamp,),
)
connection.execute(
    """
    INSERT INTO factory_state(
        singleton, mode, health, dispatch_enabled, paper_enabled, updated_at
    ) VALUES (1, 'PAUSED', 'HEALTHY', 0, 0, ?)
    """,
    (timestamp,),
)
connection.execute(
    """
    INSERT INTO schema_migrations(version, name, checksum, applied_at)
    VALUES (1, 'factory-kernel-v1', ?, ?)
    """,
    (canonical_hash(SCHEMA_V1), timestamp),
)
connection.execute("PRAGMA user_version = 1")
```

Wrap each migration's DDL, initialization, migration record, and version bump
in one transaction and roll back on every exception. Do not create a backup
for `0 → 1` because version `0` has no predecessor and the migration is
non-destructive. Later plans append immutable `Migration` records without
changing earlier SQL or checksums.

- [ ] **Step 5: Add deterministic temporary-database fixtures**

```python
# tests/factory/conftest.py
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from vesper.factory.database import Database
from vesper.factory.migrations import migrate
from vesper.factory.paths import FactoryPaths


class FakeClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


@pytest.fixture
def factory_paths(tmp_path: Path) -> FactoryPaths:
    paths = FactoryPaths.from_home((tmp_path / "factory").resolve())
    paths.create()
    return paths


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def database(factory_paths: FactoryPaths, clock: FakeClock) -> Database:
    value = Database(factory_paths.database)
    migrate(value, clock.now())
    return value
```

- [ ] **Step 6: Run focused migration verification**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_database.py -q
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile vesper/factory/database.py vesper/factory/migrations.py
```

Expected: pytest reports `3 passed`; compilation exits `0`.

- [ ] **Step 7: Commit**

```bash
git add vesper/factory/database.py vesper/factory/migrations.py tests/factory/conftest.py tests/factory/test_database.py
git commit -m "feat(factory): add schema one database"
```

### Task 3: Exact Contracts, Global Ceilings, and Frozen Campaign Records

**Files:**
- Create: `vesper/factory/contracts.py`
- Create: `vesper/factory/campaigns.py`
- Create: `tests/factory/test_campaigns.py`

**Interfaces:**
- Consumes: schema `1`, canonical helpers, `FactoryError`.
- Produces: `ResourceBudgetV1`, `AuthorityV1`, `DataContractV1`, `ResourceRequestV1`, `TaskDraftV1`, `DependencyDraftV1`, `CampaignContractV1`, `CampaignAdmissionV1`.
- Produces: `validate_budget(value: object) -> ResourceBudgetV1`, `validate_admission(value: object) -> CampaignAdmissionV1`.
- Produces: `CampaignService.configure_global_budget(connection, budget, now) -> dict[str, object]`.
- Produces: `CampaignService.insert_frozen(connection, contract, now) -> dict[str, object]`.
- Invariant: global ceilings are explicitly initialized once by a local operator; an unconfigured kernel cannot admit or resume.

- [ ] **Step 1: Write failing contract/admission tests**

```python
# tests/factory/test_campaigns.py
import json
import sqlite3

import pytest

from vesper.factory.campaigns import CampaignService
from vesper.factory.errors import FactoryError


GLOBAL_BUDGET = {
    "concurrent_workers": 4,
    "total_attempts": 40,
    "per_attempt_wall_seconds": 3600,
    "aggregate_wall_seconds": 14400,
    "cpu_percent": 80,
    "gpu_eligible": False,
    "gpu_concurrency": 0,
    "memory_bytes": 8_589_934_592,
    "artifact_bytes": 10_737_418_240,
    "terminal_bytes": 20_000_000,
    "min_free_disk_bytes": 5_368_709_120,
    "warning_threshold_percent": 80,
}
CAMPAIGN = {
    "schema_version": 1,
    "title": "Kernel acceptance campaign",
    "objective": "Prove bounded factory coordination from temporary state.",
    "repository": {
        "root": "C:\\src\\V-2.0",
        "source_commit": "0123456789abcdef0123456789abcdef01234567",
        "integration_branch": "factory/accepted",
    },
    "scope": {
        "allowed_paths": ["vesper/factory", "tests/factory"],
        "denied_paths": [
            "config", "vesper/risk", "vesper/execution", "vesper/scheduler",
            "vesper/data/massive", "vesper/data/model_research", "models",
        ],
    },
    "allowed_actions": ["read_repository", "write_scoped_code", "run_tests"],
    "denied_actions": [
        "live_trading", "paper_trading", "paid_compute",
        "remote_push", "active_model_replacement",
    ],
    "data": {
        "provider": "massive",
        "read_only": True,
        "locations": ["vesper/data/massive"],
        "universe": ["SPY"],
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
    },
    "acceptance_criteria": ["All temporary-database contract tests pass."],
    "stop_conditions": ["Stop on any protected-path request."],
    "candidate_ceiling": "RESEARCH",
    "capability_templates": ["Development", "Independent Evaluator"],
    "authority": {
        "code_mutation": True,
        "paper_execution": False,
        "paid_compute": False,
        "protected_path_edits": False,
        "live_trading": False,
        "remote_push": False,
    },
    "budget": {
        **GLOBAL_BUDGET,
        "concurrent_workers": 2,
        "total_attempts": 6,
        "aggregate_wall_seconds": 7200,
        "cpu_percent": 60,
        "memory_bytes": 4_294_967_296,
        "artifact_bytes": 1_073_741_824,
        "terminal_bytes": 5_000_000,
        "min_free_disk_bytes": 6_442_450_944,
    },
    "approval": {
        "decision_owner": "Brennan",
        "reference": "approved:kernel-acceptance",
        "approved_at": "2026-07-24T12:00:00Z",
    },
}


def test_global_budget_and_campaign_contract_are_frozen(database, clock) -> None:
    service = CampaignService()
    with database.transaction() as connection:
        service.configure_global_budget(connection, GLOBAL_BUDGET, clock.now())
        campaign = service.insert_frozen(connection, CAMPAIGN, clock.now())

    assert campaign["campaign_id"].startswith("cmp_")
    with database.connect() as connection:
        row = connection.execute(
            "SELECT contract_json, contract_hash FROM campaigns"
        ).fetchone()
        assert json.loads(row["contract_json"]) == CAMPAIGN
        assert row["contract_hash"].startswith("sha256:")
    with pytest.raises(sqlite3.IntegrityError, match="frozen"):
        with database.transaction() as connection:
            connection.execute(
                "UPDATE campaigns SET objective = 'changed' WHERE campaign_id = ?",
                (campaign["campaign_id"],),
            )


def test_admission_rejects_unconfigured_widened_or_protected_contract(
    database, clock
) -> None:
    service = CampaignService()
    with pytest.raises(FactoryError, match="global"):
        with database.transaction() as connection:
            service.insert_frozen(connection, CAMPAIGN, clock.now())

    with database.transaction() as connection:
        service.configure_global_budget(connection, GLOBAL_BUDGET, clock.now())

    too_large = {**CAMPAIGN, "budget": {**CAMPAIGN["budget"], "total_attempts": 41}}
    with pytest.raises(FactoryError, match="ceiling"):
        with database.transaction() as connection:
            service.insert_frozen(connection, too_large, clock.now())

    protected = {
        **CAMPAIGN,
        "scope": {**CAMPAIGN["scope"], "allowed_paths": ["config"]},
    }
    with pytest.raises(FactoryError, match="protected"):
        with database.transaction() as connection:
            service.insert_frozen(connection, protected, clock.now())
```

- [ ] **Step 2: Run the campaign tests and verify red**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_campaigns.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'vesper.factory.campaigns'`.

- [ ] **Step 3: Define the exact version-1 JSON contracts**

Use `TypedDict` only for static shape and deterministic explicit validators for runtime input. Do not let Pydantic defaults silently populate frozen contract fields.

```python
# vesper/factory/contracts.py
from typing import Literal, TypedDict

CampaignStatus = Literal["DRAFT", "ADMITTED", "PAUSED", "STOPPED", "CLOSED"]
CandidateStage = Literal[
    "ADMISSION", "RESEARCH", "EVALUATION", "SHADOW",
    "PAPER", "LIVE_APPROVAL_REQUIRED", "ARCHIVED",
]
TaskState = Literal[
    "BACKLOG", "READY", "RUNNING", "EVALUATING", "COMPLETED",
    "BLOCKED", "INTERRUPTED", "CANCELED",
]
AttemptOutcome = Literal[
    "VERIFIED", "REJECTED", "FAILED", "BLOCKED",
    "INCONCLUSIVE", "INTERRUPTED", "AMBIGUOUS",
]
AttentionSeverity = Literal["INFO", "WARNING", "HIGH", "CRITICAL"]
CapabilityTemplate = Literal[
    "Quant Research", "Data Engineering", "ML Systems",
    "Portfolio Evaluation", "Risk Review", "Development",
    "Independent Evaluator",
]


class ResourceBudgetV1(TypedDict):
    concurrent_workers: int
    total_attempts: int
    per_attempt_wall_seconds: int
    aggregate_wall_seconds: int
    cpu_percent: int
    gpu_eligible: bool
    gpu_concurrency: int
    memory_bytes: int
    artifact_bytes: int
    terminal_bytes: int
    min_free_disk_bytes: int
    warning_threshold_percent: int


class ScopeV1(TypedDict):
    allowed_paths: list[str]
    denied_paths: list[str]


class DataContractV1(TypedDict):
    provider: Literal["massive"]
    read_only: Literal[True]
    locations: list[str]
    universe: list[str]
    start_date: str
    end_date: str


class AuthorityV1(TypedDict):
    code_mutation: bool
    paper_execution: bool
    paid_compute: bool
    protected_path_edits: bool
    live_trading: bool
    remote_push: bool


class ApprovalV1(TypedDict):
    decision_owner: Literal["Brennan"]
    reference: str
    approved_at: str


class RepositoryContractV1(TypedDict):
    root: str
    source_commit: str
    integration_branch: Literal["factory/accepted"]


class ResourceRequestV1(TypedDict):
    resource_type: Literal[
        "FILE", "ARTIFACT", "DATASET", "COMPUTE", "GPU", "PAPER_ACCOUNT"
    ]
    resource_key: str
    access_mode: Literal["READ", "WRITE", "EXCLUSIVE", "BOUNDED"]
    amount: int
    unit: Literal["COUNT", "BYTES", "PERCENT", "SLOT"]


class TaskDraftV1(TypedDict):
    key: str
    title: str
    description: str
    workflow_stage: Literal[
        "ADMISSION", "CONTRACT", "IMPLEMENT", "TRAIN",
        "BACKTEST", "REVIEW", "NEXT",
    ]
    work_kind: str
    capability_template: CapabilityTemplate
    acceptance_criteria: list[str]
    stop_conditions: list[str]
    allowed_paths: list[str]
    required_skills: list[str]
    max_attempts: int
    requires_run_manifest: bool
    resource_requests: list[ResourceRequestV1]


class DependencyDraftV1(TypedDict):
    task_key: str
    depends_on_task_key: str
    required_receipt_kind: str


class CampaignContractV1(TypedDict):
    schema_version: Literal[1]
    title: str
    objective: str
    repository: RepositoryContractV1
    scope: ScopeV1
    allowed_actions: list[str]
    denied_actions: list[str]
    data: DataContractV1
    acceptance_criteria: list[str]
    stop_conditions: list[str]
    candidate_ceiling: Literal["RESEARCH", "EVALUATION", "SHADOW", "PAPER"]
    capability_templates: list[CapabilityTemplate]
    authority: AuthorityV1
    budget: ResourceBudgetV1
    approval: ApprovalV1


class CampaignAdmissionV1(TypedDict):
    protocol: Literal[1]
    contract: CampaignContractV1
    tasks: list[TaskDraftV1]
    dependencies: list[DependencyDraftV1]
```

Validation must reject unknown or missing keys at every level and enforce:

- all strings are non-empty after stripping; titles are at most 200 Unicode code points, descriptions/objectives at most 20,000, list fields contain no duplicates, and comments are not part of campaign contracts;
- `schema_version == 1`, `protocol == 1`, `decision_owner == "Brennan"`, and approval time parses with `parse_utc`;
- repository root is an absolute canonical Windows path supplied by the Rust
  host's read-only Git inspection, source commit is exactly 40 lowercase
  hexadecimal characters, and integration branch is exactly
  `factory/accepted`; Python freezes these values and never discovers or
  changes Git state itself;
- provider is exactly `massive`, `read_only is True`, every data location is under `vesper/data/massive`, and `start_date <= end_date` using `date.fromisoformat`;
- every protected prefix is denied and no allowed path equals or descends from `config`, `vesper/risk`, `vesper/execution`, `vesper/scheduler`, `vesper/data/massive`, `vesper/data/model_research`, or `models`;
- `paper_execution`, `paid_compute`, `protected_path_edits`, `live_trading`, and `remote_push` are all `False` in Plan 01;
- every numeric budget value is an integer, not a Boolean; positive fields are greater than zero; `gpu_concurrency == 0` when `gpu_eligible is False`; `1 <= warning_threshold_percent < 100`; `1 <= cpu_percent <= 100`;
- a campaign ceiling is less than or equal to the global value for maximum fields; campaign `min_free_disk_bytes` is greater than or equal to the global reserve; `gpu_eligible` cannot widen a global `False`;
- task keys are unique and match `[a-z][a-z0-9_-]{0,63}`, capability templates are admitted by the campaign, task paths are within campaign allowed paths, and `max_attempts <= campaign.budget.total_attempts`;
- resource keys are normalized forward-slash keys with no absolute prefix or `..`; `massive:` datasets are `READ` only; `PAPER_ACCOUNT` is rejected in Plan 01.

- [ ] **Step 4: Implement frozen global-limit and campaign inserts**

`CampaignService` owns no transaction. It receives the caller’s connection:

```python
class CampaignService:
    def configure_global_budget(
        self,
        connection: sqlite3.Connection,
        budget: object,
        now: datetime,
    ) -> dict[str, object]:
        validated = validate_budget(budget)
        rendered = canonical_json(validated)
        digest = canonical_hash(validated)
        timestamp = format_utc(now)
        row = connection.execute(
            "SELECT global_budget_hash FROM factory_config WHERE singleton = 1"
        ).fetchone()
        if row["global_budget_hash"] is not None:
            raise FactoryError(
                "GLOBAL_BUDGET_FROZEN",
                "Factory global resource ceilings are already configured.",
                409,
            )
        connection.execute(
            """
            UPDATE factory_config
            SET global_budget_json = ?, global_budget_hash = ?,
                configured_at = ?, updated_at = ?, version = version + 1
            WHERE singleton = 1
            """,
            (rendered, digest, timestamp, timestamp),
        )
        return {"global_budget": validated, "global_budget_hash": digest}

    def insert_frozen(
        self,
        connection: sqlite3.Connection,
        contract: object,
        now: datetime,
    ) -> dict[str, object]:
        global_row = connection.execute(
            "SELECT global_budget_json FROM factory_config WHERE singleton = 1"
        ).fetchone()
        if global_row["global_budget_json"] is None:
            raise FactoryError(
                "GLOBAL_BUDGET_REQUIRED",
                "Factory global resource ceilings must be configured.",
                409,
            )
        validated = validate_campaign_contract(
            contract,
            json.loads(global_row["global_budget_json"]),
        )
        campaign_id = new_id("campaign")
        timestamp = format_utc(now)
        contract_hash = canonical_hash(validated)
        budget_hash = canonical_hash(validated["budget"])
        connection.execute(
            """
            INSERT INTO campaigns(
                campaign_id, status, title, objective, contract_json,
                contract_hash, budget_json, budget_hash, approval_reference,
                admitted_at
            ) VALUES (?, 'ADMITTED', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                campaign_id,
                validated["title"],
                validated["objective"],
                canonical_json(validated),
                contract_hash,
                canonical_json(validated["budget"]),
                budget_hash,
                validated["approval"]["reference"],
                timestamp,
            ),
        )
        return {
            "campaign_id": campaign_id,
            "status": "ADMITTED",
            "contract_hash": contract_hash,
            "version": 0,
        }
```

`validate_campaign_contract()` must return a newly constructed dictionary containing only the exact contract keys in declared order-independent content; never retain an input mapping by reference.

- [ ] **Step 5: Run focused campaign verification**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_campaigns.py -q
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile vesper/factory/contracts.py vesper/factory/campaigns.py
```

Expected: pytest reports `2 passed`; compilation exits `0`.

- [ ] **Step 6: Commit**

```bash
git add vesper/factory/contracts.py vesper/factory/campaigns.py tests/factory/test_campaigns.py
git commit -m "feat(factory): freeze campaign contracts and ceilings"
```

### Task 4: Append-Only Evidence, Receipts, and Ordered Events

**Files:**
- Create: `vesper/factory/journal.py`
- Create: `vesper/factory/evidence.py`
- Create: `tests/factory/test_journal.py`
- Create: `tests/factory/test_evidence.py`
- Modify: `vesper/factory/contracts.py`

**Interfaces:**
- Consumes: temporary schema-1 database, `FactoryPaths`, canonical helpers.
- Produces: `EventV1`, `ReceiptInputV1`, `ReceiptV1`, and `RunManifestV1`.
- Produces: `Journal.append_event(connection, *, kind, aggregate_type, aggregate_id, payload, now) -> EventV1`.
- Produces: `Journal.list_events(connection, *, after: int, limit: int) -> list[EventV1]`.
- Produces: `Journal.append_receipt(connection, value: ReceiptInputV1, now: datetime) -> ReceiptV1`.
- Produces: `EvidenceService.register(connection, *, attempt_id, source_path, expected_sha256, purpose, manifest_id, now) -> dict[str, object]`.
- Invariant: evidence bytes are copied into `evidence/sha256/<first-two-hex>/<64-hex>` with exclusive creation and are never modified in place.

- [ ] **Step 1: Write failing journal and evidence tests**

```python
# tests/factory/test_journal.py
import sqlite3

import pytest

from vesper.factory.journal import Journal


def test_events_are_strictly_ordered_and_receipts_are_immutable(database, clock) -> None:
    journal = Journal()
    with database.transaction() as connection:
        first = journal.append_event(
            connection,
            kind="factory.started",
            aggregate_type="factory",
            aggregate_id="factory",
            payload={"mode": "PAUSED"},
            now=clock.now(),
        )
        second = journal.append_event(
            connection,
            kind="factory.checked",
            aggregate_type="factory",
            aggregate_id="factory",
            payload={"health": "HEALTHY"},
            now=clock.now(),
        )
    assert [first["sequence"], second["sequence"]] == [1, 2]

    with database.connect() as connection:
        assert [
            event["sequence"]
            for event in journal.list_events(connection, after=0, limit=500)
        ] == [1, 2]
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with database.transaction() as connection:
            connection.execute("UPDATE events SET kind = 'rewritten'")
```

```python
# tests/factory/test_evidence.py
from pathlib import Path

import pytest

from vesper.factory.errors import FactoryError
from vesper.factory.evidence import EvidenceService
from vesper.factory.foundation import sha256_file


def test_evidence_is_hash_checked_and_content_addressed(
    seeded_attempt, factory_paths, database, clock
) -> None:
    source = Path(seeded_attempt["worktree_path"]) / "result.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"metric":1}\n', encoding="utf-8")
    expected = sha256_file(source)
    service = EvidenceService(factory_paths)

    with database.transaction() as connection:
        evidence = service.register(
            connection,
            attempt_id=seeded_attempt["attempt_id"],
            source_path=str(source),
            expected_sha256=expected,
            purpose="test_result",
            manifest_id=None,
            now=clock.now(),
        )

    stored = Path(evidence["stored_path"])
    assert stored.is_file()
    assert stored.read_bytes() == b'{"metric":1}\n'
    assert stored.is_relative_to(factory_paths.evidence)


def test_evidence_rejects_hash_mismatch_and_path_escape(
    seeded_attempt, factory_paths, database, clock, tmp_path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    service = EvidenceService(factory_paths)
    with pytest.raises(FactoryError, match="allowed evidence root"):
        with database.transaction() as connection:
            service.register(
                connection,
                attempt_id=seeded_attempt["attempt_id"],
                source_path=str(outside),
                expected_sha256=sha256_file(outside),
                purpose="report",
                manifest_id=None,
                now=clock.now(),
            )
```

`seeded_attempt` is a narrowly scoped SQL fixture in `tests/factory/conftest.py` that inserts one admitted campaign/task/worker/session/attempt and uses a worktree under `factory_paths.worktrees`. Replace this fixture with Task 7’s public attempt API when Task 7 lands.

- [ ] **Step 2: Run focused tests and verify red**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_journal.py tests/factory/test_evidence.py -q
```

Expected: FAIL during collection because `vesper.factory.journal` and `vesper.factory.evidence` do not exist.

- [ ] **Step 3: Add exact event, receipt, and manifest contracts**

```python
class EventV1(TypedDict):
    sequence: int
    event_id: str
    kind: str
    aggregate_type: str
    aggregate_id: str
    occurred_at: str
    payload: dict[str, object]


class ReceiptInputV1(TypedDict):
    kind: str
    aggregate_type: str
    aggregate_id: str
    authority: str
    outcome: AttemptOutcome | None
    contract_hash: str
    input_hash: str
    evidence_ids: list[str]
    manifest_id: str | None
    supersedes_receipt_id: str | None
    details: dict[str, object]


class ReceiptV1(ReceiptInputV1):
    receipt_id: str
    created_at: str
    payload_hash: str


class RunManifestV1(TypedDict):
    dataset_snapshot: str
    dataset_hash: str
    universe: list[str]
    start_date: str
    end_date: str
    corporate_action_version: str
    feature_version: str
    source_commit: str
    dependency_lock_hash: str
    random_seeds: list[int]
    transaction_costs: dict[str, object]
    slippage: dict[str, object]
    evaluation_split: dict[str, object]
    runtime_versions: dict[str, str]
    compute_envelope: dict[str, object]
```

`validate_run_manifest()` must reject missing/unknown keys, invalid `sha256:` values, non-40-hex `source_commit`, empty versions/universe, duplicate universe symbols, invalid dates, non-integer seeds, and secret-like keys. It validates reproducibility shape only; it does not evaluate a research candidate.

- [ ] **Step 4: Implement journal append/read rules**

`Journal.append_event()` canonicalizes and secret-checks payload, inserts one row, reads `lastrowid`, and returns the frozen event envelope. `list_events()` rejects `after < 0` and limits outside `1..500`.

`Journal.append_receipt()` must:

1. Validate exact keys and hash syntax.
2. Verify every evidence ID exists and belongs to `aggregate_id` when `aggregate_type == "attempt"`.
3. Verify `manifest_id`, when present, names registered evidence whose purpose is `run_manifest`.
4. Require a non-empty evidence list and manifest for `kind == "evaluation.verdict"`.
5. Verify `supersedes_receipt_id` exists and matches the same aggregate; never update it.
6. Build this exact payload before hashing/inserting:

```python
payload = {
    "receipt_id": receipt_id,
    "kind": value["kind"],
    "aggregate_type": value["aggregate_type"],
    "aggregate_id": value["aggregate_id"],
    "authority": value["authority"],
    "outcome": value["outcome"],
    "contract_hash": value["contract_hash"],
    "input_hash": value["input_hash"],
    "evidence_ids": sorted(value["evidence_ids"]),
    "manifest_id": value["manifest_id"],
    "supersedes_receipt_id": value["supersedes_receipt_id"],
    "details": value["details"],
    "created_at": format_utc(now),
}
payload_hash = canonical_hash(payload)
```

7. Insert the receipt and append a `receipt.appended` event in the caller’s transaction.

- [ ] **Step 5: Implement safe immutable evidence registration**

Resolve `source_path` with `strict=True`. Permit it only when it is under the attempt’s recorded worktree or `FactoryPaths.evidence`. Reject symlinks that resolve outside either root. Compute the actual hash before any copy and compare with `hmac.compare_digest(actual, expected_sha256)`.

For a new digest, create the parent and copy through an exclusive temporary file in the destination directory:

```python
digest_hex = expected_sha256.removeprefix("sha256:")
destination = self.paths.evidence / "sha256" / digest_hex[:2] / digest_hex
destination.parent.mkdir(parents=True, exist_ok=True)
if not destination.exists():
    temporary = destination.with_name(f"{destination.name}.{new_id('evidence')}.tmp")
    with source.open("rb") as reader, temporary.open("xb") as writer:
        shutil.copyfileobj(reader, writer, length=1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())
    if sha256_file(temporary) != expected_sha256:
        temporary.unlink()
        raise FactoryError("EVIDENCE_COPY_MISMATCH", "Copied evidence hash changed.", 409)
    try:
        temporary.replace(destination)
    except FileExistsError:
        temporary.unlink()
```

After the copy, verify `sha256_file(destination)` again. If `purpose == "run_manifest"`, parse UTF-8 JSON and call `validate_run_manifest()`. Insert `evidence` and `attempt_evidence` rows, update `budget_usage.artifact_bytes` by the stored size, and append `evidence.registered` in the same transaction. A duplicate `(attempt_id, purpose, sha256)` returns the original evidence row without adding bytes or events.

- [ ] **Step 6: Run focused append-only verification**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_journal.py tests/factory/test_evidence.py -q
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile vesper/factory/journal.py vesper/factory/evidence.py vesper/factory/contracts.py
```

Expected: pytest reports all journal/evidence tests passed; compilation exits `0`.

- [ ] **Step 7: Commit**

```bash
git add vesper/factory/contracts.py vesper/factory/journal.py vesper/factory/evidence.py tests/factory/conftest.py tests/factory/test_journal.py tests/factory/test_evidence.py
git commit -m "feat(factory): append immutable evidence and journal"
```

### Task 5: Atomic Campaign Graph Admission and Guarded Task State

**Files:**
- Create: `vesper/factory/tasks.py`
- Create: `tests/factory/test_tasks.py`
- Modify: `vesper/factory/campaigns.py`
- Modify: `tests/factory/test_campaigns.py`

**Interfaces:**
- Consumes: `CampaignAdmissionV1`, `CampaignService.insert_frozen()`, `Journal`.
- Produces: `AdmissionService.admit(connection, admission, now) -> dict[str, object]`.
- Produces: `TaskService.transition(connection, *, task_id, target_state, expected_version, reason, now) -> dict[str, object]`.
- Produces: `TaskService.create_followup(connection, *, parent_task_id, draft, now) -> dict[str, object]`.
- Produces: `TaskService.complete_from_verdict(connection, *, task_id, receipt_id, expected_version, now) -> dict[str, object]`.
- Invariant: task graph creation, initial states, reservations, and admission events are one transaction; cycles or invalid references leave no campaign row.

- [ ] **Step 1: Write failing graph/state tests**

```python
# tests/factory/test_tasks.py
import pytest

from vesper.factory.errors import FactoryError
from vesper.factory.tasks import AdmissionService, TaskService


def test_admission_maps_keys_and_only_root_is_ready(
    configured_database, clock, admission_v1
) -> None:
    with configured_database.transaction() as connection:
        result = AdmissionService().admit(connection, admission_v1, clock.now())
    root = result["task_ids"]["contract"]
    child = result["task_ids"]["implement"]
    with configured_database.connect() as connection:
        states = {
            row["task_id"]: row["state"]
            for row in connection.execute("SELECT task_id, state FROM tasks")
        }
        dependency = connection.execute(
            """
            SELECT depends_on_task_id, required_receipt_kind
            FROM task_dependencies WHERE task_id = ?
            """,
            (child,),
        ).fetchone()
    assert states[root] == "READY"
    assert states[child] == "BACKLOG"
    assert dict(dependency) == {
        "depends_on_task_id": root,
        "required_receipt_kind": "evaluation.verdict",
    }


def test_direct_running_and_completion_are_denied(
    admitted_graph, configured_database, clock
) -> None:
    task_id = admitted_graph["task_ids"]["contract"]
    service = TaskService()
    with pytest.raises(FactoryError) as running:
        with configured_database.transaction() as connection:
            service.transition(
                connection,
                task_id=task_id,
                target_state="RUNNING",
                expected_version=0,
                reason="bypass",
                now=clock.now(),
            )
    assert running.value.code == "TRANSITION_DENIED"

    with pytest.raises(FactoryError) as completed:
        with configured_database.transaction() as connection:
            service.transition(
                connection,
                task_id=task_id,
                target_state="COMPLETED",
                expected_version=0,
                reason="bypass",
                now=clock.now(),
            )
    assert completed.value.code == "TRANSITION_DENIED"


def test_cycle_rejects_entire_admission(
    configured_database, clock, admission_v1
) -> None:
    invalid = {
        **admission_v1,
        "dependencies": [
            {
                "task_key": "implement",
                "depends_on_task_key": "contract",
                "required_receipt_kind": "evaluation.verdict",
            },
            {
                "task_key": "contract",
                "depends_on_task_key": "implement",
                "required_receipt_kind": "evaluation.verdict",
            },
        ],
    }
    with pytest.raises(FactoryError) as error:
        with configured_database.transaction() as connection:
            AdmissionService().admit(connection, invalid, clock.now())
    assert error.value.code == "DEPENDENCY_CYCLE"
    with configured_database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM campaigns").fetchone()[0] == 0
```

`admission_v1` contains two complete task drafts. `contract` uses stage `CONTRACT`; `implement` uses stage `IMPLEMENT`; both use `Development`, admitted paths, one `FILE`/`WRITE` request, and finite acceptance/stop lists. Its single dependency is the one asserted above. `configured_database` calls `configure_global_budget()` with the explicit `GLOBAL_BUDGET` from Task 3.

- [ ] **Step 2: Run focused tests and verify red**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_tasks.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'vesper.factory.tasks'`.

- [ ] **Step 3: Implement graph admission and task contracts**

`AdmissionService.admit()` must validate the full admission, topologically sort task keys with Kahn’s algorithm, reject cycles, call `insert_frozen()`, create all task IDs before inserting edges, and return:

```json
{
  "campaign_id": "cmp_<uuid4hex>",
  "contract_hash": "sha256:<64hex>",
  "task_ids": {"contract": "tsk_<uuid4hex>", "implement": "tsk_<uuid4hex>"},
  "last_event_sequence": 3
}
```

For each task, store this exact canonical contract:

```python
task_contract = {
    "schema_version": 1,
    "campaign_contract_hash": campaign["contract_hash"],
    "title": draft["title"],
    "description": draft["description"],
    "workflow_stage": draft["workflow_stage"],
    "work_kind": draft["work_kind"],
    "capability_template": draft["capability_template"],
    "acceptance_criteria": draft["acceptance_criteria"],
    "stop_conditions": draft["stop_conditions"],
    "allowed_paths": draft["allowed_paths"],
    "required_skills": draft["required_skills"],
    "max_attempts": draft["max_attempts"],
    "requires_run_manifest": draft["requires_run_manifest"],
    "resource_requests": draft["resource_requests"],
}
```

Tasks without predecessors start `READY`; all others start `BACKLOG`. Append one `campaign.admitted` event and one `task.created` event per task.

`TaskService.transition()` allows only:

```python
MANUAL_TRANSITIONS = {
    "BACKLOG": {"READY", "CANCELED"},
    "READY": {"BLOCKED", "CANCELED"},
    "RUNNING": {"BLOCKED", "INTERRUPTED", "CANCELED"},
    "EVALUATING": {"BLOCKED", "INTERRUPTED", "CANCELED"},
    "BLOCKED": {"READY", "CANCELED"},
    "INTERRUPTED": {"BLOCKED", "CANCELED"},
    "COMPLETED": set(),
    "CANCELED": set(),
}
```

Before `READY`, require campaign `ADMITTED`, every dependency’s `satisfied_by_receipt_id`, no unreconciled prior attempt, attempt count below `max_attempts`, and no factory stop. Compare `expected_version`; mismatch raises `FactoryError("VERSION_CONFLICT", ..., 409, {"actual_version": actual})`. Every accepted transition increments `version`, records canonical `state_details_json={"reason": reason}`, and appends `task.transitioned`.

`complete_from_verdict()` verifies receipt kind/outcome/authority/hash/evidence, updates the task from `EVALUATING` to `COMPLETED`, sets each dependent edge’s `satisfied_by_receipt_id`, refreshes dependents to `READY` only when all edges are satisfied, and appends all events in the same transaction.

If a predecessor receives `REJECTED`, `FAILED`, `BLOCKED`, `INTERRUPTED`, `AMBIGUOUS`, or `INCONCLUSIVE`, set dependents `BLOCKED` with:

```python
{
    "reason": "DEPENDENCY_NOT_VERIFIED",
    "blocked_by_receipt_ids": [receipt_id],
    "propagated_outcome": outcome,
}
```

`create_followup()` derives campaign/parent identity, validates the new task against the frozen campaign, requires allowed paths to be a subset of the parent paths, creates it as `BACKLOG`, and creates a parent dependency requiring `evaluation.verdict`. It never changes campaign authority or budget.

- [ ] **Step 4: Verify state and admission behavior**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_campaigns.py tests/factory/test_tasks.py -q
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile vesper/factory/campaigns.py vesper/factory/tasks.py
```

Expected: all campaign/task tests pass and compilation exits `0`.

- [ ] **Step 5: Commit**

```bash
git add vesper/factory/campaigns.py vesper/factory/tasks.py tests/factory/conftest.py tests/factory/test_campaigns.py tests/factory/test_tasks.py
git commit -m "feat(factory): admit guarded task graphs"
```

### Task 6: Attention, Resource Reservations, Collision Checks, and Budgets

**Files:**
- Create: `vesper/factory/attention.py`
- Create: `vesper/factory/resources.py`
- Create: `tests/factory/test_resources.py`

**Interfaces:**
- Produces: `AttentionService.raise_item(...) -> dict[str, object]` and `acknowledge(connection, attention_id, expected_version, now)`.
- Produces: `ResourceService.plan_task(connection, campaign_id, task_id, requests, now)`, `activate_for_attempt(...)`, and `release_for_attempt(...)`.
- Produces: `BudgetService.check_dispatch(connection, campaign_id, task_id, now, free_disk_bytes) -> list[dict[str, object]]`.
- Produces: `BudgetService.record_usage(connection, attempt_id, usage, now) -> dict[str, object]`.
- Consumed by: attempts, grants, stop/recovery, snapshot.

- [ ] **Step 1: Write failing collision/budget tests**

```python
# tests/factory/test_resources.py
from vesper.factory.resources import BudgetService, ResourceService


def test_overlapping_writes_collide_but_massive_reads_share(
    admitted_graph, configured_database, clock
) -> None:
    tasks = admitted_graph["task_ids"]
    service = ResourceService()
    with configured_database.transaction() as connection:
        service.plan_task(
            connection,
            admitted_graph["campaign_id"],
            tasks["contract"],
            [{
                "resource_type": "FILE",
                "resource_key": "vesper/factory",
                "access_mode": "WRITE",
                "amount": 1,
                "unit": "COUNT",
            }],
            clock.now(),
        )
        service.activate_for_attempt(
            connection, tasks["contract"], "atm_" + "1" * 32, clock.now()
        )
        collisions = service.find_collisions(
            connection,
            tasks["implement"],
            [{
                "resource_type": "FILE",
                "resource_key": "vesper/factory/tasks.py",
                "access_mode": "WRITE",
                "amount": 1,
                "unit": "COUNT",
            }],
        )
        shared = service.find_collisions(
            connection,
            tasks["implement"],
            [{
                "resource_type": "DATASET",
                "resource_key": "massive:sp500",
                "access_mode": "READ",
                "amount": 0,
                "unit": "BYTES",
            }],
        )
    assert collisions[0]["code"] == "RESOURCE_COLLISION"
    assert shared == []


def test_budget_blocks_dispatch_before_disk_reserve(
    admitted_graph, configured_database, clock
) -> None:
    task_id = admitted_graph["task_ids"]["contract"]
    with configured_database.connect() as connection:
        violations = BudgetService().check_dispatch(
            connection,
            admitted_graph["campaign_id"],
            task_id,
            clock.now(),
            free_disk_bytes=1,
        )
    assert violations[0]["code"] == "DISK_RESERVE"
    assert violations[0]["hard"] is True
```

- [ ] **Step 2: Run focused tests and verify red**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_resources.py -q
```

Expected: FAIL during collection because `vesper.factory.resources` does not exist.

- [ ] **Step 3: Implement exact resource and attention rules**

Normalize `FILE` and `ARTIFACT` keys as repository-relative `PurePosixPath` values with no `.`/`..`. Two file keys overlap when either is equal to or an ancestor of the other. Apply:

| Resource | Non-collision | Collision |
|---|---|---|
| `FILE`, `ARTIFACT` | `READ` with `READ` | overlapping key and either side `WRITE`/`EXCLUSIVE` |
| `DATASET` | exact `massive:*`, both `READ` | any mutable/write/exclusive use |
| `COMPUTE` | bounded sum within CPU/memory campaign and global ceilings | requested plus active amount exceeds either ceiling |
| `GPU` | campaign/global eligible and bounded active slots | ineligible or slot ceiling exceeded |
| `PAPER_ACCOUNT` | none in Plan 01 | always `PAPER_AUTHORITY_UNAVAILABLE` |

`plan_task()` inserts `PLANNED` rows. `activate_for_attempt()` rechecks collisions, changes only that task’s rows to `ACTIVE`, binds `attempt_id`, and appends `resources.activated`; a collision changes planned rows to `BLOCKED`, raises one `HIGH` attention item, and fails without partial activation. `release_for_attempt()` marks active rows `RELEASED`.

`AttentionService.raise_item()` deduplicates open rows by exact `dedupe_key`; a repeat increments `occurrence_count` and updates factual fields. `acknowledge()` changes only attention status/version and appends `attention.acknowledged`; it never changes a task, campaign, lease, budget, or factory state.

- [ ] **Step 4: Implement hard and warning budget checks**

Compute current usage from durable rows:

- concurrent workers: active leases;
- total attempts: all campaign attempts;
- aggregate wall time: finished attempt durations plus `now - started_at` for active attempts;
- per-attempt wall time: the attempt’s fixed `wall_deadline_at`;
- CPU/GPU/memory: active reservations plus measured peaks;
- artifacts: `sum(evidence.size_bytes)`;
- terminal output: `sum(budget_usage.terminal_bytes)`;
- disk: caller-supplied `shutil.disk_usage(paths.home).free`.

Compare both campaign and global limits. A value at or above
`limit * warning_threshold_percent // 100` raises one `WARNING` attention item.
A hard breach raises `HIGH`, blocks new dispatch, and returns
`{"hard": True, "code": <stable code>, "measured": int, "limit": int}`.
`record_usage()` accepts exactly:

```python
{
    "wall_seconds": int,
    "peak_cpu_percent": int,
    "peak_memory_bytes": int,
    "terminal_bytes": int,
}
```

Values are monotonic (`max` for peaks, nondecreasing totals). A hard result includes `stop_required=True`; process termination remains Rust-owned.

- [ ] **Step 5: Verify resources and budgets**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_resources.py -q
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile vesper/factory/attention.py vesper/factory/resources.py
```

Expected: all resource tests pass and compilation exits `0`.

- [ ] **Step 6: Commit**

```bash
git add vesper/factory/attention.py vesper/factory/resources.py tests/factory/test_resources.py
git commit -m "feat(factory): enforce resources and budgets"
```

### Task 7: Attempts, Leases, Reconciliation, and Factory Stop/Resume

**Files:**
- Create: `vesper/factory/attempts.py`
- Create: `vesper/factory/control.py`
- Create: `tests/factory/test_attempts.py`
- Create: `tests/factory/test_control.py`

**Interfaces:**
- Produces: `AttemptService.start(connection, request, now) -> AttemptLeaseV1`.
- Produces: `heartbeat(connection, session_id, now)`,
  `seal_for_evaluation(...)`, `apply_evaluation_verdict(...)`,
  `record_exit(...)`, `expire_stale(...)`, `reconcile_startup(...)`, and
  `reconcile(...)`.
- Produces: `FactoryControl.stop(connection, *, reason, operator_reference, now) -> dict[str, object]`.
- Produces: `FactoryControl.pause(connection, *, reason, operator_reference, now) -> dict[str, object]`.
- Produces: `FactoryControl.resume(connection, *, operator_reference, now) -> dict[str, object]`.
- Constants: `LEASE_TTL_SECONDS = 90`, `STOP_GRACE_SECONDS = 15`.

- [ ] **Step 1: Write failing lease/recovery/pause/stop tests**

```python
# tests/factory/test_attempts.py
from vesper.factory.attempts import AttemptService


def test_lease_heartbeat_is_bounded_and_expiry_requires_reconciliation(
    running_factory, admitted_graph, configured_database, factory_paths, clock
) -> None:
    request = {
        "task_id": admitted_graph["task_ids"]["contract"],
        "attempt_kind": "AUTHOR",
        "runtime": "fake",
        "model": "fake-v1",
        "template_version": 1,
        "worktree_path": str(factory_paths.worktrees / "attempt-one"),
        "retry_of_attempt_id": None,
    }
    service = AttemptService(factory_paths)
    with configured_database.transaction() as connection:
        started = service.start(connection, request, clock.now())
    clock.advance(seconds=91)
    with configured_database.transaction() as connection:
        interrupted = service.expire_stale(connection, clock.now())
    assert interrupted == [started["attempt_id"]]
    with configured_database.connect() as connection:
        assert connection.execute(
            "SELECT state FROM tasks WHERE task_id = ?",
            (request["task_id"],),
        ).fetchone()["state"] == "INTERRUPTED"
        assert connection.execute(
            "SELECT status FROM attempts WHERE attempt_id = ?",
            (started["attempt_id"],),
        ).fetchone()["status"] == "RECONCILING"
```

```python
# tests/factory/test_control.py
from vesper.factory.control import FactoryControl


def test_stop_revokes_work_and_resume_waits_for_reconciliation(
    active_attempt, configured_database, clock
) -> None:
    control = FactoryControl()
    with configured_database.transaction() as connection:
        stopped = control.stop(
            connection,
            reason="operator stop",
            operator_reference="local-ui:test",
            now=clock.now(),
        )
    assert stopped["mode"] == "STOPPED"
    assert stopped["grace_seconds"] == 15
    assert stopped["session_ids"] == [active_attempt["session_id"]]

    with configured_database.transaction() as connection:
        blocked = control.can_resume(connection)
    assert blocked == ["UNRECONCILED_ATTEMPTS"]
```

Add a companion test that pauses an active attempt, asserts
`dispatch_enabled == 0`, and proves its lease, grant, worker, session, and
resource reservation remain active until explicit stop or natural exit.

- [ ] **Step 2: Run focused tests and verify red**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_attempts.py tests/factory/test_control.py -q
```

Expected: FAIL during collection because the attempt/control modules do not exist.

- [ ] **Step 3: Implement exact attempt and lease behavior**

`AttemptService.start()` requires factory `RUNNING`, campaign `ADMITTED`, task `READY` for `AUTHOR` or task `EVALUATING` for `EVALUATOR`, no active task lease, budgets/collisions green, and attempt count below both task/campaign limits. Validate the absolute worktree path is under `FactoryPaths.worktrees`. In one transaction create prefixed worker/session/attempt IDs, a UUID4 lease, budget usage, activate resources, change author task `READY -> RUNNING`, and append `attempt.started`/`task.transitioned`.

An `AUTHOR` attempt may set `retry_of_attempt_id` and must have
`review_of_attempt_id=NULL`. An `EVALUATOR` attempt derives
`review_of_attempt_id` from the task's sealed current author attempt, requires
`retry_of_attempt_id=NULL`, and does not replace `tasks.current_attempt_id`.
The evaluator packet references the sealed author attempt, while its
worker/session/lease identities remain distinct.

The immutable attempt input hash is:

```python
input_hash = canonical_hash({
    "task_id": request["task_id"],
    "attempt_kind": request["attempt_kind"],
    "runtime": request["runtime"],
    "model": request["model"],
    "template_version": request["template_version"],
    "worktree_path": str(validated_worktree),
    "retry_of_attempt_id": request["retry_of_attempt_id"],
    "review_of_attempt_id": derived_review_of_attempt_id,
})
```

Set `wall_deadline_at = min(started_at + per_attempt_wall_seconds,
campaign aggregate-wall deadline)`. Heartbeat takes no caller duration and sets
`expires_at = min(now + 90 seconds, wall_deadline_at)` only for the matching
active session/lease.

`seal_for_evaluation()` verifies evidence belongs to the attempt, freezes every
`attempt_evidence.sealed_at`, sets attempt `EVIDENCE_SEALED`, releases lease and
resources, revokes the runtime grant, ends worker/session, transitions the task
to `EVALUATING`, and appends a `task.evaluation_requested` receipt/event.

`apply_evaluation_verdict()` accepts only a previously appended
`evaluation.verdict` receipt whose aggregate is the sealed author attempt,
authority is `independent-evaluator-v1`, contract/input hashes match, and
evidence/manifest IDs are registered to the review chain. `VERIFIED` ends the
author attempt and moves `EVALUATING → COMPLETED`; every other frozen outcome
ends it and moves the task to `BLOCKED` with an attention item. It appends the
task event in the caller's transaction and never constructs a verdict itself.

`expire_stale()` and `reconcile_startup()` revoke grants/leases, set attempts
`RECONCILING` with `outcome="INTERRUPTED"`, tasks `INTERRUPTED`, sessions
`INTERRUPTED`, raise `HIGH` attention, and append one interruption receipt per
attempt. Startup always sets factory mode `PAUSED`; it never retries.

`reconcile()` accepts only:

```python
outcome: Literal["VERIFIED", "FAILED", "BLOCKED"]
```

It requires an independent `authority="reconciler-v1"` and registered evidence.
`VERIFIED` moves an author task to `EVALUATING`; `FAILED` or `BLOCKED` moves it
to `BLOCKED`. It appends exactly one `attempt.reconciliation` receipt, ends the
attempt, and does not create a retry. A subsequent explicit `BLOCKED -> READY`
transition is the only retry gate.

- [ ] **Step 4: Implement atomic pause/stop/resume**

`pause()` sets `PAUSED`/`dispatch_enabled=0`, appends one local-operator
receipt/event, and leaves active attempts, leases, grants, resources, and paper
envelope state unchanged. It is idempotent while already paused.

`stop()`:

1. returns the existing stop result without another receipt when already
   `STOPPED`;
2. sets `STOPPED`, `dispatch_enabled=0`, `paper_enabled=0`;
3. revokes every grant and lease;
4. marks active attempts `RECONCILING`/`INTERRUPTED`, tasks `INTERRUPTED`, and
   sessions `STOP_REQUESTED`;
5. releases active resources;
6. appends one authoritative `factory.stop` receipt with
   `authority="local-operator-v1"` and one `factory.stopped` event;
7. returns sorted session IDs and `grace_seconds=15` for Rust to stop process
   trees.

`resume()` requires a configured global budget, no `ACTIVE` lease, no
`RECONCILING` attempt, no open critical recovery item, and an explicit
`operator_reference`. It sets `RUNNING`, enables dispatch, leaves paper disabled,
and appends `factory.resumed`. Workers, MCP tools, and restored sessions have no
resume entry point.

- [ ] **Step 5: Verify attempts and control**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_attempts.py tests/factory/test_control.py -q
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile vesper/factory/attempts.py vesper/factory/control.py
```

Expected: all attempt/control tests pass and compilation exits `0`.

- [ ] **Step 6: Commit**

```bash
git add vesper/factory/attempts.py vesper/factory/control.py tests/factory/conftest.py tests/factory/test_attempts.py tests/factory/test_control.py
git commit -m "feat(factory): reconcile attempts and factory control"
```

### Task 8: Idempotent Commands, Kernel Façade, Snapshots, and Event Pages

**Files:**
- Create: `vesper/factory/commands.py`
- Create: `vesper/factory/snapshot.py`
- Create: `vesper/factory/kernel.py`
- Create: `tests/factory/test_commands.py`
- Create: `tests/factory/test_snapshot.py`
- Modify: `vesper/factory/__init__.py`

**Interfaces:**
- Produces: `FactoryKernel.open(paths, clock=utc_now) -> FactoryKernel`.
- Produces: `FactoryKernel.execute_command(envelope) -> tuple[int, dict[str, object]]`.
- Produces: `FactoryKernel.snapshot() -> FactorySnapshotV1`, `events(after, limit) -> dict[str, object]`.
- Produces the stable in-process integration methods consumed by later plans:
  `load_campaign`, `load_task`, `load_attempt`, `load_evidence`,
  `list_receipts`, `list_events`, `register_evidence`,
  `append_receipt`, `append_event`, `create_attention_item`,
  `create_followup_task`, `reserve_resource`, `release_resource`, and
  `seal_attempt_for_evaluation`, and `apply_evaluation_verdict`. Mutating
  methods require an explicit open connection from
  `FactoryKernel.transaction()` so a downstream adapter can compose its own
  schema rows with kernel receipts/events atomically.
- Produces command kinds: `campaign.admit`, `task.transition`,
  `attempt.reconcile`, `factory.pause`, `factory.stop`, `factory.resume`,
  `attention.acknowledge`, `runtime.session_started`,
  `runtime.session_exited`, `runtime.report_usage`.

- [ ] **Step 1: Write failing idempotency/snapshot tests**

```python
# tests/factory/test_commands.py
from vesper.factory.errors import FactoryError


def test_identical_command_replays_and_changed_input_conflicts(kernel, admission_v1) -> None:
    envelope = {
        "protocol": 1,
        "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
        "kind": "campaign.admit",
        "payload": admission_v1,
        "expected_version": 0,
    }
    first = kernel.execute_command(envelope)
    second = kernel.execute_command(envelope)
    assert second == first

    changed = {**envelope, "payload": {**admission_v1, "tasks": []}}
    try:
        kernel.execute_command(changed)
    except FactoryError as error:
        assert error.code == "IDEMPOTENCY_CONFLICT"
        assert error.http_status == 409
    else:
        raise AssertionError("changed idempotency input was accepted")
```

```python
# tests/factory/test_snapshot.py
def test_snapshot_matches_protocol_and_event_cursor(kernel) -> None:
    snapshot = kernel.snapshot()
    assert list(snapshot) == [
        "protocol", "generated_at", "last_event_sequence", "factory",
        "campaigns", "candidates", "tasks", "attempts", "workers",
        "sessions", "attention_items", "resource_reservations",
    ]
    assert snapshot["protocol"] == 1
    assert snapshot["candidates"] == []
    page = kernel.events(after=0, limit=500)
    assert page["protocol"] == 1
    assert page["last_event_sequence"] == snapshot["last_event_sequence"]
```

- [ ] **Step 2: Run focused tests and verify red**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_commands.py tests/factory/test_snapshot.py -q
```

Expected: FAIL during collection because command/snapshot/kernel modules do not exist.

- [ ] **Step 3: Implement exact command replay**

Validate exact envelope keys/types. Hash the full canonical envelope. Under one
`BEGIN IMMEDIATE` transaction:

```python
existing = connection.execute(
    "SELECT * FROM command_results WHERE idempotency_key = ?",
    (envelope["idempotency_key"],),
).fetchone()
if existing is not None:
    if not hmac.compare_digest(existing["input_hash"], input_hash):
        raise FactoryError(
            "IDEMPOTENCY_CONFLICT",
            "Idempotency key was already used with different input.",
            409,
        )
    return existing["http_status"], json.loads(existing["result_json"])

result = dispatch_validated_command(connection, envelope)
last_sequence = connection.execute(
    "SELECT COALESCE(MAX(sequence), 0) FROM events"
).fetchone()[0]
body = {
    "ok": True,
    "command_id": new_id("command"),
    "result": result,
    "last_event_sequence": last_sequence,
}
```

Insert canonical `body` into `command_results` before commit. Validation/policy
errors use stable `FactoryError` responses and are not cached. The handlers map:

| Kind | Payload | Version |
|---|---|---|
| `campaign.admit` | exact `CampaignAdmissionV1` | `0` |
| `task.transition` | `task_id`, `target_state`, `reason` | task version |
| `attempt.reconcile` | `attempt_id`, `outcome`, `evidence_ids`, `reason` | attempt version |
| `factory.pause` | `reason`, `operator_reference` | factory version |
| `factory.stop` | `reason`, `operator_reference` | factory version |
| `factory.resume` | `operator_reference` | factory version |
| `attention.acknowledge` | `attention_id` | item version |
| `runtime.session_started` | `session_id`, `process_id`, `resolved_path`, `runtime_version`, `worktree_path` | session version |
| `runtime.session_exited` | `session_id`, `exit_code`, `reason`, `terminal_bytes`, `log_path` | session version |
| `runtime.report_usage` | `attempt_id`, `usage` | attempt version |

Reject unknown payload keys and command kinds. Runtime command fields match
Plan 03 exactly. `runtime.session_started` changes only `GRANTED → RUNNING`;
`runtime.session_exited` records truthful exit/interruption evidence and
reconciliation state, revokes the runtime grant, releases its lease/resources,
and ends worker/session atomically. Neither launches, retries, nor declares
task success. The separate revoke endpoint is idempotent failure-path cleanup
when Rust cannot report a truthful exit.

- [ ] **Step 4: Implement snapshot/event projection and façade**

`FactorySnapshotV1` is exactly:

```python
{
    "protocol": 1,
    "generated_at": format_utc(clock()),
    "last_event_sequence": int,
    "factory": {
        "version": int,
        "mode": str,
        "health": str,
        "market_status": "UNKNOWN",
        "next_gate": None,
    },
    "campaigns": list[dict[str, object]],
    "candidates": [],
    "tasks": list[dict[str, object]],
    "attempts": list[dict[str, object]],
    "workers": list[dict[str, object]],
    "sessions": list[dict[str, object]],
    "attention_items": list[dict[str, object]],
    "resource_reservations": list[dict[str, object]],
}
```

Lists sort by `created_at`, then ID. Parse JSON columns into objects and omit
`token_digest`, `input_hash` from grants, sidecar token, raw worker token, and
authorization data. Events return:

For every non-empty list, project the exact additive record fields in Plan
02's **Desktop Contract V1**; do not expose raw SQL rows. In schema `1`,
`candidates` is empty, task runtime/attempt values are `null` when inactive,
progress/gate values are derived from authoritative state/dependencies, and
`factory.market_status="UNKNOWN"`/`factory.next_gate=null` remain truthful
placeholders until a later owning plan can populate them.

```python
{
    "protocol": 1,
    "events": journal.list_events(connection, after=after, limit=limit),
    "last_event_sequence": max_sequence,
}
```

`FactoryKernel` owns `paths`, `database`, `clock`, and service instances.
Mutating methods open one transaction and pass its connection through all
services; query methods open one read connection. `open()` creates paths,
migrates schema `1`, and runs startup reconciliation once per process.

The downstream integration methods above are thin façades over the same
services and validators; they are not a second command path. Their mutation
signatures begin with `connection: sqlite3.Connection`, reject a connection
not opened by this kernel, and never commit. Add focused tests proving a
downstream callback can append a receipt and event in the same transaction and
that an exception rolls both back. Plans 04 and 05 may use this port only from
their single named kernel adapters.

- [ ] **Step 5: Verify commands and projections**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_commands.py tests/factory/test_snapshot.py -q
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile vesper/factory/commands.py vesper/factory/snapshot.py vesper/factory/kernel.py vesper/factory/__init__.py
```

Expected: all command/snapshot tests pass and compilation exits `0`.

- [ ] **Step 6: Commit**

```bash
git add vesper/factory/__init__.py vesper/factory/commands.py vesper/factory/snapshot.py vesper/factory/kernel.py tests/factory/conftest.py tests/factory/test_commands.py tests/factory/test_snapshot.py
git commit -m "feat(factory): add idempotent kernel commands"
```

### Task 9: Autonomous Dispatch, One-Time Worker Grants, and Seven FastMCP Tools

**Files:**
- Create: `vesper/factory/dispatch.py`
- Create: `vesper/factory/grants.py`
- Create: `vesper/factory/mcp_server.py`
- Create: `tests/factory/test_dispatch.py`
- Create: `tests/factory/test_grants.py`
- Create: `tests/factory/test_mcp_tools.py`
- Modify: `vesper/factory/contracts.py`
- Modify: `vesper/factory/kernel.py`

**Interfaces:**
- Produces: `DispatchService.select(connection, request, now) -> DispatchSelectionV1 | None`.
- Produces: `FactoryKernel.issue_runtime_grant(request) -> dict[str, object] | None`, `revoke_runtime_grant(session_id)`.
- Produces: `WorkerGrantMiddleware(app, kernel)` and `current_worker_grant() -> WorkerGrantV1`.
- Produces: `create_mcp_server(kernel) -> FastMCP`.
- Invariant: exactly seven tools, no resources, no prompts, no model-controlled worker/task/attempt/session/lease identity arguments, and no process launch in Python.

- [ ] **Step 1: Write failing dispatch, grant, and tool tests**

```python
# tests/factory/test_grants.py
def test_worker_token_is_returned_once_and_only_digest_is_stored(
    running_kernel, admitted_graph, factory_paths
) -> None:
    request = {
        "protocol": 1,
        "idempotency_key": "0f4dbf0a-2417-4718-8cb8-82f5d765f421",
        "selection": "TASK",
        "task_id": admitted_graph["task_ids"]["contract"],
        "expected_version": 0,
        "runtime_capabilities": [
            {"runtime": "fake", "author": True, "read_only_reviewer": True}
        ],
    }
    first = running_kernel.issue_runtime_grant(request)
    second = running_kernel.issue_runtime_grant(request)
    assert isinstance(first["worker_token"], str)
    assert first["selection"] == "TASK"
    assert first["attempt_kind"] == "AUTHOR"
    assert first["runtime"] == "fake"
    assert first["worktree"]["worktree_path"].startswith(
        str(factory_paths.worktrees)
    )
    assert first["task_packet"]["sha256"].startswith("sha256:")
    assert second["worker_token"] is None
    assert second["token_status"] == "ALREADY_RETURNED"
    with running_kernel.database.connect() as connection:
        stored = connection.execute(
            "SELECT token_digest FROM runtime_grants"
        ).fetchone()["token_digest"]
    assert first["worker_token"] not in stored
```

```python
# tests/factory/test_dispatch.py
def test_next_claim_is_deterministic_and_empty_queue_changes_nothing(
    running_kernel, admitted_parallel_graph
) -> None:
    request = {
        "protocol": 1,
        "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
        "selection": "NEXT",
        "expected_factory_version": running_kernel.snapshot()["factory"]["version"],
        "runtime_capabilities": [
            {"runtime": "codex", "author": True, "read_only_reviewer": True},
            {"runtime": "hermes", "author": True, "read_only_reviewer": False},
        ],
    }
    grant = running_kernel.issue_runtime_grant(request)
    assert grant["task_id"] == admitted_parallel_graph["oldest_ready_task_id"]
    assert grant["runtime"] in {
        item["runtime"] for item in request["runtime_capabilities"]
    }
    running_kernel.finish_fixture_attempt(grant["attempt_id"])

    empty = running_kernel.issue_runtime_grant({
        **request,
        "idempotency_key": "bd20d99d-b106-47a5-89f6-d59028928284",
        "expected_factory_version": running_kernel.snapshot()["factory"]["version"],
    })
    assert empty is None
```

```python
# tests/factory/test_mcp_tools.py
import asyncio

from vesper.factory.mcp_server import create_mcp_server


def test_fastmcp_exports_exact_task_scoped_tools(kernel_with_grant) -> None:
    kernel, grant_context = kernel_with_grant
    server = create_mcp_server(kernel)
    tools = asyncio.run(server.list_tools())
    assert [tool.name for tool in tools] == [
        "vesper_task_show",
        "vesper_heartbeat",
        "vesper_submit_evidence",
        "vesper_create_followup",
        "vesper_block",
        "vesper_comment",
        "vesper_request_evaluation",
    ]
    with grant_context:
        shown = asyncio.run(server.call_tool("vesper_task_show", {}))
    assert shown["protocol"] == 1
    assert shown["task"]["task_id"] == grant_context.grant.task_id
```

- [ ] **Step 2: Run focused tests and verify red**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_dispatch.py tests/factory/test_grants.py tests/factory/test_mcp_tools.py -q
```

Expected: FAIL during collection because dispatch/grant/MCP modules do not exist.

- [ ] **Step 3: Implement deterministic `TASK` and `NEXT` selection**

Accept exactly the two roadmap request variants. Normalize
`runtime_capabilities` as unique runtime records in canonical
`["codex", "hermes", "fake"]` order; `fake` is rejected outside tests.
Only records with `author=true` are eligible for `READY`; only records with
`read_only_reviewer=true` are eligible for `EVALUATING`. `TASK` requires at
least one eligible runtime. `NEXT` may supply an empty list and receives `None`
without task mutation; this is the truthful optional-runtime idle state.

For `TASK`, load exactly that task and require its supplied version. For
`NEXT`, compare the factory version, then choose in this order:

1. eligible `EVALUATING` tasks by `updated_at`, then `task_id`;
2. eligible `READY` tasks by workflow-stage order, `created_at`, then
   `task_id`;
3. the campaign/task runtime route when available, otherwise the first
   available runtime in canonical `codex`, `hermes` order.

Before Plan 05 has an activated canary-backed route, every capability template
uses immutable template version `1`, model selection `"agent-default"`, and
runtime preference `codex` then `hermes`; `Independent Evaluator` additionally
requires `read_only_reviewer=true`. `"agent-default"` means the adapter uses
the separately authenticated CLI's configured model without inventing a model
flag. The chosen runtime/model/template version are frozen on the worker and
attempt before launch. Plan 05 may replace this route only through its
versioned canary/rollback contract.

Eligibility rechecks factory/campaign mode, dependencies, attempt ceilings,
worker ceilings, disk/resource budgets, declared writable-path collisions,
and stop state in the same `BEGIN IMMEDIATE` transaction as grant creation.
An evaluator claim uses `attempt_kind="EVALUATOR"`, a fresh worker/session,
the `Independent Evaluator` capability template, and only frozen sealed inputs;
it never inherits author conversation state. If no work is eligible, return
`None` without appending an event, receipt, command result, or idempotency row.
Policy-blocked work creates one deduplicated attention item and is skipped; an
unexpected error aborts the claim.

- [ ] **Step 4: Implement one-time grant issuance, the complete packet, and bearer context**

Generate exactly 32 random bytes and return unpadded base64url:

```python
raw_token = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
token_digest = hashlib.sha256(raw_token.encode("ascii")).hexdigest()
```

Issue a grant by calling `AttemptService.start()` and inserting only digest and
identity fields. Python derives attempt kind, model/template route, repository
identity, deterministic worktree path, limits, and packet from frozen records;
none are accepted from Rust or React. First response is exactly:

```python
{
    "protocol": 1,
    "selection": "NEXT",
    "worker_id": "wrk_<uuid4hex>",
    "task_id": "tsk_<uuid4hex>",
    "attempt_id": "atm_<uuid4hex>",
    "session_id": "ses_<uuid4hex>",
    "lease_id": "<uuid4>",
    "session_version": 0,
    "attempt_kind": "AUTHOR",
    "review_of_attempt_id": None,
    "runtime": "codex",
    "expires_at": "2026-07-24T12:01:30Z",
    "worker_token": "<base64url>",
    "token_status": "ISSUED",
    "mcp_path": "/mcp",
    "worktree": {
        "repository_root": "C:\\src\\V-2.0",
        "worktree_path": "C:\\Users\\me\\AppData\\Local\\Vesper\\Factory\\worktrees\\atm_...",
        "branch_name": "factory/attempt/atm_...",
        "source_commit": "0123456789abcdef0123456789abcdef01234567",
        "read_only": False,
    },
    "limits": {
        "wall_seconds": 1800,
        "cpu_percent": 80,
        "memory_bytes": 4294967296,
        "terminal_bytes": 5000000,
    },
    "task_packet": {
        "protocol": 1,
        "canonical_json": "{\"protocol\":1,...}",
        "sha256": "sha256:<64-lowercase-hex>",
    },
    "last_event_sequence": 12
}
```

Reviewer grants set `attempt_kind="EVALUATOR"` and `worktree.read_only=true`.
They set `review_of_attempt_id` to the sealed author attempt; author grants set
it to `None`.
Their packet contains the frozen contract, sealed diff/artifacts, tests,
evidence, manifests, and receipt chain but no author terminal/conversation
content. `run_manifest_schema.required` is the complete roadmap field list
only when the task contract sets `requires_run_manifest=true`; otherwise it is
an empty list.

For identical `idempotency_key`/input, return the same metadata with
`worker_token=None`, `token_status="ALREADY_RETURNED"`. Different input returns
`409 IDEMPOTENCY_CONFLICT`. Rust must revoke that session and use a new key if
it lost the first response; the kernel never persists recoverable token bytes.

`WorkerGrantMiddleware` accepts only `Authorization: Bearer <token>`, hashes
the ASCII token, constant-time compares the digest, and requires no revocation,
unexpired grant, active lease, matching worker/session/attempt/task, and factory
`RUNNING`. It stores a frozen `WorkerGrantV1` in a `ContextVar` for only the
downstream ASGI call and resets it in `finally`. Failures return `401` or `403`
without token-bearing details.

- [ ] **Step 5: Register exact FastMCP 1.28.1 tools**

Construct:

```python
mcp = FastMCP(
    "Vesper Factory",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)
```

Register in this order with `@mcp.tool()` and these exact model-visible
signatures/results:

```python
async def vesper_task_show() -> dict[str, object]
async def vesper_heartbeat() -> dict[str, object]
async def vesper_submit_evidence(
    path: str,
    sha256: str,
    purpose: str,
    manifest_id: str | None = None,
) -> dict[str, object]
async def vesper_create_followup(
    title: str,
    description: str,
    work_kind: str,
    capability_template: CapabilityTemplate,
    acceptance_criteria: list[str],
    resource_requests: list[ResourceRequestV1],
) -> dict[str, object]
async def vesper_block(
    reason: str,
    required_resolution: str,
) -> dict[str, object]
async def vesper_comment(message: str) -> dict[str, object]
async def vesper_request_evaluation(
    summary: str,
    evidence_ids: list[str],
) -> dict[str, object]
```

Every function begins `grant = current_worker_grant()` and passes only that
derived identity to `FactoryKernel`. Tool behavior:

- `task_show`: return protocol, frozen campaign/task, dependency receipt IDs,
  attempt, lease, and receipt chain; omit all tokens and unrelated campaigns.
- `heartbeat`: renew fixed lease TTL; no input controls time/identity.
- `submit_evidence`: use Task 4 validation and return evidence identity/hash.
- `create_followup`: inherit parent paths, skills, stop conditions, maximum
  attempts, and `requires_run_manifest`; validate requested capability/resources
  within campaign bounds.
- `block`: require non-empty reason/resolution, append blocker receipt,
  transition `RUNNING -> BLOCKED`, release/revoke grant, and raise attention.
- `comment`: accept at most 4096 UTF-8 bytes, secret-check, append only
  `task.comment` event, return event ID/sequence.
- `request_evaluation`: require at least one evidence ID owned by the active
  attempt, validate required run manifest, call `seal_for_evaluation()`, and
  return state `EVALUATING`. The background host then obtains a fresh reviewer
  through its next `NEXT` claim; this tool never launches a process.

For an evaluator grant, `submit_evidence` permits exactly one strict
`purpose="evaluation_verdict"` JSON artifact in addition to ordinary
supporting evidence. On truthful evaluator session exit, later Plan 04 logic
validates that artifact and the independent session identity before appending
an authoritative verdict. Plan 01 stores it only as evidence and never
interprets research outcomes.

Policy errors become MCP tool errors with the stable code at the start of the
message. No tool calls shell commands or opens SQLite directly.

- [ ] **Step 6: Verify dispatch, grants, packets, and tools**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_dispatch.py tests/factory/test_grants.py tests/factory/test_mcp_tools.py -q
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile vesper/factory/dispatch.py vesper/factory/grants.py vesper/factory/mcp_server.py
```

Expected: grant/tool tests pass, the exact seven-name assertion passes, and
compilation exits `0`.

- [ ] **Step 7: Commit**

```bash
git add vesper/factory/contracts.py vesper/factory/kernel.py vesper/factory/dispatch.py vesper/factory/grants.py vesper/factory/mcp_server.py tests/factory/conftest.py tests/factory/test_dispatch.py tests/factory/test_grants.py tests/factory/test_mcp_tools.py
git commit -m "feat(factory): dispatch task scoped workers"
```

### Task 10: Authenticated Starlette API, Loopback Uvicorn Server, and Sidecar Fixture

**Files:**
- Create: `vesper/factory/api.py`
- Create: `vesper/factory/server.py`
- Create: `tests/factory/sidecar_fixture.py`
- Create: `tests/factory/test_api.py`
- Create: `tests/factory/test_mcp_transport.py`

**Interfaces:**
- Produces: `create_app(kernel, session_token) -> Starlette`.
- Produces: `serve(kernel, session_token, stdout=sys.stdout) -> None`.
- Publishes exactly the roadmap routes and readiness line.
- Consumed by: Plans 02 and 03 through HTTP/MCP contracts and the process fixture.

- [ ] **Step 1: Write failing API/transport tests**

```python
# tests/factory/test_api.py
from starlette.testclient import TestClient

from vesper.factory.api import create_app


def test_v1_requires_token_and_replays_command(kernel, admission_v1) -> None:
    token = "sidecar-test-token"
    with TestClient(create_app(kernel, token)) as client:
        assert client.get("/v1/health").status_code == 401
        headers = {"Authorization": f"Bearer {token}"}
        health = client.get("/v1/health", headers=headers)
        assert health.json()["schema"] == 1
        envelope = {
            "protocol": 1,
            "idempotency_key": "6802fb2f-2657-4c65-9ec8-f6e1693315ca",
            "kind": "campaign.admit",
            "payload": admission_v1,
            "expected_version": 0,
        }
        first = client.post("/v1/commands", headers=headers, json=envelope)
        second = client.post("/v1/commands", headers=headers, json=envelope)
    assert first.status_code == 200
    assert second.json() == first.json()


def test_error_envelope_is_stable(kernel) -> None:
    token = "sidecar-test-token"
    with TestClient(create_app(kernel, token)) as client:
        response = client.get(
            "/v1/events?after=0&limit=501",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 400
    assert response.json() == {
        "ok": False,
        "error": {
            "code": "INVALID_EVENT_LIMIT",
            "message": "Event limit must be between 1 and 500.",
            "details": {},
        },
    }


def test_next_dispatch_returns_204_when_queue_is_empty(running_kernel) -> None:
    token = "sidecar-test-token"
    request = {
        "protocol": 1,
        "idempotency_key": "12ee9c8e-4727-46bc-9204-823d31f9511e",
        "selection": "NEXT",
        "expected_factory_version": running_kernel.snapshot()["factory"]["version"],
        "runtime_capabilities": [
            {"runtime": "codex", "author": True, "read_only_reviewer": True}
        ],
    }
    with TestClient(create_app(running_kernel, token)) as client:
        response = client.post(
            "/v1/runtime-grants",
            headers={"Authorization": f"Bearer {token}"},
            json=request,
        )
    assert response.status_code == 204
    assert response.content == b""
```

- [ ] **Step 2: Run focused tests and verify red**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_api.py tests/factory/test_mcp_transport.py -q
```

Expected: FAIL during collection because API/server modules do not exist.

- [ ] **Step 3: Implement exact route/auth contracts**

Routes:

```text
GET  /v1/health
GET  /v1/snapshot
GET  /v1/events?after=<sequence>&limit=<1..500>
POST /v1/commands
POST /v1/runtime-grants
POST /v1/runtime-grants/<session_id>/revoke
MOUNT /mcp
```

All `/v1/*` requests require constant-time comparison with the launch token.
`/mcp` uses only `WorkerGrantMiddleware`. Reject requests to other paths with
`404`. JSON bodies must be objects and reject malformed JSON with
`400 INVALID_JSON`. `/v1/runtime-grants` validates exactly the roadmap's
tagged `TASK` and `NEXT` requests; an eligible claim returns the complete grant
object, while an empty `NEXT` claim returns `204` with no body or state change.

Success:

```json
{"ok":true,"command_id":"cmd_<uuid4hex>","result":{},"last_event_sequence":42}
```

Failure:

```json
{"ok":false,"error":{"code":"TRANSITION_DENIED","message":"Task dependencies are not complete.","details":{}}}
```

`GET /v1/health` returns:

```python
{
    "protocol": 1,
    "schema": 1,
    "pid": os.getpid(),
    "mode": state["mode"],
    "health": state["health"],
}
```

Build MCP lifespan using the 1.28.1 session manager:

```python
mcp = create_mcp_server(kernel)
mcp_transport = mcp.streamable_http_app()

@asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield

routes = [
    Route("/v1/health", health, methods=["GET"]),
    Route("/v1/snapshot", snapshot, methods=["GET"]),
    Route("/v1/events", events, methods=["GET"]),
    Route("/v1/commands", commands, methods=["POST"]),
    Route("/v1/runtime-grants", runtime_grants, methods=["POST"]),
    Route(
        "/v1/runtime-grants/{session_id:str}/revoke",
        revoke_runtime_grant,
        methods=["POST"],
    ),
    Mount("/mcp", app=WorkerGrantMiddleware(mcp_transport, kernel)),
]
```

Wrap only `/v1` with session-token middleware. Do not add CORS because React
never calls the sidecar.

- [ ] **Step 4: Bind one loopback socket and emit exact readiness**

`serve()` rejects a missing/empty `VESPER_FACTORY_SESSION_TOKEN`, creates and
binds one IPv4 socket to `("127.0.0.1", 0)`, listens, and obtains the assigned
port. After paths/migration/startup reconciliation and before serving, write
exactly one stdout line:

```python
readiness = {
    "protocol": 1,
    "port": port,
    "pid": os.getpid(),
    "schema": 1,
}
print(
    "VESPER_FACTORY_READY " + canonical_json(readiness),
    file=stdout,
    flush=True,
)
```

Start:

```python
config = uvicorn.Config(
    create_app(kernel, session_token),
    host="127.0.0.1",
    port=port,
    access_log=False,
    log_config=None,
)
asyncio.run(uvicorn.Server(config).serve(sockets=[listener]))
```

Uvicorn diagnostics go to stderr. No token or environment dump is logged.

`tests/factory/sidecar_fixture.py` must expose:

```python
@dataclass(frozen=True)
class RunningSidecar:
    process: subprocess.Popen[str]
    base_url: str
    session_token: str
    home: Path


@contextmanager
def running_sidecar(tmp_path: Path) -> Iterator[RunningSidecar]
```

The fixture launches `scripts/factory.py serve` with a temporary absolute
`VESPER_FACTORY_HOME`, a test token, reads and validates the single readiness
line, yields the process contract, then terminates only that recorded process
with a five-second timeout. It is the cross-language fixture for Plans 02/03.

- [ ] **Step 5: Verify API and real MCP transport**

`test_mcp_transport.py` uses `running_sidecar`, issues a real runtime grant,
then creates:

```python
http_client = httpx.AsyncClient(
    headers={"Authorization": f"Bearer {worker_token}"}
)
async with streamable_http_client(
    f"{sidecar.base_url}/mcp",
    http_client=http_client,
) as (read_stream, write_stream, _):
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        names = [tool.name for tool in (await session.list_tools()).tools]
```

Assert the exact seven names and that a missing/revoked bearer token fails.

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_api.py tests/factory/test_mcp_transport.py -q
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile vesper/factory/api.py vesper/factory/server.py tests/factory/sidecar_fixture.py
```

Expected: API and live transport tests pass; compilation exits `0`.

- [ ] **Step 6: Commit**

```bash
git add vesper/factory/api.py vesper/factory/server.py tests/factory/sidecar_fixture.py tests/factory/test_api.py tests/factory/test_mcp_transport.py
git commit -m "feat(factory): serve authenticated loopback api"
```

### Task 11: Factory CLI and M1 Temporary-Database Acceptance

**Files:**
- Create: `vesper/factory/cli.py`
- Create: `scripts/factory.py`
- Create: `tests/factory/test_cli.py`
- Create: `tests/factory/test_m1_acceptance.py`

**Interfaces:**
- Produces: `main(argv: Sequence[str] | None = None) -> int`.
- Produces commands: `init`, `admit`, `snapshot`, `events`, `transition`,
  `reconcile`, `pause`, `stop`, `resume`, `serve`.
- Acceptance: exercises all M1 behavior against temporary app-data state without process launching or product research.

- [ ] **Step 1: Write failing CLI/M1 tests**

```python
# tests/factory/test_cli.py
import json

from vesper.factory.cli import main


def test_init_and_snapshot_emit_canonical_json(
    factory_paths, global_budget_file, capsys
) -> None:
    assert main([
        "init",
        "--home", str(factory_paths.home),
        "--global-budget", str(global_budget_file),
    ]) == 0
    configured = json.loads(capsys.readouterr().out)
    assert configured["schema"] == 1
    assert configured["mode"] == "PAUSED"
    assert main(["snapshot", "--home", str(factory_paths.home)]) == 0
    assert json.loads(capsys.readouterr().out)["protocol"] == 1
```

```python
# tests/factory/test_m1_acceptance.py
def test_m1_kernel_acceptance(m1_harness) -> None:
    result = m1_harness.run()
    assert result == {
        "campaign_admitted": True,
        "task_transitioned": True,
        "next_dispatch_claimed": True,
        "lease_acquired": True,
        "lease_reconciled": True,
        "evidence_and_receipts_appended": True,
        "mcp_tools_called": [
            "vesper_task_show",
            "vesper_heartbeat",
            "vesper_submit_evidence",
            "vesper_create_followup",
            "vesper_block",
            "vesper_comment",
            "vesper_request_evaluation",
        ],
        "stop_resume_verified": True,
        "event_sequences_contiguous": True,
    }
```

- [ ] **Step 2: Run focused tests and verify red**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_cli.py tests/factory/test_m1_acceptance.py -q
```

Expected: FAIL during collection because `vesper.factory.cli` does not exist.

- [ ] **Step 3: Implement exact CLI**

Use `argparse`, return `0` on success and `2` on `FactoryError`. Success writes
one canonical JSON object to stdout; errors write the stable error body to
stderr. Commands:

```text
factory.py init --home ABSOLUTE --global-budget FILE
factory.py admit --home ABSOLUTE --file FILE --idempotency-key UUID
factory.py snapshot --home ABSOLUTE
factory.py events --home ABSOLUTE --after INT --limit INT
factory.py transition --home ABSOLUTE --task-id ID --to STATE --expected-version INT --reason TEXT --idempotency-key UUID
factory.py reconcile --home ABSOLUTE --attempt-id ID --outcome VERIFIED|FAILED|BLOCKED --evidence-id ID --reason TEXT --expected-version INT --idempotency-key UUID
factory.py pause --home ABSOLUTE --reason TEXT --operator-reference TEXT --expected-version INT --idempotency-key UUID
factory.py stop --home ABSOLUTE --reason TEXT --operator-reference TEXT --expected-version INT --idempotency-key UUID
factory.py resume --home ABSOLUTE --operator-reference TEXT --expected-version INT --idempotency-key UUID
factory.py serve
```

`serve` reads only `VESPER_FACTORY_HOME`/`LOCALAPPDATA` and
`VESPER_FACTORY_SESSION_TOKEN`; it accepts no token argument. `init` is the only
Plan 01 path that sets factory-wide ceilings and refuses a second value.

Match existing repository launcher style:

```python
#!/usr/bin/env python3
"""Run the Vesper factory kernel."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vesper.factory.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Build the M1 harness without external effects**

The harness uses one `tmp_path` home/database and a fake clock. It:

1. configures explicit global ceilings and resumes;
2. admits a two-card dependency graph;
3. performs a guarded manual transition;
4. issues a `NEXT` fake runtime grant, proves deterministic task selection,
   and heartbeats it;
5. registers a real temporary evidence file and append-only receipt;
6. invokes each FastMCP tool under a fresh task-scoped grant (tools that end a
   grant use separate bounded tasks);
7. expires one lease, proves automatic retry is denied, and reconciles it;
8. pauses dispatch without terminating one active fixture, then stops the
   factory and verifies grants/leases revoked plus one stop receipt;
9. reconciles interrupted attempts and explicitly resumes;
10. reads events in pages of two and asserts sequences equal
    `list(range(1, last_sequence + 1))`.

No harness assertion may mark evaluation/candidate success, launch a runtime,
call Massive/Alpaca, modify protected paths, or alter active models.

- [ ] **Step 5: Run M1, compilation, and the full Python suite**

From Git Bash:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-pytest-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" .venv/Scripts/python.exe -m pytest tests/factory/test_cli.py tests/factory/test_m1_acceptance.py -q --basetemp="$TMPROOT/focused"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile vesper/factory/*.py scripts/factory.py
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" .venv/Scripts/python.exe -m pytest -q --basetemp="$TMPROOT/full"
```

Expected: focused M1 tests pass, compilation exits `0`, and the complete Python
suite passes. Any failure blocks the M1 gate.

- [ ] **Step 6: Inspect scope and commit**

Run:

```bash
git diff --check
git diff --stat
git status --short
git diff -- requirements.txt vesper/factory scripts/factory.py tests/factory
```

Expected: only `requirements.txt`, `vesper/factory/`, `scripts/factory.py`, and
`tests/factory/` appear; no protected path appears.

```bash
git add requirements.txt vesper/factory scripts/factory.py tests/factory
git commit -m "feat(factory): complete kernel m1 acceptance"
```

## Final Acceptance Checklist

- [ ] Schema `1` migrates a temporary database transactionally, enables WAL and
      foreign keys, starts paused, and rejects a newer schema.
- [ ] Campaign/task contracts are canonical, immutable, bounded by frozen
      factory ceilings, and protected paths/effects fail closed.
- [ ] Dependencies, transitions, attempts, leases, receipts, evidence, events,
      attention, reservations, budgets, pause/stop/resume, and reconciliation
      pass focused tests.
- [ ] Duplicate commands return the original response; changed duplicate input
      returns `409 IDEMPOTENCY_CONFLICT`.
- [ ] Runtime grants return raw token bytes once, persist only SHA-256 digests,
      bind authority to worker/task/attempt/session/lease identity, and return
      a complete canonical task packet.
- [ ] `TASK` and `NEXT` claims are atomic and deterministic; an empty queue
      returns `204` without mutation, and reviewer claims use fresh evaluator
      identities with sealed read-only inputs.
- [ ] FastMCP `1.28.1` exposes exactly the seven frozen tools through `/mcp`.
- [ ] The sidecar binds only `127.0.0.1` on an assigned port, prints exactly one
      readiness line, and authenticates every `/v1/*` request.
- [ ] `FactorySnapshotV1` and paged events preserve exact protocol fields and
      contiguous monotonic ordering; `candidates` is truthfully empty.
- [ ] M1 acceptance, all factory tests, the existing Python suite, compilation,
      `git diff --check`, and protected-path scope inspection are green.
- [ ] Plans 02 and 03 receive schema `1`, stable API/MCP and dispatch/grant
      interfaces, and `tests/factory/sidecar_fixture.py` without requiring
      product behavior outside this plan.
