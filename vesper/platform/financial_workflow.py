"""Sibling LangGraph for bounded financial research."""

from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from typing import Protocol, TypedDict

from .contracts import (
    DerivedDatasetReceipt,
    FinancialAnalysisPlan,
    FinancialEventEnvelope,
    FinancialGapAssessment,
    FinancialRecommendation,
    FinancialResearchRequest,
    FinancialResearchStatus,
    FinancialTriggerDecision,
)
from .financial_research import (
    FINANCIAL_RESEARCH_NON_AUTHORITY,
    build_coverage_analysis_plan,
    build_coverage_research_request,
    decide_financial_trigger,
    validate_financial_analysis_plan,
)
from .runtime_env import enforce_offline_runtime_environment

enforce_offline_runtime_environment()

from langgraph.graph import END, START, StateGraph  # noqa: E402


FINANCIAL_RESEARCH_RUN_NAMESPACE = ("financial-research", "runs")
_GENERIC_FAILURE_REASON = "Financial research workflow failed."


class FinancialResearchWorkflowError(RuntimeError):
    """The sibling workflow stopped without an accepted recommendation."""


def _financial_thread_id(run_id: str) -> str:
    return f"financial-research:{run_id}"


class FinancialResearchExecutor(Protocol):
    def execute(
        self,
        event: FinancialEventEnvelope,
        request: FinancialResearchRequest,
        plan: FinancialAnalysisPlan,
    ) -> tuple[DerivedDatasetReceipt, FinancialGapAssessment, FinancialRecommendation]: ...


class FinancialResearchRuntimeState(TypedDict, total=False):
    event: Mapping[str, object]
    status: str
    trigger: Mapping[str, object] | None
    request: Mapping[str, object] | None
    plan: Mapping[str, object] | None
    dataset: Mapping[str, object] | None
    assessment: Mapping[str, object] | None
    recommendation: Mapping[str, object] | None


def _dump(model) -> dict[str, object]:
    return model.model_dump(mode="json")


def _parse(model_type, value):
    return model_type.model_validate_json(json.dumps(value))


