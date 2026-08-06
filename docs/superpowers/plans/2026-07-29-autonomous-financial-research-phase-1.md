# Autonomous Financial Research Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic sibling financial-research workflow that accepts direct requests and weak-model-result events, validates a typed acyclic analysis plan, performs one read-only local Massive coverage analysis, writes immutable derived/evidence receipts, and returns a non-authoritative report.

**Architecture:** Add Phase 1 contracts to the existing Pydantic contract module, keep deterministic planning/execution in a focused `financial_research.py` module, and compile a separate LangGraph in `financial_workflow.py`. `LocalPlatformService` and Typer expose explicit start/status commands while reusing controller-owned SQLite, evidence storage, and `PlatformPaths.root / "derived"`; the existing seven-node software-change graph remains unchanged.

**Tech Stack:** Python 3.11, Pydantic v2, LangGraph, SQLite read-only URI access, Typer, pytest, Ruff, existing `FilesystemEvidenceStore` and `SqliteStoreAdapter`.

## Global Constraints

- Phase 1 only: no parallel workers, generated code, repair loop, web retrieval, model training, candidate registry, promotion, or scheduler activation.
- Never modify or write beneath `vesper/data/massive/` or `vesper/data/model_research/`.
- The only active event types are `direct-request` and `weak-model-result`; all other event types fail closed as unsupported in Phase 1.
- Derived output defaults to `PlatformPaths.root / "derived"` and must resolve outside the repository and protected data roots.
- Reports and recommendations are research evidence only and never grant trade, order, capital, risk, deployment, scheduler, or model-promotion authority.
- Every production behavior is introduced through a red-green TDD cycle.

---

### Task 1: Phase 1 research contracts

**Files:**
- Modify: `vesper/platform/contracts.py`
- Modify: `tests/platform/test_contracts.py`

**Interfaces:**
- Produces: `FinancialEventType`, `FinancialResearchStatus`, `FinancialEventEnvelope`, `FinancialTriggerDecision`, `FinancialResearchRequest`, `AnalysisNode`, `FinancialAnalysisPlan`, `DerivedDatasetReceipt`, `FinancialGapAssessment`, and `FinancialRecommendation`.
- All records carry `run_id`, `event_id`, UTC creation time, content hashes/evidence where applicable, and explicit non-authority state.

- [ ] **Step 1: Write failing construction and validation tests**

```python
def test_phase_one_financial_contract_chain_is_typed():
    event = direct_financial_event()
    plan = coverage_analysis_plan(event)
    assert plan.nodes[1].depends_on == (plan.nodes[0].node_id,)

def test_financial_recommendation_requires_non_authority_statement():
    payload = valid_recommendation().model_dump()
    payload["non_authority"] = ""
    with pytest.raises(ValidationError):
        FinancialRecommendation.model_validate(payload)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/test_contracts.py -q`
Expected: import/collection failure because the Phase 1 contracts do not exist.

- [ ] **Step 3: Implement the minimal immutable contracts**

Use `RunContract`, `NonEmptyStr`, `Sha256`, `RelativePath`, UTC validators, tuples, and discriminating enums already present in `contracts.py`. A weak-result event requires both `observed_metric` and `threshold`; a direct request forbids them. `DerivedDatasetReceipt` requires nonempty schema, source/transform/cache hashes, coverage dates, lineage IDs, and a validation evidence reference.

- [ ] **Step 4: Run contract tests and verify GREEN**

Run: `uv run --locked python -m pytest tests/platform/test_contracts.py -q`
Expected: all contract tests pass.

- [ ] **Step 5: Commit**

```powershell
git add vesper/platform/contracts.py tests/platform/test_contracts.py
git commit -m "feat(research): define phase one financial contracts"
```

### Task 2: Deterministic intake, planner, and DAG validation

**Files:**
- Create: `vesper/platform/financial_research.py`
- Create: `tests/platform/test_financial_research.py`

**Interfaces:**
- Produces: `decide_financial_trigger(event: FinancialEventEnvelope) -> FinancialTriggerDecision`.
- Produces: `build_coverage_research_request(event, decision) -> FinancialResearchRequest`.
- Produces: `build_coverage_analysis_plan(request) -> FinancialAnalysisPlan`.
- Produces: `validate_financial_analysis_plan(plan) -> tuple[str, ...]` returning deterministic topological order or raising `FinancialResearchError`.

- [ ] **Step 1: Write failing intake and DAG tests**

```python
def test_direct_request_and_weak_result_below_threshold_trigger_research():
    assert decide_financial_trigger(direct_event()).should_research is True
    assert decide_financial_trigger(weak_event(observed=0.01, threshold=0.03)).should_research

def test_weak_result_at_or_above_threshold_is_ignored():
    assert decide_financial_trigger(weak_event(observed=0.03, threshold=0.03)).should_research is False

def test_plan_validator_rejects_cycles_before_execution():
    with pytest.raises(FinancialResearchError, match="cycle"):
        validate_financial_analysis_plan(cyclic_plan())
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/test_financial_research.py -q`
Expected: import failure because `financial_research.py` is absent.

