"""Local graph-backed service used by the Typer control surface."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Callable

from .contracts import (
    ApprovalDecision,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RunStatus,
    SpecialistReceipt,
    TaskRequest,
)
from .persistence import PlatformPaths, PlatformPersistence, open_persistence
from .workflow import (
    APPROVAL_REQUEST_NAMESPACE,
    WorkflowController,
    WorkflowView,
    build_workflow,
)


class SpecialistRuntimeUnavailable(RuntimeError):
    """No real or deterministic specialist runtime was configured."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class _UnavailableSpecialists:
    def execute(self, request):
        raise SpecialistRuntimeUnavailable(
            "create requires an explicitly configured specialist runtime; real Codex execution "
            "is not enabled by the offline platform CLI"
        )


class _UnavailableValidator:
    def validate(self, request, development_receipt):
        raise SpecialistRuntimeUnavailable("deterministic validator is not configured")


class _UnavailableRiskReviewer:
    def review(self, request, development_receipt, validation):
        raise SpecialistRuntimeUnavailable("Risk Review specialist is not configured")


class LocalPlatformService:
    """Open local persistence per command and expose graph lifecycle operations."""

    def __init__(
        self,
        paths: PlatformPaths,
        *,
        controller_factory: Callable[[PlatformPersistence], WorkflowController] | None = None,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.paths = paths
        self._controller_factory = controller_factory
        self._clock = clock
        self._id_factory = id_factory

    def create_run(
        self,
        objective: str,
        workspace: str,
        repository_revision: str,
    ) -> dict[str, object]:
        if self._controller_factory is None:
            raise SpecialistRuntimeUnavailable(
                "offline CLI has no specialist runtime; inject deterministic specialists or use "
                "the separately approved local Codex boundary"
            )
        task = TaskRequest(
            run_id=self._id_factory(),
            task_id=self._id_factory(),
            repository_revision=repository_revision,
            created_at=self._clock(),
            objective=objective,
            repository_root=workspace,
            acceptance_checks=("controller-configured deterministic validation",),
        )
        with open_persistence(self.paths) as persistence:
            view = self._controller(persistence).start(task)
        return self._view_payload(view)

    def inspect_run(self, run_id: str) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            view = self._controller(persistence).inspect(run_id)
        return self._view_payload(view)

    def resume_run(self, run_id: str) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            view = self._controller(persistence).resume(run_id)
        return self._view_payload(view)

    def list_receipts(self, run_id: str) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            view = self._controller(persistence).inspect(run_id)
        return {
            "run_id": run_id,
            "status": view.state.status.value,
            "receipts": [receipt.model_dump(mode="json") for receipt in view.state.receipts],
        }

    def list_evidence(self, run_id: str) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            view = self._controller(persistence).inspect(run_id)
        artifacts = []
        for receipt in view.state.receipts:
            artifacts.extend(receipt.evidence)
        if view.state.validation is not None:
            for check in view.state.validation.checks:
                artifacts.extend(check.evidence)
        if view.state.risk_review is not None:
            artifacts.extend(view.state.risk_review.evidence)
        if view.pending_approval is not None:
            artifacts.extend(view.pending_approval.evidence)
        unique = {
            (artifact.relative_path, artifact.sha256): artifact.model_dump(mode="json")
            for artifact in artifacts
        }
        return {
            "run_id": run_id,
            "status": view.state.status.value,
            "evidence": list(unique.values()),
        }

    def list_pending_approvals(self) -> dict[str, object]:
        pending = []
        with open_persistence(self.paths) as persistence:
            controller = self._controller(persistence)
            for raw in persistence.store.search(APPROVAL_REQUEST_NAMESPACE, limit=100):
                request = HumanApprovalRequest.model_validate_json(json.dumps(raw))
                view = controller.inspect(request.run_id)
                if view.state.status is RunStatus.AWAITING_APPROVAL:
                    pending.append(self._view_payload(view))
        pending.sort(key=lambda item: str(item["run_id"]))
        return {"pending": pending}

    def approve_run(
        self,
        run_id: str,
        checkpoint_id: str,
        operator_id: str,
        reason: str,
    ) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            controller = self._controller(persistence)
            view = controller.inspect(run_id)
            decision = self._decision(
                view,
                checkpoint_id=checkpoint_id,
                operator_id=operator_id,
                reason=reason,
                decision=ApprovalDecision.APPROVE,
            )
            controller.record_decision(run_id, decision)
            payload = self._view_payload(controller.inspect(run_id))
        payload["resume_required"] = True
        return payload

    def reject_run(
        self,
        run_id: str,
        checkpoint_id: str,
        operator_id: str,
        reason: str,
    ) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            controller = self._controller(persistence)
            view = controller.inspect(run_id)
            decision = self._decision(
                view,
                checkpoint_id=checkpoint_id,
                operator_id=operator_id,
                reason=reason,
                decision=ApprovalDecision.REJECT,
            )
            controller.record_decision(run_id, decision)
            rejected = controller.resume(run_id)
        return self._view_payload(rejected)

    def cancel_run(self, run_id: str, reason: str) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            view = self._controller(persistence).cancel(run_id, reason)
        return self._view_payload(view)

    def _controller(self, persistence: PlatformPersistence) -> WorkflowController:
        if self._controller_factory is not None:
            return self._controller_factory(persistence)
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            store=persistence.langgraph_store,
            specialists=_UnavailableSpecialists(),
            validator=_UnavailableValidator(),
            risk_reviewer=_UnavailableRiskReviewer(),
            clock=self._clock,
        )
        return WorkflowController(graph=graph, store=persistence.store, clock=self._clock)

    def _decision(
        self,
        view: WorkflowView,
        *,
        checkpoint_id: str,
        operator_id: str,
        reason: str,
        decision: ApprovalDecision,
    ) -> HumanApprovalDecision:
        request = view.pending_approval
        if request is None:
            raise RuntimeError("run has no pending approval request")
        return HumanApprovalDecision(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            approval_id=self._id_factory(),
            request_id=request.request_id,
            checkpoint_id=checkpoint_id,
            operator_id=operator_id,
            decision=decision,
            reason=reason,
            decided_at=self._clock(),
        )

    @staticmethod
    def _view_payload(view: WorkflowView) -> dict[str, object]:
        return {
            "run_id": view.state.run_id,
            "task_id": view.state.task_id,
            "status": view.state.status.value,
            "checkpoint_id": view.checkpoint_id,
            "next_nodes": list(view.next_nodes),
            "correction_count": view.state.correction_count,
            "pending_approval": (
                None
                if view.pending_approval is None
                else view.pending_approval.model_dump(mode="json")
            ),
            "terminal_reason": view.state.terminal_reason,
        }
