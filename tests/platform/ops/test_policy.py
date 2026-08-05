from __future__ import annotations

from datetime import datetime, timezone

import pytest

from vesper.platform.ops.activation import (
    ActivationAuthorityError,
    ActivationCapability,
    ActivationGrant,
    OperationsActivation,
    OperationsActivationStore,
)
from vesper.platform.ops.policy import (
    BoundedWorkQueue,
    OperationsPolicy,
    OperationsState,
    ReconciliationGate,
    ResourceBudget,
    ResourceState,
)
from vesper.platform.ops.training import (
    CandidateApprovalError,
    CandidateTrainingRequest,
    WorkItem,
    canonical_training_request_sha256,
)
from vesper.platform.tui.views import CapabilityState, CapabilityView


UTC = timezone.utc


class AvailableQwenPort:
    def available(self) -> CapabilityView:
        return CapabilityView(
            capability_id="ops.qwen-work",
            state=CapabilityState.ENABLED,
            reason=None,
        )

    def run_one(self, _work_item):
        raise AssertionError("pure policy must not run adapters")


class AvailableTrainingPort:
    def available(self) -> CapabilityView:
        return CapabilityView(
            capability_id="ops.candidate-training",
            state=CapabilityState.ENABLED,
            reason=None,
        )

    def train_and_evaluate(self, _request):
        raise AssertionError("pure policy must not run adapters")


class FailingAuthority:
    def require(self, _capability, _receipt_id) -> None:
        raise ActivationAuthorityError("activation receipt is unavailable or mismatched")


class ExactTrainingApprovals:
    def __init__(self, *requests: CandidateTrainingRequest) -> None:
        self.hashes = {
            request.request_id: canonical_training_request_sha256(request)
            for request in requests
        }

    def require(self, request: CandidateTrainingRequest) -> None:
        if self.hashes.get(request.request_id) != canonical_training_request_sha256(request):
            raise CandidateApprovalError("candidate request is not exactly approved")


class ReceiptAuthority:
    def __init__(self, activation: OperationsActivation) -> None:
        self.activation = activation

    def require(self, capability: ActivationCapability, receipt_id: str) -> None:
        grant = getattr(self.activation, capability.value)
        if not grant.enabled or grant.receipt_id != receipt_id:
            raise ActivationAuthorityError("activation receipt is unavailable or mismatched")


def activation_store(*enabled: ActivationCapability) -> OperationsActivationStore:
    values = {
        capability.value: ActivationGrant(
            enabled=capability in enabled,
            receipt_id=f"receipt-{capability.value}" if capability in enabled else None,
        )
        for capability in ActivationCapability
    }
    activation = OperationsActivation(**values)
    return OperationsActivationStore(activation, ReceiptAuthority(activation))


def policy(
    store: OperationsActivationStore,
    *,
    training: bool = True,
    approved_requests: tuple[CandidateTrainingRequest, ...] = (),
) -> OperationsPolicy:
    return OperationsPolicy(
        store,
        qwen_port=AvailableQwenPort(),
        training_port=AvailableTrainingPort() if training else None,
        training_approvals=ExactTrainingApprovals(*approved_requests),
    )


def resources(**changes) -> ResourceState:
    values = {
        "gpu_percent": 10,
        "gpu_temperature_c": 45,
        "memory_percent": 30,
        "disk_free_gb": 100,
        "recent_errors": 0,
        "qwen_lease_active": False,
    }
    values.update(changes)
    return ResourceState(**values)


def state(*items: WorkItem, **changes) -> OperationsState:
    values = {"resources": resources(), "work_items": items}
    values.update(changes)
    return OperationsState(**values)


@pytest.mark.parametrize(
    ("instant", "quiet"),
    [
        (datetime(2026, 1, 5, 23, 59, tzinfo=UTC), False),  # 18:59 ET
        (datetime(2026, 1, 6, 0, 0, tzinfo=UTC), True),  # 19:00 ET
        (datetime(2026, 1, 6, 12, 59, tzinfo=UTC), True),  # 07:59 ET
        (datetime(2026, 1, 6, 13, 0, tzinfo=UTC), False),  # 08:00 ET
        (datetime(2026, 7, 6, 22, 59, tzinfo=UTC), False),  # 18:59 EDT
        (datetime(2026, 7, 6, 23, 0, tzinfo=UTC), True),  # 19:00 EDT
        (datetime(2026, 7, 7, 11, 59, tzinfo=UTC), True),  # 07:59 EDT
        (datetime(2026, 7, 7, 12, 0, tzinfo=UTC), False),  # 08:00 EDT
        (datetime(2026, 7, 5, 16, 0, tzinfo=UTC), True),  # weekend
        (datetime(2026, 3, 8, 7, 0, tzinfo=UTC), True),  # spring DST transition
        (datetime(2026, 11, 1, 6, 0, tzinfo=UTC), True),  # fall DST transition
    ],
)
def test_quiet_mode_uses_eastern_wall_clock_and_weekends(instant, quiet) -> None:
    scheduler = policy(activation_store())
    assert scheduler.is_quiet_mode(instant) is quiet


