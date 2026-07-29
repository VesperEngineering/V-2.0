import hashlib
import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import vesper.platform.financial_research as financial_research
from vesper.platform.contracts import (
    AnalysisNode,
    FinancialAnalysisPlan,
    FinancialEventEnvelope,
    FinancialEventType,
    FinancialResearchStatus,
)
from vesper.platform.evidence import FilesystemEvidenceStore
from vesper.platform.financial_research import (
    FinancialResearchError,
    LocalFinancialResearchExecutor,
    build_coverage_analysis_plan,
    build_coverage_research_request,
    decide_financial_trigger,
    validate_financial_analysis_plan,
)


NOW = datetime(2026, 7, 29, 16, 0, tzinfo=timezone.utc)
COMMON = {
    "run_id": "run-001",
    "task_id": "task-001",
    "repository_revision": "be183b2",
    "created_at": NOW,
    "event_id": "event-001",
    "non_authority": "Research only; no trading, deployment, or capital-allocation authority.",
}


def direct_event() -> FinancialEventEnvelope:
    return FinancialEventEnvelope(
        **COMMON,
        event_type=FinancialEventType.DIRECT_REQUEST,
        occurred_at=NOW - timedelta(days=2),
        observed_at=NOW,
        symbols=("SPY",),
        origin="operator",
        deduplication_key="direct-request-spy",
        payload_sha256="a" * 64,
        summary="Assess SPY coverage for a research request.",
    )


def weak_event(*, observed: float, threshold: float) -> FinancialEventEnvelope:
    return FinancialEventEnvelope(
        **COMMON,
        event_type=FinancialEventType.WEAK_MODEL_RESULT,
        occurred_at=NOW,
        observed_at=NOW,
        symbols=("SPY",),
        origin="model-evaluation",
        deduplication_key="weak-result-spy",
        payload_sha256="b" * 64,
        summary="Model result needs coverage analysis.",
        observed_metric=observed,
        threshold=threshold,
    )


def market_database(massive_root: Path, *, null_close: bool = False) -> Path:
    database = massive_root / "sp500" / "sp500_ohlcv.sqlite"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE sp500_ohlcv "
            "(ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
        )
        connection.executemany(
            "INSERT INTO sp500_ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                ("SPY", "2026-07-27", 1.0, 1.0, 1.0, 1.0, 1.0),
                ("SPY", "2026-07-28", 2.0, 2.0, 2.0, None if null_close else 2.0, 2.0),
                ("SPY", "2026-07-29", 3.0, 3.0, 3.0, 3.0, 3.0),
                ("SPY", "2026-07-30", 4.0, 4.0, 4.0, 4.0, 4.0),
                ("QQQ", "2026-07-28", 5.0, 5.0, 5.0, 5.0, 5.0),
            ),
        )
    return database


def executor(
    tmp_path: Path,
    *,
    derived_root: Path | None = None,
    evidence: object | None = None,
):
    return LocalFinancialResearchExecutor(
        massive_root=tmp_path / "massive",
        derived_root=derived_root or tmp_path / "derived",
        evidence=(
            FilesystemEvidenceStore(tmp_path / "evidence") if evidence is None else evidence
        ),
        clock=lambda: NOW,
    )


def execution_inputs():
    event = direct_event()
    request = build_coverage_research_request(event, decide_financial_trigger(event))
    return event, request, build_coverage_analysis_plan(request)


def cyclic_plan() -> FinancialAnalysisPlan:
    first = AnalysisNode(
        **COMMON,
        node_id="market-coverage-source",
        kind="source-coverage",
        depends_on=("coverage-summary",),
        output_schema=("symbol", "coverage_start", "coverage_end"),
        transform_sha256="c" * 64,
    )
    second = AnalysisNode(
        **COMMON,
        node_id="coverage-summary",
        kind="coverage-summary",
        depends_on=(first.node_id,),
        output_schema=("symbol", "coverage_days"),
        transform_sha256="d" * 64,
    )
    return FinancialAnalysisPlan(
        **COMMON,
        plan_id="plan-001",
        status=FinancialResearchStatus.PLANNED,
        nodes=(first, second),
        acceptance_checks=("coverage dates are present",),
    )


def test_direct_request_and_weak_result_below_threshold_trigger_research():
    assert decide_financial_trigger(direct_event()).should_research is True
    assert (
        decide_financial_trigger(weak_event(observed=0.01, threshold=0.03)).should_research is True
    )


def test_weak_result_at_or_above_threshold_is_ignored():
    decision = decide_financial_trigger(weak_event(observed=0.03, threshold=0.03))

    assert decision.should_research is False
    assert decision.status is FinancialResearchStatus.IGNORED


