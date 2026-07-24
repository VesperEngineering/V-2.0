# Vesper Research Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the receipt-backed Vesper research pipeline from candidate admission through deterministic research, independent evaluation, shadow observation, bounded Alpaca paper operation, and the hard `LIVE_APPROVAL_REQUIRED` stop.

**Architecture:** Plan 04 consumes the schema-1 factory kernel, native desktop shell, and agent execution paths from Plans 01–03. New Python modules keep research policy and workflow truth in `vesper.factory.research`, store immutable files only under `%LOCALAPPDATA%\Vesper\Factory`, and project additive research views through the frozen sidecar command/snapshot contracts; Rust performs read-only Git inspection, while React renders typed views and never owns gate state.

**Tech Stack:** Python 3.11, stdlib `sqlite3`/`hashlib`/`json`/`csv`/`decimal`/`zoneinfo`, existing `alpaca-py>=0.30.0`, pytest, Tauri 2, Rust stable, React 19, TypeScript, Vite, Vitest, React Testing Library.

## Global Constraints

- Before any code edit, follow `AGENTS.md`: load matching skills, query the repository `.codegraph` index for every symbol/file to be changed, and read `SKILLS/CODE.md` plus `SKILLS/EXAMPLES.md`.
- The current local clone does not contain `.codegraph`. Implementation must run from the canonical Windows checkout where the index exists, or stop and refresh/create the required index before editing code.
- Do not edit `config/`, `vesper/risk.py`, `vesper/execution.py`, scheduler code, `vesper/data/massive/`, `vesper/data/model_research/`, or active model artifacts without a new exact-scope approval.
- Plan 04 additionally forbids edits under `models/`, `vesper/risk/`, `vesper/execution/`, `vesper/scheduler/`, `vesper/data/`, `vesper/engine.py`, `scripts/run_paper.py`, and the existing Tkinter dashboard.
- Massive data is opened read-only. No guard may fall back to yfinance, another provider, a different SQLite file, or a mutable connection.
- Alpaca is paper-only and remains disabled until an immutable, human-reviewed P2 envelope is active. Every paper effect is revalidated at effect time against the exact paper endpoint and account.
- Keep the Tkinter dashboard and current engine operational until the final parity gate.
- Use test-first changes, surgical diffs, deterministic assertions, and one focused commit per task.
- Use generated UUID4 identifiers with stable prefixes (`cmp_`, `cnd_`, `tsk_`, `atm_`, `rcp_`, `evt_`, `wrk_`, `ses_`, `evd_`, `lsn_`, `att_`, `rsv_`). Store UTC timestamps as RFC 3339 strings ending in `Z`.
- Store flexible payloads as canonical JSON: UTF-8, sorted keys, compact separators. Hash canonical bytes with SHA-256.
- Never store raw session tokens, worker tokens, broker credentials, provider credentials, or unbounded terminal output in SQLite.
- Candidate artifacts are copied into `%LOCALAPPDATA%\Vesper\Factory\candidates\<candidate_id>\artifacts\sha256\<digest>\<filename>` using exclusive creation. They never replace or shadow `models/xgb_ranker.json`, `models/xgb_ranker.metadata.json`, any other file under `models/`, or an active path from `config/settings.yaml`.
- Run manifests are immutable evidence under `%LOCALAPPDATA%\Vesper\Factory\manifests\sha256\<digest>.json`. Replay and reproduction create linked attempts and never rewrite a manifest, artifact, evidence object, or receipt.
- No task in this plan authorizes live trading, live endpoints, live model deployment, active-model replacement, capital allocation, risk-limit changes, paid compute, remote push, release publication, scheduler changes, or learning/lesson promotion.
- Python broker tests inject `FakePaperGateway` from `tests/factory/research/fakes.py`; test code never reaches Alpaca or any other network endpoint.
- Add only database migration `2`, owned by
  `vesper/factory/research/migration.py`, and register it through the existing
  Plan 01 migration runner. The sidecar API remains protocol `1`; after this
  plan the readiness line reports `"schema":2`. No other schema or protocol
  change is permitted.

---

## Dependencies, Serialization, and Acceptance Gates

Do not execute Task 1 against the baseline repository. Rebase onto the merged
Plan 01–03 implementation and verify all dependency gates below; a missing
interface is a blocked precondition, not permission to invent a second kernel,
sidecar, runtime manager, dispatcher, or frontend client.

### Required earlier-plan gates

- [ ] **M1 / Plan 01 — Factory Kernel:** the schema-1 kernel can admit a
  campaign, create an attempt, append immutable evidence and receipts, reserve
  resources, append ordered events, create attention items, enforce idempotent
  commands, and replay a snapshot from a temporary SQLite database.
- [ ] **M2 / Plan 02 — Native Desktop Shell:** the Tauri shell starts and
  authenticates the sidecar, owns the typed command/snapshot proxy, renders
  navigation from `FactorySnapshotV1`, and has a fake-sidecar frontend fixture.
- [ ] **M3 / Plan 03 — Agent Execution:** attempts have authoritative author
  worker/session/worktree/source-commit identities; evaluator sessions can be
  launched fresh and read-only; runtime events come from the Rust host; evidence
  paths and terminal/test receipts are available without trusting worker prose.
- [ ] **Cross-plan serialization:** shared edits to the sidecar composition
  root, command registry, snapshot projector, Tauri command registration,
  `apps/desktop/src/App.tsx`, and shared frontend API types are rebased after
  Plans 01–03 and are not edited concurrently.
- [ ] **CodeGraph gate:** the canonical checkout has a current `.codegraph`
  index and every file/symbol named in the task being executed has been queried.

### Exact Plan 01–03 ports consumed by Plan 04

Plan 04 owns a thin adapter in
`vesper/factory/research/kernel_adapter.py`. It consumes these exact operations
from the merged schema-1 kernel. Mutations receive the explicit open
connection from Plan 01's stable transaction port. Candidate persistence and
candidate transitions are Plan 04-owned operations implemented by that adapter
against the migration-2 tables; all other operations delegate to Plan 01. The
adapter is the only Plan 04 module allowed to import kernel implementation
classes:

```python
load_campaign(campaign_id: str) -> CampaignRecordV1
load_task(task_id: str) -> TaskRecordV1
load_attempt(attempt_id: str) -> AttemptRecordV1
load_evidence(evidence_id: str) -> EvidenceRecordV1
list_receipts(aggregate_type: str, aggregate_id: str) -> tuple[ReceiptRecordV1, ...]
list_events(kinds: tuple[str, ...], campaign_id: str | None) -> tuple[EventRecordV1, ...]
register_evidence(connection, draft: EvidenceCreateV1) -> EvidenceRecordV1
append_receipt(connection, draft: ReceiptCreateV1) -> ReceiptRecordV1
append_event(connection, draft: EventCreateV1) -> EventRecordV1
create_attention_item(
    connection,
    draft: AttentionItemCreateV1,
) -> AttentionItemRecordV1
create_followup_task(connection, draft: FollowupTaskCreateV1) -> TaskRecordV1
reserve_resource(
    connection,
    draft: ResourceReservationCreateV1,
) -> ResourceReservationRecordV1
release_resource(
    connection,
    reservation_id: str,
    reason_receipt_id: str,
) -> ResourceReservationRecordV1
seal_attempt_for_evaluation(
    connection,
    attempt_id: str,
    evidence_ids: tuple[str, ...],
) -> AttemptRecordV1
apply_evaluation_verdict(
    connection,
    author_attempt_id: str,
    verdict_receipt_id: str,
) -> TaskRecordV1
```

The adapter itself additionally exposes `load_candidate`, `create_candidate`,
and `commit_candidate_transition`; these are not required from or delegated to
the Plan 01 kernel. Reproduction creates a bounded follow-up task and lets the
Plan 01/03 `NEXT` dispatcher create its attempt. Independent review registers
the sealed evaluation bundle and moves the author attempt to `EVALUATING`;
the Plan 03 background supervisor launches the fresh read-only reviewer. No
Python research method directly starts a CLI.

`commit_candidate_transition` is one SQLite transaction: compare the candidate
version and `from_stage`, validate supplied predecessor receipt IDs, update the
candidate stage/version, append the authoritative transition receipt, append
the ordered event, and create any attention item. It either commits all records
or commits none.

The desktop consumes these exact merged-shell ports:

```typescript
export interface FactoryClientV1 {
  snapshot(): Promise<FactorySnapshotV1>;
  command<TResult>(
    kind: string,
    payload: Record<string, unknown>,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<TResult>;
}

export interface RuntimeReviewScopeV1 {
  attempt_id: string;
  worktree_root: string;
  base_commit: string;
  head_commit: string;
}
```

Only the Rust host receives `worktree_root`; React requests review by
`attempt_id`.

### Plan 04 command kinds

All mutations travel through the frozen `POST /v1/commands` envelope and carry
an idempotency key. Read-only comparison and review commands use the same typed
proxy but create no workflow records.

| Kind | Exact payload | Result |
|---|---|---|
| `candidate.register` | `CandidateRegisterCommandV1` | `CandidateRecordV1` |
| `manifest.register` | `ManifestRegisterCommandV1` | `RegisteredManifestV1` |
| `candidate.transition` | `CandidateTransitionCommandV1` | `CandidateRecordV1` |
| `evaluation.run` | `EvaluationRunCommandV1` | `DeterministicEvaluationV1` |
| `experiment.fork` | `ExperimentForkCommandV1` | `ExperimentForkResultV1` |
| `experiment.compare` | `ExperimentCompareCommandV1` | `CandidateComparisonV1` |
| `experiment.reproduce` | `ExperimentReproduceCommandV1` | `ReproductionResultV1` |
| `shadow.record` | `ShadowObservationCommandV1` | `ReceiptRecordV1` |
| `shadow.evaluate` | `ShadowEvaluateCommandV1` | `ShadowGateResultV1` |
| `paper.activate_envelope` | `PaperEnvelopeActivateCommandV1` | `PaperEnvelopeV1` |
| `paper.submit_effect` | `PaperEffectCommandV1` | `PaperEffectResultV1` |
| `analytics.export_csv` | `AnalyticsExportCommandV1` | `AnalyticsExportV1` |
| `review.bundle` | `{"attempt_id":"atm_..."}` | `EvidenceReviewBundleV1` |
| `review.accept_verdict` | `{"attempt_id":"atm_...","verdict_receipt_id":"rcp_..."}` | `CandidateRecordV1` |
| `review.reject_verdict` | `{"attempt_id":"atm_...","verdict_receipt_id":"rcp_...","reason":"contract-bound reason"}` | `ReceiptRecordV1` |
| `review.return_with_instruction` | `{"attempt_id":"atm_...","instruction":"bounded correction","max_additional_attempts":1}` | `TaskRecordV1` |

`campaign.stop` remains the non-delegable Plan 01 operator command. Plan 04
does not create a competing stop path.

Independent verdict submission is intentionally absent from the external
command map. The evaluator registers a strict verdict artifact through its
task-scoped evidence tool; composition of Plan 01's truthful
`runtime.session_exited` handler invokes the internal Plan 04 finalizer with the
recorded evaluator attempt ID. Neither React nor a model can claim evaluator
identity in a verdict command.

### M4 acceptance gate

- [ ] Candidate stages follow the frozen
  `ADMISSION → RESEARCH → EVALUATION → SHADOW → PAPER → LIVE_APPROVAL_REQUIRED`
  graph, with `ARCHIVED` terminal from any non-archived stage.
- [ ] Every forward gate requires immutable evidence, a complete hash-valid
  `RunManifestV1` where applicable, deterministic checks, and a fresh
  independent verdict.
- [ ] Massive checks prove the exact file hash and use SQLite
  `mode=ro&immutable=1`; integrity, adjustment, universe, chronology,
  availability, purge/embargo, and leakage failures block without fallback.
- [ ] Candidate artifacts and manifests are content-addressed under factory app
  data, and byte-for-byte tests prove active model/config files are untouched.
- [ ] Fork, compare, and reproduce retain parent receipt, immutable manifest,
  exact changed fields, author/evaluator identities, metrics, costs, resource
  use, and field-level replay differences.
- [ ] Shadow evaluation records no broker effect.
- [ ] Every Alpaca effect rechecks the human-reviewed P2 envelope, fixed paper
  endpoint, account, time, universe, notional, positions, order count, data
  freshness, reconciliation, global stop, and kill conditions. Ambiguity
  disables further effects and is never retried automatically.
- [ ] Analytics are computed only from authoritative receipts and host/controller
  measurements and export deterministic local CSV under factory app data.
- [ ] Research, Factory Overview, and integrated read-only Review render from
  typed snapshots/commands; the panel cannot edit, stage, resolve, push, or
  publish source.
- [ ] `LIVE_APPROVAL_REQUIRED` creates an actionable human gate and exposes no
  live-effect or active-model replacement command.
- [ ] Focused Python, Rust, frontend, integration, and existing Vesper suites
  pass with no protected-path diff.

Plan 05 may consume Plan 04's verified attempt, verdict, lineage, and runtime
records as episode inputs. Plan 04 does not create, canary, activate, revert, or
promote a lesson. Plan 06 consumes the completed M4 gate for failure injection,
packaging, Windows smoke, and soak verification.

## Frozen Plan 04 Data Contracts

### `RunManifestV1`

Version 1 is strict: every key below is required, no extra top-level key is
accepted, JSON numbers must be finite, symbols are sorted and unique, hashes
use lowercase `sha256:` plus 64 hexadecimal characters, and all date/time
ordering is validated before canonicalization.