def test_priority_is_deterministic_and_rechecks_after_one_unit() -> None:
    items = (
        WorkItem(work_id="research", kind="research", agent_id="v20-product", objective="r"),
        WorkItem(work_id="normal", kind="normal", agent_id="v20-product", objective="n"),
        WorkItem(work_id="portfolio", kind="portfolio", agent_id="v20-portfolio-researcher", objective="p"),
        WorkItem(work_id="approval", kind="approval", agent_id="v20-risk-review", objective="a"),
    )
    scheduler = policy(activation_store(ActivationCapability.CONTINUOUS_WORK))

    decision = scheduler.next_action(
        state(*items, has_incident=True),
        datetime(2026, 1, 6, 15, 0, tzinfo=UTC),
    )
    assert decision.kind == "incident"
    assert decision.max_units == 1

    decision = scheduler.next_action(
        state(*items),
        datetime(2026, 1, 6, 15, 0, tzinfo=UTC),
    )
    assert decision.kind == "work"
    assert decision.work_id == "approval"
    assert decision.pause_seconds >= 2


def test_operator_command_is_available_but_background_work_needs_grant() -> None:
    scheduler = policy(activation_store())
    now = datetime(2026, 1, 6, 15, 0, tzinfo=UTC)

    assert scheduler.next_action(state(operator_command_id="command-1"), now).kind == "operator-command"
    queued = WorkItem(work_id="normal", kind="normal", agent_id="v20-product", objective="n")
    decision = scheduler.next_action(state(queued), now)
    assert decision.kind == "rest"
    assert decision.reason == "Continuous work is not activated."


def test_approval_and_portfolio_work_precede_an_operator_command_when_enabled() -> None:
    scheduler = policy(activation_store(ActivationCapability.CONTINUOUS_WORK))
    now = datetime(2026, 1, 6, 15, 0, tzinfo=UTC)
    approval = WorkItem(
        work_id="approval-1",
        kind="approval",
        agent_id="v20-risk-review",
        objective="Review approval.",
    )
    portfolio = WorkItem(
        work_id="portfolio-1",
        kind="portfolio",
        agent_id="v20-portfolio-researcher",
        objective="Review portfolio.",
    )

    decision = scheduler.next_action(
        state(portfolio, approval, operator_command_id="command-1"),
        now,
    )
    assert decision.work_id == "approval-1"


def test_enabled_grant_still_rests_when_the_effect_adapter_is_unavailable() -> None:
    now = datetime(2026, 1, 6, 15, 0, tzinfo=UTC)
    normal = WorkItem(
        work_id="normal-1",
        kind="normal",
        agent_id="v20-product",
        objective="Review queue.",
    )
    no_qwen = OperationsPolicy(
        activation_store(ActivationCapability.CONTINUOUS_WORK),
    )
    assert no_qwen.next_action(state(normal), now).reason == (
        "The qwen:64k runtime adapter is not configured."
    )

    request = CandidateTrainingRequest(
        request_id="candidate-1",
        model_family="approved-family",
        strategy="ml_model",
        feature_set_id="features-1",
        data_identity="snapshot-1",
        evaluation_contract="evaluation-1",
        artifact_root="candidates/candidate-1",
    )
    candidate = WorkItem(
        work_id="candidate-1",
        kind="candidate",
        agent_id="v20-model-researcher",
        objective="Evaluate candidate.",
        training_request=request,
    )
    no_training = policy(
        activation_store(
            ActivationCapability.CONTINUOUS_WORK,
            ActivationCapability.CANDIDATE_TRAINING,
        ),
        training=False,
        approved_requests=(request,),
    )
    assert no_training.next_action(state(candidate), now).reason == (
        "No approved candidate training adapter is configured."
    )


def test_mismatched_activation_receipt_returns_rest_before_adapter_health() -> None:
    activation = OperationsActivation(
        continuous_work=ActivationGrant(enabled=True, receipt_id="wrong")
    )
    scheduler = OperationsPolicy(
        OperationsActivationStore(activation, FailingAuthority()),
        qwen_port=AvailableQwenPort(),
    )
    queued = WorkItem(
        work_id="normal-1",
        kind="normal",
        agent_id="v20-product",
        objective="Review queue.",
    )

    decision = scheduler.next_action(
        state(queued),
        datetime(2026, 1, 6, 15, 0, tzinfo=UTC),
    )
    assert decision.kind == "rest"
    assert decision.reason == "Continuous-work authority could not be validated."