def test_coverage_request_and_plan_have_static_deterministic_order():
    event = direct_event()
    request = build_coverage_research_request(event, decide_financial_trigger(event))
    plan = build_coverage_analysis_plan(request)

    assert plan.nodes[0].node_id == "market-coverage-source"
    assert plan.nodes[1].depends_on == ("market-coverage-source",)
    assert validate_financial_analysis_plan(plan) == (
        "market-coverage-source",
        "coverage-summary",
    )


def test_plan_validator_rejects_cycles_before_execution():
    with pytest.raises(FinancialResearchError, match="cycle"):
        validate_financial_analysis_plan(cyclic_plan())


def test_plan_validator_rejects_non_static_phase_one_topology():
    event = direct_event()
    request = build_coverage_research_request(event, decide_financial_trigger(event))
    plan = build_coverage_analysis_plan(request)
    source, summary = plan.nodes
    incomplete = plan.model_copy(update={"nodes": (summary.model_copy(update={"depends_on": ()}),)})
    disconnected = plan.model_copy(
        update={"nodes": (source, summary.model_copy(update={"depends_on": ()}))}
    )

    for candidate in (incomplete, disconnected):
        with pytest.raises(FinancialResearchError, match="static"):
            validate_financial_analysis_plan(candidate)


@pytest.mark.parametrize(
    ("kind", "output_schema"),
    (
        ("unsupported-operation", ("symbol",)),
        ("source-coverage", ("symbol", "coverage_days")),
    ),
)
def test_plan_validator_rejects_unsupported_operations_and_schemas(kind, output_schema):
    node = AnalysisNode(
        **COMMON,
        node_id="market-coverage-source",
        kind=kind,
        output_schema=output_schema,
        transform_sha256="e" * 64,
    )
    plan = FinancialAnalysisPlan(
        **COMMON,
        plan_id="plan-001",
        status=FinancialResearchStatus.PLANNED,
        nodes=(node,),
        acceptance_checks=("coverage dates are present",),
    )

    with pytest.raises(FinancialResearchError):
        validate_financial_analysis_plan(plan)


def test_executor_reads_market_database_without_mutating_source(tmp_path):
    database = market_database(tmp_path / "massive")
    before = database.read_bytes()
    source_files = tuple(sorted(path.relative_to(tmp_path / "massive") for path in (tmp_path / "massive").rglob("*")))

    dataset, gap, report = executor(tmp_path).execute(*execution_inputs())

    assert database.read_bytes() == before
    assert tuple(
        sorted(path.relative_to(tmp_path / "massive") for path in (tmp_path / "massive").rglob("*"))
    ) == source_files
    assert dataset.row_count == 3
    assert dataset.ticker_count == 1
    assert dataset.coverage_start == "2026-07-27"
    assert dataset.coverage_end == "2026-07-29"
    assert gap.status is FinancialResearchStatus.COMPLETE
    assert report.non_authority.startswith("Research evidence only")


def test_executor_opens_sqlite_read_only_and_binds_request_values(tmp_path, monkeypatch):
    market_database(tmp_path / "massive")
    original_connect = financial_research.sqlite3.connect
    connect_calls = []
    aggregate_calls = []

    class RecordingConnection:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, statement, parameters=()):
            if f'FROM "{financial_research._TABLE_NAME}"' in statement:
                aggregate_calls.append((statement, parameters))
            return self.connection.execute(statement, parameters)

        def close(self):
            self.connection.close()

    def recording_connect(*args, **kwargs):
        connect_calls.append((args, kwargs))
        return RecordingConnection(original_connect(*args, **kwargs))

    monkeypatch.setattr(financial_research.sqlite3, "connect", recording_connect)

    executor(tmp_path).execute(*execution_inputs())

    assert "mode=ro" in connect_calls[0][0][0]
    assert connect_calls[0][1]["uri"] is True
    statement, parameters = aggregate_calls[0]
    assert "SPY" not in statement
    assert "2026-07-27" not in statement
    assert parameters == ("SPY", "2026-07-27", "2026-07-29")


def test_executor_rejects_derived_root_inside_repository_or_protected_data(tmp_path):
    repository = Path(__file__).resolve().parents[2]

    for derived_root in (
        repository / "derived",
        repository / "vesper" / "data" / "massive" / "derived",
        repository / "vesper" / "data" / "model_research" / "derived",
        tmp_path / "massive" / "derived",
    ):
        with pytest.raises(FinancialResearchError, match="derived root"):
            executor(tmp_path, derived_root=derived_root)