```json
{
  "schema_version": 1,
  "dataset_snapshot": {
    "provider": "massive",
    "path": "D:\\vesper\\vesper_data\\massive\\sp500\\sp500_ohlcv.sqlite",
    "sqlite_schema": "sp500_ohlcv_v1",
    "table": "sp500_ohlcv",
    "snapshot_id": "massive-sp500-20260721",
    "received_at": "2026-07-22T22:42:38Z",
    "revision": "massive-20260721"
  },
  "dataset_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "universe": {
    "asset_class": "US_EQUITIES_ETFS",
    "membership_mode": "SINGLE_ASSET",
    "symbols": ["SPY"],
    "membership_evidence_id": "evd_11111111-1111-4111-8111-111111111111"
  },
  "start_date": "2010-01-04",
  "end_date": "2025-12-31",
  "corporate_action_version": {
    "version": "massive-total-return-20260717",
    "price_basis": "TOTAL_RETURN_ADJUSTED",
    "evidence_id": "evd_22222222-2222-4222-8222-222222222222"
  },
  "feature_version": {
    "name": "spy-momentum-v1",
    "source_sha256": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "information_time": "SESSION_CLOSE"
  },
  "source_commit": "0123456789abcdef0123456789abcdef01234567",
  "dependency_lock_hash": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "random_seeds": {
    "bootstrap": 42,
    "model": 7
  },
  "transaction_costs": {
    "commission_bps": "0",
    "fees_bps": "0"
  },
  "slippage": {
    "model": "fixed_bps",
    "value_bps": "10"
  },
  "evaluation_split": {
    "train": {
      "start_date": "2010-01-04",
      "end_date": "2018-12-31"
    },
    "selection": {
      "start_date": "2019-01-09",
      "end_date": "2021-12-31"
    },
    "holdout": {
      "start_date": "2022-01-10",
      "end_date": "2025-12-31"
    },
    "label_horizon_sessions": 5,
    "purge_sessions": 5,
    "embargo_sessions": 5,
    "execution_time": "NEXT_SESSION_OPEN",
    "holdout_sealed": true
  },
  "runtime_versions": {
    "python": "3.11.9",
    "vesper": "0123456789abcdef0123456789abcdef01234567"
  },
  "compute_envelope": {
    "max_wall_seconds": 3600,
    "max_cpu_cores": 8,
    "max_memory_mb": 16384,
    "gpu_allowed": false
  }
}
```

Allowed `dataset_snapshot.sqlite_schema` values are
`sp500_ohlcv_v1` and `total_return_ohlcv_v1`. Allowed
`universe.membership_mode` values are `SINGLE_ASSET`, `POINT_IN_TIME`, and
`FIXED_VALIDATION`; `FIXED_VALIDATION` may support validation evidence but
cannot pass a broad candidate gate. Allowed price bases are
`SPLIT_ADJUSTED` and `TOTAL_RETURN_ADJUSTED`. Raw prices cannot pass feature,
backtest, or model evaluation.

### Candidate and gate records

```python
CandidateStage = Literal[
    "ADMISSION",
    "RESEARCH",
    "EVALUATION",
    "SHADOW",
    "PAPER",
    "LIVE_APPROVAL_REQUIRED",
    "ARCHIVED",
]

GateStatus = Literal["PASS", "FAIL", "MISSING", "BLOCKED"]

@dataclass(frozen=True)
class CandidateRecordV1:
    candidate_id: str
    campaign_id: str
    name: str
    stage: CandidateStage
    version: int
    contract_hash: str
    parent_candidate_id: str | None
    artifact_evidence_ids: tuple[str, ...]
    manifest_evidence_id: str | None
    created_at: str
    updated_at: str

@dataclass(frozen=True)
class GateFindingV1:
    code: str
    status: GateStatus
    message: str
    evidence_ids: tuple[str, ...]

@dataclass(frozen=True)
class GateReportV1:
    gate: str
    candidate_id: str
    attempt_id: str
    manifest_evidence_id: str
    status: GateStatus
    findings: tuple[GateFindingV1, ...]
    canonical_sha256: str
```

### P2 paper envelope and effect

Money and quantities are canonical non-negative decimal strings. `side` is
`BUY` or `SELL`; symbols are uppercase US equity/ETF symbols with no slash.

```python
@dataclass(frozen=True)
class PaperEnvelopeV1:
    schema_version: Literal[1]
    envelope_id: str
    campaign_id: str
    candidate_id: str
    paper_account_id: str
    permitted_universe: tuple[str, ...]
    max_gross_notional: str
    max_positions: int
    max_orders_per_session: int
    market_timezone: Literal["America/New_York"]
    market_open: str
    market_close: str
    expires_at: str
    max_session_loss: str
    max_market_data_age_seconds: int
    human_review_receipt_id: str
    canonical_sha256: str

@dataclass(frozen=True)
class PaperEffectCommandV1:
    candidate_id: str
    envelope_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: str
    estimated_price: str
    market_observed_at: str
    requested_at: str

@dataclass(frozen=True)
class PaperEffectResultV1:
    status: Literal["SUBMITTED", "REJECTED", "AMBIGUOUS"]
    receipt_id: str
    external_order_id: str | None
    reason_code: str
```

The only accepted production endpoint is
`https://paper-api.alpaca.markets`. No endpoint is supplied by a worker,
campaign, command payload, or protected config file.

## File Responsibility Map

### Python factory sidecar

- Create `vesper/factory/research/__init__.py`: public Plan 04 exports only.
- Create `vesper/factory/research/contracts.py`: frozen version-1 dataclasses,
  literals, command payloads, and view models.
- Create `vesper/factory/research/migration.py`: database migration `2` for
  candidate, manifest, lineage, and paper-envelope indexes.
- Create `vesper/factory/research/ports.py`: Plan 04-owned kernel, clock, hash,
  and paper-gateway ports.
- Create `vesper/factory/research/kernel_adapter.py`: sole adapter from the
  merged Plan 01–03 kernel/runtime APIs to Plan 04 ports.
- Create `vesper/factory/research/artifacts.py`: content-addressed candidate
  artifact and manifest storage under factory app data.
- Create `vesper/factory/research/manifests.py`: strict immutable
  `RunManifestV1` validation and registration.
- Create `vesper/factory/research/massive_guard.py`: exact-path, read-only
  SQLite integrity and adjustment/universe checks.
- Create `vesper/factory/research/chronology.py`: session-order,
  feature/execution-clock, split, purge/embargo, holdout, and leakage checks.
- Create `vesper/factory/research/candidates.py`: registry and fail-closed
  lifecycle gates.
- Create `vesper/factory/research/evaluation.py`: deterministic criteria,
  sealed evaluation bundle, fresh evaluator launch, and independent verdict.
- Create `vesper/factory/research/lineage.py`: fork, compare, reproduce/replay,
  and field-difference reports.
- Create `vesper/factory/research/shadow.py`: no-effect observations and gate.
- Create `vesper/factory/research/paper.py`: P2 envelope and effect-time policy.
- Create `vesper/factory/research/alpaca_paper.py`: fixed-paper Alpaca adapter;
  no live or configurable endpoint.
- Create `vesper/factory/research/analytics.py`: receipt/runtime-derived metrics
  and deterministic CSV bytes.
- Create `vesper/factory/research/review.py`: evidence/test/manifest/verdict
  review bundle and Rust-only Git scope.
- Create `vesper/factory/research/commands.py`: exact command handlers.
- Create `vesper/factory/research/snapshot.py`: additive research projection
  for `FactorySnapshotV1`.
- Modify `vesper/factory/kernel.py`: instantiate and register one research
  service bundle after the merged kernel exists.
- Modify `vesper/factory/migrations.py`: register migration `2` after
  `SCHEMA_V1` without changing migration `1`.
- Modify `vesper/factory/commands.py`: register the Plan 04 command map without
  changing the frozen HTTP envelope.
- Modify `vesper/factory/snapshot.py`: append the version-1 `research` key
  without renaming or removing frozen snapshot fields.

### Python tests

- Create `tests/factory/research/__init__.py`.
- Create `tests/factory/research/fakes.py`: in-memory kernel, deterministic
  clock, and fake paper gateway used only by tests.
- Create focused test modules matching every Python module above.
- Create `tests/factory/research/test_pipeline_integration.py`: full M4 flow.
- Modify `tests/factory/test_snapshot_contract.py`: prove the additive snapshot
  keeps every frozen Plan 01 field.
- Modify `tests/factory/test_command_contract.py`: prove command idempotency and
  stable errors for all Plan 04 mutations.

### Rust host

- Create `apps/desktop/src-tauri/src/review.rs`: validated read-only Git
  changed-file, commit, and side-by-side content inspection.
- Modify `apps/desktop/src-tauri/src/lib.rs`: register only
  `inspect_attempt_review`.

### React desktop

- Create `apps/desktop/src/features/research/types.ts`: exact wire/view types.
- Create `apps/desktop/src/features/research/api.ts`: typed command adapter.
- Create `apps/desktop/src/features/research/EvidenceLadder.tsx`.
- Create `apps/desktop/src/features/research/ExperimentComparison.tsx`.
- Create `apps/desktop/src/features/research/ResearchView.tsx`.
- Create `apps/desktop/src/features/overview/FactoryOverviewView.tsx`.
- Create `apps/desktop/src/features/overview/AnalyticsPanel.tsx`.
- Create `apps/desktop/src/features/review/ReviewPanel.tsx`.
- Create focused component tests beside those feature folders.
- Modify `apps/desktop/src/App.tsx`: add Research and Factory Overview routes
  and the review drawer through the existing Plan 02 navigation.

### Task 1: Freeze Plan 04 Contracts and Test Ports

**Files:**
- Create: `vesper/factory/research/__init__.py`
- Create: `vesper/factory/research/contracts.py`
- Create: `vesper/factory/research/migration.py`
- Create: `vesper/factory/research/ports.py`
- Create: `vesper/factory/research/kernel_adapter.py`
- Modify: `vesper/factory/migrations.py`
- Create: `tests/factory/research/__init__.py`
- Create: `tests/factory/research/fakes.py`
- Create: `tests/factory/research/test_contracts.py`
- Create: `tests/factory/research/test_migration.py`

**Interfaces:**
- Consumes: the exact Plan 01–03 operations listed in “Dependencies,
  Serialization, and Acceptance Gates.”
- Produces: database schema `2`, `CandidateRecordV1`, `GateFindingV1`, `GateReportV1`,
  `ReceiptRecordV1`, `EvidenceRecordV1`, `AttemptRecordV1`,
  `ResearchKernelPort`, `ClockPort`, `PaperGatewayPort`, and
  `SchemaContractError`.

- [ ] **Step 1: Write the failing contract and adapter tests**

```python
# tests/factory/research/test_contracts.py
from dataclasses import FrozenInstanceError

import pytest

from vesper.factory.research.contracts import CandidateRecordV1, SchemaContractError
from vesper.factory.research.kernel_adapter import KernelAdapter
from vesper.factory.research.ports import REQUIRED_KERNEL_OPERATIONS


def test_candidate_record_is_frozen():
    candidate = CandidateRecordV1(
        candidate_id="cnd_11111111-1111-4111-8111-111111111111",
        campaign_id="cmp_11111111-1111-4111-8111-111111111111",
        name="SPY momentum",
        stage="ADMISSION",
        version=1,
        contract_hash="sha256:" + "a" * 64,
        parent_candidate_id=None,
        artifact_evidence_ids=(),
        manifest_evidence_id=None,
        created_at="2026-07-24T12:00:00Z",
        updated_at="2026-07-24T12:00:00Z",
    )

    with pytest.raises(FrozenInstanceError):
        candidate.stage = "RESEARCH"


def test_kernel_adapter_fails_closed_when_a_dependency_operation_is_missing():
    incomplete_kernel = type("IncompleteKernel", (), {})()

    with pytest.raises(SchemaContractError, match="load_campaign"):
        KernelAdapter(incomplete_kernel)

    assert "seal_attempt_for_evaluation" in REQUIRED_KERNEL_OPERATIONS
    assert "apply_evaluation_verdict" in REQUIRED_KERNEL_OPERATIONS
    assert "create_followup_task" in REQUIRED_KERNEL_OPERATIONS
    assert "load_candidate" not in REQUIRED_KERNEL_OPERATIONS
```

Add a migration test that starts from a real Plan 01 schema-1 temporary
database and proves the ordered upgrade:

```python
# tests/factory/research/test_migration.py
def test_research_migration_upgrades_schema_one_to_two(factory_db_v1):
    migrate(factory_db_v1)
    with sqlite3.connect(factory_db_v1) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {"candidates", "candidate_manifests", "paper_envelopes"} <= tables
```

- [ ] **Step 2: Run the focused test and verify the red state**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-contracts-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_contracts.py \
  tests/factory/research/test_migration.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection with
`ModuleNotFoundError: No module named 'vesper.factory.research'`.

- [ ] **Step 3: Add the frozen contracts and strict adapter**

Use frozen dataclasses for every record crossing a Plan 04 boundary. The
adapter validates all dependency methods at construction and delegates without
renaming payload fields:

`migration.py` exports exactly `SCHEMA_V2`:

```python
# vesper/factory/research/migration.py
SCHEMA_V2 = """
CREATE TABLE candidates (
    candidate_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    name TEXT NOT NULL,
    stage TEXT NOT NULL CHECK(stage IN (
        'ADMISSION','RESEARCH','EVALUATION','SHADOW',
        'PAPER','LIVE_APPROVAL_REQUIRED','ARCHIVED'
    )),
    version INTEGER NOT NULL CHECK(version >= 1),
    contract_hash TEXT NOT NULL,
    parent_candidate_id TEXT REFERENCES candidates(candidate_id),
    artifact_evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    manifest_evidence_id TEXT REFERENCES evidence(evidence_id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(campaign_id, name)
);
CREATE TABLE candidate_manifests (
    candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
    manifest_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(candidate_id, evidence_id)
);
CREATE TABLE paper_envelopes (
    envelope_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
    payload_json TEXT NOT NULL,
    canonical_hash TEXT NOT NULL,
    human_review_receipt_id TEXT NOT NULL REFERENCES receipts(receipt_id),
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','EXPIRED','REVOKED','STOPPED')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_candidates_campaign_stage
    ON candidates(campaign_id, stage);
CREATE INDEX idx_candidate_manifests_attempt
    ON candidate_manifests(attempt_id);
CREATE INDEX idx_paper_envelopes_candidate_status
    ON paper_envelopes(candidate_id, status);
"""
```