def test_bad_continuous_receipt_does_not_block_explicit_operator_command() -> None:
    activation = OperationsActivation(
        continuous_work=ActivationGrant(enabled=True, receipt_id="wrong")
    )
    scheduler = OperationsPolicy(
        OperationsActivationStore(activation, FailingAuthority()),
    )

    decision = scheduler.next_action(
        state(operator_command_id="command-1"),
        datetime(2026, 1, 6, 15, 0, tzinfo=UTC),
    )
    assert decision.kind == "operator-command"


@pytest.mark.parametrize(
    "resource_changes",
    [
        {"gpu_temperature_c": 90},
        {"memory_percent": 95},
        {"disk_free_gb": 2},
        {"recent_errors": 3},
        {"qwen_lease_active": True},
    ],
)
def test_resource_or_single_lease_pressure_rests(resource_changes) -> None:
    scheduler = policy(activation_store(ActivationCapability.CONTINUOUS_WORK))
    queued = WorkItem(work_id="normal", kind="normal", agent_id="v20-product", objective="n")
    decision = scheduler.next_action(
        state(queued, resources=resources(**resource_changes)),
        datetime(2026, 1, 6, 15, 0, tzinfo=UTC),
    )
    assert decision.kind == "rest"


def test_quiet_mode_uses_lower_gpu_budget_and_longer_pause() -> None:
    scheduler = policy(activation_store(ActivationCapability.CONTINUOUS_WORK))
    queued = WorkItem(work_id="normal", kind="normal", agent_id="v20-product", objective="n")

    normal = scheduler.next_action(state(queued), datetime(2026, 1, 6, 15, 0, tzinfo=UTC))
    quiet = scheduler.next_action(state(queued), datetime(2026, 1, 6, 2, 0, tzinfo=UTC))

    assert quiet.gpu_budget_percent < normal.gpu_budget_percent
    assert quiet.pause_seconds >= 30
    assert normal.pause_seconds >= 2


def test_daily_curation_and_runtime_start_each_need_their_own_grant() -> None:
    now = datetime(2026, 1, 6, 15, 0, tzinfo=UTC)
    continuous = ActivationCapability.CONTINUOUS_WORK
    daily = ActivationCapability.DAILY_MEMORY_CURATION
    runtime = ActivationCapability.RUNTIME_START

    assert policy(activation_store(continuous)).next_action(
        state(daily_curation_due=True), now
    ).kind == "rest"
    assert policy(activation_store(continuous, daily)).next_action(
        state(daily_curation_due=True), now
    ).kind == "curate-memory"
    assert policy(activation_store()).next_action(
        state(runtime_start_requested=True), now
    ).kind == "rest"
    assert policy(activation_store(runtime)).next_action(
        state(runtime_start_requested=True), now
    ).kind == "runtime-start"


def test_candidate_training_binds_request_and_needs_both_grants() -> None:
    request = CandidateTrainingRequest(
        request_id="candidate-1",
        model_family="approved-family",
        strategy="ml_model",
        feature_set_id="features-1",
        data_identity="snapshot-1",
        evaluation_contract="evaluation-1",
        artifact_root="candidates/candidate-1",
    )
    item = WorkItem(
        work_id="candidate-1",
        kind="candidate",
        agent_id="v20-model-researcher",
        objective="Evaluate candidate.",
        training_request=request,
    )
    now = datetime(2026, 1, 6, 15, 0, tzinfo=UTC)

    continuous = ActivationCapability.CONTINUOUS_WORK
    training = ActivationCapability.CANDIDATE_TRAINING
    assert policy(activation_store(continuous)).next_action(state(item), now).kind == "rest"
    decision = policy(
        activation_store(continuous, training),
        approved_requests=(request,),
    ).next_action(state(item), now)
    assert decision.kind == "candidate-training"
    assert decision.training_request == request

    changed = request.model_copy(update={"data_identity": "unapproved-snapshot"})
    changed_item = item.model_copy(update={"training_request": changed})
    rejected = policy(
        activation_store(continuous, training),
        approved_requests=(request,),
    ).next_action(state(changed_item), now)
    assert rejected.kind == "rest"
    assert rejected.reason == "Candidate training request is not exactly approved."

    invalid_item = item.model_copy(update={"work_id": "candidate-2"})
    invalid = policy(
        activation_store(continuous, training),
        approved_requests=(request,),
    ).next_action(state(invalid_item), now)
    assert invalid.kind == "rest"
    assert invalid.reason == "Queued work failed strict validation."