- [ ] **Step 3: Implement the two-node Phase 1 plan**

The static plan contains `market-coverage-source` followed by `coverage-summary`. Validate unique node IDs, known dependencies, declared schemas, supported operation names, and acyclicity with a deterministic Kahn traversal. Do not introduce a general planner abstraction or model call.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `uv run --locked python -m pytest tests/platform/test_financial_research.py -q`
Expected: intake and plan-validation tests pass.

- [ ] **Step 5: Commit**

```powershell
git add vesper/platform/financial_research.py tests/platform/test_financial_research.py
git commit -m "feat(research): validate phase one analysis plans"
```

### Task 3: Read-only coverage analysis and immutable derived receipts

**Files:**
- Modify: `vesper/platform/financial_research.py`
- Modify: `tests/platform/test_financial_research.py`
- Read for pattern only: `vesper/platform/research.py`
- Read for pattern only: `vesper/platform/evidence.py`

**Interfaces:**
- Produces: `LocalFinancialResearchExecutor(massive_root, derived_root, evidence, clock)`.
- Produces: `execute(event, request, plan) -> tuple[DerivedDatasetReceipt, FinancialGapAssessment, FinancialRecommendation]`.
- Reads `massive_root / "sp500" / "sp500_ohlcv.sqlite"` using SQLite `mode=ro` and bound parameters.
- Writes immutable canonical JSON only beneath `derived_root / run_id`; evidence copies use `FilesystemEvidenceStore.put_bytes`.

- [ ] **Step 1: Write failing boundary and output tests**

```python
def test_executor_reads_market_database_without_mutating_source(tmp_path):
    database = market_database(tmp_path / "massive")
    before = database.read_bytes()
    dataset, gap, report = executor(tmp_path).execute(event(), request(), plan())
    assert database.read_bytes() == before
    assert dataset.row_count == 3
    assert report.non_authority.startswith("Research evidence only")

def test_executor_rejects_derived_root_inside_repository_or_protected_data(tmp_path):
    with pytest.raises(FinancialResearchError, match="derived root"):
        executor(tmp_path, derived_root=tmp_path / "repo" / "derived")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/test_financial_research.py -q`
Expected: executor import or attribute failure.

- [ ] **Step 3: Implement one bounded coverage query**

Query only requested symbols and inclusive dates; return row count, ticker count, start/end coverage, and null close count. No prices or raw rows enter the report. Hash the source database without loading it wholly, hash canonical plan/transform JSON, derive a cache key, atomically create the immutable derived JSON, and bind its validation artifact into `DerivedDatasetReceipt`.

- [ ] **Step 4: Add fail-closed tests for missing/malformed/linked data and replay**

Assert missing database, malformed SQLite, invalid dates, symlink/reparse-point data, duplicate mismatched writes, and nonempty null-close counts return a failed gap assessment or raise before recommendation acceptance. Replaying identical inputs must yield identical dataset bytes and hashes.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `uv run --locked python -m pytest tests/platform/test_financial_research.py tests/platform/test_evidence.py -q`
Expected: all tests pass and source bytes remain unchanged.

- [ ] **Step 6: Commit**

```powershell
git add vesper/platform/financial_research.py tests/platform/test_financial_research.py
git commit -m "feat(research): execute read-only coverage analysis"
```

### Task 4: Sibling LangGraph and persisted research state

**Files:**
- Create: `vesper/platform/financial_workflow.py`
- Create: `tests/platform/test_financial_workflow.py`
- Modify: `vesper/platform/persistence.py` only if a focused store helper is required

**Interfaces:**
- Produces: `build_financial_research_workflow(checkpointer, store, executor)`.
- Produces: `FinancialResearchController.start(event) -> FinancialRecommendation` and `inspect(run_id) -> Mapping[str, object]`.
- Graph nodes: `trigger -> request -> plan -> execute -> report`; ignored weak events end after `trigger` with persisted `ignored` status.
- Store namespace: `("financial-research", "runs")`, keyed by `run_id`.

- [ ] **Step 1: Write failing sibling-graph tests**

```python
def test_direct_event_reaches_completed_report_without_software_graph(tmp_path):
    controller = financial_controller(tmp_path)
    report = controller.start(direct_event())
    assert report.status is FinancialResearchStatus.COMPLETED
    assert controller.inspect(report.run_id)["recommendation"]["run_id"] == report.run_id

def test_weak_event_above_threshold_is_persisted_as_ignored(tmp_path):
    report = financial_controller(tmp_path).start(weak_event(observed=0.04, threshold=0.03))
    assert report.status is FinancialResearchStatus.IGNORED
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/test_financial_workflow.py -q`
Expected: import failure because the sibling workflow is absent.

- [ ] **Step 3: Implement the minimal graph and controller**

Use a separate `StateGraph`; do not modify `build_workflow`. Persist the complete accepted output only after the executor succeeds. Failed validation or execution persists a generic failure reason without raw data or secrets and never fabricates a recommendation.