Register `Migration(version=2, name="research_pipeline", sql=SCHEMA_V2)` after
Plan 01's immutable migration `1`. The runner executes `1 → 2` in order,
records the SHA-256 of `SCHEMA_V2`, and reports `2` in health/readiness only
after the migration transaction commits.

```python
# vesper/factory/research/ports.py
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Final

from .contracts import (
    AttentionItemCreateV1,
    AttentionItemRecordV1,
    AttemptRecordV1,
    CampaignRecordV1,
    CandidateCreateV1,
    CandidateRecordV1,
    CandidateTransitionCommitV1,
    EvidenceCreateV1,
    EvidenceRecordV1,
    EventCreateV1,
    EventRecordV1,
    FollowupTaskCreateV1,
    PaperAccountSnapshotV1,
    PaperEffectRequestV1,
    PaperGatewayResultV1,
    ReceiptCreateV1,
    ReceiptRecordV1,
    ResourceReservationCreateV1,
    ResourceReservationRecordV1,
    TaskRecordV1,
)

REQUIRED_KERNEL_OPERATIONS: Final[tuple[str, ...]] = (
    "load_campaign",
    "load_task",
    "load_attempt",
    "register_evidence",
    "load_evidence",
    "list_receipts",
    "append_receipt",
    "append_event",
    "create_attention_item",
    "create_followup_task",
    "reserve_resource",
    "release_resource",
    "list_events",
    "seal_attempt_for_evaluation",
    "apply_evaluation_verdict",
)


class ResearchKernelPort(ABC):
    @abstractmethod
    def load_campaign(self, campaign_id: str) -> CampaignRecordV1:
        raise NotImplementedError("ResearchKernelPort.load_campaign")

    @abstractmethod
    def load_task(self, task_id: str) -> TaskRecordV1:
        raise NotImplementedError("ResearchKernelPort.load_task")

    @abstractmethod
    def load_candidate(self, candidate_id: str) -> CandidateRecordV1:
        raise NotImplementedError("ResearchKernelPort.load_candidate")

    @abstractmethod
    def create_candidate(
        self, draft: CandidateCreateV1, idempotency_key: str
    ) -> CandidateRecordV1:
        raise NotImplementedError("ResearchKernelPort.create_candidate")

    @abstractmethod
    def load_attempt(self, attempt_id: str) -> AttemptRecordV1:
        raise NotImplementedError("ResearchKernelPort.load_attempt")

    @abstractmethod
    def create_followup_task(
        self, connection: sqlite3.Connection, draft: FollowupTaskCreateV1
    ) -> TaskRecordV1:
        raise NotImplementedError("ResearchKernelPort.create_followup_task")

    @abstractmethod
    def register_evidence(
        self, connection: sqlite3.Connection, draft: EvidenceCreateV1
    ) -> EvidenceRecordV1:
        raise NotImplementedError("ResearchKernelPort.register_evidence")

    @abstractmethod
    def load_evidence(self, evidence_id: str) -> EvidenceRecordV1:
        raise NotImplementedError("ResearchKernelPort.load_evidence")

    @abstractmethod
    def list_receipts(
        self, aggregate_type: str, aggregate_id: str
    ) -> tuple[ReceiptRecordV1, ...]:
        raise NotImplementedError("ResearchKernelPort.list_receipts")

    @abstractmethod
    def append_receipt(
        self, connection: sqlite3.Connection, draft: ReceiptCreateV1
    ) -> ReceiptRecordV1:
        raise NotImplementedError("ResearchKernelPort.append_receipt")

    @abstractmethod
    def commit_candidate_transition(
        self, draft: CandidateTransitionCommitV1, idempotency_key: str
    ) -> CandidateRecordV1:
        raise NotImplementedError("ResearchKernelPort.commit_candidate_transition")

    @abstractmethod
    def create_attention_item(
        self, connection: sqlite3.Connection, draft: AttentionItemCreateV1
    ) -> AttentionItemRecordV1:
        raise NotImplementedError("ResearchKernelPort.create_attention_item")

    @abstractmethod
    def append_event(
        self, connection: sqlite3.Connection, draft: EventCreateV1
    ) -> EventRecordV1:
        raise NotImplementedError("ResearchKernelPort.append_event")

    @abstractmethod
    def reserve_resource(
        self,
        connection: sqlite3.Connection,
        draft: ResourceReservationCreateV1,
    ) -> ResourceReservationRecordV1:
        raise NotImplementedError("ResearchKernelPort.reserve_resource")

    @abstractmethod
    def release_resource(
        self,
        connection: sqlite3.Connection,
        reservation_id: str,
        reason_receipt_id: str,
    ) -> ResourceReservationRecordV1:
        raise NotImplementedError("ResearchKernelPort.release_resource")

    @abstractmethod
    def list_events(
        self, kinds: tuple[str, ...], campaign_id: str | None
    ) -> tuple[EventRecordV1, ...]:
        raise NotImplementedError("ResearchKernelPort.list_events")

    @abstractmethod
    def seal_attempt_for_evaluation(
        self,
        connection: sqlite3.Connection,
        attempt_id: str,
        evidence_ids: tuple[str, ...],
    ) -> AttemptRecordV1:
        raise NotImplementedError("ResearchKernelPort.seal_attempt_for_evaluation")

    @abstractmethod
    def apply_evaluation_verdict(
        self,
        connection: sqlite3.Connection,
        author_attempt_id: str,
        verdict_receipt_id: str,
    ) -> TaskRecordV1:
        raise NotImplementedError("ResearchKernelPort.apply_evaluation_verdict")


class ClockPort(ABC):
    @abstractmethod
    def now(self) -> datetime:
        raise NotImplementedError("ClockPort.now")


class PaperGatewayPort(ABC):
    endpoint: str

    @abstractmethod
    def inspect_account(self, paper_account_id: str) -> PaperAccountSnapshotV1:
        raise NotImplementedError("PaperGatewayPort.inspect_account")

    @abstractmethod
    def submit_order(self, request: PaperEffectRequestV1) -> PaperGatewayResultV1:
        raise NotImplementedError("PaperGatewayPort.submit_order")
```

`contracts.py` must define every imported record as `@dataclass(frozen=True)`
with the exact fields in this plan. It must also export:

```python
class SchemaContractError(ValueError):
    """Raised when a frozen schema or dependency contract is violated."""


CandidateStage = Literal[
    "ADMISSION",
    "RESEARCH",
    "EVALUATION",
    "SHADOW",
    "PAPER",
    "LIVE_APPROVAL_REQUIRED",
    "ARCHIVED",
]

AttemptOutcome = Literal[
    "VERIFIED",
    "REJECTED",
    "FAILED",
    "BLOCKED",
    "INCONCLUSIVE",
    "INTERRUPTED",
    "AMBIGUOUS",
]
```

`KernelAdapter.__init__` must iterate `REQUIRED_KERNEL_OPERATIONS`, collect
missing or non-callable names, and raise
`SchemaContractError("Missing kernel operations: " + ", ".join(missing))`.
`KernelAdapter` owns `load_candidate`, `create_candidate`, and
`commit_candidate_transition` against the three schema-2 tables. Creation and
transition each use one Plan 01 database transaction and append their receipt
and ordered event through connection-aware journal methods in that same
transaction. The transition update is:

```sql
UPDATE candidates
SET stage = ?, version = version + 1, updated_at = ?
WHERE candidate_id = ? AND stage = ? AND version = ?
```

If the update count is not exactly one, raise `CANDIDATE_VERSION_CONFLICT` and
append nothing. Every other adapter operation delegates to the injected Plan
01 kernel. The adapter never shells out, opens a second database, or asks a
worker to mutate candidate state.

`tests/factory/research/fakes.py` implements every port in memory, records
calls in insertion order, uses RFC 3339 UTC timestamps, and never imports
`alpaca`.

- [ ] **Step 4: Run tests and compile the new modules**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-contracts-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_contracts.py \
  tests/factory/research/test_migration.py -q \
  --basetemp="$TMPROOT/pytest"
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile \
  vesper/factory/research/__init__.py \
  vesper/factory/research/contracts.py \
  vesper/factory/research/migration.py \
  vesper/factory/research/ports.py \
  vesper/factory/research/kernel_adapter.py \
  vesper/factory/migrations.py
```

Expected: the focused test file passes and every compilation command exits
zero.

- [ ] **Step 5: Commit the contract seam**

```bash
git diff --check
git add \
  vesper/factory/research/__init__.py \
  vesper/factory/research/contracts.py \
  vesper/factory/research/migration.py \
  vesper/factory/research/ports.py \
  vesper/factory/research/kernel_adapter.py \
  vesper/factory/migrations.py \
  tests/factory/research/__init__.py \
  tests/factory/research/fakes.py \
  tests/factory/research/test_contracts.py \
  tests/factory/research/test_migration.py
git commit -m "feat(factory): add research pipeline contracts"
```

### Task 2: Seal Immutable Manifests and Candidate Artifacts

**Files:**
- Create: `vesper/factory/research/artifacts.py`
- Create: `vesper/factory/research/manifests.py`
- Create: `tests/factory/research/test_artifacts.py`
- Create: `tests/factory/research/test_manifests.py`

**Interfaces:**
- Consumes: `ResearchKernelPort.register_evidence`,
  `ResearchKernelPort.load_evidence`, `%LOCALAPPDATA%\Vesper\Factory`, and an
  attempt worktree path from `AttemptRecordV1`.
- Produces:
  `ArtifactVault(factory_home: Path)`,
  `ArtifactVault.store_candidate_artifact(candidate_id, source, worktree) -> StoredArtifactV1`,
  `RunManifestValidator.validate(payload) -> ValidatedManifestV1`, and
  `ManifestRegistry.register(candidate_id, attempt_id, payload, idempotency_key) -> RegisteredManifestV1`.

- [ ] **Step 1: Write failing immutability, path, and schema tests**

```python
# tests/factory/research/test_artifacts.py
from pathlib import Path

import pytest

from vesper.factory.research.artifacts import ArtifactPathError, ArtifactVault


def test_candidate_artifact_is_content_addressed_and_cannot_touch_active_model(tmp_path):
    factory_home = tmp_path / "Factory"
    worktree = tmp_path / "worktree"
    source = worktree / "candidate.bin"
    active_model = tmp_path / "repo" / "models" / "xgb_ranker.json"
    source.parent.mkdir(parents=True)
    active_model.parent.mkdir(parents=True)
    source.write_bytes(b"candidate-v1")
    active_model.write_bytes(b"active-v1")

    stored = ArtifactVault(factory_home).store_candidate_artifact(
        "cnd_11111111-1111-4111-8111-111111111111", source, worktree
    )

    assert stored.path.read_bytes() == b"candidate-v1"
    assert stored.path.is_relative_to(factory_home / "candidates")
    assert active_model.read_bytes() == b"active-v1"
    with pytest.raises(FileExistsError):
        stored.path.write_bytes(b"replacement")


def test_candidate_artifact_rejects_source_outside_attempt_worktree(tmp_path):
    source = tmp_path / "outside.bin"
    source.write_bytes(b"outside")

    with pytest.raises(ArtifactPathError, match="attempt worktree"):
        ArtifactVault(tmp_path / "Factory").store_candidate_artifact(
            "cnd_11111111-1111-4111-8111-111111111111",
            source,
            tmp_path / "worktree",
        )
```

```python
# tests/factory/research/test_manifests.py
import copy

import pytest

from vesper.factory.research.manifests import ManifestValidationError, RunManifestValidator
from tests.factory.research.fakes import valid_manifest_payload


@pytest.mark.parametrize(
    "field",
    (
        "dataset_snapshot",
        "dataset_hash",
        "universe",
        "start_date",
        "end_date",
        "corporate_action_version",
        "feature_version",
        "source_commit",
        "dependency_lock_hash",
        "random_seeds",
        "transaction_costs",
        "slippage",
        "evaluation_split",
        "runtime_versions",
        "compute_envelope",
    ),
)
def test_manifest_requires_every_frozen_field(field):
    payload = valid_manifest_payload()
    payload.pop(field)

    with pytest.raises(ManifestValidationError, match=field):
        RunManifestValidator().validate(payload)


def test_manifest_canonical_bytes_do_not_change_when_input_is_mutated():
    payload = valid_manifest_payload()
    validated = RunManifestValidator().validate(payload)
    original = copy.deepcopy(validated.canonical_bytes)

    payload["random_seeds"]["model"] = 99

    assert validated.canonical_bytes == original
```

- [ ] **Step 2: Run the focused tests and verify the red state**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-manifests-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_artifacts.py \
  tests/factory/research/test_manifests.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection because `artifacts.py` and `manifests.py` do
not exist.

- [ ] **Step 3: Implement exclusive content-addressed storage and strict V1 validation**

Use the exact top-level manifest key set and copy bytes with exclusive create:

```python
# vesper/factory/research/artifacts.py
from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


class ArtifactPathError(ValueError):
    """Raised when an artifact cannot be stored without violating its boundary."""


