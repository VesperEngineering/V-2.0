from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import vesper.platform.financial_workflow as financial_workflow
from vesper.platform.contracts import (
    FinancialEventEnvelope,
    FinancialEventType,
    FinancialResearchStatus,
    FinancialTriggerDecision,
)
from vesper.platform.financial_research import LocalFinancialResearchExecutor
from vesper.platform.financial_workflow import (
    FinancialResearchController,
    build_financial_research_workflow,
)
from vesper.platform.persistence import PlatformPaths, open_persistence


NOW = datetime(2026, 7, 29, 16, 0, tzinfo=timezone.utc)
COMMON = {
    "run_id": "run-001",
    "task_id": "task-001",
    "repository_revision": "e22b1bc",
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


def market_database(root: Path, *, null_close: bool = False) -> None:
    database = root / "sp500" / "sp500_ohlcv.sqlite"
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
                (
                    "SPY",
                    "2026-07-28",
                    2.0,
                    2.0,
                    2.0,
                    None if null_close else 2.0,
                    2.0,
                ),
                ("SPY", "2026-07-29", 3.0, 3.0, 3.0, 3.0, 3.0),
            ),
        )


def financial_controller(
    tmp_path: Path,
    persistence,
    *,
    executor=None,
) -> FinancialResearchController:
    executor = executor or LocalFinancialResearchExecutor(
        massive_root=tmp_path / "massive",
        derived_root=tmp_path / "derived",
        evidence=persistence.evidence,
        clock=lambda: NOW,
    )
    graph = build_financial_research_workflow(
        checkpointer=persistence.checkpointer,
        store=persistence.langgraph_store,
        executor=executor,
    )
    return FinancialResearchController(graph=graph, store=persistence.store)


def test_direct_event_reaches_completed_report_without_software_graph(tmp_path):
    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        controller = financial_controller(tmp_path, persistence)

        report = controller.start(direct_event())

        assert report.status is FinancialResearchStatus.COMPLETED
        assert controller.inspect(report.run_id)["recommendation"]["run_id"] == report.run_id
        assert set(controller.graph.get_graph().nodes) == {
            "__start__",
            "trigger",
            "request",
            "plan",
            "execute",
            "report",
            "__end__",
        }


def test_weak_event_above_threshold_is_persisted_as_ignored(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        controller = financial_controller(tmp_path, persistence)

        report = controller.start(weak_event(observed=0.04, threshold=0.03))

        assert isinstance(report, FinancialTriggerDecision)
        assert report.status is FinancialResearchStatus.IGNORED
        assert controller.inspect(report.run_id)["status"] == "ignored"
        assert "recommendation" not in controller.inspect(report.run_id)


def test_plan_validation_failure_persists_only_a_generic_reason(tmp_path, monkeypatch):
    def reject_plan(_plan):
        raise ValueError("secret validation detail")

    monkeypatch.setattr(financial_workflow, "validate_financial_analysis_plan", reject_plan)
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        controller = financial_controller(tmp_path, persistence)

        with pytest.raises(RuntimeError, match="Financial research workflow failed"):
            controller.start(direct_event())

        record = controller.inspect("run-001")
        assert record == {
            "run_id": "run-001",
            "status": "stopped",
            "failure_reason": "Financial research workflow failed.",
        }
        assert list(
            persistence.checkpointer.list({"configurable": {"thread_id": "run-001"}})
        ) == []


def test_executor_failure_persists_no_raw_data_or_recommendation(tmp_path):
    class FailingExecutor:
        def execute(self, _event, _request, _plan):
            raise RuntimeError("secret executor detail")

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        controller = financial_controller(
            tmp_path,
            persistence,
            executor=FailingExecutor(),
        )

        with pytest.raises(RuntimeError, match="Financial research workflow failed"):
            controller.start(
                direct_event().model_copy(update={"summary": "secret raw event content"})
            )

        record = controller.inspect("run-001")
        assert record == {
            "run_id": "run-001",
            "status": "stopped",
            "failure_reason": "Financial research workflow failed.",
        }
        assert "recommendation" not in record
        assert list(
            persistence.checkpointer.list({"configurable": {"thread_id": "run-001"}})
        ) == []


def test_completed_output_remains_inspectable_after_persistence_reopens(tmp_path):
    paths = PlatformPaths.below(tmp_path / "platform")
    market_database(tmp_path / "massive")
    with open_persistence(paths) as persistence:
        report = financial_controller(tmp_path, persistence).start(direct_event())

    with open_persistence(paths) as persistence:
        record = financial_controller(tmp_path, persistence).inspect(report.run_id)

    assert record["status"] == "completed"
    assert record["request"]["run_id"] == report.run_id
    assert record["plan"]["run_id"] == report.run_id
    assert record["dataset"]["run_id"] == report.run_id
    assert record["assessment"]["run_id"] == report.run_id
    assert record["recommendation"]["run_id"] == report.run_id


def test_stopped_executor_report_is_not_promoted_to_completed(tmp_path):
    market_database(tmp_path / "massive", null_close=True)
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        controller = financial_controller(tmp_path, persistence)

        report = controller.start(direct_event())

        assert report.status is FinancialResearchStatus.STOPPED
        assert controller.inspect(report.run_id)["status"] == "stopped"
