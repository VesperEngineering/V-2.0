"""Pure scheduling decisions for bounded local V20 operations."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from vesper.platform.ops.activation import (
    ActivationAuthorityError,
    ActivationCapability,
    ActivationGrant,
    OperationsActivationStore,
)
from vesper.platform.ops.training import (
    CandidateApprovalError,
    CandidateTrainingApprovalStore,
    CandidateTrainingPort,
    CandidateTrainingRequest,
    QwenWorkPort,
    UnavailableQwenWorkPort,
    UnavailableCandidateTrainingApprovalStore,
    UnavailableTrainingPort,
    WorkItem,
    validate_work_item,
)
from vesper.platform.tui.views import CapabilityState, CapabilityView


_EASTERN = ZoneInfo("America/New_York")
_PRIORITY = {
    "incident": 0,
    "approval": 1,
    "portfolio": 2,
    "operator-command": 3,
    "normal": 4,
    "candidate": 4,
    "research": 5,
}


@dataclass(frozen=True, slots=True)
class ResourceBudget:
    normal_gpu_budget_percent: int = 70
    quiet_gpu_budget_percent: int = 35
    maximum_gpu_temperature_c: int = 85
    maximum_memory_percent: int = 90
    minimum_disk_free_gb: int = 10
    maximum_recent_errors: int = 2
    normal_pause_seconds: int = 2
    quiet_pause_seconds: int = 30

    def __post_init__(self) -> None:
        bounded_percent = (
            self.normal_gpu_budget_percent,
            self.quiet_gpu_budget_percent,
            self.maximum_memory_percent,
        )
        if any(type(value) is not int or not 0 <= value <= 100 for value in bounded_percent):
            raise ValueError("resource percentages must be integers from 0 through 100")
        if self.quiet_gpu_budget_percent >= self.normal_gpu_budget_percent:
            raise ValueError("quiet GPU budget must be lower than normal")
        if self.maximum_gpu_temperature_c <= 0 or self.minimum_disk_free_gb < 0:
            raise ValueError("resource thresholds are invalid")
        if self.maximum_recent_errors < 0:
            raise ValueError("error threshold is invalid")
        if self.normal_pause_seconds < 2 or self.quiet_pause_seconds < 30:
            raise ValueError("operation pauses are below their safe minimum")


@dataclass(frozen=True, slots=True)
class ResourceState:
    gpu_percent: int
    gpu_temperature_c: int
    memory_percent: int
    disk_free_gb: int
    recent_errors: int
    qwen_lease_active: bool

    def __post_init__(self) -> None:
        if any(
            type(value) is not int
            for value in (
                self.gpu_percent,
                self.gpu_temperature_c,
                self.memory_percent,
                self.disk_free_gb,
                self.recent_errors,
            )
        ):
            raise TypeError("resource readings must be integers")
        if not 0 <= self.gpu_percent <= 100 or not 0 <= self.memory_percent <= 100:
            raise ValueError("resource percentages are invalid")
        if min(self.gpu_temperature_c, self.disk_free_gb, self.recent_errors) < 0:
            raise ValueError("resource readings cannot be negative")


@dataclass(frozen=True, slots=True)
class OperationsState:
    resources: ResourceState
    work_items: tuple[WorkItem, ...] = ()
    has_incident: bool = False
    incident_id: str | None = None
    operator_command_id: str | None = None
    daily_curation_due: bool = False
    runtime_start_requested: bool = False

    def __post_init__(self) -> None:
        if type(self.work_items) is not tuple or any(
            type(item) is not WorkItem for item in self.work_items
        ):
            raise TypeError("work_items must be a tuple of WorkItem")


@dataclass(frozen=True, slots=True)
class ActionDecision:
    kind: str
    reason: str
    work_id: str | None = None
    training_request: CandidateTrainingRequest | None = None
    pause_seconds: int = 2
    gpu_budget_percent: int = 0
    max_units: int = 1


class OperationsPolicy:
    def __init__(
        self,
        activation_store: OperationsActivationStore,
        budget: ResourceBudget = ResourceBudget(),
        *,
        qwen_port: QwenWorkPort | None = None,
        training_port: CandidateTrainingPort | None = None,
        training_approvals: CandidateTrainingApprovalStore | None = None,
    ) -> None:
        self._activation_store = activation_store
        self._budget = budget
        self._qwen_port = UnavailableQwenWorkPort() if qwen_port is None else qwen_port
        self._training_port = (
            UnavailableTrainingPort() if training_port is None else training_port
        )
        self._training_approvals = (
            UnavailableCandidateTrainingApprovalStore()
            if training_approvals is None
            else training_approvals
        )

    @property
    def resource_budget(self) -> ResourceBudget:
        return self._budget

    def is_quiet_mode(self, now_utc: datetime) -> bool:
        if now_utc.tzinfo is None or now_utc.utcoffset() is None:
            raise ValueError("now_utc must be timezone-aware")
        local = now_utc.astimezone(_EASTERN)
        return local.weekday() >= 5 or local.hour >= 19 or local.hour < 8

    def next_action(self, state: OperationsState, now_utc: datetime) -> ActionDecision:
        if type(state) is not OperationsState:
            raise TypeError("state must be OperationsState")
        quiet = self.is_quiet_mode(now_utc)
        pause = self._budget.quiet_pause_seconds if quiet else self._budget.normal_pause_seconds
        gpu_budget = (
            self._budget.quiet_gpu_budget_percent
            if quiet
            else self._budget.normal_gpu_budget_percent
        )
        try:
            work_items = tuple(validate_work_item(item) for item in state.work_items)
            work_validation_failed = False
        except (TypeError, ValueError):
            work_items = ()
            work_validation_failed = True

        incident_items = tuple(item for item in work_items if item.kind == "incident")
        if state.has_incident or incident_items:
            incident_id = state.incident_id
            if incident_id is None and incident_items:
                incident_id = min(incident_items, key=lambda item: item.work_id).work_id
            return ActionDecision(
                kind="incident",
                reason="An incident has priority.",
                work_id=incident_id,
                pause_seconds=pause,
                gpu_budget_percent=gpu_budget,
            )
        if state.runtime_start_requested:
            grant = self._validated_grant(ActivationCapability.RUNTIME_START)
            if grant is None:
                return self._rest("Runtime start authority could not be validated.", pause)
            if not grant.enabled:
                return self._rest("Runtime start is not activated.", pause)
            return ActionDecision(
                kind="runtime-start",
                reason="Runtime start has a validated authority receipt.",
                pause_seconds=pause,
                gpu_budget_percent=gpu_budget,
            )

        continuous = self._validated_grant(ActivationCapability.CONTINUOUS_WORK)
        if continuous is None:
            if state.operator_command_id is not None:
                return ActionDecision(
                    kind="operator-command",
                    reason="An explicit operator command has priority.",
                    work_id=state.operator_command_id,
                    pause_seconds=pause,
                    gpu_budget_percent=gpu_budget,
                )
            return self._rest("Continuous-work authority could not be validated.", pause)
        resource_reason = (
            self._resource_blocker(state.resources, gpu_budget)
            if continuous.enabled
            else "Continuous work is not activated."
        )
        if continuous.enabled and resource_reason is None:
            urgent = tuple(
                item for item in work_items if item.kind in {"approval", "portfolio"}
            )
            if urgent:
                qwen_reason = self._adapter_blocker(self._qwen_port, "ops.qwen-work")
                if qwen_reason is None:
                    item = min(urgent, key=lambda value: (_PRIORITY[value.kind], value.work_id))
                    return ActionDecision(
                        kind="work",
                        reason="Highest-priority bounded work item selected.",
                        work_id=item.work_id,
                        pause_seconds=pause,
                        gpu_budget_percent=gpu_budget,
                    )
        if state.operator_command_id is not None:
            return ActionDecision(
                kind="operator-command",
                reason="An explicit operator command has priority.",
                work_id=state.operator_command_id,
                pause_seconds=pause,
                gpu_budget_percent=gpu_budget,
            )
        if work_validation_failed:
            return self._rest("Queued work failed strict validation.", pause)
        if not continuous.enabled:
            return self._rest("Continuous work is not activated.", pause)
        if resource_reason is not None:
            return self._rest(resource_reason, pause)
        if state.daily_curation_due:
            daily = self._validated_grant(ActivationCapability.DAILY_MEMORY_CURATION)
            if daily is None:
                return self._rest("Daily-curation authority could not be validated.", pause)
            if not daily.enabled:
                return self._rest("Daily memory curation is not activated.", pause)
            return ActionDecision(
                kind="curate-memory",
                reason="Daily curation has a validated authority receipt.",
                pause_seconds=pause,
                gpu_budget_percent=gpu_budget,
            )
        if not work_items:
            return self._rest("No work is queued.", pause)

        item = min(work_items, key=lambda value: (_PRIORITY[value.kind], value.work_id))
        if item.kind == "candidate":
            training = self._validated_grant(ActivationCapability.CANDIDATE_TRAINING)
            if training is None:
                return self._rest("Candidate-training authority could not be validated.", pause)
            if not training.enabled:
                return self._rest("Candidate training is not activated.", pause)
            try:
                self._training_approvals.require(item.training_request)
            except CandidateApprovalError:
                return self._rest(
                    "Candidate training request is not exactly approved.",
                    pause,
                )
            except Exception:
                return self._rest(
                    "Candidate training approval could not be validated.",
                    pause,
                )
            training_reason = self._adapter_blocker(
                self._training_port,
                "ops.candidate-training",
            )
            if training_reason is not None:
                return self._rest(training_reason, pause)
            return ActionDecision(
                kind="candidate-training",
                reason="Candidate training has all required grants.",
                work_id=item.work_id,
                training_request=item.training_request,
                pause_seconds=pause,
                gpu_budget_percent=gpu_budget,
            )
        qwen_reason = self._adapter_blocker(self._qwen_port, "ops.qwen-work")
        if qwen_reason is not None:
            return self._rest(qwen_reason, pause)
        return ActionDecision(
            kind="work",
            reason="Highest-priority bounded work item selected.",
            work_id=item.work_id,
            pause_seconds=pause,
            gpu_budget_percent=gpu_budget,
        )

    def _resource_blocker(self, state: ResourceState, gpu_budget: int) -> str | None:
        if state.qwen_lease_active:
            return "The single Qwen work lease is already held."
        if state.gpu_percent > gpu_budget:
            return "GPU use is above the active budget."
        if state.gpu_temperature_c >= self._budget.maximum_gpu_temperature_c:
            return "GPU temperature is above the safe threshold."
        if state.memory_percent >= self._budget.maximum_memory_percent:
            return "Memory use is above the safe threshold."
        if state.disk_free_gb <= self._budget.minimum_disk_free_gb:
            return "Disk free space is below the safe threshold."
        if state.recent_errors >= self._budget.maximum_recent_errors:
            return "Recent errors require a rest period."
        return None

    @staticmethod
    def _rest(reason: str, pause_seconds: int) -> ActionDecision:
        return ActionDecision(kind="rest", reason=reason, pause_seconds=pause_seconds)

    @staticmethod
    def _adapter_blocker(port: object, expected_id: str) -> str | None:
        try:
            capability = port.available()  # type: ignore[attr-defined]
        except Exception:
            return "The operations adapter health check failed."
        if type(capability) is not CapabilityView:
            return "The operations adapter returned an invalid capability state."
        if capability.capability_id != expected_id:
            return "The operations adapter capability identity does not match."
        if capability.state is CapabilityState.ENABLED:
            return None
        return capability.reason or "The operations adapter is unavailable."

    def _validated_grant(
        self,
        capability: ActivationCapability,
    ) -> ActivationGrant | None:
        try:
            return self._activation_store.validated_grant(capability)
        except ActivationAuthorityError:
            return None


class BoundedWorkQueue:
    def __init__(
        self,
        *,
        global_cap: int,
        per_agent_cap: int,
        reserved_incident_slots: int = 1,
    ) -> None:
        if global_cap <= 0 or per_agent_cap <= 0 or per_agent_cap > global_cap:
            raise ValueError("queue caps are invalid")
        if not 0 <= reserved_incident_slots <= global_cap:
            raise ValueError("reserved incident slots are invalid")
        self._global_cap = global_cap
        self._per_agent_cap = per_agent_cap
        self._reserved_incident_slots = reserved_incident_slots
        self._items: dict[str, WorkItem] = {}
        self._dedup: dict[str, str] = {}

    def enqueue(self, item: WorkItem) -> WorkItem:
        item = validate_work_item(item)
        existing_item = self._items.get(item.work_id)
        if existing_item is not None:
            if existing_item == item:
                return existing_item
            raise ValueError("work ID already exists with different content")
        key = self._semantic_key(item)
        existing_id = self._dedup.get(key)
        if existing_id is not None:
            return self._items[existing_id]
        if len(self._items) >= self._global_cap:
            raise OverflowError("global queue cap reached")
        counts = Counter(value.agent_id for value in self._items.values())
        if counts[item.agent_id] >= self._per_agent_cap:
            raise OverflowError("per-agent queue cap reached")
        non_incident_count = sum(item.kind != "incident" for item in self._items.values())
        if (
            item.kind != "incident"
            and non_incident_count >= self._global_cap - self._reserved_incident_slots
        ):
            raise OverflowError("background queue cap reached; incident capacity is reserved")
        self._items[item.work_id] = item
        self._dedup[key] = item.work_id
        return item

    def items(self) -> tuple[WorkItem, ...]:
        return tuple(self._items.values())

    def remove(self, work_id: str) -> WorkItem | None:
        item = self._items.pop(work_id, None)
        if item is None:
            return None
        self._dedup.pop(self._semantic_key(item), None)
        return item

    @staticmethod
    def _semantic_key(item: WorkItem) -> str:
        payload = json.dumps(
            item.model_dump(mode="json", exclude={"work_id"}),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass(slots=True)
class ReconciliationGate:
    queue: BoundedWorkQueue
    orders_blocked: bool = field(default=False, init=False)
    rebalance_blocked: bool = field(default=False, init=False)
    _tasks: dict[tuple[str, str, str], WorkItem] = field(default_factory=dict, init=False)
    _mismatches: set[tuple[str, str, str]] = field(default_factory=set, init=False)

    def observe_mismatch(
        self,
        source_kind: str,
        source_adapter: str,
        mismatch_id: str,
    ) -> WorkItem:
        if not all(type(value) is str and value.strip() for value in (
            source_kind,
            source_adapter,
            mismatch_id,
        )):
            raise ValueError("reconciliation identity is incomplete")
        key = (source_kind, source_adapter, mismatch_id)
        self._mismatches.add(key)
        self.orders_blocked = True
        self.rebalance_blocked = True
        task = self._tasks.get(key)
        if task is None:
            digest = hashlib.sha256("\0".join(key).encode("utf-8")).hexdigest()[:32]
            task = WorkItem(
                work_id=f"reconcile-{digest}",
                kind="incident",
                agent_id="v20-execution-performance-analyst",
                source_adapter_id=source_adapter,
                objective=(
                    f"Reconcile {source_kind} mismatch {mismatch_id} from "
                    f"source adapter {source_adapter}."
                ),
            )
            task = self.queue.enqueue(task)
            self._tasks[key] = task
        return task

    def resolve_mismatch(
        self,
        source_kind: str,
        source_adapter: str,
        mismatch_id: str,
    ) -> None:
        key = (source_kind, source_adapter, mismatch_id)
        self._mismatches.discard(key)
        task = self._tasks.pop(key, None)
        if task is not None:
            self.queue.remove(task.work_id)
        blocked = bool(self._mismatches)
        self.orders_blocked = blocked
        self.rebalance_blocked = blocked