@dataclass(frozen=True)
class StoredArtifactV1:
    path: Path
    sha256: str
    size_bytes: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ArtifactVault:
    def __init__(self, factory_home: Path):
        self._factory_home = factory_home.resolve()

    def store_candidate_artifact(
        self, candidate_id: str, source: Path, attempt_worktree: Path
    ) -> StoredArtifactV1:
        source = source.resolve(strict=True)
        worktree = attempt_worktree.resolve(strict=True)
        if not source.is_file() or not source.is_relative_to(worktree):
            raise ArtifactPathError("Candidate artifact must be a file inside the attempt worktree.")
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", source.name)
        digest = _sha256(source)
        destination = (
            self._factory_home
            / "candidates"
            / candidate_id
            / "artifacts"
            / "sha256"
            / digest
            / safe_name
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if _sha256(destination) != digest:
                raise ArtifactPathError("Existing candidate artifact hash mismatch.")
        else:
            with source.open("rb") as reader, destination.open("xb") as writer:
                shutil.copyfileobj(reader, writer, length=1_048_576)
            if _sha256(destination) != digest:
                destination.unlink()
                raise ArtifactPathError("Copied candidate artifact hash mismatch.")
            os.chmod(destination, 0o444)
        return StoredArtifactV1(
            path=destination,
            sha256=f"sha256:{digest}",
            size_bytes=destination.stat().st_size,
        )

    def store_manifest(self, canonical_bytes: bytes) -> StoredArtifactV1:
        digest = hashlib.sha256(canonical_bytes).hexdigest()
        destination = (
            self._factory_home / "manifests" / "sha256" / f"{digest}.json"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != canonical_bytes:
                raise ArtifactPathError("Existing manifest bytes do not match its digest.")
        else:
            with destination.open("xb") as writer:
                writer.write(canonical_bytes)
            os.chmod(destination, 0o444)
        return StoredArtifactV1(
            path=destination,
            sha256=f"sha256:{digest}",
            size_bytes=len(canonical_bytes),
        )
```

`RunManifestValidator.validate` must:

1. require `schema_version == 1`;
2. require exactly the 15 frozen roadmap fields plus `schema_version`;
3. validate every nested key and enum shown in the frozen example;
4. reject booleans where an integer is required, non-finite numbers, negative
   money/resource values, empty version strings, duplicate/unsorted symbols,
   non-Massive providers, cryptocurrency symbols, raw price bases, invalid
   hashes, invalid RFC 3339 timestamps, invalid ISO dates, and reversed ranges;
5. require `source_commit` to be 40 lowercase hexadecimal characters;
6. require `holdout_sealed is True`, positive label horizon, and
   `purge_sessions` and `embargo_sessions` at least the label horizon;
7. freeze a deep JSON copy, serialize with
   `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
   allow_nan=False).encode("utf-8")`, and return that byte string plus its
   `sha256:` digest.

`ManifestRegistry.register` writes the canonical bytes with
`ArtifactVault.store_manifest`, registers that exact path/hash as immutable
evidence with purpose `run-manifest-v1`, and appends a
`manifest.registered` receipt binding candidate, attempt, evidence, and
manifest hash. Repeating an idempotency key with identical input returns the
original evidence; conflicting input returns the kernel's
`IDEMPOTENCY_CONFLICT`.

- [ ] **Step 4: Run focused tests, compilation, and an active-artifact byte check**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-manifests-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_artifacts.py \
  tests/factory/research/test_manifests.py -q \
  --basetemp="$TMPROOT/pytest"
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile \
  vesper/factory/research/artifacts.py \
  vesper/factory/research/manifests.py
git diff --exit-code -- models config
```

Expected: both focused test files pass, both modules compile, and
`git diff --exit-code -- models config` exits zero.

- [ ] **Step 5: Commit immutable research storage**

```bash
git diff --check
git add \
  vesper/factory/research/artifacts.py \
  vesper/factory/research/manifests.py \
  tests/factory/research/test_artifacts.py \
  tests/factory/research/test_manifests.py
git commit -m "feat(factory): seal research manifests and artifacts"
```

### Task 3: Add Massive Read-Only Integrity Guards

**Files:**
- Create: `vesper/factory/research/massive_guard.py`
- Create: `tests/factory/research/test_massive_guard.py`

**Interfaces:**
- Consumes: `ValidatedManifestV1`, exact evidence hashes for universe and
  corporate actions, and campaign-approved read-only Massive roots.
- Produces:
  `MassiveGuard(allowed_roots, evidence_loader).evaluate(manifest) -> GateReportV1`
  and
  `MassiveGuard.session_dates(manifest) -> tuple[str, ...]`.
- Does not consume: `vesper.data.feed.MassiveFeed`, yfinance, protected
  settings, or a mutable SQLite connection.

- [ ] **Step 1: Write failing read-only, hash, integrity, and no-fallback tests**

```python
# tests/factory/research/test_massive_guard.py
import sqlite3

import pytest

from vesper.factory.research.massive_guard import MassiveGuard
from vesper.factory.research.manifests import RunManifestValidator
from tests.factory.research.fakes import (
    evidence_loader,
    valid_manifest_payload,
    write_total_return_massive_fixture,
)


def test_massive_guard_passes_a_hash_bound_total_return_fixture(tmp_path):
    database, database_hash = write_total_return_massive_fixture(tmp_path)
    payload = valid_manifest_payload(database=database, dataset_hash=database_hash)

    report = MassiveGuard((tmp_path,), evidence_loader()).evaluate(
        RunManifestValidator().validate(payload)
    )

    assert report.status == "PASS"
    assert {finding.code for finding in report.findings} >= {
        "DATASET_HASH_MATCH",
        "SQLITE_READ_ONLY",
        "REQUIRED_SCHEMA",
        "UNIQUE_OBSERVATIONS",
        "MONOTONIC_SESSIONS",
        "FINITE_POSITIVE_OHLC",
        "NONNEGATIVE_VOLUME",
        "ADJUSTMENT_EVIDENCE",
        "UNIVERSE_EVIDENCE",
    }


def test_massive_guard_blocks_hash_mismatch_without_trying_another_file(tmp_path):
    database, _ = write_total_return_massive_fixture(tmp_path)
    payload = valid_manifest_payload(
        database=database,
        dataset_hash="sha256:" + "f" * 64,
    )
    guard = MassiveGuard((tmp_path,), evidence_loader())

    report = guard.evaluate(RunManifestValidator().validate(payload))

    assert report.status == "FAIL"
    assert report.findings[0].code == "DATASET_HASH_MISMATCH"
    assert guard.opened_paths == (database.resolve(),)


def test_massive_guard_connection_cannot_write(tmp_path):
    database, database_hash = write_total_return_massive_fixture(tmp_path)
    guard = MassiveGuard((tmp_path,), evidence_loader())
    connection = guard.open_read_only(database, database_hash)

    with pytest.raises(sqlite3.OperationalError):
        connection.execute("CREATE TABLE forbidden_write (value TEXT)")
```

Add parameterized cases for duplicate `(ticker, session)` rows, non-monotonic
or missing sessions, null/NaN/infinite/non-positive OHLC, `high` below
`open`/`close`, `low` above `open`/`close`, negative volume, missing adapter
metadata, raw price basis, fixed broad universe, missing membership evidence,
wrong table/schema, and a path outside approved roots. Each case asserts a
stable finding code and `FAIL`.

- [ ] **Step 2: Run the guard tests and verify the red state**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-massive-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_massive_guard.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection with
`ModuleNotFoundError: No module named 'vesper.factory.research.massive_guard'`.

- [ ] **Step 3: Implement one exact-path, query-only guard**

Open only the manifest path. Percent-encode the resolved Windows path for the
SQLite URI, enable query-only mode, and never catch a failure by choosing a
different provider:

```python
# vesper/factory/research/massive_guard.py
from __future__ import annotations

import hashlib
import math
import sqlite3
from pathlib import Path
from urllib.parse import quote


class MassiveGuard:
    def __init__(self, allowed_roots, evidence_loader):
        self._allowed_roots = tuple(Path(root).resolve() for root in allowed_roots)
        self._evidence_loader = evidence_loader
        self._opened_paths: list[Path] = []

    @property
    def opened_paths(self) -> tuple[Path, ...]:
        return tuple(self._opened_paths)

    def open_read_only(self, path: Path, expected_hash: str) -> sqlite3.Connection:
        resolved = path.resolve(strict=True)
        if not any(resolved.is_relative_to(root) for root in self._allowed_roots):
            raise ValueError("MASSIVE_PATH_OUTSIDE_APPROVED_ROOT")
        self._opened_paths.append(resolved)
        if self._file_hash(resolved) != expected_hash:
            raise ValueError("DATASET_HASH_MISMATCH")
        uri = f"file:{quote(str(resolved), safe='/:')}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
        return connection

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1_048_576), b""):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"
```

`evaluate` dispatches only on the manifest's exact
`dataset_snapshot.sqlite_schema`:

- `sp500_ohlcv_v1` requires table
  `sp500_ohlcv(ticker,date,open,high,low,close,volume)`;
- `total_return_ohlcv_v1` requires
  `adapter_metadata(key,value)`,
  `ohlcv_data(ticker,timestamp,open,high,low,close,volume,timeframe)`, and
  `ohlcv_source_map(ticker,timestamp,timeframe,source_sha256)`.

For both schemas, use parameterized queries for the manifest's exact symbols
and date range. Reject missing/extra requested symbols, duplicate primary keys,
unordered or duplicate sessions per symbol, non-finite/non-positive prices,
invalid OHLC bounds, negative volume, and coverage outside the manifest range.
For the adapter schema require `price_basis` to equal the manifest's
`corporate_action_version.price_basis`, `timeframe=1day`, and a non-empty source
SHA-256 per row. For the primary raw table return
`ADJUSTMENT_EVIDENCE_MISSING`; do not infer adjustment from a log.

Load the exact `universe.membership_evidence_id` and
`corporate_action_version.evidence_id` through `evidence_loader`, verify each
evidence object's stored bytes still match its recorded hash, and reject a
`FIXED_VALIDATION` universe when more than one symbol is claimed. Sort findings
by a fixed check-order tuple before canonical hashing so repeated evaluations
produce identical report bytes.

- [ ] **Step 4: Run focused tests and compile**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-massive-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_massive_guard.py -q \
  --basetemp="$TMPROOT/pytest"
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile \
  vesper/factory/research/massive_guard.py
```

Expected: all Massive guard cases pass and compilation exits zero.

- [ ] **Step 5: Commit the read-only data gate**

```bash
git diff --check
git add \
  vesper/factory/research/massive_guard.py \
  tests/factory/research/test_massive_guard.py
git commit -m "feat(factory): guard Massive research inputs"
```

### Task 4: Enforce Chronology, Availability, Purge, Embargo, and Leakage

**Files:**
- Create: `vesper/factory/research/chronology.py`
- Create: `tests/factory/research/test_chronology.py`

**Interfaces:**
- Consumes: `ValidatedManifestV1`,
  `MassiveGuard.session_dates(manifest) -> tuple[str, ...]`, and immutable
  `holdout.accessed` receipts for the manifest evidence ID.
- Produces:
  `ChronologyGuard.evaluate(manifest, session_dates, holdout_receipts) -> GateReportV1`
  and
  `ChronologyGuard.authorize_holdout_access(manifest, purpose, prior_receipts) -> HoldoutAccessV1`.

- [ ] **Step 1: Write failing boundary and leakage tests**

```python
# tests/factory/research/test_chronology.py
from dataclasses import replace

import pytest

from vesper.factory.research.chronology import ChronologyGuard
from vesper.factory.research.manifests import RunManifestValidator
from tests.factory.research.fakes import valid_manifest_payload


SESSIONS = (
    "2018-12-28",
    "2018-12-31",
    "2019-01-02",
    "2019-01-03",
    "2019-01-04",
    "2019-01-07",
    "2019-01-08",
    "2019-01-09",
    "2021-12-30",
    "2021-12-31",
    "2022-01-03",
    "2022-01-04",
    "2022-01-05",
    "2022-01-06",
    "2022-01-07",
    "2022-01-10",
)


def test_chronology_passes_five_full_purged_and_embargoed_sessions():
    manifest = RunManifestValidator().validate(valid_manifest_payload())

    report = ChronologyGuard().evaluate(manifest, SESSIONS, ())

    assert report.status == "PASS"
    assert {finding.code for finding in report.findings} >= {
        "PARTITIONS_STRICTLY_ORDERED",
        "FEATURE_EXECUTION_CLOCK_VALID",
        "PURGE_SATISFIED",
        "EMBARGO_SATISFIED",
        "HOLDOUT_SEALED",
        "NO_HOLDOUT_REUSE",
    }


def test_chronology_blocks_a_label_window_crossing_selection():
    payload = valid_manifest_payload()
    payload["evaluation_split"]["train"]["end_date"] = "2019-01-04"
    manifest = RunManifestValidator().validate(payload)

    report = ChronologyGuard().evaluate(manifest, SESSIONS, ())

    assert report.status == "FAIL"
    assert "LABEL_WINDOW_CROSSES_BOUNDARY" in {
        finding.code for finding in report.findings
    }


def test_holdout_cannot_be_used_for_selection_or_used_twice():
    manifest = RunManifestValidator().validate(valid_manifest_payload())
    selection_receipt = type(
        "Receipt",
        (),
        {"kind": "holdout.accessed", "payload": {"purpose": "selection"}},
    )()

    report = ChronologyGuard().evaluate(manifest, SESSIONS, (selection_receipt,))

    assert report.status == "FAIL"
    assert "HOLDOUT_REUSED_FOR_SELECTION" in {
        finding.code for finding in report.findings
    }
    with pytest.raises(ValueError, match="already consumed"):
        ChronologyGuard().authorize_holdout_access(
            manifest,
            "final_evaluation",
            (
                type(
                    "Receipt",
                    (),
                    {
                        "kind": "holdout.accessed",
                        "payload": {"purpose": "final_evaluation"},
                    },
                )(),
            ),
        )
```

Add cases for overlapping date ranges, a boundary date absent from the exact
session calendar, fewer than `label_horizon_sessions` full sessions between
partitions, same-session execution, unsealed holdout, end date after the
dataset snapshot cutoff, and a prior reproduction that reports a field-level
input mismatch. Every rejection asserts its stable code.

- [ ] **Step 2: Run chronology tests and verify the red state**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-chronology-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_chronology.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection with
`ModuleNotFoundError: No module named 'vesper.factory.research.chronology'`.

- [ ] **Step 3: Implement deterministic session-index checks**

Use whole sessions, not calendar-day subtraction:

```python
# vesper/factory/research/chronology.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class HoldoutAccessV1:
    manifest_sha256: str
    purpose: Literal["final_evaluation", "reproduction"]


def _full_session_gap(
    session_index: dict[str, int], earlier_end: str, later_start: str
) -> int:
    if earlier_end not in session_index or later_start not in session_index:
        raise ValueError("SPLIT_BOUNDARY_NOT_IN_SESSION_CALENDAR")
    return session_index[later_start] - session_index[earlier_end] - 1


def _boundary_findings(manifest, session_dates):
    split = manifest.payload["evaluation_split"]
    session_index = {date: index for index, date in enumerate(session_dates)}
    required = max(
        split["label_horizon_sessions"],
        split["purge_sessions"],
        split["embargo_sessions"],
    )
    pairs = (
        ("train", "selection"),
        ("selection", "holdout"),
    )
    findings = []
    for earlier, next_partition in pairs:
        gap = _full_session_gap(
            session_index,
            split[earlier]["end_date"],
            split[next_partition]["start_date"],
        )
        if gap < required:
            findings.append(
                (
                    "LABEL_WINDOW_CROSSES_BOUNDARY",
                    f"{earlier}->{next_partition} has {gap} full sessions; {required} required.",
                )
            )
    return findings
```

`ChronologyGuard.evaluate` must append findings in this fixed order:

1. `PARTITIONS_STRICTLY_ORDERED`: every partition is inside the manifest range,
   each start is at or before its end, and
   `train.end < selection.start < selection.end < holdout.start`;
2. `BOUNDARIES_IN_SESSION_CALENDAR`: all six boundary dates are present;
3. `FEATURE_EXECUTION_CLOCK_VALID`:
   `feature_version.information_time == SESSION_CLOSE` requires
   `evaluation_split.execution_time == NEXT_SESSION_OPEN`;
4. `PURGE_SATISFIED`: the number of full intervening sessions is at least
   `purge_sessions` and the label horizon;
5. `EMBARGO_SATISFIED`: the same gap is at least `embargo_sessions`;
6. `HOLDOUT_SEALED`: the boolean is exactly `True`;
7. `NO_HOLDOUT_REUSE`: no `holdout.accessed` receipt has purpose `selection`,
   and at most one prior `final_evaluation` receipt exists;
8. `REPRODUCTION_INPUTS_MATCH`: any reproduction receipt used as gate evidence
   has an empty input-difference list.

The report is `PASS` only when every finding is `PASS`. Missing session or
receipt evidence is `MISSING`, not an inferred pass.

`authorize_holdout_access` accepts only `final_evaluation` or `reproduction`.
It rejects selection, rejects a second final evaluation, and returns an
immutable draft that the evaluation service binds into a
`holdout.accessed` receipt before reading holdout outcomes.

- [ ] **Step 4: Run focused tests and compile**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-chronology-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_chronology.py -q \
  --basetemp="$TMPROOT/pytest"
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile \
  vesper/factory/research/chronology.py
```

Expected: every chronology/leakage case passes and compilation exits zero.

- [ ] **Step 5: Commit chronology enforcement**

```bash
git diff --check
git add \
  vesper/factory/research/chronology.py \
  tests/factory/research/test_chronology.py
git commit -m "feat(factory): enforce research chronology"
```

### Task 5: Implement the Candidate Registry and Fail-Closed Lifecycle

**Files:**
- Create: `vesper/factory/research/candidates.py`
- Create: `tests/factory/research/test_candidates.py`

**Interfaces:**
- Consumes: `ResearchKernelPort`, candidate artifact evidence, validated
  manifest evidence, gate reports, authoritative receipts, campaign status and
  authority, and optimistic candidate `version`.
- Produces:
  `CandidateRegistry.register(command, idempotency_key) -> CandidateRecordV1`
  and
  `CandidateRegistry.transition(command, idempotency_key) -> CandidateRecordV1`.

- [ ] **Step 1: Write failing registry and stage-gate tests**

```python
# tests/factory/research/test_candidates.py
import pytest

from vesper.factory.research.candidates import CandidateGateError, CandidateRegistry
from vesper.factory.research.contracts import CandidateTransitionCommandV1
from tests.factory.research.fakes import FakeKernel, admitted_candidate


def test_research_to_evaluation_requires_artifact_manifest_and_both_data_gates():
    kernel = FakeKernel(candidate=admitted_candidate(stage="RESEARCH"))
    registry = CandidateRegistry(kernel)
    command = CandidateTransitionCommandV1(
        candidate_id=kernel.candidate.candidate_id,
        to_stage="EVALUATION",
        expected_version=kernel.candidate.version,
        predecessor_receipt_ids=(),
    )

    with pytest.raises(CandidateGateError) as error:
        registry.transition(command, "transition-1")

    assert error.value.code == "CANDIDATE_GATE_BLOCKED"
    assert error.value.missing == (
        "candidate artifact",
        "manifest.validated VERIFIED receipt",
        "data.integrity VERIFIED receipt",
        "data.chronology VERIFIED receipt",
        "research.completed VERIFIED receipt",
    )
    assert kernel.transition_calls == []


def test_evaluation_to_shadow_requires_a_fresh_independent_verified_verdict():
    kernel = FakeKernel(candidate=admitted_candidate(stage="EVALUATION"))
    kernel.add_receipt(
        kind="evaluation.verdict",
        outcome="VERIFIED",
        authority="author-worker",
    )

    with pytest.raises(CandidateGateError, match="independent-evaluator-v1"):
        CandidateRegistry(kernel).transition(
            CandidateTransitionCommandV1(
                candidate_id=kernel.candidate.candidate_id,
                to_stage="SHADOW",
                expected_version=kernel.candidate.version,
                predecessor_receipt_ids=tuple(
                    receipt.receipt_id for receipt in kernel.receipts
                ),
            ),
            "transition-2",
        )


def test_candidate_can_never_advance_past_live_approval_required():
    kernel = FakeKernel(
        candidate=admitted_candidate(stage="LIVE_APPROVAL_REQUIRED")
    )

    with pytest.raises(CandidateGateError) as error:
        CandidateRegistry(kernel).transition(
            CandidateTransitionCommandV1(
                candidate_id=kernel.candidate.candidate_id,
                to_stage="PAPER",
                expected_version=kernel.candidate.version,
                predecessor_receipt_ids=(),
            ),
            "transition-3",
        )

    assert error.value.code == "LIVE_APPROVAL_HARD_STOP"
```

Add tests for campaign not `ADMITTED`, stale expected version, unknown/skipped
transition, missing artifact bytes, candidate artifact path outside factory
home, failed/inconclusive/ambiguous predecessor outcomes, SHADOW-to-PAPER
without an active human-reviewed P2 envelope, PAPER-to-LIVE without independent
paper evidence, and archive from every non-archived stage.

- [ ] **Step 2: Run candidate tests and verify the red state**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-candidates-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_candidates.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection with
`ModuleNotFoundError: No module named 'vesper.factory.research.candidates'`.

- [ ] **Step 3: Implement the exact graph and receipt requirements**

```python
# vesper/factory/research/candidates.py
from __future__ import annotations

from dataclasses import dataclass


ALLOWED_NEXT: dict[str, frozenset[str]] = {
    "ADMISSION": frozenset(("RESEARCH", "ARCHIVED")),
    "RESEARCH": frozenset(("EVALUATION", "ARCHIVED")),
    "EVALUATION": frozenset(("SHADOW", "ARCHIVED")),
    "SHADOW": frozenset(("PAPER", "ARCHIVED")),
    "PAPER": frozenset(("LIVE_APPROVAL_REQUIRED", "ARCHIVED")),
    "LIVE_APPROVAL_REQUIRED": frozenset(("ARCHIVED",)),
    "ARCHIVED": frozenset(),
}

REQUIRED_GATES: dict[tuple[str, str], tuple[tuple[str, str, str | None], ...]] = {
    ("ADMISSION", "RESEARCH"): (
        ("campaign.admitted", "VERIFIED", "human-operator-v1"),
    ),
    ("RESEARCH", "EVALUATION"): (
        ("manifest.validated", "VERIFIED", "factory-controller-v1"),
        ("data.integrity", "VERIFIED", "deterministic-data-guard-v1"),
        ("data.chronology", "VERIFIED", "deterministic-data-guard-v1"),
        ("research.completed", "VERIFIED", None),
    ),
    ("EVALUATION", "SHADOW"): (
        ("evaluation.deterministic", "VERIFIED", "deterministic-evaluator-v1"),
        ("evaluation.verdict", "VERIFIED", "independent-evaluator-v1"),
    ),
    ("SHADOW", "PAPER"): (
        ("shadow.gate", "VERIFIED", "deterministic-evaluator-v1"),
        ("shadow.verdict", "VERIFIED", "independent-evaluator-v1"),
        ("paper.envelope.activated", "VERIFIED", "human-reviewed-p2-v1"),
    ),
    ("PAPER", "LIVE_APPROVAL_REQUIRED"): (
        ("paper.gate", "VERIFIED", "deterministic-evaluator-v1"),
        ("paper.verdict", "VERIFIED", "independent-evaluator-v1"),
    ),
}


@dataclass(frozen=True)
class CandidateGateError(ValueError):
    code: str
    message: str
    missing: tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.message
```

`register` must require an admitted campaign, an immutable contract hash, a
unique candidate name inside the campaign, no active-artifact path, and a
candidate ceiling of at least `RESEARCH`. It creates stage `ADMISSION` and a
`candidate.registered` receipt/event through the kernel.

`transition` must:

1. load candidate and campaign;
2. reject any destination not in `ALLOWED_NEXT[current_stage]`;
3. reject stale `expected_version`;
4. resolve the command's predecessor receipt IDs and require exact candidate,
   campaign, manifest, artifact, and input hashes;
5. require every tuple in `REQUIRED_GATES[(from_stage, to_stage)]`;
6. additionally require at least one immutable candidate artifact and one
   manifest evidence object before `EVALUATION`;
7. require evaluator worker/session IDs to differ from the author before
   `SHADOW` or `PAPER`;
8. call `commit_candidate_transition` once with `from_stage`, `to_stage`,
   `expected_version`, exact predecessor IDs, and receipt authority
   `candidate-controller-v1`;
9. when entering `LIVE_APPROVAL_REQUIRED`, include one `HIGH` attention item
   whose only allowed actions are `archive` and `request_exact_scope_approval`;
10. expose no operation from `LIVE_APPROVAL_REQUIRED` to a live or active stage.

Archiving appends a reasoned operator receipt and never deletes artifacts,
manifests, history, or evidence.

- [ ] **Step 4: Run focused tests and compile**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-candidates-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_candidates.py -q \
  --basetemp="$TMPROOT/pytest"
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile \
  vesper/factory/research/candidates.py
git diff --exit-code -- \
  models config vesper/engine.py vesper/data vesper/execution vesper/risk vesper/scheduler
```

Expected: all lifecycle cases pass, compilation exits zero, and the protected
paths have no diff.

- [ ] **Step 5: Commit the candidate lifecycle**

```bash
git diff --check
git add \
  vesper/factory/research/candidates.py \
  tests/factory/research/test_candidates.py
git commit -m "feat(factory): add candidate lifecycle gates"
```

### Task 6: Add Deterministic Evaluation and Independent Verdicts

**Files:**
- Create: `vesper/factory/research/evaluation.py`
- Create: `tests/factory/research/test_evaluation.py`

**Interfaces:**
- Consumes: frozen campaign metric criteria, `MetricReportV1`, candidate
  artifact/manifest/data/chronology hashes, authoritative author attempt
  identity, and Plan 01/03's fresh read-only reviewer dispatch.
- Produces:
  `DeterministicEvaluator.evaluate(bundle) -> DeterministicEvaluationV1`,
  `EvaluationService.request_independent_review(...) -> AttemptRecordV1`, and
  `EvaluationService.finalize_reviewer_exit(evaluator_attempt_id) -> ReceiptRecordV1`.

- [ ] **Step 1: Write failing deterministic and independence tests**

```python
# tests/factory/research/test_evaluation.py
from dataclasses import replace

import pytest

from vesper.factory.research.evaluation import (
    DeterministicEvaluator,
    EvaluationIndependenceError,
    EvaluationService,
)
from tests.factory.research.fakes import (
    FakeKernel,
    deterministic_evaluation_bundle,
)


def test_same_frozen_inputs_produce_identical_evaluation_bytes():
    bundle = deterministic_evaluation_bundle()
    evaluator = DeterministicEvaluator()

    first = evaluator.evaluate(bundle)
    second = evaluator.evaluate(bundle)

    assert first.canonical_bytes == second.canonical_bytes
    assert first.canonical_sha256 == second.canonical_sha256
    assert first.outcome == "VERIFIED"


@pytest.mark.parametrize(
    ("operator", "actual", "threshold", "passes"),
    (
        (">=", "0.031", "0.030", True),
        ("<=", "0.099", "0.100", True),
        (">", "1.000", "1.000", False),
        ("<", "1.000", "1.000", False),
        ("==", "0.1000", "0.1", True),
    ),
)
def test_metric_criteria_use_exact_decimal_comparison(
    operator, actual, threshold, passes
):
    bundle = deterministic_evaluation_bundle(
        operator=operator,
        actual=actual,
        threshold=threshold,
    )

    result = DeterministicEvaluator().evaluate(bundle)

    assert (result.outcome == "VERIFIED") is passes


def test_author_session_cannot_finalize_its_own_verdict():
    kernel = FakeKernel.with_evaluation_attempts(
        author_worker_id="wrk_author",
        author_session_id="ses_author",
        evaluator_worker_id="wrk_author",
        evaluator_session_id="ses_author",
    )
    kernel.seed_evaluator_verdict_evidence("atm_author")

    with pytest.raises(EvaluationIndependenceError, match="fresh evaluator"):
        EvaluationService(kernel).finalize_reviewer_exit("atm_author")

    assert kernel.appended_receipts == []
```

Add tests rejecting an evaluator with the same worker but a different session,
the same session but a different claimed worker, a non-`Independent Evaluator`
template, inherited author conversation, a writable evaluator worktree,
different bundle/input/contract hashes, absent deterministic evidence,
missing/multiple/malformed `evaluation_verdict` evidence, non-finite metrics,
a verdict outside frozen `AttemptOutcome`, nonzero/ambiguous reviewer exit, and
a second conflicting finalization.

- [ ] **Step 2: Run evaluation tests and verify the red state**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-evaluation-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_evaluation.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection with
`ModuleNotFoundError: No module named 'vesper.factory.research.evaluation'`.

- [ ] **Step 3: Implement exact-decimal checks and a sealed review bundle**

```python
# vesper/factory/research/evaluation.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


OPERATORS = {
    ">=": lambda actual, threshold: actual >= threshold,
    "<=": lambda actual, threshold: actual <= threshold,
    ">": lambda actual, threshold: actual > threshold,
    "<": lambda actual, threshold: actual < threshold,
    "==": lambda actual, threshold: actual == threshold,
}


class EvaluationIndependenceError(ValueError):
    """Raised when evaluator identity or isolation is not independent."""


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"Invalid decimal metric: {value}") from error
    if not parsed.is_finite():
        raise ValueError(f"Non-finite metric: {value}")
    return parsed