def test_executor_requires_concrete_filesystem_evidence_store(tmp_path):
    class FakeEvidenceStore:
        root = tmp_path / "evidence"

        def put_bytes(self, **_kwargs):
            raise AssertionError("unsafe evidence store must not be called")

    with pytest.raises(FinancialResearchError, match="evidence store"):
        executor(tmp_path, evidence=FakeEvidenceStore())


def test_executor_rejects_evidence_root_inside_repository_massive_or_derived(tmp_path):
    repository = Path(__file__).resolve().parents[2]
    market_database(tmp_path / "massive")
    unsafe_roots = (
        repository,
        tmp_path / "massive",
        tmp_path / "derived",
        tmp_path / "derived" / "evidence",
    )

    for evidence_root in unsafe_roots:
        store = FilesystemEvidenceStore(evidence_root)
        with pytest.raises(FinancialResearchError, match="evidence root"):
            executor(tmp_path, evidence=store)

    assert not (repository / "runs" / "run-001").exists()


def test_executor_revalidates_mutated_evidence_root_before_any_output(tmp_path):
    market_database(tmp_path / "massive")
    store = FilesystemEvidenceStore(tmp_path / "evidence")
    research = executor(tmp_path, evidence=store)
    store.root = tmp_path / "massive"

    with pytest.raises(FinancialResearchError, match="evidence root"):
        research.execute(*execution_inputs())

    assert not (tmp_path / "derived").exists()
    assert not (tmp_path / "massive" / "runs" / "run-001").exists()


@pytest.mark.parametrize("source_state", ("missing", "malformed"))
def test_executor_rejects_missing_or_malformed_market_database(tmp_path, source_state):
    if source_state == "malformed":
        database = tmp_path / "massive" / "sp500" / "sp500_ohlcv.sqlite"
        database.parent.mkdir(parents=True)
        database.write_bytes(b"not-a-sqlite-database")

    with pytest.raises(FinancialResearchError, match="market database"):
        executor(tmp_path).execute(*execution_inputs())


@pytest.mark.parametrize("invalid_date", ("1999-99-99", "not-a-date", 20260701))
def test_executor_rejects_invalid_requested_symbol_date_anywhere_in_source(
    tmp_path,
    invalid_date,
):
    database = market_database(tmp_path / "massive")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO sp500_ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("SPY", invalid_date, 1.0, 1.0, 1.0, 1.0, 1.0),
        )

    with pytest.raises(FinancialResearchError, match="invalid dates"):
        executor(tmp_path).execute(*execution_inputs())

    assert not (tmp_path / "derived").exists()


def test_executor_rejects_python_invalid_year_zero_date_for_requested_symbol(tmp_path):
    database = market_database(tmp_path / "massive")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO sp500_ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("SPY", "0000-01-01", 1.0, 1.0, 1.0, 1.0, 1.0),
        )

    with pytest.raises(FinancialResearchError, match="invalid dates"):
        executor(tmp_path).execute(*execution_inputs())

    assert not (tmp_path / "derived").exists()


def test_executor_ignores_invalid_dates_for_unrequested_symbols(tmp_path):
    database = market_database(tmp_path / "massive")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO sp500_ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("QQQ", "not-a-date", 1.0, 1.0, 1.0, 1.0, 1.0),
        )

    dataset, _, _ = executor(tmp_path).execute(*execution_inputs())

    assert dataset.row_count == 3


@pytest.mark.parametrize(
    ("start", "end"),
    (("2026-02-30", "2026-07-29"), ("2026-07-29", "2026-07-27")),
)
def test_executor_rejects_invalid_request_dates_before_writing(tmp_path, start, end):
    market_database(tmp_path / "massive")
    event, request, plan = execution_inputs()
    invalid = request.model_copy(
        update={"time_window_start": start, "time_window_end": end}
    )

    with pytest.raises(FinancialResearchError, match="date"):
        executor(tmp_path).execute(event, invalid, plan)

    assert not (tmp_path / "derived").exists()


def test_executor_rejects_symlinked_market_source(tmp_path):
    actual = tmp_path / "actual-massive"
    database = market_database(actual)
    linked = tmp_path / "massive"
    try:
        linked.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    before = database.read_bytes()

    with pytest.raises(FinancialResearchError, match="unsafe"):
        executor(tmp_path).execute(*execution_inputs())

    assert database.read_bytes() == before