def _event_fingerprint(event: FinancialEventEnvelope) -> str:
    canonical = json.dumps(
        _dump(event),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def _stored_outcome(
    record: Mapping[str, object],
) -> FinancialRecommendation | FinancialTriggerDecision:
    recommendation = record.get("recommendation")
    if recommendation is not None:
        return _parse(FinancialRecommendation, recommendation)
    trigger = record.get("trigger")
    if record.get("status") == FinancialResearchStatus.IGNORED.value and trigger is not None:
        return _parse(FinancialTriggerDecision, trigger)
    raise FinancialResearchWorkflowError(_GENERIC_FAILURE_REASON)


def _authority(model) -> tuple[object, ...]:
    return (
        model.run_id,
        model.task_id,
        model.repository_revision,
        model.created_at,
        model.event_id,
    )


def _validate_executor_outputs(
    event: FinancialEventEnvelope,
    request: FinancialResearchRequest,
    plan: FinancialAnalysisPlan,
    dataset: DerivedDatasetReceipt,
    assessment: FinancialGapAssessment,
    recommendation: FinancialRecommendation,
) -> None:
    expected = _authority(event)
    if any(
        _authority(output) != expected
        for output in (request, plan, dataset, assessment, recommendation)
    ):
        raise FinancialResearchWorkflowError("financial research authority mismatch")
    if request.non_authority != event.non_authority or plan.non_authority != event.non_authority:
        raise FinancialResearchWorkflowError("financial research authority mismatch")
    if any(
        output.non_authority != FINANCIAL_RESEARCH_NON_AUTHORITY
        for output in (dataset, assessment, recommendation)
    ):
        raise FinancialResearchWorkflowError("financial research authority mismatch")
    if recommendation.status is FinancialResearchStatus.COMPLETE:
        coherent = assessment.status is FinancialResearchStatus.COMPLETE
    elif recommendation.status is FinancialResearchStatus.STOPPED:
        coherent = assessment.status in {
            FinancialResearchStatus.NEEDS_RESEARCH,
            FinancialResearchStatus.NEEDS_ANALYSIS,
            FinancialResearchStatus.STOPPED,
        }
    else:
        coherent = False
    if not coherent:
        raise FinancialResearchWorkflowError("financial research terminal state mismatch")


def build_financial_research_workflow(*, checkpointer, store, executor: FinancialResearchExecutor):
    def trigger_node(state: FinancialResearchRuntimeState) -> dict[str, object]:
        event = _parse(FinancialEventEnvelope, state["event"])
        decision = decide_financial_trigger(event)
        return {
            "status": decision.status.value,
            "trigger": _dump(decision),
        }

    def request_node(state: FinancialResearchRuntimeState) -> dict[str, object]:
        event = _parse(FinancialEventEnvelope, state["event"])
        decision = _parse(FinancialTriggerDecision, state["trigger"])
        request = build_coverage_research_request(event, decision)
        return {"status": request.status.value, "request": _dump(request)}

    def plan_node(state: FinancialResearchRuntimeState) -> dict[str, object]:
        request = _parse(FinancialResearchRequest, state["request"])
        plan = build_coverage_analysis_plan(request)
        validate_financial_analysis_plan(plan)
        return {"status": plan.status.value, "plan": _dump(plan)}

    def execute_node(state: FinancialResearchRuntimeState) -> dict[str, object]:
        event = _parse(FinancialEventEnvelope, state["event"])
        request = _parse(FinancialResearchRequest, state["request"])
        plan = _parse(FinancialAnalysisPlan, state["plan"])
        dataset, assessment, recommendation = executor.execute(event, request, plan)
        _validate_executor_outputs(
            event,
            request,
            plan,
            dataset,
            assessment,
            recommendation,
        )
        return {
            "dataset": _dump(dataset),
            "assessment": _dump(assessment),
            "recommendation": _dump(recommendation),
        }

    def report_node(state: FinancialResearchRuntimeState) -> dict[str, object]:
        recommendation = _parse(FinancialRecommendation, state["recommendation"])
        report = (
            recommendation.model_copy(update={"status": FinancialResearchStatus.COMPLETED})
            if recommendation.status is FinancialResearchStatus.COMPLETE
            else recommendation
        )
        return {
            "status": report.status.value,
            "recommendation": _dump(report),
        }

    builder = StateGraph(FinancialResearchRuntimeState)
    builder.add_node("trigger", trigger_node)
    builder.add_node("request", request_node)
    builder.add_node("plan", plan_node)
    builder.add_node("execute", execute_node)
    builder.add_node("report", report_node)
    builder.add_edge(START, "trigger")
    builder.add_conditional_edges(
        "trigger",
        lambda state: (
            "request" if state["status"] != FinancialResearchStatus.IGNORED.value else "end"
        ),
        {"request": "request", "end": END},
    )
    builder.add_edge("request", "plan")
    builder.add_edge("plan", "execute")
    builder.add_edge("execute", "report")
    builder.add_edge("report", END)
    return builder.compile(checkpointer=checkpointer, store=store)


class FinancialResearchController:
    def __init__(self, *, graph, store) -> None:
        self.graph = graph
        self.store = store

    def start(
        self,
        event: FinancialEventEnvelope,
    ) -> FinancialRecommendation | FinancialTriggerDecision:
        fingerprint = _event_fingerprint(event)
        existing = self.store.get(FINANCIAL_RESEARCH_RUN_NAMESPACE, event.run_id)
        if existing is not None:
            if existing.get("event_fingerprint") == fingerprint:
                return _stored_outcome(existing)
            raise FinancialResearchWorkflowError(_GENERIC_FAILURE_REASON) from None
        initial: FinancialResearchRuntimeState = {
            "event": _dump(event),
            "status": FinancialResearchStatus.REQUESTED.value,
            "trigger": None,
            "request": None,
            "plan": None,
            "dataset": None,
            "assessment": None,
            "recommendation": None,
        }
        try:
            result = self.graph.invoke(initial, self._config(event.run_id))
        except Exception:
            try:
                self.graph.checkpointer.delete_thread(_financial_thread_id(event.run_id))
            except Exception:
                pass
            try:
                self.store.put(
                    FINANCIAL_RESEARCH_RUN_NAMESPACE,
                    event.run_id,
                    {
                        "run_id": event.run_id,
                        "status": FinancialResearchStatus.STOPPED.value,
                        "failure_reason": _GENERIC_FAILURE_REASON,
                        "event_fingerprint": fingerprint,
                    },
                )
            except Exception:
                pass
            raise FinancialResearchWorkflowError(_GENERIC_FAILURE_REASON) from None
        if result["status"] == FinancialResearchStatus.IGNORED.value:
            decision = _parse(FinancialTriggerDecision, result["trigger"])
            self.store.put(
                FINANCIAL_RESEARCH_RUN_NAMESPACE,
                event.run_id,
                {
                    "run_id": event.run_id,
                    "status": FinancialResearchStatus.IGNORED.value,
                    "reason": "Event did not trigger bounded financial research.",
                    "event_fingerprint": fingerprint,
                    "trigger": result["trigger"],
                },
            )
            return decision

        recommendation = _parse(FinancialRecommendation, result["recommendation"])
        self.store.put(
            FINANCIAL_RESEARCH_RUN_NAMESPACE,
            event.run_id,
            {
                "run_id": event.run_id,
                "status": result["status"],
                "event_fingerprint": fingerprint,
                "trigger": result["trigger"],
                "request": result["request"],
                "plan": result["plan"],
                "dataset": result["dataset"],
                "assessment": result["assessment"],
                "recommendation": result["recommendation"],
            },
        )
        return recommendation

    def inspect(self, run_id: str) -> Mapping[str, object]:
        record = self.store.get(FINANCIAL_RESEARCH_RUN_NAMESPACE, run_id)
        if record is None:
            raise KeyError(f"financial research run not found: {run_id}")
        return record

    @staticmethod
    def _config(run_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": _financial_thread_id(run_id)}}