def _canonical_bytes(value: dict) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class MetricCriterionV1:
    metric: str
    operator: str
    threshold: str


class DeterministicEvaluator:
    def evaluate(self, bundle):
        checks = []
        for criterion in sorted(bundle.criteria, key=lambda item: item.metric):
            if criterion.operator not in OPERATORS:
                raise ValueError(f"Unknown metric operator: {criterion.operator}")
            actual_text = bundle.metric_report.metrics[criterion.metric]
            passed = OPERATORS[criterion.operator](
                _decimal(actual_text),
                _decimal(criterion.threshold),
            )
            checks.append(
                {
                    "metric": criterion.metric,
                    "operator": criterion.operator,
                    "threshold": criterion.threshold,
                    "actual": actual_text,
                    "passed": passed,
                }
            )
        payload = {
            "schema_version": 1,
            "candidate_id": bundle.candidate_id,
            "attempt_id": bundle.attempt_id,
            "contract_hash": bundle.contract_hash,
            "input_hash": bundle.input_hash,
            "manifest_evidence_id": bundle.manifest_evidence_id,
            "artifact_evidence_ids": sorted(bundle.artifact_evidence_ids),
            "data_gate_receipt_ids": sorted(bundle.data_gate_receipt_ids),
            "checks": checks,
            "outcome": "VERIFIED" if all(item["passed"] for item in checks) else "REJECTED",
        }
        canonical = _canonical_bytes(payload)
        return bundle.result_type(
            outcome=payload["outcome"],
            checks=tuple(checks),
            canonical_bytes=canonical,
            canonical_sha256=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
        )
