"""Deterministic Phase 1 financial-research intake and planning."""

from __future__ import annotations

from hashlib import sha256

from vesper.platform.contracts import (
    AnalysisNode,
    FinancialAnalysisPlan,
    FinancialEventEnvelope,
    FinancialEventType,
    FinancialResearchRequest,
    FinancialResearchStatus,
    FinancialTriggerDecision,
)


class FinancialResearchError(ValueError):
    """A financial-research request or plan is not admitted for Phase 1."""


_SUPPORTED_OPERATIONS = {
    "source-coverage": ("symbol", "coverage_start", "coverage_end"),
    "coverage-summary": ("symbol", "coverage_days"),
}


def decide_financial_trigger(event: FinancialEventEnvelope) -> FinancialTriggerDecision:
    if event.event_type is FinancialEventType.DIRECT_REQUEST:
        triggered = True
        reason = "A direct operator request is in scope for analysis-only research."
    else:
        triggered = event.observed_metric < event.threshold
        reason = (
            "The weak model result is below the admitted threshold."
            if triggered
            else "The weak model result meets or exceeds the admitted threshold."
        )

    return FinancialTriggerDecision(
        run_id=event.run_id,
        task_id=event.task_id,
        repository_revision=event.repository_revision,
        created_at=event.created_at,
        event_id=event.event_id,
        non_authority=event.non_authority,
        triggered=triggered,
        status=(
            FinancialResearchStatus.REQUESTED if triggered else FinancialResearchStatus.STOPPED
        ),
        reason=reason,
        workflow="analysis-only",
        resource_budget="bounded-local",
    )


def build_coverage_research_request(
    event: FinancialEventEnvelope,
    decision: FinancialTriggerDecision,
) -> FinancialResearchRequest:
    if not decision.should_research:
        raise FinancialResearchError("ignored events cannot build a research request")
    if (
        decision.run_id != event.run_id
        or decision.task_id != event.task_id
        or decision.repository_revision != event.repository_revision
        or decision.event_id != event.event_id
    ):
        raise FinancialResearchError("trigger decision authority does not match the event")

    start, end = sorted(
        (event.occurred_at.date().isoformat(), event.observed_at.date().isoformat())
    )
    symbols = ", ".join(event.symbols)
    return FinancialResearchRequest(
        run_id=event.run_id,
        task_id=event.task_id,
        repository_revision=event.repository_revision,
        created_at=event.created_at,
        event_id=event.event_id,
        non_authority=event.non_authority,
        request_id=f"{event.event_id}-coverage",
        status=FinancialResearchStatus.REQUESTED,
        questions=(f"What local coverage exists for {symbols}?",),
        source_classes=("local-market-data",),
        symbols=event.symbols,
        time_window_start=start,
        time_window_end=end,
        sufficiency_criteria=("Coverage dates are known.",),
    )


def build_coverage_analysis_plan(request: FinancialResearchRequest) -> FinancialAnalysisPlan:
    source = AnalysisNode(
        run_id=request.run_id,
        task_id=request.task_id,
        repository_revision=request.repository_revision,
        created_at=request.created_at,
        event_id=request.event_id,
        non_authority=request.non_authority,
        node_id="market-coverage-source",
        kind="source-coverage",
        output_schema=_SUPPORTED_OPERATIONS["source-coverage"],
        transform_sha256=_transform_hash("source-coverage"),
    )
    summary = AnalysisNode(
        run_id=request.run_id,
        task_id=request.task_id,
        repository_revision=request.repository_revision,
        created_at=request.created_at,
        event_id=request.event_id,
        non_authority=request.non_authority,
        node_id="coverage-summary",
        kind="coverage-summary",
        depends_on=(source.node_id,),
        output_schema=_SUPPORTED_OPERATIONS["coverage-summary"],
        transform_sha256=_transform_hash("coverage-summary"),
    )
    return FinancialAnalysisPlan(
        run_id=request.run_id,
        task_id=request.task_id,
        repository_revision=request.repository_revision,
        created_at=request.created_at,
        event_id=request.event_id,
        non_authority=request.non_authority,
        plan_id=f"{request.request_id}-plan",
        status=FinancialResearchStatus.PLANNED,
        nodes=(source, summary),
        acceptance_checks=("coverage dates are present",),
    )


def validate_financial_analysis_plan(plan: FinancialAnalysisPlan) -> tuple[str, ...]:
    node_ids = tuple(node.node_id for node in plan.nodes)
    if len(set(node_ids)) != len(node_ids):
        raise FinancialResearchError("analysis plan contains duplicate node IDs")

    known_node_ids = set(node_ids)
    for node in plan.nodes:
        expected_schema = _SUPPORTED_OPERATIONS.get(node.kind)
        if expected_schema is None:
            raise FinancialResearchError(f"unsupported analysis operation: {node.kind}")
        if node.output_schema != expected_schema:
            raise FinancialResearchError(f"invalid output schema for operation: {node.kind}")
        if not set(node.depends_on).issubset(known_node_ids):
            raise FinancialResearchError("analysis plan has an unknown dependency")

    remaining_dependencies = {node.node_id: set(node.depends_on) for node in plan.nodes}
    ready = [node.node_id for node in plan.nodes if not remaining_dependencies[node.node_id]]
    order: list[str] = []
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for node in plan.nodes:
            dependencies = remaining_dependencies[node.node_id]
            if node_id not in dependencies:
                continue
            dependencies.remove(node_id)
            if not dependencies:
                ready.append(node.node_id)

    if len(order) != len(plan.nodes):
        raise FinancialResearchError("analysis plan contains a dependency cycle")

    expected_nodes = ("market-coverage-source", "coverage-summary")
    if node_ids != expected_nodes:
        raise FinancialResearchError("Phase 1 requires the static two-node analysis plan")
    source, summary = plan.nodes
    if (
        source.kind != "source-coverage"
        or source.depends_on
        or summary.kind != "coverage-summary"
        or summary.depends_on != (source.node_id,)
    ):
        raise FinancialResearchError("Phase 1 requires the static two-node analysis plan")
    return tuple(order)


def _transform_hash(operation: str) -> str:
    return sha256(operation.encode("utf-8")).hexdigest()
