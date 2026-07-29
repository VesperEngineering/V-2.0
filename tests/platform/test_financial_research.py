from datetime import datetime, timezone

import pytest

from vesper.platform.contracts import (
    AnalysisNode,
    FinancialAnalysisPlan,
    FinancialEventEnvelope,
    FinancialEventType,
    FinancialResearchStatus,
)
from vesper.platform.financial_research import (
    FinancialResearchError,
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
        occurred_at=NOW,
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
    assert (
        decide_financial_trigger(weak_event(observed=0.03, threshold=0.03)).should_research is False
    )


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