```

Before metric evaluation, require:

- manifest, artifact, input, contract, Massive-integrity, chronology, and
  holdout-access hashes to match the sealed bundle;
- every deterministic predecessor receipt outcome to be `VERIFIED`;
- criteria to be non-empty, unique by metric, and frozen in the campaign
  contract;
- metric and dispersion values to be canonical finite decimal strings;
- transaction-cost, slippage, turnover, and resource-use fields to be present.

`request_independent_review` creates one immutable `EvaluationBundleV1`,
registers its canonical bytes as evidence, then calls the Plan 01 transaction
port's `seal_attempt_for_evaluation` with that bundle and the frozen author
evidence. This moves the task to `EVALUATING`; the Plan 03 headless dispatcher
obtains a fresh `NEXT` reviewer grant whose packet references the bundle,
read-only worktree, and no author conversation. The research sidecar never
launches a CLI directly.

`finalize_reviewer_exit` loads author and evaluator identity from kernel
records rather than command claims. On truthful evaluator session exit it
loads exactly one evaluator-owned evidence object with
`purpose="evaluation_verdict"`, parses its strict version-1 JSON, and rejects
stdout prose or a command-supplied identity as verdict authority. Require
the evaluator attempt's immutable `review_of_attempt_id` to name the sealed
author attempt, different worker IDs, different session IDs, the exact
`Independent Evaluator` template, capability-proven read-only launch,
unchanged bundle hash, and an outcome in the frozen `AttemptOutcome`. Append:

```json
{
  "kind": "evaluation.verdict",
  "aggregate_type": "attempt",
  "authority": "independent-evaluator-v1",
  "outcome": "VERIFIED",
  "contract_hash": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  "input_hash": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
  "evidence_ids": ["evd_33333333-3333-4333-8333-333333333333"],
  "manifest_id": "evd_44444444-4444-4444-8444-444444444444",
  "created_at": "2026-07-24T12:00:00Z"
}
```

The evaluator service never updates candidate stage directly; the candidate
registry consumes the appended verdict through its atomic gate. In the same
transaction, the service calls Plan 01's `apply_evaluation_verdict` for the
sealed author attempt so only `VERIFIED` can move the task to `COMPLETED`; all
other outcomes block it. Process exit alone never advances task state.

- [ ] **Step 4: Run focused tests and compile**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-evaluation-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_evaluation.py -q \
  --basetemp="$TMPROOT/pytest"
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile \
  vesper/factory/research/evaluation.py
```

Expected: deterministic metric and independence tests pass, and compilation
exits zero.

- [ ] **Step 5: Commit independent evaluation**

```bash
git diff --check
git add \
  vesper/factory/research/evaluation.py \
  tests/factory/research/test_evaluation.py
git commit -m "feat(factory): add independent research evaluation"
```

### Task 7: Add Experiment Lineage, Fork, Compare, and Reproduce

**Files:**
- Create: `vesper/factory/research/lineage.py`
- Create: `tests/factory/research/test_lineage.py`

**Interfaces:**
- Consumes: an authoritative parent research receipt, immutable parent
  manifest evidence, `ForkPolicyV1`, evaluation receipts, runtime measurement
  events, and `ResearchKernelPort.create_followup_task`.
- Produces:
  `LineageService.fork(command, idempotency_key) -> ExperimentForkResultV1`,
  `LineageService.compare(left_id, right_id) -> CandidateComparisonV1`,
  `LineageService.reproduce(command, idempotency_key) -> ReproductionResultV1`,
  and `field_differences(left, right) -> tuple[FieldDifferenceV1, ...]`.

- [ ] **Step 1: Write failing lineage tests**

```python
# tests/factory/research/test_lineage.py
import pytest

from vesper.factory.research.lineage import LineageError, LineageService
from tests.factory.research.fakes import FakeKernel, fork_command, verified_parent


def test_default_fork_changes_exactly_one_allowed_manifest_field():
    kernel = FakeKernel.with_parent(verified_parent())
    original = kernel.parent_manifest_bytes

    result = LineageService(kernel).fork(
        fork_command(
            changes=(
                {
                    "json_pointer": "/random_seeds/model",
                    "before": 7,
                    "after": 11,
                },
            )
        ),
        "fork-1",
    )

    assert kernel.parent_manifest_bytes == original
    assert result.parent_candidate_id == kernel.parent_candidate.candidate_id
    assert result.changed_fields[0].json_pointer == "/random_seeds/model"
    assert result.child.stage == "RESEARCH"


def test_default_fork_rejects_two_variables():
    kernel = FakeKernel.with_parent(verified_parent())

    with pytest.raises(LineageError, match="one declared experimental variable"):
        LineageService(kernel).fork(
            fork_command(
                changes=(
                    {"json_pointer": "/random_seeds/model", "before": 7, "after": 11},
                    {"json_pointer": "/slippage/value_bps", "before": "10", "after": "12"},
                )
            ),
            "fork-2",
        )


def test_reproduce_uses_original_manifest_bytes_and_queues_a_followup_task():
    kernel = FakeKernel.with_parent(verified_parent())

    result = LineageService(kernel).reproduce(
        kernel.reproduction_command(), "reproduce-1"
    )

    assert result.task.task_id != kernel.parent_attempt.task_id
    assert result.task.state == "READY"
    assert result.task.state_details["reproduction_of_attempt_id"] == (
        kernel.parent_attempt.attempt_id
    )
    assert result.manifest_sha256 == kernel.parent_manifest_sha256
    assert kernel.manifest_write_calls == []
    assert kernel.created_attempts == []
```

Add comparison assertions for metrics, confidence/dispersion, turnover,
transaction costs, slippage, dataset/evaluation hashes, gate outcomes,
CPU/GPU/memory/disk/wall time, runtime/template, and evaluator findings.
Field differences must be sorted JSON pointers and distinguish input from
output differences.

- [ ] **Step 2: Run lineage tests and verify the red state**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-lineage-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_lineage.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection because `lineage.py` does not exist.

- [ ] **Step 3: Implement immutable JSON-pointer lineage**

```python
# vesper/factory/research/lineage.py
from dataclasses import dataclass


@dataclass(frozen=True)
class ManifestChangeV1:
    json_pointer: str
    before: object
    after: object


@dataclass(frozen=True)
class ForkPolicyV1:
    max_changed_fields: int
    allowed_json_pointers: tuple[str, ...]


def field_differences(left: object, right: object, pointer: str = ""):
    if isinstance(left, dict) and isinstance(right, dict):
        differences = []
        for key in sorted(set(left) | set(right)):
            escaped = key.replace("~", "~0").replace("/", "~1")
            child = f"{pointer}/{escaped}"
            differences.extend(
                field_differences(left.get(key), right.get(key), child)
            )
        return tuple(differences)
    if isinstance(left, list) and isinstance(right, list):
        differences = []
        for index in range(max(len(left), len(right))):
            lvalue = left[index] if index < len(left) else None
            rvalue = right[index] if index < len(right) else None
            differences.extend(
                field_differences(lvalue, rvalue, f"{pointer}/{index}")
            )
        return tuple(differences)
    if left != right:
        return (FieldDifferenceV1(pointer or "/", left, right),)
    return ()
```

`fork` verifies the parent receipt is `VERIFIED`, belongs to the parent
candidate, and binds the inherited manifest. It checks `before` against the
immutable source, applies only allow-listed pointers, enforces
`max_changed_fields` from the frozen campaign contract, revalidates the child
manifest, creates a child in `RESEARCH`, and appends `experiment.forked` with
parent receipt, inherited manifest, exact changes, reason, and hashes.

`compare` reads only authoritative reports and returns fields in stable name
order. `reproduce` passes the original manifest evidence ID and
`reproduction_of_attempt_id` into a bounded `READY` follow-up task; it does not
write manifest bytes or create an attempt itself. The Plan 01/03 `NEXT`
dispatcher creates the linked attempt. Its authoritative completion appends
`experiment.reproduced` with sorted input/output differences and fails the
reproducibility gate when deterministic outputs differ.

- [ ] **Step 4: Run focused tests and compile**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-lineage-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_lineage.py -q \
  --basetemp="$TMPROOT/pytest"
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile \
  vesper/factory/research/lineage.py
```

Expected: all lineage cases pass and compilation exits zero.

- [ ] **Step 5: Commit experiment lineage**

```bash
git diff --check
git add \
  vesper/factory/research/lineage.py \
  tests/factory/research/test_lineage.py
git commit -m "feat(factory): add experiment lineage"
```

### Task 8: Implement the No-Effect Shadow Gate

**Files:**
- Create: `vesper/factory/research/shadow.py`
- Create: `tests/factory/research/test_shadow.py`

**Interfaces:**
- Consumes: a `SHADOW` candidate, immutable signal/market hashes, host
  timestamps, `ShadowGatePolicyV1`, and frozen metric criteria.
- Produces:
  `ShadowService.record(command, idempotency_key) -> ReceiptRecordV1` and
  `ShadowService.evaluate(command, idempotency_key) -> ShadowGateResultV1`.

- [ ] **Step 1: Write failing no-effect and threshold tests**

```python
# tests/factory/research/test_shadow.py
from vesper.factory.research.shadow import ShadowService
from tests.factory.research.fakes import FakeKernel, FakePaperGateway, shadow_policy


def test_shadow_records_observations_without_broker_calls():
    kernel = FakeKernel.with_shadow_candidate()
    gateway = FakePaperGateway()
    service = ShadowService(kernel)

    receipt = service.record(kernel.shadow_observation(), "shadow-observation-1")

    assert receipt.kind == "shadow.observation"
    assert receipt.payload["no_external_effect"] is True
    assert gateway.inspect_calls == []
    assert gateway.submit_calls == []


def test_shadow_gate_requires_distinct_sessions_and_frozen_metrics():
    kernel = FakeKernel.with_shadow_candidate()
    kernel.add_shadow_observations(session_count=5, observation_count=20)

    result = ShadowService(kernel).evaluate(
        kernel.shadow_evaluate_command(policy=shadow_policy(5, 20)),
        "shadow-gate-1",
    )

    assert result.outcome == "VERIFIED"
    assert result.session_count == 5
    assert result.observation_count == 20
```

Add failures for wrong stage, duplicate signal ID, stale market hash, fewer
sessions/observations, missing cost/slippage fields, non-finite metrics,
unmatched intended/observed timestamps, and any payload containing an external
order ID or effect receipt.

- [ ] **Step 2: Run shadow tests and verify the red state**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-shadow-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_shadow.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection because `shadow.py` does not exist.

- [ ] **Step 3: Implement shadow receipts and deterministic gate output**

```python
# vesper/factory/research/shadow.py
from dataclasses import dataclass


@dataclass(frozen=True)
class ShadowObservationV1:
    candidate_id: str
    attempt_id: str
    session_date: str
    signal_id: str
    symbol: str
    intended_side: str
    intended_quantity: str
    reference_price: str
    signal_input_hash: str
    market_data_hash: str
    observed_at: str
    no_external_effect: bool = True


@dataclass(frozen=True)
class ShadowGatePolicyV1:
    minimum_sessions: int
    minimum_observations: int
    criteria: tuple[object, ...]
