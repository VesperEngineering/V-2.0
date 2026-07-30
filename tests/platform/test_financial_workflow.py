from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

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
    FinancialResearchWorkflowError,
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
        requested_start_date="2026-07-27",
        requested_end_date="2026-07-29",
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
        requested_start_date="2026-07-27",
        requested_end_date="2026-07-29",
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
    executor = executor or local_executor(tmp_path, persistence)
    graph = build_financial_research_workflow(
        checkpointer=persistence.checkpointer,
        store=persistence.langgraph_store,
        executor=executor,
    )
    return FinancialResearchController(graph=graph, store=persistence.store)


def local_executor(tmp_path: Path, persistence) -> LocalFinancialResearchExecutor:
    return LocalFinancialResearchExecutor(
        massive_root=tmp_path / "massive",
        derived_root=tmp_path / "derived",
        evidence=persistence.evidence,
        clock=lambda: NOW,
    )


class CountingExecutor:
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = 0

    def execute(self, event, request, plan):
        self.calls += 1
        return self.delegate.execute(event, request, plan)


class MutatingExecutor:
    def __init__(self, delegate, mutate):
        self.delegate = delegate
        self.mutate = mutate

    def execute(self, event, request, plan):
        return self.mutate(self.delegate.execute(event, request, plan))


def terminal_record_hash(record) -> str:
    payload = {key: value for key, value in record.items() if key != "terminal_record_sha256"}
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def financial_histories(persistence):
    return (
        list(persistence.checkpointer.list({"configurable": {"thread_id": "run-001"}})),
        list(
            persistence.checkpointer.list(
                {"configurable": {"thread_id": "financial-research:run-001"}}
            )
        ),
    )


def assert_replay_rejected_without_mutation(controller, persistence, record, histories):
    with pytest.raises(FinancialResearchWorkflowError) as caught:
        controller.start(direct_event())

    assert str(caught.value) == "Financial research workflow failed."
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
    assert persistence.store.get(("financial-research", "runs"), "run-001") == record
    with pytest.raises(FinancialResearchWorkflowError):
        controller.inspect("run-001")
    assert financial_histories(persistence) == histories


def software_checkpoint(checkpointer, run_id: str):
    class SoftwareState(TypedDict):
        marker: str

    builder = StateGraph(SoftwareState)
    builder.add_node("software", lambda state: {"marker": state["marker"]})
    builder.add_edge(START, "software")
    builder.add_edge("software", END)
    graph = builder.compile(checkpointer=checkpointer)
    graph.invoke({"marker": "software-history"}, {"configurable": {"thread_id": run_id}})
    return graph


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


def test_workflow_accepts_generated_outputs_created_after_event_intake(tmp_path):
    market_database(tmp_path / "massive")
    generated_times = tuple(NOW + timedelta(minutes=offset) for offset in range(1, 5))
    clock_values = iter(generated_times)
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        executor = LocalFinancialResearchExecutor(
            massive_root=tmp_path / "massive",
            derived_root=tmp_path / "derived",
            evidence=persistence.evidence,
            clock=lambda: next(clock_values),
        )
        controller = financial_controller(tmp_path, persistence, executor=executor)

        report = controller.start(direct_event())
        record = controller.inspect("run-001")

    assert report.status is FinancialResearchStatus.COMPLETED
    assert report.created_at == generated_times[3]
    assert record["dataset"]["created_at"] == generated_times[1].isoformat().replace("+00:00", "Z")


def test_completed_status_exposes_the_hash_bound_initiating_event(tmp_path):
    event = direct_event()
    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        record = financial_controller(tmp_path, persistence).start(event)
        inspected = financial_controller(tmp_path, persistence).inspect(record.run_id)

    assert FinancialEventEnvelope.model_validate_json(json.dumps(inspected["event"])) == event
    assert set(inspected) == {
        "run_id",
        "status",
        "event",
        "event_fingerprint",
        "trigger",
        "request",
        "plan",
        "dataset",
        "assessment",
        "recommendation",
        "terminal_record_sha256",
    }