def test_queue_caps_duplicates_and_reconciliation_are_idempotent() -> None:
    queue = BoundedWorkQueue(global_cap=3, per_agent_cap=2)
    first = WorkItem(work_id="work-1", kind="normal", agent_id="v20-product", objective="same")
    duplicate = WorkItem(work_id="work-2", kind="normal", agent_id="v20-product", objective="same")
    assert queue.enqueue(first).work_id == "work-1"
    assert queue.enqueue(duplicate).work_id == "work-1"
    queue.enqueue(WorkItem(work_id="work-3", kind="normal", agent_id="v20-product", objective="other"))
    with pytest.raises(OverflowError, match="per-agent"):
        queue.enqueue(WorkItem(work_id="work-4", kind="normal", agent_id="v20-product", objective="third"))

    gate = ReconciliationGate(queue)
    first_task = gate.observe_mismatch("positions", "alpaca-paper", "mismatch-1")
    second_task = gate.observe_mismatch("positions", "alpaca-paper", "mismatch-1")
    assert first_task.work_id == second_task.work_id
    assert gate.orders_blocked is True
    assert gate.rebalance_blocked is True
    assert first_task.kind == "incident"
    assert first_task.agent_id == "v20-execution-performance-analyst"
    assert first_task.source_adapter_id == "alpaca-paper"
    gate.resolve_mismatch("positions", "alpaca-paper", "mismatch-1")
    assert gate.orders_blocked is False
    assert gate.rebalance_blocked is False


def test_queue_reserves_capacity_for_one_urgent_incident() -> None:
    queue = BoundedWorkQueue(global_cap=3, per_agent_cap=2)
    queue.enqueue(
        WorkItem(
            work_id="normal-1",
            kind="normal",
            agent_id="v20-product",
            objective="first",
        )
    )
    queue.enqueue(
        WorkItem(
            work_id="normal-2",
            kind="normal",
            agent_id="v20-risk-review",
            objective="second",
        )
    )
    with pytest.raises(OverflowError, match="incident capacity"):
        queue.enqueue(
            WorkItem(
                work_id="normal-3",
                kind="normal",
                agent_id="v20-development",
                objective="third",
            )
        )
    incident = queue.enqueue(
        WorkItem(
            work_id="incident-1",
            kind="incident",
            agent_id="v20-execution-performance-analyst",
            objective="urgent",
        )
    )
    assert incident.work_id == "incident-1"


def test_candidate_dedup_includes_the_exact_training_binding() -> None:
    queue = BoundedWorkQueue(global_cap=3, per_agent_cap=3, reserved_incident_slots=0)
    first_request = CandidateTrainingRequest(
        request_id="candidate-1",
        model_family="approved-family",
        strategy="ml_model",
        feature_set_id="features-1",
        data_identity="snapshot-1",
        evaluation_contract="evaluation-1",
        artifact_root="candidates/candidate-1",
    )
    second_request = first_request.model_copy(
        update={
            "request_id": "candidate-2",
            "data_identity": "snapshot-2",
            "artifact_root": "candidates/candidate-2",
        }
    )
    first = WorkItem(
        work_id="candidate-1",
        kind="candidate",
        agent_id="v20-model-researcher",
        objective="Evaluate candidate.",
        training_request=first_request,
    )
    second = WorkItem(
        work_id="candidate-2",
        kind="candidate",
        agent_id="v20-model-researcher",
        objective="Evaluate candidate.",
        training_request=second_request,
    )
    assert queue.enqueue(first).work_id == "candidate-1"
    assert queue.enqueue(second).work_id == "candidate-2"


def test_failed_reconciliation_enqueue_never_loses_the_blocking_mismatch() -> None:
    queue = BoundedWorkQueue(global_cap=1, per_agent_cap=1, reserved_incident_slots=1)
    queue.enqueue(
        WorkItem(
            work_id="incident:filler",
            kind="incident",
            agent_id="v20-execution-performance-analyst",
            objective="Existing urgent incident.",
        )
    )
    gate = ReconciliationGate(queue)
    with pytest.raises(OverflowError, match="global"):
        gate.observe_mismatch("positions", "adapter-one", "mismatch-one")
    assert gate.orders_blocked is True
    queue.remove("incident:filler")

    gate.observe_mismatch("positions", "adapter-two", "mismatch-two")
    gate.resolve_mismatch("positions", "adapter-two", "mismatch-two")
    assert gate.orders_blocked is True
    assert gate.rebalance_blocked is True
    gate.resolve_mismatch("positions", "adapter-one", "mismatch-one")
    assert gate.orders_blocked is False


def test_config_is_conservative_and_rejects_invalid_thresholds() -> None:
    budget = ResourceBudget()
    assert budget.quiet_pause_seconds >= 30
    assert budget.normal_pause_seconds >= 2
    assert budget.quiet_gpu_budget_percent < budget.normal_gpu_budget_percent
    with pytest.raises(ValueError):
        ResourceBudget(quiet_gpu_budget_percent=90, normal_gpu_budget_percent=50)