@pytest.mark.parametrize("suffix", ("-wal", "-shm", "-journal"))
def test_executor_rejects_sqlite_sidecars_before_reading(tmp_path, suffix):
    database = market_database(tmp_path / "massive")
    Path(f"{database}{suffix}").write_bytes(b"sidecar")

    with pytest.raises(FinancialResearchError, match="sidecar"):
        executor(tmp_path).execute(*execution_inputs())

    assert not (tmp_path / "derived").exists()


def test_executor_rejects_source_identity_change_between_reopens(tmp_path, monkeypatch):
    market_database(tmp_path / "massive")
    original_identity = financial_research._source_identity
    calls = 0

    def changing_identity(root, path):
        nonlocal calls
        calls += 1
        identity = original_identity(root, path)
        if calls >= 3:
            return replace(identity, mtime_ns=identity.mtime_ns + 1)
        return identity

    monkeypatch.setattr(financial_research, "_source_identity", changing_identity)

    with pytest.raises(FinancialResearchError, match="changed during analysis"):
        executor(tmp_path).execute(*execution_inputs())

    assert not (tmp_path / "derived" / "run-001").exists()


def test_executor_rejects_derived_root_swap_before_child_creation(tmp_path):
    market_database(tmp_path / "massive")
    research = executor(tmp_path)
    derived = research.derived_root
    original = tmp_path / "original-derived"
    if derived.exists():
        derived.rename(original)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        derived.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    with pytest.raises(FinancialResearchError, match="derived"):
        research.execute(*execution_inputs())

    assert not (outside / "run-001").exists()


def test_executor_replay_is_byte_and_hash_stable(tmp_path):
    market_database(tmp_path / "massive")
    research = executor(tmp_path)
    first, first_gap, first_report = research.execute(*execution_inputs())
    output = research.derived_root.joinpath(*first.derived_output_path.split("/"))
    first_bytes = output.read_bytes()

    second, second_gap, second_report = research.execute(*execution_inputs())

    assert output.read_bytes() == first_bytes
    assert hashlib.sha256(first_bytes).hexdigest() == first.validation_evidence.sha256
    assert second == first
    assert second_gap == first_gap
    assert second_report == first_report
    payload = json.loads(first_bytes)
    assert set(payload) == {
        "cache_key_sha256",
        "coverage_end",
        "coverage_start",
        "dataset_id",
        "event_id",
        "lineage_ids",
        "null_close_count",
        "plan_sha256",
        "repository_revision",
        "row_count",
        "run_id",
        "source_sha256",
        "symbols",
        "task_id",
        "ticker_count",
        "time_window_end",
        "time_window_start",
        "transform_sha256",
    }


def test_executor_rejects_mismatched_existing_immutable_output(tmp_path):
    market_database(tmp_path / "massive")
    research = executor(tmp_path)
    dataset, _, _ = research.execute(*execution_inputs())
    output = research.derived_root.joinpath(*dataset.derived_output_path.split("/"))
    output.write_bytes(b"mismatched")

    with pytest.raises(FinancialResearchError, match="different content"):
        research.execute(*execution_inputs())


def test_executor_rejects_unsafe_run_id_before_creating_output_directory(tmp_path):
    market_database(tmp_path / "massive")
    event, request, plan = execution_inputs()
    event = event.model_copy(update={"run_id": "../escape"})
    request = request.model_copy(update={"run_id": "../escape"})
    plan = plan.model_copy(
        update={
            "run_id": "../escape",
            "nodes": tuple(node.model_copy(update={"run_id": "../escape"}) for node in plan.nodes),
        }
    )

    with pytest.raises(FinancialResearchError, match="run ID"):
        executor(tmp_path).execute(event, request, plan)

    assert not (tmp_path / "escape").exists()


def test_executor_translates_mismatched_evidence_copy_to_financial_error(tmp_path):
    market_database(tmp_path / "massive")
    research = executor(tmp_path)
    dataset, _, _ = research.execute(*execution_inputs())
    evidence_path = research.evidence.root / dataset.validation_evidence.relative_path
    evidence_path.write_bytes(b"mismatched")

    with pytest.raises(FinancialResearchError, match="evidence copy"):
        research.execute(*execution_inputs())


def test_null_close_count_stops_recommendation_acceptance(tmp_path):
    market_database(tmp_path / "massive", null_close=True)

    dataset, gap, report = executor(tmp_path).execute(*execution_inputs())

    assert dataset.null_close_count == 1
    assert gap.status is FinancialResearchStatus.NEEDS_ANALYSIS
    assert gap.supported_claims == ()
    assert gap.unresolved_gaps
    assert report.status is FinancialResearchStatus.STOPPED