```

Reject `no_external_effect is not True` and reject any external order/effect
field before appending. Evaluate distinct session dates, unique signal IDs,
fresh hashes, required counts, and frozen criteria with
`DeterministicEvaluator`. Append `shadow.gate` under
`deterministic-evaluator-v1`; request a fresh independent evaluator for
`shadow.verdict`. Neither path accepts or receives a paper gateway.

- [ ] **Step 4: Run focused tests and compile**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-shadow-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_shadow.py -q \
  --basetemp="$TMPROOT/pytest"
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile \
  vesper/factory/research/shadow.py
```

Expected: all shadow cases pass and compilation exits zero.

- [ ] **Step 5: Commit the shadow gate**

```bash
git diff --check
git add \
  vesper/factory/research/shadow.py \
  tests/factory/research/test_shadow.py
git commit -m "feat(factory): add no-effect shadow gate"
```

### Task 9: Enforce the P2 Alpaca-Paper Envelope at Effect Time

**Files:**
- Create: `vesper/factory/research/paper.py`
- Create: `vesper/factory/research/alpaca_paper.py`
- Create: `tests/factory/research/test_paper.py`

**Interfaces:**
- Consumes: `PaperEnvelopeV1`, human receipt authority
  `human-reviewed-p2-v1`, candidate stage `PAPER`, factory safety state,
  `ClockPort`, `PaperGatewayPort`, and a paper-account resource reservation.
- Produces:
  `PaperService.activate_envelope(command, idempotency_key) -> PaperEnvelopeV1`
  and
  `PaperService.submit_effect(command, idempotency_key) -> PaperEffectResultV1`.

- [ ] **Step 1: Write failing effect-time and ambiguity tests using only the fake gateway**

```python
# tests/factory/research/test_paper.py
from datetime import timedelta

import pytest

from vesper.factory.research.paper import PaperPolicyError, PaperService
from tests.factory.research.fakes import FakeClock, FakeKernel, FakePaperGateway


def test_expired_envelope_is_rechecked_immediately_before_effect():
    clock = FakeClock("2026-07-24T14:00:00Z")
    kernel = FakeKernel.with_active_paper_envelope(expires_at="2026-07-24T14:01:00Z")
    gateway = FakePaperGateway()
    service = PaperService(kernel, gateway, clock)
    clock.advance(timedelta(minutes=2))

    with pytest.raises(PaperPolicyError) as error:
        service.submit_effect(kernel.paper_effect_command(), "paper-effect-1")

    assert error.value.code == "PAPER_ENVELOPE_EXPIRED"
    assert gateway.submit_calls == []


@pytest.mark.parametrize(
    "failure_code",
    (
        "FACTORY_STOPPED",
        "PAPER_ACCOUNT_MISMATCH",
        "OUTSIDE_MARKET_WINDOW",
        "SYMBOL_NOT_PERMITTED",
        "GROSS_NOTIONAL_EXCEEDED",
        "MAX_POSITIONS_EXCEEDED",
        "MAX_ORDERS_EXCEEDED",
        "SESSION_LOSS_KILL",
        "MARKET_DATA_STALE",
        "RECONCILIATION_REQUIRED",
        "PROVIDER_AMBIGUOUS",
    ),
)
def test_each_effect_time_guard_blocks_before_submit(failure_code):
    kernel, gateway, clock = FakeKernel.paper_case(failure_code)

    with pytest.raises(PaperPolicyError) as error:
        PaperService(kernel, gateway, clock).submit_effect(
            kernel.paper_effect_command(), f"paper-{failure_code}"
        )

    assert error.value.code == failure_code
    assert gateway.submit_calls == []


def test_unknown_gateway_result_is_ambiguous_and_never_retried():
    kernel = FakeKernel.with_active_paper_envelope()
    gateway = FakePaperGateway(raise_after_submit=True)
    service = PaperService(kernel, gateway, FakeClock("2026-07-24T15:00:00Z"))

    result = service.submit_effect(kernel.paper_effect_command(), "paper-effect-2")

    assert result.status == "AMBIGUOUS"
    assert len(gateway.submit_calls) == 1
    assert kernel.paper_authority_disabled is True
    assert kernel.attention_items[-1].severity == "HIGH"
```

Add tests for a non-paper endpoint, absent/failed human receipt, worker-created
envelope, envelope widening/renewal, candidate mismatch, account reservation
collision, duplicate idempotency, and assertion that no test imports or opens
the Alpaca SDK.

- [ ] **Step 2: Run paper tests and verify the red state**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-paper-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_paper.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection because `paper.py` does not exist.

- [ ] **Step 3: Implement immutable envelope activation and the last-moment guard**

```python
# vesper/factory/research/paper.py
from dataclasses import dataclass
from decimal import Decimal


ALPACA_PAPER_ENDPOINT = "https://paper-api.alpaca.markets"


@dataclass(frozen=True)
class PaperPolicyError(ValueError):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def projected_gross_notional(snapshot, command) -> Decimal:
    current = snapshot.position_market_values.get(command.symbol, Decimal("0"))
    signed_delta = Decimal(command.quantity) * Decimal(command.estimated_price)
    if command.side == "SELL":
        signed_delta = -signed_delta
    return (
        Decimal(snapshot.gross_notional)
        - abs(Decimal(current))
        + abs(Decimal(current) + signed_delta)
    )
```

`activate_envelope` requires a `VERIFIED` human receipt with authority
`human-reviewed-p2-v1`, exact campaign/candidate/account identity, sorted
universe, positive bounds, New York window, future expiry, explicit kill
conditions, and an exclusive `paper-account:<account_id>` reservation. It
stores canonical envelope bytes as evidence and appends
`paper.envelope.activated`. No update or renewal operation exists.

Immediately before every `submit_order`, `submit_effect` must reload candidate,
envelope, human receipt, global stop, reconciliation state, provider state,
resource reservation, and gateway account snapshot. Require:

- endpoint exactly `ALPACA_PAPER_ENDPOINT` and account environment `paper`;
- candidate stage `PAPER`, exact account, unexpired envelope, weekday New York
  market window, and gateway clock open;
- permitted symbol and US equity/ETF syntax;
- projected gross notional, projected position count, and session order count
  within bounds;
- session P&L above the loss kill, market data age within the envelope, no
  factory stop, no unresolved reconciliation, and no provider ambiguity.

Append a pre-effect receipt, call the gateway once, then append `SUBMITTED`,
`REJECTED`, or `AMBIGUOUS`. On unknown status/timeout, append `AMBIGUOUS`,
disable the envelope through an authoritative receipt, create `HIGH`
attention, and perform no retry.

The production adapter has no configurable endpoint:

```python
# vesper/factory/research/alpaca_paper.py
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from .paper import ALPACA_PAPER_ENDPOINT


class AlpacaPaperGateway:
    endpoint = ALPACA_PAPER_ENDPOINT

    def __init__(self, api_key: str, api_secret: str):
        self._client = TradingClient(api_key, api_secret, paper=True)

    def submit_order(self, request):
        order = self._client.submit_order(
            MarketOrderRequest(
                symbol=request.symbol,
                qty=request.quantity,
                side=OrderSide.BUY if request.side == "BUY" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
        )
        return request.result_type(
            external_order_id=str(order.id),
            status=str(order.status),
        )
```

`inspect_account` maps Alpaca account, positions, orders, and clock into
`PaperAccountSnapshotV1`; it returns no credentials and logs no secret. The
factory composition root reads the existing `ALPACA_API_KEY` and
`ALPACA_API_SECRET` environment variables without persisting them.

- [ ] **Step 4: Run focused tests, compile, and scan for a live endpoint**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-paper-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_paper.py -q \
  --basetemp="$TMPROOT/pytest"
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile \
  vesper/factory/research/paper.py \
  vesper/factory/research/alpaca_paper.py
test "$(rg -n 'https://api\.alpaca\.markets' vesper/factory/research | wc -l)" -eq 0
```

Expected: all fake-gateway tests pass, compilation exits zero, and the live
endpoint scan returns zero matches.

- [ ] **Step 5: Commit bounded paper enforcement**

```bash
git diff --check
git add \
  vesper/factory/research/paper.py \
  vesper/factory/research/alpaca_paper.py \
  tests/factory/research/test_paper.py
git commit -m "feat(factory): enforce paper effect envelope"
```

### Task 10: Derive Factory Analytics and Deterministic CSV

**Files:**
- Create: `vesper/factory/research/analytics.py`
- Create: `tests/factory/research/test_analytics.py`

**Interfaces:**
- Consumes: append-only receipts and ordered events from
  `ResearchKernelPort.list_receipts/list_events`; trusted measurement sources
  are only `rust-host-v1` and `factory-controller-v1`.
- Produces:
  `AnalyticsService.snapshot(campaign_id) -> FactoryAnalyticsV1` and
  `AnalyticsService.export_csv(command, idempotency_key) -> AnalyticsExportV1`.

- [ ] **Step 1: Write failing source-trust and CSV tests**

```python
# tests/factory/research/test_analytics.py
from vesper.factory.research.analytics import AnalyticsService
from tests.factory.research.fakes import FakeKernel


def test_analytics_ignore_worker_self_report_and_use_receipts_and_host_measurements():
    kernel = FakeKernel.with_analytics_records()
    kernel.add_runtime_measurement(source="worker-self-report", metric="wall_seconds", value="1")

    analytics = AnalyticsService(kernel, kernel.factory_home).snapshot(None)

    assert analytics.verified_completion_rate == "0.500000"
    assert analytics.rejection_rate == "0.250000"
    assert analytics.resource_totals["wall_seconds"] == "120.000000"


def test_csv_bytes_are_stable_and_written_under_factory_home():
    kernel = FakeKernel.with_analytics_records()
    service = AnalyticsService(kernel, kernel.factory_home)

    first = service.export_csv(kernel.analytics_export_command(), "csv-1")
    second = service.export_csv(kernel.analytics_export_command(), "csv-1")

    assert first.sha256 == second.sha256
    assert first.path == second.path
    assert first.path.is_relative_to(kernel.factory_home / "exports" / "analytics")
    assert first.path.read_text(encoding="utf-8").splitlines()[0] == (
        "generated_at,scope,campaign_id,metric,dimensions_json,"
        "numerator,denominator,value,unit"
    )
```

Cover completion/rejection/autonomy/intervention rates; queue, execution,
evaluation, and blocked durations; attempts/retries/interruption/ambiguity;
runtime/template performance; exposed token/context usage; CPU/GPU/memory/disk
and wall time; stage survival; data-integrity and reproducibility failures.

- [ ] **Step 2: Run analytics tests and verify the red state**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-analytics-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_analytics.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: FAIL during collection because `analytics.py` does not exist.

- [ ] **Step 3: Implement explicit denominators and stable long-form CSV**

```python
# vesper/factory/research/analytics.py
from dataclasses import dataclass


TRUSTED_MEASUREMENT_SOURCES = frozenset(
    ("rust-host-v1", "factory-controller-v1")
)
CSV_FIELDS = (
    "generated_at",
    "scope",
    "campaign_id",
    "metric",
    "dimensions_json",
    "numerator",
    "denominator",
    "value",
    "unit",
)


@dataclass(frozen=True)
class MetricRowV1:
    generated_at: str
    scope: str
    campaign_id: str
    metric: str
    dimensions_json: str
    numerator: str
    denominator: str
    value: str
    unit: str
```

Use receipt outcomes for counts and ordered controller events for state
durations. Use only trusted runtime measurements, sort dimensions and rows,
quantize decimal results to six places, and use nearest-rank p50/p95. A zero
denominator yields value `0.000000` and retains numerator/denominator.

Serialize with `csv.DictWriter(..., fieldnames=CSV_FIELDS, lineterminator="\n")`
and UTF-8. Store once with exclusive creation at
`Factory/exports/analytics/<UTC compact>-<first 12 digest chars>.csv`, register
the path/hash as evidence, and append `analytics.exported`. No telemetry or
network export exists.

- [ ] **Step 4: Run focused tests and compile**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-analytics-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_analytics.py -q \
  --basetemp="$TMPROOT/pytest"
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile \
  vesper/factory/research/analytics.py
```

Expected: analytics and byte-stable CSV tests pass; compilation exits zero.

- [ ] **Step 5: Commit analytics and export**

```bash
git diff --check
git add \
  vesper/factory/research/analytics.py \
  tests/factory/research/test_analytics.py
git commit -m "feat(factory): add receipt-derived analytics"
```

### Task 11: Wire Sidecar Commands, Snapshot Projection, and Read-Only Git Review

**Files:**
- Create: `vesper/factory/research/commands.py`
- Create: `vesper/factory/research/snapshot.py`
- Create: `vesper/factory/research/review.py`
- Create: `tests/factory/research/test_commands.py`
- Create: `tests/factory/research/test_snapshot.py`
- Create: `tests/factory/research/test_review.py`
- Modify: `vesper/factory/kernel.py`
- Modify: `vesper/factory/commands.py`
- Modify: `vesper/factory/snapshot.py`
- Modify: `tests/factory/test_snapshot_contract.py`
- Modify: `tests/factory/test_command_contract.py`
- Create: `apps/desktop/src-tauri/src/review.rs`
- Modify: `apps/desktop/src-tauri/src/lib.rs`

**Interfaces:**
- Consumes: the frozen `/v1/commands` envelope, `FactorySnapshotV1`, recorded
  attempt worktree/base/head commits, and all Plan 04 services.
- Produces: `RESEARCH_COMMAND_HANDLERS`, additive
  `FactorySnapshotV1.research`, `EvidenceReviewBundleV1`,
  `ReviewScopeV1`, and Tauri
  `inspect_attempt_review(attempt_id: String) -> GitReviewV1`.

- [ ] **Step 1: Write failing command/snapshot/review tests**

