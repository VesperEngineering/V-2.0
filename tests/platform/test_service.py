from __future__ import annotations

from datetime import datetime, timezone

from vesper.platform.contracts import (
    EvidenceArtifactRef,
    ExecutionStatus,
    RiskDecision,
    RiskReviewDecision,
    RunStatus,
    SpecialistReceipt,
    ValidationCheck,
    ValidationResult,
)
from vesper.platform.persistence import PlatformPaths
from vesper.platform.cli import build_app
from vesper.platform.service import LocalPlatformService
from vesper.platform.workflow import WorkflowController, build_workflow
from typer.testing import CliRunner


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)


def evidence(request, name):
    return EvidenceArtifactRef(
        run_id=request.run_id,
        task_id=request.task_id,
        repository_revision=request.repository_revision,
        created_at=request.created_at,
        artifact_id=name,
        relative_path=f"runs/{request.run_id}/{name}.json",
        sha256="b" * 64,
        size_bytes=12,
        media_type="application/json",
    )


class Specialists:
    def execute(self, request):
        return SpecialistReceipt(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            receipt_id=f"{request.role.value}-{request.attempt}",
            role=request.role,
            attempt=request.attempt,
            status=ExecutionStatus.COMPLETED,
            evidence=(evidence(request, f"{request.role.value}-{request.attempt}"),),
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
                    name="tests",
                    passed=True,
                    command="pytest",
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
            rationale="Approved by deterministic fake.",
            evidence=(evidence(request, "risk"),),
        )


def runtime_factory(persistence):
    graph = build_workflow(
        checkpointer=persistence.checkpointer,
        store=persistence.langgraph_store,
        specialists=Specialists(),
        validator=Validator(),
        risk_reviewer=Reviewer(),
        clock=lambda: NOW,
    )
    return WorkflowController(graph=graph, store=persistence.store, clock=lambda: NOW)


def service(tmp_path, ids):
    identifiers = iter(ids)
    return LocalPlatformService(
        PlatformPaths.below(tmp_path / "platform"),
        controller_factory=runtime_factory,
        clock=lambda: NOW,
        id_factory=lambda: next(identifiers),
    )


def test_service_create_inspect_approve_and_resume(tmp_path):
    platform = service(tmp_path, ("run-001", "task-001", "approval-001"))

    created = platform.create_run("Build slice", str(tmp_path), "abc123")
    inspected = platform.inspect_run("run-001")
    approved = platform.approve_run(
        "run-001",
        created["checkpoint_id"],
        "operator",
        "Reviewed evidence",
    )
    accepted = platform.resume_run("run-001")

    assert created["status"] == RunStatus.AWAITING_APPROVAL.value
    assert inspected["status"] == RunStatus.AWAITING_APPROVAL.value
    assert approved["resume_required"] is True
    assert accepted["status"] == RunStatus.ACCEPTED.value


def test_service_rejects_pending_run_at_boundary(tmp_path):
    platform = service(tmp_path, ("run-001", "task-001", "approval-001"))
    created = platform.create_run("Build slice", str(tmp_path), "abc123")

    rejected = platform.reject_run(
        "run-001",
        created["checkpoint_id"],
        "operator",
        "Rejected after review",
    )

    assert rejected["status"] == RunStatus.REJECTED.value


def test_service_reopens_status_receipts_evidence_and_pending_approvals(tmp_path):
    paths = PlatformPaths.below(tmp_path / "platform")
    first = service(tmp_path, ("run-001", "task-001"))
    first.create_run("Build slice", str(tmp_path), "abc123")
    reopened = LocalPlatformService(
        paths,
        controller_factory=runtime_factory,
        clock=lambda: NOW,
        id_factory=lambda: "unused",
    )

    status = reopened.inspect_run("run-001")
    receipts = reopened.list_receipts("run-001")
    evidence_items = reopened.list_evidence("run-001")
    approvals = reopened.list_pending_approvals()

    assert status["status"] == RunStatus.AWAITING_APPROVAL.value
    assert len(receipts["receipts"]) == 2
    assert {item["artifact_id"] for item in evidence_items["evidence"]} >= {
        "validation",
        "risk",
    }
    assert approvals["pending"][0]["run_id"] == "run-001"


def test_service_cancel_is_explicit_and_persisted(tmp_path):
    platform = service(tmp_path, ("run-001", "task-001"))
    platform.create_run("Build slice", str(tmp_path), "abc123")

    cancelled = platform.cancel_run("run-001", "Operator cancelled")
    reopened = platform.inspect_run("run-001")

    assert cancelled["status"] == RunStatus.CANCELLED.value
    assert reopened["status"] == RunStatus.CANCELLED.value
    assert cancelled["pending_approval"] is None
    assert reopened["pending_approval"] is None


def test_default_cli_inspects_approves_and_resumes_persisted_graph(tmp_path):
    platform = service(tmp_path, ("run-001", "task-001"))
    created = platform.create_run("Build slice", str(tmp_path), "abc123")
    paths = platform.paths
    common_options = [
        "--state-db",
        str(paths.checkpoint_db),
        "--evidence-root",
        str(paths.evidence_root),
        "--json",
    ]
    runner = CliRunner()
    app = build_app()

    status = runner.invoke(app, [*common_options, "status", "run-001"])
    approved = runner.invoke(
        app,
        [
            *common_options,
            "approve",
            "run-001",
            "--checkpoint-id",
            created["checkpoint_id"],
            "--operator-id",
            "operator",
            "--reason",
            "Reviewed",
        ],
    )
    resumed = runner.invoke(app, [*common_options, "resume", "run-001"])

    assert status.exit_code == 0, status.output
    assert '"status": "awaiting-approval"' in status.output
    assert approved.exit_code == 0, approved.output
    assert '"resume_required": true' in approved.output
    assert resumed.exit_code == 0, resumed.output
    assert '"status": "accepted"' in resumed.output
