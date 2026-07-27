"""Fresh-process deny-egress probe used by the LangSmith isolation test."""

from __future__ import annotations

import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path


def install_socket_guard() -> list[object]:
    attempts: list[object] = []

    def deny_connect(self, address):
        attempts.append(address)
        raise AssertionError(f"network connection attempted: {address!r}")

    def deny_connect_ex(self, address):
        attempts.append(address)
        raise AssertionError(f"network connection attempted: {address!r}")

    socket.socket.connect = deny_connect
    socket.socket.connect_ex = deny_connect_ex
    return attempts


def main() -> None:
    attempts = install_socket_guard()
    canary = socket.socket()
    try:
        try:
            canary.connect(("127.0.0.1", 9))
        except AssertionError:
            pass
    finally:
        canary.close()
    if not attempts:
        raise AssertionError("socket deny-egress guard canary did not fire")
    attempts.clear()

    from vesper.platform.contracts import (
        ApprovalDecision,
        DevelopmentSpecialistOutput,
        EvidenceArtifactRef,
        ExecutionStatus,
        HumanApprovalDecision,
        ProductSpecialistOutput,
        RiskDecision,
        RiskReviewDecision,
        RunStatus,
        SpecialistReceipt,
        SpecialistRole,
        TaskRequest,
        ValidationCheck,
        ValidationResult,
    )
    from vesper.platform.persistence import PlatformPaths, open_persistence
    from vesper.platform.workflow import WorkflowController, build_workflow

    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert os.environ["LANGSMITH_TRACING_V2"] == "false"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
    assert os.environ["LANGGRAPH_CLI_NO_ANALYTICS"] == "1"

    now = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)

    def evidence(request, name):
        return EvidenceArtifactRef(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            artifact_id=name,
            relative_path=f"runs/{request.run_id}/{name}.json",
            sha256="c" * 64,
            size_bytes=1,
            media_type="application/json",
        )

    class Specialists:
        def execute(self, request):
            output = None
            if request.role is SpecialistRole.PRODUCT:
                output = ProductSpecialistOutput(
                    run_id=request.run_id,
                    task_id=request.task_id,
                    repository_revision=request.repository_revision,
                    created_at=request.created_at,
                    role=request.role,
                    attempt=request.attempt,
                    route=SpecialistRole.DEVELOPMENT,
                    summary="Offline bounded task.",
                    development_instructions="Run only the offline probe.",
                    acceptance_checks=("deny-egress probe",),
                )
            elif request.role is SpecialistRole.DEVELOPMENT:
                output = DevelopmentSpecialistOutput(
                    run_id=request.run_id,
                    task_id=request.task_id,
                    repository_revision=request.repository_revision,
                    created_at=request.created_at,
                    role=request.role,
                    attempt=request.attempt,
                    summary="Offline probe completed.",
                )
            return SpecialistReceipt(
                run_id=request.run_id,
                task_id=request.task_id,
                repository_revision=request.repository_revision,
                created_at=request.created_at,
                receipt_id=f"{request.role.value}-{request.attempt}",
                role=request.role,
                attempt=request.attempt,
                status=ExecutionStatus.COMPLETED,
                output=output,
                evidence=(evidence(request, request.role.value),),
            )

    class Validator:
        def validate(self, request, development_receipt):
            return ValidationResult(
                run_id=request.run_id,
                task_id=request.task_id,
                repository_revision=request.repository_revision,
                created_at=request.created_at,
                attempt=development_receipt.attempt,
                passed=True,
                checks=(
                    ValidationCheck(
                        name="offline",
                        passed=True,
                        command="offline",
                        exit_code=0,
                        evidence=(evidence(request, "validation"),),
                    ),
                ),
            )

    class Reviewer:
        def review(self, request, development_receipt, validation):
            return RiskReviewDecision(
                run_id=request.run_id,
                task_id=request.task_id,
                repository_revision=request.repository_revision,
                created_at=request.created_at,
                attempt=development_receipt.attempt,
                decision=RiskDecision.APPROVE,
                rationale="Offline fake approved.",
                evidence=(evidence(request, "risk"),),
                scope_compliant=True,
                evidence_owned=True,
                prohibited_actions_compliant=True,
            )

    task = TaskRequest(
        run_id="offline-run",
        task_id="offline-task",
        repository_revision="offline-revision",
        created_at=now,
        objective="Prove local graph execution does not attempt network access.",
        repository_root=str(Path(sys.argv[1]).resolve()),
        acceptance_checks=("deny-egress probe",),
    )
    paths = PlatformPaths.below(Path(sys.argv[1]) / "platform")
    with open_persistence(paths) as persistence:
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            store=persistence.langgraph_store,
            specialists=Specialists(),
            validator=Validator(),
            risk_reviewer=Reviewer(),
            workspace_hasher=lambda _workspace: "b" * 64,
            clock=lambda: now,
        )
        workflow = WorkflowController(
            graph=graph,
            store=persistence.store,
            workspace_hasher=lambda _workspace: "b" * 64,
            clock=lambda: now,
        )
        pending = workflow.start(task)
        persistence.store.put(("probe",), "item", {"offline": True})
        assert persistence.store.get(("probe",), "item") == {"offline": True}
        assert persistence.store.search(("probe",)) == ({"offline": True},)
        assert list(graph.get_state_history({"configurable": {"thread_id": "offline-run"}}))
        decision = HumanApprovalDecision(
            run_id=task.run_id,
            task_id=task.task_id,
            repository_revision=task.repository_revision,
            created_at=now,
            approval_id="offline-approval",
            request_id=pending.pending_approval.request_id,
            checkpoint_id=pending.checkpoint_id,
            operator_id="offline-operator",
            decision=ApprovalDecision.APPROVE,
            reason="Offline verification.",
            decided_at=now,
        )
        workflow.record_decision(task.run_id, decision)
        accepted = workflow.resume(task.run_id)
        assert accepted.state.status is RunStatus.ACCEPTED

    if attempts:
        raise AssertionError(f"network attempts occurred: {attempts!r}")
    print("offline-langsmith-network-proof: ok")


if __name__ == "__main__":
    main()