```python
# tests/factory/research/test_commands.py
from vesper.factory.research.commands import RESEARCH_COMMAND_HANDLERS


def test_all_frozen_research_commands_are_registered():
    assert set(RESEARCH_COMMAND_HANDLERS) == {
        "candidate.register",
        "manifest.register",
        "candidate.transition",
        "evaluation.run",
        "experiment.fork",
        "experiment.compare",
        "experiment.reproduce",
        "shadow.record",
        "shadow.evaluate",
        "paper.activate_envelope",
        "paper.submit_effect",
        "analytics.export_csv",
        "review.bundle",
        "review.accept_verdict",
        "review.reject_verdict",
        "review.return_with_instruction",
    }
```

```python
# tests/factory/research/test_snapshot.py
def test_research_projection_is_additive(factory_snapshot):
    projected = factory_snapshot()

    assert projected["protocol"] == 1
    assert "candidates" in projected
    assert projected["research"]["schema_version"] == 1
    assert set(projected["research"]) == {
        "schema_version",
        "candidate_details",
        "lineage_edges",
        "evidence_ladders",
        "recent_receipts",
        "analytics",
    }
```

Rust tests in `review.rs` must reject an unknown attempt, a worktree outside
the recorded factory worktree root, an invalid commit hash, a path escaping the
worktree, and any Git subcommand outside `diff`, `show`, and `log`. A passing
fixture returns changed files, side-by-side old/new text, binary markers,
commits, and `truncated`.

- [ ] **Step 2: Run Python and Rust tests and verify the red state**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-integration-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_commands.py \
  tests/factory/research/test_snapshot.py \
  tests/factory/research/test_review.py -q \
  --basetemp="$TMPROOT/pytest"
cd apps/desktop/src-tauri
cargo test review -- --nocapture
```

Expected: Python collection fails because Plan 04 integration modules do not
exist; Rust compilation fails because `review` is not registered.

- [ ] **Step 3: Register exact handlers and additive projection**

```python
# vesper/factory/research/commands.py
RESEARCH_COMMAND_HANDLERS = {
    "candidate.register": "candidate_register",
    "manifest.register": "manifest_register",
    "candidate.transition": "candidate_transition",
    "evaluation.run": "evaluation_run",
    "experiment.fork": "experiment_fork",
    "experiment.compare": "experiment_compare",
    "experiment.reproduce": "experiment_reproduce",
    "shadow.record": "shadow_record",
    "shadow.evaluate": "shadow_evaluate",
    "paper.activate_envelope": "paper_activate_envelope",
    "paper.submit_effect": "paper_submit_effect",
    "analytics.export_csv": "analytics_export_csv",
    "review.bundle": "review_bundle",
    "review.accept_verdict": "review_accept_verdict",
    "review.reject_verdict": "review_reject_verdict",
    "review.return_with_instruction": "review_return_with_instruction",
}
```

Bind each name to one typed service method in the composition root. Mutation
handlers pass the command envelope's idempotency key and expected version;
stable policy errors retain `code`, factual `message`, and structured
`details`. `experiment.compare` and `review.bundle` are read-only.

Extend the existing `runtime.session_exited` composition hook without adding a
second public command: after Plan 01 records a truthful evaluator exit, call
`EvaluationService.finalize_reviewer_exit(recorded_attempt_id)` in the same
kernel transaction. A missing or invalid verdict artifact appends a blocked
review receipt and attention item; process exit `0` is never interpreted as a
verified verdict.

The additive snapshot value is exactly:

```json
{
  "schema_version": 1,
  "candidate_details": [],
  "lineage_edges": [],
  "evidence_ladders": {},
  "recent_receipts": [],
  "analytics": {
    "verified_completion_rate": "0.000000",
    "rejection_rate": "0.000000",
    "autonomy_ratio": "0.000000",
    "resource_totals": {}
  }
}
```

`review.bundle` returns tests, compile results, manifest, evidence, and
independent verdict. `ReviewScopeV1` containing the absolute worktree remains
Rust-only.

In Rust, resolve the scope from the authenticated sidecar by attempt ID, verify
the worktree is under the recorded factory worktree root, validate both commits
as 40 lowercase hex, and invoke Git with argument arrays plus
`--no-ext-diff`, `--no-textconv`, `--no-color`, and
`--literal-pathspecs`. Do not expose write, stage, checkout, reset, merge,
rebase, push, or publish operations. Cap returned text at 2 MiB and set
`truncated=true` at the cap.

- [ ] **Step 4: Run focused Python/Rust checks and compile Python**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-integration-green-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_commands.py \
  tests/factory/research/test_snapshot.py \
  tests/factory/research/test_review.py \
  tests/factory/test_snapshot_contract.py \
  tests/factory/test_command_contract.py -q \
  --basetemp="$TMPROOT/pytest"
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m py_compile \
  vesper/factory/research/commands.py \
  vesper/factory/research/snapshot.py \
  vesper/factory/research/review.py
cd apps/desktop/src-tauri
cargo fmt --check
cargo test review
```

Expected: all focused Python tests pass, Python compilation exits zero, Rust
formatting passes, and Rust review tests pass.

- [ ] **Step 5: Commit command and review integration**

```bash
git diff --check
git add \
  vesper/factory/research/commands.py \
  vesper/factory/research/snapshot.py \
  vesper/factory/research/review.py \
  vesper/factory/kernel.py \
  vesper/factory/commands.py \
  vesper/factory/snapshot.py \
  tests/factory/research/test_commands.py \
  tests/factory/research/test_snapshot.py \
  tests/factory/research/test_review.py \
  tests/factory/test_snapshot_contract.py \
  tests/factory/test_command_contract.py \
  apps/desktop/src-tauri/src/review.rs \
  apps/desktop/src-tauri/src/lib.rs
git commit -m "feat(factory): expose research pipeline views"
```

### Task 12: Build Research, Factory Overview, Review UI, and Pass M4

**Files:**
- Create: `apps/desktop/src/features/research/types.ts`
- Create: `apps/desktop/src/features/research/api.ts`
- Create: `apps/desktop/src/features/research/EvidenceLadder.tsx`
- Create: `apps/desktop/src/features/research/ExperimentComparison.tsx`
- Create: `apps/desktop/src/features/research/ResearchView.tsx`
- Create: `apps/desktop/src/features/research/ResearchView.test.tsx`
- Create: `apps/desktop/src/features/overview/AnalyticsPanel.tsx`
- Create: `apps/desktop/src/features/overview/FactoryOverviewView.tsx`
- Create: `apps/desktop/src/features/overview/FactoryOverviewView.test.tsx`
- Create: `apps/desktop/src/features/review/ReviewPanel.tsx`
- Create: `apps/desktop/src/features/review/ReviewPanel.test.tsx`
- Modify: `apps/desktop/src/App.tsx`
- Create: `tests/factory/research/test_pipeline_integration.py`

**Interfaces:**
- Consumes: `FactoryClientV1`, additive `snapshot.research`,
  `inspect_attempt_review`, and the exact Plan 04 command kinds.
- Produces these exact props:

```typescript
export interface ResearchViewProps {
  campaign: ResearchCampaignViewV1;
  candidates: readonly ResearchCandidateViewV1[];
  selectedCandidateId: string | null;
  comparison: CandidateComparisonV1 | null;
  onSelectCandidate(candidateId: string): void;
  onFork(command: ExperimentForkCommandV1): Promise<void>;
  onCompare(leftCandidateId: string, rightCandidateId: string): Promise<void>;
  onReproduce(command: ExperimentReproduceCommandV1): Promise<void>;
  onOpenReview(attemptId: string): void;
}

export interface FactoryOverviewViewProps {
  model: FactoryOverviewV1;
  onSelectCandidate(candidateId: string): void;
  onOpenReceipt(receiptId: string): void;
  onExportCsv(campaignId: string | null): Promise<void>;
}

export interface ReviewPanelProps {
  bundle: EvidenceReviewBundleV1;
  git: GitReviewV1;
  pending: boolean;
  onAcceptVerdict(verdictReceiptId: string): Promise<void>;
  onRejectVerdict(verdictReceiptId: string, reason: string): Promise<void>;
  onReturnWithInstruction(instruction: string): Promise<void>;
  onStopCampaign(): Promise<void>;
  onClose(): void;
}
```

- [ ] **Step 1: Write failing component and full-pipeline tests**

```tsx
// apps/desktop/src/features/review/ReviewPanel.test.tsx
import { render, screen } from "@testing-library/react";
import { ReviewPanel } from "./ReviewPanel";
import { reviewProps } from "../test-fixtures";

test("review is read-only and exposes only governed decisions", () => {
  render(<ReviewPanel {...reviewProps()} />);

  expect(screen.getByText("src/example.py")).toBeInTheDocument();
  expect(screen.getByText("Independent evaluator: VERIFIED")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Accept verdict" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Return with instruction" })).toBeEnabled();
  expect(screen.queryByRole("textbox", { name: "Source editor" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /stage|push|publish/i })).not.toBeInTheDocument();
});
```

Research tests assert objective/bounds, evidence ladder, metrics/history,
lineage, workers/queue, terminal selection, and fork/compare/reproduce
callbacks. Overview tests assert the six frozen stages, receipt activity,
health, verified rate, evaluator independence, exact blocked-gate reason,
analytics, CSV export, and a hard stop at `LIVE_APPROVAL_REQUIRED`.

The Python integration test executes:

```text
register candidate → seal artifact/manifest → Massive integrity/chronology
→ RESEARCH → deterministic evaluation → independent verdict → SHADOW
→ no-effect observations/verdict → activate human P2 envelope
→ fake Alpaca paper effect/verdict → LIVE_APPROVAL_REQUIRED
→ fork/compare/reproduce → analytics CSV
```

It asserts original manifest/evidence/receipts remain byte-identical, active
model/config bytes are unchanged, the fake gateway is called only in `PAPER`,
and no live or learning command exists.

- [ ] **Step 2: Run frontend and integration tests and verify the red state**

Run:

```bash
cd apps/desktop
pnpm test --run \
  src/features/research/ResearchView.test.tsx \
  src/features/overview/FactoryOverviewView.test.tsx \
  src/features/review/ReviewPanel.test.tsx
cd ../..
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-pipeline-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest \
  tests/factory/research/test_pipeline_integration.py -q \
  --basetemp="$TMPROOT/pytest"
```

Expected: frontend tests fail because the three view modules do not exist;
Python collection fails because the M4 integration test has not been added.

- [ ] **Step 3: Implement typed views and route them through the existing shell**

`types.ts` mirrors wire field names exactly. `api.ts` maps each action to the
frozen command kind and generates a UUID idempotency key for mutations.

`ResearchView` renders one campaign objective/bounds, candidate metrics and
history, the six-item evidence ladder (`DATA`, `CHRONOLOGY`, `LEAKAGE`, `OOS`,
`SHADOW`, `PAPER`), experiment queue/current workers, comparison, and the
Plan 03 terminal for the selected attempt.

`FactoryOverviewView` renders:

```typescript
export const CANDIDATE_COLUMNS = [
  "ADMISSION",
  "RESEARCH",
  "EVALUATION",
  "SHADOW",
  "PAPER",
  "LIVE_APPROVAL_REQUIRED",
] as const;
```

It shows immutable receipts, health, measured verified rate, active workers,
author/evaluator IDs, blocked gates, exact missing evidence/approval, and
`AnalyticsPanel`. CSV export displays the returned local path and hash.
`LIVE_APPROVAL_REQUIRED` has no advance action.

`ReviewPanel` shows changed-file tree, side-by-side old/new text, binary
markers, commits, test/compile results, manifest, evidence, and independent
findings. Its only mutations are accept verdict, reject verdict, bounded
return instruction, and existing `campaign.stop`. `App.tsx` adds Research and
Factory Overview to Plan 02 navigation and opens Review as a drawer; it does
not replace Mission Control.

- [ ] **Step 4: Run M4 and repository verification**

Run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-plan04-full-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest -q \
  --basetemp="$TMPROOT/pytest"
cd apps/desktop
pnpm lint
pnpm test --run
pnpm build
cd src-tauri
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test
cd ../../..
git diff --check
git diff --exit-code -- \
  models config vesper/engine.py vesper/data vesper/execution vesper/risk vesper/scheduler
```

Expected: the existing and Plan 04 Python suites pass; frontend lint, tests,
and build pass; Rust formatting, clippy, and tests pass; diff checks pass; and
protected paths have no diff.

- [ ] **Step 5: Commit the M4 desktop and integration gate**

```bash
git add \
  apps/desktop/src/features/research/types.ts \
  apps/desktop/src/features/research/api.ts \
  apps/desktop/src/features/research/EvidenceLadder.tsx \
  apps/desktop/src/features/research/ExperimentComparison.tsx \
  apps/desktop/src/features/research/ResearchView.tsx \
  apps/desktop/src/features/research/ResearchView.test.tsx \
  apps/desktop/src/features/overview/AnalyticsPanel.tsx \
  apps/desktop/src/features/overview/FactoryOverviewView.tsx \
  apps/desktop/src/features/overview/FactoryOverviewView.test.tsx \
  apps/desktop/src/features/review/ReviewPanel.tsx \
  apps/desktop/src/features/review/ReviewPanel.test.tsx \
  apps/desktop/src/App.tsx \
  tests/factory/research/test_pipeline_integration.py
git commit -m "feat(desktop): deliver research pipeline views"
```

## M4 Completion Record

After Task 12, attach the following to the Plan 04 completion receipt:

- focused receipts from Tasks 1–12;
- full Python, frontend, Rust, build, and protected-path command results;
- one immutable successful reproduction report and one intentionally rejected
  mismatch report;
- one shadow receipt proving `no_external_effect=true`;
- one fake-gateway paper receipt proving effect-time validation and one
  ambiguity receipt proving no retry;
- the deterministic analytics CSV path/hash;
- screenshots of Research, Factory Overview, and read-only Review;
- the exact `LIVE_APPROVAL_REQUIRED` attention item.

M4 is complete only when every roadmap M4 checkbox is evidenced. Completion
does not grant Plan 05 lesson promotion, Plan 06 release authority, live
trading, active-artifact replacement, or protected-path authority.