- [ ] **Step 4: Run sibling and existing workflow suites**

Run: `uv run --locked python -m pytest tests/platform/test_financial_workflow.py tests/platform/test_workflow.py -q`
Expected: both sibling and seven-node workflow tests pass.

- [ ] **Step 5: Commit**

```powershell
git add vesper/platform/financial_workflow.py tests/platform/test_financial_workflow.py vesper/platform/persistence.py
git commit -m "feat(research): add sibling financial workflow"
```

### Task 5: Service and CLI entrypoints

**Files:**
- Modify: `vesper/platform/service.py`
- Modify: `vesper/platform/cli.py`
- Modify: `tests/platform/test_service.py`
- Modify: `tests/platform/test_cli.py`

**Interfaces:**
- Produces: `LocalPlatformService.start_financial_research(event_type, objective, symbols, start_date, end_date, observed_metric, threshold)`.
- Produces: `LocalPlatformService.inspect_financial_research(run_id)`.
- CLI commands: `financial-research-start` and `financial-research-status`.

- [ ] **Step 1: Write failing service and CLI tests**

```python
def test_service_runs_direct_financial_research_below_platform_root(tmp_path):
    result = service(tmp_path).start_financial_research(
        "direct-request", "Check coverage", ("AAA",), "2026-01-01", "2026-01-31", None, None
    )
    assert result["status"] == "completed"

def test_cli_exposes_only_start_and_status_for_phase_one():
    help_result = runner.invoke(build_app(service_factory=factory), ["--help"])
    assert "financial-research-start" in help_result.stdout
    assert "financial-research-promote" not in help_result.stdout
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/test_service.py tests/platform/test_cli.py -q`
Expected: missing service methods and commands.

- [ ] **Step 3: Implement service composition and CLI**

Create the event with controller-owned IDs/time, validate `derived_root = paths.root / "derived"` against repository/protected roots, open persistence per command, and run the sibling controller. CLI accepts repeatable `--symbol`, ISO `--start-date`/`--end-date`, and optional weak-result metric/threshold; invalid combinations fail before persistence.

- [ ] **Step 4: Run service, CLI, and import tests**

Run: `uv run --locked python -m pytest tests/platform/test_service.py tests/platform/test_cli.py tests/test_imports.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add vesper/platform/service.py vesper/platform/cli.py tests/platform/test_service.py tests/platform/test_cli.py
git commit -m "feat(research): expose phase one research commands"
```

### Task 6: Operator documentation and verification receipt

**Files:**
- Modify: `README.md`
- Create: `docs/runbooks/autonomous-financial-research.md`
- Create: `docs/adr/ADR-0004-autonomous-financial-research-phase-1.md`
- Create: `docs/receipts/autonomous-financial-research-phase-1-receipt.md`
- Modify: `knowledge/inbox/autonomous-financial-research-engine.md` only to record Phase 1 implementation evidence while retaining `vesper_status: candidate`

**Interfaces:**
- Documents the two Phase 1 commands, derived/evidence locations, supported events, read-only boundaries, comparison-run procedure, and August 12 review gate.

- [ ] **Step 1: Document the exact operator flow**

Include direct-request and weak-result examples using explicit controller-owned state/evidence paths. State that the implementation is shadow research only: no orders, promotion, training, web retrieval, scheduler activation, or automatic two-week schedule.

- [ ] **Step 2: Run documentation and CLI checks**

Run: `uv run --locked vesper-agent --help`
Run: `uv run --locked vesper-agent financial-research-start --help`
Run: `uv run --locked vesper-agent financial-research-status --help`
Run: `git diff --check`
Expected: commands and links are present; no whitespace errors.

- [ ] **Step 3: Run required verification**

```powershell
uv run --locked python -m pytest tests/platform/test_financial_research.py tests/platform/test_financial_workflow.py tests/platform/test_contracts.py tests/platform/test_service.py tests/platform/test_cli.py -q
uv run --locked python -m pytest tests -q
uv run --locked ruff format --check vesper tests
uv run --locked ruff check vesper scripts tests
uv run --locked python -m compileall -q vesper scripts tests
uv lock --check
git diff --check
git status --short
```

- [ ] **Step 4: Write the receipt from actual results and commit**

```powershell
git add README.md docs/adr/ADR-0004-autonomous-financial-research-phase-1.md docs/runbooks/autonomous-financial-research.md docs/receipts/autonomous-financial-research-phase-1-receipt.md knowledge/inbox/autonomous-financial-research-engine.md
git commit -m "docs(research): document phase one operations"
```

## Plan self-review

- Phase 1 spec coverage: contracts, two admitted event types, typed acyclic plan, one read-only analysis, immutable derived/evidence receipt, sibling graph, service/CLI, and report are each assigned.
- Deferred phases are explicit global exclusions.
- Existing software workflow remains untouched except shared service/CLI composition.
- Every production task starts with a named failing test and ends with focused verification and a commit.
- No placeholder steps or undefined later-phase interfaces remain.