def test_weak_event_above_threshold_is_persisted_as_ignored(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        controller = financial_controller(tmp_path, persistence)

        report = controller.start(weak_event(observed=0.04, threshold=0.03))

        assert isinstance(report, FinancialTriggerDecision)
        assert report.status is FinancialResearchStatus.IGNORED
        assert controller.inspect(report.run_id)["status"] == "ignored"
        assert len(controller.inspect(report.run_id)["terminal_record_sha256"]) == 64
        assert "recommendation" not in controller.inspect(report.run_id)


def test_ignored_status_exposes_the_hash_bound_initiating_event(tmp_path):
    event = weak_event(observed=0.04, threshold=0.03)
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        controller = financial_controller(tmp_path, persistence)
        controller.start(event)

        inspected = controller.inspect(event.run_id)

    assert FinancialEventEnvelope.model_validate_json(json.dumps(inspected["event"])) == event
    assert set(inspected) == {
        "run_id",
        "status",
        "reason",
        "event",
        "event_fingerprint",
        "trigger",
        "terminal_record_sha256",
    }


@pytest.mark.parametrize(
    "corruption",
    ("hash", "shape", "chain", "authority", "status"),
)
def test_status_rejects_corrupt_accepted_terminal_records(tmp_path, corruption):
    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        controller = financial_controller(tmp_path, persistence)
        controller.start(direct_event())
        record = dict(persistence.store.get(("financial-research", "runs"), "run-001"))
        if corruption == "hash":
            record["terminal_record_sha256"] = "0" * 64
        elif corruption == "shape":
            record["private_claim"] = "must not be exposed"
        elif corruption == "chain":
            request = dict(record["request"])
            request["non_authority"] = "Grants trading authority."
            record["request"] = request
        elif corruption == "authority":
            event = dict(record.get("event", direct_event().model_dump(mode="json")))
            event["run_id"] = "foreign-run"
            record["event"] = event
        else:
            recommendation = dict(record["recommendation"])
            recommendation["status"] = FinancialResearchStatus.REQUESTED.value
            record["recommendation"] = recommendation
        if corruption != "hash":
            record["terminal_record_sha256"] = terminal_record_hash(record)
        persistence.store.put(("financial-research", "runs"), "run-001", record)

        with pytest.raises(FinancialResearchWorkflowError) as caught:
            controller.inspect("run-001")

    assert str(caught.value) == "Financial research workflow failed."
    assert "private" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_status_rejects_corrupt_ignored_terminal_record(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        controller = financial_controller(tmp_path, persistence)
        controller.start(weak_event(observed=0.04, threshold=0.03))
        record = dict(persistence.store.get(("financial-research", "runs"), "run-001"))
        trigger = dict(record["trigger"])
        trigger["triggered"] = True
        record["trigger"] = trigger
        record["terminal_record_sha256"] = terminal_record_hash(record)
        persistence.store.put(("financial-research", "runs"), "run-001", record)

        with pytest.raises(
            FinancialResearchWorkflowError, match="Financial research workflow failed"
        ):
            controller.inspect("run-001")


def test_status_validates_the_exact_generic_failure_shape(tmp_path):
    class FailingExecutor:
        def execute(self, _event, _request, _plan):
            raise RuntimeError("private executor detail")

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        controller = financial_controller(tmp_path, persistence, executor=FailingExecutor())
        with pytest.raises(FinancialResearchWorkflowError):
            controller.start(direct_event())
        valid_failure = controller.inspect("run-001")
        assert set(valid_failure) == {
            "run_id",
            "status",
            "failure_reason",
            "event_fingerprint",
        }
        corrupted = {**valid_failure, "private_claim": "must not be exposed"}
        persistence.store.put(("financial-research", "runs"), "run-001", corrupted)

        with pytest.raises(FinancialResearchWorkflowError) as caught:
            controller.inspect("run-001")

    assert str(caught.value) == "Financial research workflow failed."


def test_plan_validation_failure_persists_only_a_generic_reason(tmp_path, monkeypatch):
    def reject_plan(_plan):
        raise ValueError("secret validation detail")

    monkeypatch.setattr(financial_workflow, "validate_financial_analysis_plan", reject_plan)
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        controller = financial_controller(tmp_path, persistence)

        with pytest.raises(RuntimeError, match="Financial research workflow failed"):
            controller.start(direct_event())

        record = controller.inspect("run-001")
        assert record["run_id"] == "run-001"
        assert record["status"] == "stopped"
        assert record["failure_reason"] == "Financial research workflow failed."
        assert len(record["event_fingerprint"]) == 64
        assert set(record) == {
            "run_id",
            "status",
            "failure_reason",
            "event_fingerprint",
        }
        assert (
            list(
                persistence.checkpointer.list(
                    {"configurable": {"thread_id": "financial-research:run-001"}}
                )
            )
            == []
        )


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
        assert record["run_id"] == "run-001"
        assert record["status"] == "stopped"
        assert record["failure_reason"] == "Financial research workflow failed."
        assert len(record["event_fingerprint"]) == 64
        assert set(record) == {
            "run_id",
            "status",
            "failure_reason",
            "event_fingerprint",
        }
        assert "recommendation" not in record
        assert (
            list(
                persistence.checkpointer.list(
                    {"configurable": {"thread_id": "financial-research:run-001"}}
                )
            )
            == []
        )


@pytest.mark.parametrize(
    ("delete_fails", "put_fails"),
    ((True, False), (False, True), (True, True)),
)
def test_cleanup_failures_never_leak_private_failure_details(
    tmp_path, monkeypatch, delete_fails, put_fails
):
    class FailingExecutor:
        def execute(self, _event, _request, _plan):
            raise RuntimeError("private executor path")

    def fail_delete(_thread_id):
        raise RuntimeError("private checkpoint database path")

    def fail_put(_namespace, _key, _value):
        raise RuntimeError("private store database path")

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        controller = financial_controller(tmp_path, persistence, executor=FailingExecutor())
        if delete_fails:
            monkeypatch.setattr(controller.graph.checkpointer, "delete_thread", fail_delete)
        if put_fails:
            monkeypatch.setattr(controller.store, "put", fail_put)

        with pytest.raises(FinancialResearchWorkflowError) as caught:
            controller.start(direct_event())

        assert str(caught.value) == "Financial research workflow failed."
        assert caught.value.__cause__ is None
        assert caught.value.__suppress_context__ is True
        if not put_fails:
            assert controller.inspect("run-001")["failure_reason"] == (
                "Financial research workflow failed."
            )
        if not delete_fails:
            assert (
                list(
                    persistence.checkpointer.list(
                        {"configurable": {"thread_id": "financial-research:run-001"}}
                    )
                )
                == []
            )


def test_post_success_store_failure_is_sanitized_cleaned_and_retryable(
    tmp_path,
    monkeypatch,
):
    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        software_checkpoint(persistence.checkpointer, "run-001")
        software_history = list(
            persistence.checkpointer.list({"configurable": {"thread_id": "run-001"}})
        )
        executor = CountingExecutor(local_executor(tmp_path, persistence))
        controller = financial_controller(tmp_path, persistence, executor=executor)
        original_put = persistence.store.put
        failed = False

        def fail_terminal_once(namespace, key, value):
            nonlocal failed
            if not failed and "terminal_record_sha256" in value:
                failed = True
                raise RuntimeError("private terminal store database path")
            original_put(namespace, key, value)

        monkeypatch.setattr(persistence.store, "put", fail_terminal_once)

        with pytest.raises(FinancialResearchWorkflowError) as caught:
            controller.start(direct_event())

        assert str(caught.value) == "Financial research workflow failed."
        assert "private" not in str(caught.value)
        assert set(controller.inspect("run-001")) == {
            "run_id",
            "status",
            "failure_reason",
            "event_fingerprint",
        }
        assert (
            list(
                persistence.checkpointer.list(
                    {"configurable": {"thread_id": "financial-research:run-001"}}
                )
            )
            == []
        )
        assert (
            list(persistence.checkpointer.list({"configurable": {"thread_id": "run-001"}}))
            == software_history
        )
        monkeypatch.setattr(persistence.store, "put", original_put)

        retried = controller.start(direct_event())

        assert retried.status is FinancialResearchStatus.COMPLETED
        assert executor.calls == 2
        assert controller.inspect("run-001")["status"] == "completed"


def test_post_ignored_store_failure_is_sanitized_cleaned_and_retryable(
    tmp_path,
    monkeypatch,
):
    event = weak_event(observed=0.04, threshold=0.03)
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        controller = financial_controller(tmp_path, persistence)
        original_put = persistence.store.put
        failed = False

        def fail_terminal_once(namespace, key, value):
            nonlocal failed
            if not failed and "terminal_record_sha256" in value:
                failed = True
                raise RuntimeError("private ignored store database path")
            original_put(namespace, key, value)

        monkeypatch.setattr(persistence.store, "put", fail_terminal_once)

        with pytest.raises(FinancialResearchWorkflowError) as caught:
            controller.start(event)

        assert str(caught.value) == "Financial research workflow failed."
        assert "private" not in str(caught.value)
        assert set(controller.inspect("run-001")) == {
            "run_id",
            "status",
            "failure_reason",
            "event_fingerprint",
        }
        assert (
            list(
                persistence.checkpointer.list(
                    {"configurable": {"thread_id": "financial-research:run-001"}}
                )
            )
            == []
        )
        monkeypatch.setattr(persistence.store, "put", original_put)

        retried = controller.start(event)

        assert retried.status is FinancialResearchStatus.IGNORED
        assert controller.inspect("run-001")["status"] == "ignored"


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
        assert len(controller.inspect(report.run_id)["terminal_record_sha256"]) == 64


@pytest.mark.parametrize("output_index", (0, 1, 2))
@pytest.mark.parametrize(
    ("authority_field", "foreign_value"),
    (
        ("run_id", "foreign-run"),
        ("non_authority", "Grants trading authority."),
    ),
)
def test_foreign_executor_output_authority_fails_without_raw_persistence(
    tmp_path, output_index, authority_field, foreign_value
):
    def replace_authority(outputs):
        changed = list(outputs)
        changed[output_index] = changed[output_index].model_copy(
            update={authority_field: foreign_value}
        )
        return tuple(changed)

    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        executor = MutatingExecutor(local_executor(tmp_path, persistence), replace_authority)
        controller = financial_controller(tmp_path, persistence, executor=executor)

        with pytest.raises(RuntimeError, match="Financial research workflow failed"):
            controller.start(direct_event())

        record = controller.inspect("run-001")
        assert record["failure_reason"] == "Financial research workflow failed."
        assert "dataset" not in record
        assert "assessment" not in record
        assert "recommendation" not in record
        assert (
            list(
                persistence.checkpointer.list(
                    {"configurable": {"thread_id": "financial-research:run-001"}}
                )
            )
            == []
        )


@pytest.mark.parametrize(
    ("assessment_status", "recommendation_status"),
    (
        (FinancialResearchStatus.NEEDS_ANALYSIS, FinancialResearchStatus.COMPLETE),
        (FinancialResearchStatus.COMPLETE, FinancialResearchStatus.STOPPED),
        (FinancialResearchStatus.COMPLETE, FinancialResearchStatus.REQUESTED),
        (FinancialResearchStatus.REQUESTED, FinancialResearchStatus.STOPPED),
    ),
)
def test_incoherent_executor_terminal_states_fail_closed(
    tmp_path, assessment_status, recommendation_status
):
    def replace_statuses(outputs):
        dataset, assessment, recommendation = outputs
        return (
            dataset,
            assessment.model_copy(update={"status": assessment_status}),
            recommendation.model_copy(update={"status": recommendation_status}),
        )

    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        executor = MutatingExecutor(local_executor(tmp_path, persistence), replace_statuses)
        controller = financial_controller(tmp_path, persistence, executor=executor)

        with pytest.raises(RuntimeError, match="Financial research workflow failed"):
            controller.start(direct_event())

        record = controller.inspect("run-001")
        assert record["failure_reason"] == "Financial research workflow failed."
        assert "recommendation" not in record
        assert (
            list(
                persistence.checkpointer.list(
                    {"configurable": {"thread_id": "financial-research:run-001"}}
                )
            )
            == []
        )


def test_financial_checkpoints_are_namespaced_from_software_history(tmp_path):
    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        software_checkpoint(persistence.checkpointer, "run-001")

        financial_controller(tmp_path, persistence).start(direct_event())

        software_history = list(
            persistence.checkpointer.list({"configurable": {"thread_id": "run-001"}})
        )
        financial_history = list(
            persistence.checkpointer.list(
                {"configurable": {"thread_id": "financial-research:run-001"}}
            )
        )
        assert software_history
        assert financial_history
        assert any(
            item.checkpoint["channel_values"].get("marker") == "software-history"
            for item in software_history
        )
        assert all("event" not in item.checkpoint["channel_values"] for item in software_history)


def test_financial_failure_cleanup_preserves_software_history(tmp_path):
    class FailingExecutor:
        def execute(self, _event, _request, _plan):
            raise RuntimeError("private database path")

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        software_checkpoint(persistence.checkpointer, "run-001")
        software_history_before = list(
            persistence.checkpointer.list({"configurable": {"thread_id": "run-001"}})
        )
        controller = financial_controller(tmp_path, persistence, executor=FailingExecutor())

        with pytest.raises(RuntimeError, match="Financial research workflow failed"):
            controller.start(direct_event())

        assert (
            list(persistence.checkpointer.list({"configurable": {"thread_id": "run-001"}}))
            == software_history_before
        )
        assert (
            list(
                persistence.checkpointer.list(
                    {"configurable": {"thread_id": "financial-research:run-001"}}
                )
            )
            == []
        )


def test_identical_terminal_replay_returns_persisted_outcome_without_execution(tmp_path):
    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        executor = CountingExecutor(local_executor(tmp_path, persistence))
        controller = financial_controller(tmp_path, persistence, executor=executor)
        first = controller.start(direct_event())
        first_record = dict(controller.inspect("run-001"))
        assert len(first_record["terminal_record_sha256"]) == 64
        first_history = list(
            persistence.checkpointer.list(
                {"configurable": {"thread_id": "financial-research:run-001"}}
            )
        )

        replay = controller.start(direct_event())

        assert replay == first
        assert executor.calls == 1
        assert controller.inspect("run-001") == first_record
        assert (
            list(
                persistence.checkpointer.list(
                    {"configurable": {"thread_id": "financial-research:run-001"}}
                )
            )
            == first_history
        )


@pytest.mark.parametrize("tampered_field", ("conclusions", "evidence"))
def test_tampered_terminal_payload_is_rejected_without_replay_mutation(tmp_path, tampered_field):
    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        software_checkpoint(persistence.checkpointer, "run-001")
        executor = CountingExecutor(local_executor(tmp_path, persistence))
        controller = financial_controller(tmp_path, persistence, executor=executor)
        controller.start(direct_event())
        record = dict(controller.inspect("run-001"))
        recommendation = dict(record["recommendation"])
        if tampered_field == "conclusions":
            recommendation["conclusions"] = ["private tampered conclusion"]
        else:
            evidence = [dict(item) for item in recommendation["evidence"]]
            evidence[0]["relative_path"] = "private/tampered-evidence.json"
            recommendation["evidence"] = evidence
        record["recommendation"] = recommendation
        persistence.store.put(("financial-research", "runs"), "run-001", record)
        stored_record = dict(persistence.store.get(("financial-research", "runs"), "run-001"))
        histories = financial_histories(persistence)

        assert_replay_rejected_without_mutation(controller, persistence, stored_record, histories)

        assert executor.calls == 1


def test_malformed_stored_outcome_is_sanitized_without_replay_mutation(tmp_path):
    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        software_checkpoint(persistence.checkpointer, "run-001")
        executor = CountingExecutor(local_executor(tmp_path, persistence))
        controller = financial_controller(tmp_path, persistence, executor=executor)
        controller.start(direct_event())
        record = dict(controller.inspect("run-001"))
        record["recommendation"] = {"private_validation_detail": "secret schema path"}
        record["terminal_record_sha256"] = terminal_record_hash(record)
        persistence.store.put(("financial-research", "runs"), "run-001", record)
        stored_record = dict(persistence.store.get(("financial-research", "runs"), "run-001"))
        histories = financial_histories(persistence)

        assert_replay_rejected_without_mutation(controller, persistence, stored_record, histories)

        assert executor.calls == 1


@pytest.mark.parametrize("hash_state", ("missing", "mismatched"))
def test_invalid_terminal_hash_is_rejected_without_replay_mutation(tmp_path, hash_state):
    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        software_checkpoint(persistence.checkpointer, "run-001")
        executor = CountingExecutor(local_executor(tmp_path, persistence))
        controller = financial_controller(tmp_path, persistence, executor=executor)
        controller.start(direct_event())
        record = dict(controller.inspect("run-001"))
        if hash_state == "missing":
            record.pop("terminal_record_sha256", None)
        else:
            record["terminal_record_sha256"] = "0" * 64
        persistence.store.put(("financial-research", "runs"), "run-001", record)
        stored_record = dict(persistence.store.get(("financial-research", "runs"), "run-001"))
        histories = financial_histories(persistence)

        assert_replay_rejected_without_mutation(controller, persistence, stored_record, histories)

        assert executor.calls == 1


@pytest.mark.parametrize(
    ("outcome_field", "invalid_value"),
    (
        ("run_id", "foreign-run"),
        ("status", FinancialResearchStatus.REQUESTED.value),
        ("non_authority", "Grants trading authority."),
    ),
)
def test_rehashed_incoherent_terminal_outcome_is_rejected(tmp_path, outcome_field, invalid_value):
    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        software_checkpoint(persistence.checkpointer, "run-001")
        executor = CountingExecutor(local_executor(tmp_path, persistence))
        controller = financial_controller(tmp_path, persistence, executor=executor)
        controller.start(direct_event())
        record = dict(controller.inspect("run-001"))
        recommendation = dict(record["recommendation"])
        recommendation[outcome_field] = invalid_value
        record["recommendation"] = recommendation
        record["terminal_record_sha256"] = terminal_record_hash(record)
        persistence.store.put(("financial-research", "runs"), "run-001", record)
        stored_record = dict(persistence.store.get(("financial-research", "runs"), "run-001"))
        histories = financial_histories(persistence)

        assert_replay_rejected_without_mutation(controller, persistence, stored_record, histories)

        assert executor.calls == 1


@pytest.mark.parametrize(
    "contract_name",
    ("trigger", "request", "plan", "dataset", "assessment"),
)
def test_rehashed_tampered_terminal_contract_chain_is_rejected(tmp_path, contract_name):
    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        software_checkpoint(persistence.checkpointer, "run-001")
        executor = CountingExecutor(local_executor(tmp_path, persistence))
        controller = financial_controller(tmp_path, persistence, executor=executor)
        controller.start(direct_event())
        record = dict(controller.inspect("run-001"))
        contract = dict(record[contract_name])
        if contract_name == "trigger":
            contract["run_id"] = "foreign-run"
        elif contract_name == "request":
            contract["non_authority"] = "Grants trading authority."
        elif contract_name == "plan":
            contract["status"] = FinancialResearchStatus.IGNORED.value
        elif contract_name == "dataset":
            contract["validation_evidence"] = {"private_detail": "secret evidence path"}
        else:
            contract["status"] = FinancialResearchStatus.NEEDS_ANALYSIS.value
        record[contract_name] = contract
        record["terminal_record_sha256"] = terminal_record_hash(record)
        persistence.store.put(("financial-research", "runs"), "run-001", record)
        stored_record = dict(persistence.store.get(("financial-research", "runs"), "run-001"))
        histories = financial_histories(persistence)

        assert_replay_rejected_without_mutation(controller, persistence, stored_record, histories)

        assert executor.calls == 1


def test_conflicting_terminal_replay_fails_without_modifying_terminal_state(tmp_path):
    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        executor = CountingExecutor(local_executor(tmp_path, persistence))
        controller = financial_controller(tmp_path, persistence, executor=executor)
        controller.start(direct_event())
        first_record = dict(controller.inspect("run-001"))
        first_history = list(
            persistence.checkpointer.list(
                {"configurable": {"thread_id": "financial-research:run-001"}}
            )
        )
        conflict = direct_event().model_copy(update={"summary": "Conflicting replay."})

        with pytest.raises(RuntimeError, match="Financial research workflow failed"):
            controller.start(conflict)

        assert executor.calls == 1
        assert controller.inspect("run-001") == first_record
        assert (
            list(
                persistence.checkpointer.list(
                    {"configurable": {"thread_id": "financial-research:run-001"}}
                )
            )
            == first_history
        )


def test_failure_attempt_after_completion_returns_accepted_output_without_execution(tmp_path):
    class FailingExecutor:
        calls = 0

        def execute(self, _event, _request, _plan):
            self.calls += 1
            raise RuntimeError("must not execute")

    market_database(tmp_path / "massive")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        accepted = financial_controller(tmp_path, persistence).start(direct_event())
        first_record = dict(financial_controller(tmp_path, persistence).inspect("run-001"))
        first_history = list(
            persistence.checkpointer.list(
                {"configurable": {"thread_id": "financial-research:run-001"}}
            )
        )
        executor = FailingExecutor()
        controller = financial_controller(tmp_path, persistence, executor=executor)

        replay = controller.start(direct_event())

        assert replay == accepted
        assert executor.calls == 0
        assert controller.inspect("run-001") == first_record
        assert (
            list(
                persistence.checkpointer.list(
                    {"configurable": {"thread_id": "financial-research:run-001"}}
                )
            )
            == first_history
        )
