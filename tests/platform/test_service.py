from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from vesper.platform.contracts import (
    CodexExecutionReceipt,
    DataResearchResult,
    DevelopmentSpecialistOutput,
    EvidenceArtifactRef,
    ExecutionStatus,
    ModelEvaluationResult,
    ProductSpecialistOutput,
    RiskDecision,
    RiskReviewDecision,
    RunStatus,
    SpecialistReceipt,
    SpecialistRole,
    ValidationCheck,
    ValidationResult,
)
from vesper.platform.persistence import PlatformPaths, open_persistence
from vesper.platform.opencode import _process_identity
from vesper.platform.sandbox_runtime import DockerCodexRuntime
from vesper.platform.cli import build_app
from vesper.platform.service import (
    LocalPlatformService,
    SpecialistRuntimeUnavailable,
    _repository_lease,
)
from vesper.platform.workflow import WorkflowController, build_workflow
from typer.testing import CliRunner


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def copy_model_evaluation_fixture(repository: Path) -> None:
    config = repository / "config"
    config.mkdir(exist_ok=True)
    (config / "settings.yaml").write_text(
        "strategy:\n  params:\n    model_path: models/xgb_ranker.json\n",
        encoding="utf-8",
    )
    models = repository / "models"
    models.mkdir(exist_ok=True)
    shutil.copy2(REPOSITORY_ROOT / "models" / "xgb_ranker.json", models)
    shutil.copy2(REPOSITORY_ROOT / "models" / "xgb_ranker.metadata.json", models)


def create_knowledge_fixture(repository: Path) -> Path:
    knowledge = repository / "knowledge"
    note = knowledge / "skills" / "documentation-marker.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        """---
vesper_id: documentation-marker
vesper_kind: skill
vesper_status: approved
vesper_scope: shared
title: Harmless documentation marker
tags:
  - documentation
  - marker
---
# Harmless documentation marker

Create only the bounded documentation marker requested by the controller.
""",
        encoding="utf-8",
    )
    return knowledge


def test_service_syncs_searches_and_reports_repository_knowledge(tmp_path, monkeypatch):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    monkeypatch.chdir(repository)
    knowledge = create_knowledge_fixture(repository)
    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        knowledge_root=knowledge,
    )

    synchronized = platform.sync_knowledge()
    searched = platform.search_knowledge("documentation marker", "v20-development")
    status = platform.knowledge_status()

    assert synchronized == {"added": 1, "updated": 0, "unchanged": 0, "deleted": 0}
    assert [item["knowledge_id"] for item in searched["results"]] == ["documentation-marker"]
    assert status == {"documents": 1, "memory": 0, "skill": 1}
    with pytest.raises(SpecialistRuntimeUnavailable, match="unknown specialist role"):
        platform.search_knowledge("documentation marker", "unknown")


def test_operator_knowledge_commands_reject_vault_outside_current_repository(tmp_path, monkeypatch):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    monkeypatch.chdir(repository)
    external_knowledge = create_knowledge_fixture(tmp_path / "external")
    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        knowledge_root=external_knowledge,
    )

    with pytest.raises(SpecialistRuntimeUnavailable, match="inside the current repository"):
        platform.sync_knowledge()


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
        output = None
        if request.role.value == "v20-product":
            output = ProductSpecialistOutput(
                run_id=request.run_id,
                task_id=request.task_id,
                repository_revision=request.repository_revision,
                created_at=request.created_at,
                role=request.role,
                attempt=request.attempt,
                route=SpecialistRole.DEVELOPMENT,
                summary="Bounded task.",
                development_instructions="Implement only the bounded task.",
                acceptance_checks=("git-diff-check",),
            )
        elif request.role.value == "v20-development":
            output = DevelopmentSpecialistOutput(
                run_id=request.run_id,
                task_id=request.task_id,
                repository_revision=request.repository_revision,
                created_at=request.created_at,
                role=request.role,
                attempt=request.attempt,
                summary="Implemented bounded task.",
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
    def review(self, request, development_receipt, validation, **_research):
        return RiskReviewDecision(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            attempt=development_receipt.attempt,
            decision=RiskDecision.APPROVE,
            rationale="Approved by deterministic fake.",
            evidence=(evidence(request, "risk"),),
            scope_compliant=True,
            evidence_owned=True,
            prohibited_actions_compliant=True,
        )


class DataResearcher:
    def research(self, request):
        return DataResearchResult(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            available=True,
            database_path="vesper/data/massive/sp500/sp500_ohlcv.sqlite",
            table_name="sp500_ohlcv",
            row_count=100,
            ticker_count=10,
            start_date="2020-01-02",
            end_date="2026-07-27",
            required_columns=("ticker", "date", "open", "high", "low", "close", "volume"),
            null_price_rows=0,
            invalid_date_rows=0,
            split_adjustments_path="vesper/data/massive/split_adjustments.json",
            split_adjustments_sha256="c" * 64,
            evidence=(evidence(request, "data-research"),),
        )


class ModelEvaluator:
    def evaluate(self, request):
        return ModelEvaluationResult(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            available=True,
            configured_model_path="models/xgb_ranker.json",
            metadata_path="models/xgb_ranker.metadata.json",
            actual_sha256="d" * 64,
            expected_sha256="d" * 64,
            hash_matches=True,
            label_horizon=5,
            train_ic=0.04,
            out_of_sample_ic=0.03,
            train_samples=100,
            test_samples=50,
            evaluation_passed=True,
            evidence=(evidence(request, "model-evaluation"),),
        )


def runtime_factory(persistence):
    graph = build_workflow(
        checkpointer=persistence.checkpointer,
        store=persistence.langgraph_store,
        specialists=Specialists(),
        data_researcher=DataResearcher(),
        model_evaluator=ModelEvaluator(),
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
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    created = platform.create_run("Build slice", str(workspace), "abc123")
    inspected = platform.inspect_run("run-001")
    approved = platform.approve_run(
        "run-001",
        created["checkpoint_id"],
        "operator",
        "Reviewed evidence",
    )
    accepted = platform.resume_run("run-001")

    assert created["status"] == RunStatus.AWAITING_APPROVAL.value
    assert created["data_research"]["available"] is True
    assert created["model_evaluation"]["evaluation_passed"] is True
    assert inspected["status"] == RunStatus.AWAITING_APPROVAL.value
    assert approved["resume_required"] is True
    assert accepted["status"] == RunStatus.ACCEPTED.value


def test_service_rejects_unsafe_acceptance_checks_before_constructing_controller(tmp_path):
    constructed = False

    def should_not_construct(_persistence):
        nonlocal constructed
        constructed = True
        raise AssertionError("controller must not start")

    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "platform"),
        controller_factory=should_not_construct,
    )

    with pytest.raises(SpecialistRuntimeUnavailable, match="unsafe deterministic"):
        platform.create_run(
            "Do not run",
            str(tmp_path),
            "abc123",
            ("shell::whoami",),
        )

    assert constructed is False
    assert not platform.paths.checkpoint_db.exists()


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"specialist_runtime": "unknown"}, "unsupported specialist runtime"),
        ({"specialist_runtime": "opencode"}, "exact provider/model"),
        ({"opencode_model": "opencode/model"}, "require the OpenCode runtime"),
        ({"allow_repository_root_workspace": True}, "requires the OpenCode runtime"),
        (
            {
                "specialist_runtime": "opencode",
                "opencode_model": "opencode/model",
                "allow_repository_root_workspace": True,
                "require_disposable_worktree": False,
            },
            "requires a standalone disposable clone",
        ),
        (
            {
                "specialist_runtime": "opencode",
                "opencode_model": "opencode/model",
                "opencode_credential_environment_key": "",
            },
            "cannot be empty",
        ),
    ],
)
def test_service_rejects_invalid_runtime_configuration(tmp_path, options, message):
    with pytest.raises(SpecialistRuntimeUnavailable, match=message):
        LocalPlatformService(PlatformPaths.below(tmp_path / "platform"), **options)


def test_service_rejects_pending_run_at_boundary(tmp_path):
    platform = service(tmp_path, ("run-001", "task-001", "approval-001"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    created = platform.create_run("Build slice", str(workspace), "abc123")

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
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first.create_run("Build slice", str(workspace), "abc123")
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
        "data-research",
        "model-evaluation",
        "validation",
        "risk",
    }
    assert approvals["pending"][0]["run_id"] == "run-001"


def test_active_listing_is_read_only_when_graph_has_terminal_status(tmp_path):
    platform = service(tmp_path, ("run-001", "task-001"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    platform.create_run("Build slice", str(workspace), "abc123")
    platform.control.set_run_status("run-001", "running")

    active = platform.list_active_runs()

    assert active == {"active": []}
    assert platform.control.run_record("run-001")["status"] == "running"


def test_inspection_does_not_overwrite_live_control_status(tmp_path):
    platform = service(tmp_path, ("run-001", "task-001"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    platform.create_run("Build slice", str(workspace), "abc123")
    platform.control.set_run_status("run-001", "running")

    inspected = platform.inspect_run("run-001")

    assert inspected["status"] == RunStatus.AWAITING_APPROVAL.value
    assert platform.control.run_record("run-001")["status"] == "running"


def test_service_cancel_is_explicit_and_persisted(tmp_path):
    platform = service(tmp_path, ("run-001", "task-001"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    platform.create_run("Build slice", str(workspace), "abc123")

    cancelled = platform.cancel_run("run-001", "Operator cancelled")
    reopened = platform.inspect_run("run-001")

    assert cancelled["status"] == RunStatus.CANCELLED.value
    assert reopened["status"] == RunStatus.CANCELLED.value
    assert cancelled["pending_approval"] is None
    assert reopened["pending_approval"] is None


def test_default_cli_inspects_approves_and_resumes_persisted_graph(tmp_path):
    platform = service(tmp_path, ("run-001", "task-001"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    created = platform.create_run("Build slice", str(workspace), "abc123")
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


class CompositionAdapter:
    authentication_type = "chatgpt"
    permission_profile = "docker-one-shot"

    def __init__(self):
        self.calls = []

    def execute(self, item, **kwargs):
        self.calls.append((item, kwargs))
        if item.role.value == "v20-product":
            output = {
                "schema_version": "1.0",
                "run_id": item.run_id,
                "task_id": item.task_id,
                "repository_revision": item.repository_revision,
                "created_at": item.created_at.isoformat().replace("+00:00", "Z"),
                "role": item.role.value,
                "attempt": item.attempt,
                "route": "v20-development",
                "summary": "Bounded documentation exercise.",
                "development_instructions": "Create M2-CONTROLLED-EXERCISE.md.",
                "acceptance_checks": ["git-diff-check"],
                "memory": [
                    {
                        "memory_type": "product-decision",
                        "content": "Product routed task to v20-development.",
                        "confidence": 0.9,
                    }
                ],
            }
        elif item.role.value == "v20-development":
            Path(item.workspace, "M2-CONTROLLED-EXERCISE.md").write_text(
                "# V20 M2 controlled exercise\n",
                encoding="utf-8",
            )
            output = {
                "schema_version": "1.0",
                "run_id": item.run_id,
                "task_id": item.task_id,
                "repository_revision": item.repository_revision,
                "created_at": item.created_at.isoformat().replace("+00:00", "Z"),
                "role": item.role.value,
                "attempt": item.attempt,
                "summary": "Created the requested file.",
                "changed_files": ["M2-CONTROLLED-EXERCISE.md"],
                "verification_commands": [],
                "residual_risks": [],
                "memory": [
                    {
                        "memory_type": "development-episode",
                        "content": (
                            "Validated Development attempt 1; "
                            "changed_files=M2-CONTROLLED-EXERCISE.md"
                        ),
                        "confidence": 0.9,
                    }
                ],
            }
        else:
            output = {
                "schema_version": "1.0",
                "run_id": item.run_id,
                "task_id": item.task_id,
                "repository_revision": item.repository_revision,
                "created_at": item.created_at.isoformat().replace("+00:00", "Z"),
                "role": item.role.value,
                "attempt": item.attempt,
                "decision": "approve",
                "rationale": "The isolated documentation change is supported.",
                "reviewed_changed_files": ["M2-CONTROLLED-EXERCISE.md"],
                "scope_compliant": True,
                "evidence_owned": True,
                "prohibited_actions_compliant": True,
                "residual_risks": [],
                "memory": [
                    {
                        "memory_type": "risk-decision",
                        "content": "Risk Review decision=approve; attempt=1",
                        "confidence": 0.9,
                    }
                ],
            }
        return CodexExecutionReceipt(
            run_id=item.run_id,
            task_id=item.task_id,
            repository_revision=item.repository_revision,
            created_at=item.created_at,
            execution_id=f"exec-{item.role.value}-{item.attempt}",
            role=item.role,
            attempt=item.attempt,
            status=ExecutionStatus.COMPLETED,
            sandbox=item.permissions.sandbox,
            model=kwargs["model"],
            workspace=item.workspace,
            approval_mode="deny-all",
            authentication_type=self.authentication_type,
            permission_profile=self.permission_profile,
            started_at=NOW,
            finished_at=NOW,
            thread_id=f"thread-{item.role.value}",
            final_response=json.dumps(output),
        )


class OpenCodeCompositionAdapter(CompositionAdapter):
    authentication_type = "opencode-local"
    permission_profile = "opencode-host"


@pytest.mark.parametrize(
    ("specialist_runtime", "model", "adapter_type"),
    [
        ("docker-codex", None, CompositionAdapter),
        ("opencode", "opencode/north-mini-code-free", OpenCodeCompositionAdapter),
    ],
)
def test_service_loads_selected_production_composition_without_real_provider(
    tmp_path, specialist_runtime, model, adapter_type
):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    (repository / "README.md").write_text("test repository\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=V20 Test",
            "-c",
            "user.email=v20-test@example.invalid",
            "commit",
            "-q",
            "-m",
            "baseline",
        ],
        cwd=repository,
        check=True,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    profiles = repository / "profiles" / "native"
    shutil.copytree(REPOSITORY_ROOT / "profiles" / "native", profiles)
    copy_model_evaluation_fixture(repository)
    knowledge = create_knowledge_fixture(repository)
    workspace = repository / "exercise"
    workspace.mkdir()
    identifiers = iter(
        (
            "run-001",
            "task-001",
            "candidate-product",
            "memory-product",
            "candidate-development",
            "memory-development",
            "candidate-risk",
            "memory-risk",
        )
    )
    adapter = adapter_type()
    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        profiles_root=profiles,
        adapter_factory=lambda repository_root, models: adapter,
        specialist_runtime=specialist_runtime,
        opencode_model=model,
        knowledge_root=knowledge,
        require_disposable_worktree=False,
        require_clean_worktree=False,
        approved_workspace_relative_paths=(Path("exercise"),),
        clock=lambda: NOW,
        id_factory=lambda: next(identifiers),
    )

    created = platform.create_run(
        "Create a harmless documentation marker.",
        str(workspace),
        revision,
        (
            "git-diff-check",
            "path-exists::M2-CONTROLLED-EXERCISE.md",
            "file-contains::M2-CONTROLLED-EXERCISE.md::V20 M2 controlled exercise",
        ),
    )

    assert created["status"] == RunStatus.AWAITING_APPROVAL.value
    assert Path(workspace, "M2-CONTROLLED-EXERCISE.md").is_file()
    assert len(platform.list_receipts("run-001")["receipts"]) == 3
    assert len(adapter.calls) == 3
    assert all("<v20_knowledge>" in call[1]["prompt"] for call in adapter.calls)
    assert all("Harmless documentation marker" in call[1]["prompt"] for call in adapter.calls)
    with open_persistence(platform.paths) as persisted:
        runtime = persisted.store.get(("system", "run-runtime"), "run-001")
        assert runtime["specialist_runtime"] == specialist_runtime
        assert runtime["specialist_model"] == model
        assert runtime["research_data_root"] == str(REPOSITORY_ROOT / "vesper" / "data" / "massive")
        assert runtime["knowledge_root"] == str(knowledge)
        assert (
            persisted.store.get(
                ("runs", "run-001", "knowledge"),
                SpecialistRole.DEVELOPMENT.value,
            )
            is not None
        )
        assert (
            len(
                persisted.store.search(
                    ("profiles", "v20-product", "product-decisions"),
                    limit=10,
                )
            )
            == 1
        )
        assert (
            len(
                persisted.store.search(
                    ("profiles", "v20-development", "development-episodes"),
                    limit=10,
                )
            )
            == 1
        )
        assert (
            len(
                persisted.store.search(
                    ("profiles", "v20-risk-review", "risk-decisions"),
                    limit=10,
                )
            )
            == 1
        )

    (profiles / "v20-product" / "SOUL.md").write_text(
        "modified after checkpoint\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecialistRuntimeUnavailable, match="profile bytes"):
        platform.resume_run("run-001")


def test_opencode_service_allows_explicit_clean_disposable_clone_root(tmp_path):
    origin = tmp_path / "origin.git"
    repository = tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(repository)], check=True)
    subprocess.run(["git", "switch", "-q", "-c", "m2/root-workspace"], cwd=repository, check=True)
    profiles = repository / "profiles" / "native"
    shutil.copytree(REPOSITORY_ROOT / "profiles" / "native", profiles)
    copy_model_evaluation_fixture(repository)
    create_knowledge_fixture(repository)
    (repository / "README.md").write_text("test repository\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=V20 Test",
            "-c",
            "user.email=v20-test@example.invalid",
            "commit",
            "-q",
            "-m",
            "baseline",
        ],
        cwd=repository,
        check=True,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    identifiers = iter(
        (
            "run-001",
            "task-001",
            "candidate-product",
            "memory-product",
            "candidate-development",
            "memory-development",
            "candidate-risk",
            "memory-risk",
        )
    )
    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        profiles_root=profiles,
        adapter_factory=lambda _root, _models: OpenCodeCompositionAdapter(),
        specialist_runtime="opencode",
        opencode_model="opencode/mimo-v2.5-free",
        allow_repository_root_workspace=True,
        clock=lambda: NOW,
        id_factory=lambda: next(identifiers),
    )

    created = platform.create_run(
        "Create a harmless root-workspace marker.",
        str(repository),
        revision,
        (
            "git-diff-check",
            "path-exists::M2-CONTROLLED-EXERCISE.md",
        ),
    )

    assert created["status"] == RunStatus.AWAITING_APPROVAL.value
    assert (repository / "M2-CONTROLLED-EXERCISE.md").is_file()


def test_repository_lease_rejects_concurrent_controller_operation(tmp_path):
    repository = tmp_path / "repo"
    (repository / ".git").mkdir(parents=True)

    with _repository_lease(repository):
        with pytest.raises(SpecialistRuntimeUnavailable, match="owns the repository lease"):
            with _repository_lease(repository):
                pass


def test_research_data_root_cannot_overlap_specialist_repository(tmp_path):
    repository = tmp_path / "repo"
    workspace = repository / "docs" / "m2-controlled-exercise"
    workspace.mkdir(parents=True)
    profiles = repository / "profiles" / "native"
    profiles.mkdir(parents=True)
    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        profiles_root=profiles,
        research_data_root=repository / "vesper" / "data" / "massive",
        require_disposable_worktree=False,
    )

    with pytest.raises(SpecialistRuntimeUnavailable, match="must not overlap"):
        platform._validate_production_boundaries(repository, workspace)


def test_platform_state_cannot_overlap_research_data_root(tmp_path):
    repository = tmp_path / "repo"
    workspace = repository / "docs" / "m2-controlled-exercise"
    workspace.mkdir(parents=True)
    profiles = repository / "profiles" / "native"
    profiles.mkdir(parents=True)
    research_data_root = tmp_path / "protected-massive"
    platform = LocalPlatformService(
        PlatformPaths.below(research_data_root / "platform-state"),
        profiles_root=profiles,
        research_data_root=research_data_root,
        require_disposable_worktree=False,
    )

    with pytest.raises(SpecialistRuntimeUnavailable, match="must not overlap the research"):
        platform._validate_production_boundaries(repository, workspace)


def test_resume_revalidates_evidence_root_boundary(tmp_path):
    repository = tmp_path / "repo"
    workspace = repository / "docs" / "m2-controlled-exercise"
    workspace.mkdir(parents=True)
    profiles = repository / "profiles" / "native"
    shutil.copytree(REPOSITORY_ROOT / "profiles" / "native", profiles)
    state = tmp_path / "state"
    paths = PlatformPaths(
        root=state,
        checkpoint_db=state / "checkpoints.sqlite3",
        store_db=state / "store.sqlite3",
        knowledge_index_db=state / "knowledge-index.sqlite3",
        evidence_root=repository / "controller-evidence",
    )
    research_data_root = tmp_path / "protected-massive"
    platform = LocalPlatformService(
        paths,
        profiles_root=profiles,
        research_data_root=research_data_root,
        require_disposable_worktree=False,
    )
    with open_persistence(paths) as persistence:
        persistence.store.put(
            ("system", "run-runtime"),
            "run-001",
            {
                "repository_root": str(repository),
                "workspace": str(workspace),
                "repository_revision": "abc123",
                "profiles_root": str(profiles),
                "profile_fingerprints": platform._profile_fingerprints(),
                "research_data_root": str(research_data_root),
            },
        )

        with pytest.raises(SpecialistRuntimeUnavailable, match="platform state and evidence"):
            platform._controller_for_run(persistence, "run-001")


def test_resume_rejects_missing_persisted_research_data_root(tmp_path):
    repository = tmp_path / "repo"
    workspace = repository / "docs" / "m2-controlled-exercise"
    workspace.mkdir(parents=True)
    profiles = repository / "profiles" / "native"
    shutil.copytree(REPOSITORY_ROOT / "profiles" / "native", profiles)
    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        profiles_root=profiles,
        research_data_root=tmp_path / "protected-massive",
        require_disposable_worktree=False,
    )
    with open_persistence(platform.paths) as persistence:
        persistence.store.put(
            ("system", "run-runtime"),
            "run-001",
            {
                "repository_root": str(repository),
                "workspace": str(workspace),
                "repository_revision": "abc123",
                "profiles_root": str(profiles),
                "profile_fingerprints": platform._profile_fingerprints(),
            },
        )

        with pytest.raises(SpecialistRuntimeUnavailable, match="metadata is malformed"):
            platform._controller_for_run(persistence, "run-001")


@pytest.mark.parametrize("custom_runtime", (False, True))
def test_stale_active_record_is_preserved_when_reconciliation_is_unsafe(
    tmp_path,
    custom_runtime,
):
    repository = tmp_path / "repo"
    (repository / ".git").mkdir(parents=True)
    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        adapter_factory=(lambda _root, _models: object()) if custom_runtime else None,
    )
    execution_id = "execution-001"
    sandbox_name = DockerCodexRuntime.expected_sandbox_name(
        SpecialistRole.DEVELOPMENT.value,
        execution_id,
    )
    if not custom_runtime:
        sandbox_name = "v20-unrelated-sandbox"
    platform.control.mark_active(
        run_id="run-001",
        execution_id=execution_id,
        sandbox_name=sandbox_name,
        role=SpecialistRole.DEVELOPMENT.value,
        attempt=1,
    )

    persistence = SimpleNamespace(
        store=SimpleNamespace(get=lambda _namespace, _key: {"repository_root": str(repository)})
    )
    expected = "custom runtime" if custom_runtime else "sandbox identity"
    with pytest.raises(SpecialistRuntimeUnavailable, match=expected):
        with platform._lease_for_run(persistence, "run-001"):
            pass

    assert platform.control.active_execution("run-001") is not None


def test_active_record_must_match_requested_run_id(tmp_path):
    repository = tmp_path / "repo"
    (repository / ".git").mkdir(parents=True)
    platform = LocalPlatformService(PlatformPaths.below(tmp_path / "state"))
    execution_id = "execution-001"
    role = SpecialistRole.PRODUCT.value
    platform.control.mark_active(
        run_id="run-001",
        execution_id=execution_id,
        sandbox_name=DockerCodexRuntime.expected_sandbox_name(role, execution_id),
        role=role,
        attempt=1,
    )
    active_path = platform.control.root / "run-001" / "active.json"
    payload = json.loads(active_path.read_text(encoding="utf-8"))
    payload["run_id"] = "different-run"
    active_path.write_text(json.dumps(payload), encoding="utf-8")
    persistence = SimpleNamespace(
        store=SimpleNamespace(get=lambda _namespace, _key: {"repository_root": str(repository)})
    )

    with pytest.raises(SpecialistRuntimeUnavailable, match="sandbox identity"):
        with platform._lease_for_run(persistence, "run-001"):
            pass

    assert platform.control.active_execution("run-001") is not None


def test_stale_opencode_process_is_terminated_after_controller_loss(tmp_path):
    repository = tmp_path / "repo"
    (repository / ".git").mkdir(parents=True)
    platform = LocalPlatformService(PlatformPaths.below(tmp_path / "state"))
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        identity = _process_identity(child.pid)
        assert identity is not None
        platform.control.mark_active_process(
            run_id="run-001",
            execution_id="execution-001",
            runtime="opencode",
            process_id=child.pid,
            process_identity=identity,
            role=SpecialistRole.DEVELOPMENT.value,
            attempt=1,
        )
        persistence = SimpleNamespace(
            store=SimpleNamespace(
                get=lambda _namespace, _key: {
                    "repository_root": str(repository),
                    "specialist_runtime": "opencode",
                }
            )
        )

        with platform._lease_for_run(persistence, "run-001"):
            pass

        child.wait(timeout=5)
        assert platform.control.active_execution("run-001") is None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_unidentifiable_opencode_process_record_is_preserved(tmp_path, monkeypatch):
    repository = tmp_path / "repo"
    (repository / ".git").mkdir(parents=True)
    platform = LocalPlatformService(PlatformPaths.below(tmp_path / "state"))
    platform.control.mark_active_process(
        run_id="run-001",
        execution_id="execution-001",
        runtime="opencode",
        process_id=os.getpid(),
        process_identity="recorded-identity",
        role=SpecialistRole.DEVELOPMENT.value,
        attempt=1,
    )
    persistence = SimpleNamespace(
        store=SimpleNamespace(
            get=lambda _namespace, _key: {
                "repository_root": str(repository),
                "specialist_runtime": "opencode",
            }
        )
    )
    monkeypatch.setattr("vesper.platform.service._process_identity", lambda _pid: None)
    monkeypatch.setattr("vesper.platform.service._process_exists", lambda _pid: None)

    with pytest.raises(SpecialistRuntimeUnavailable, match="cannot be identified"):
        with platform._lease_for_run(persistence, "run-001"):
            pass

    assert platform.control.active_execution("run-001") is not None


def test_cancel_run_signals_active_sandbox_from_another_controller_thread(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    profiles = repository / "profiles" / "native"
    shutil.copytree(REPOSITORY_ROOT / "profiles" / "native", profiles)
    copy_model_evaluation_fixture(repository)
    create_knowledge_fixture(repository)
    workspace = repository / "exercise"
    workspace.mkdir()
    (workspace / "README.md").write_text("bounded\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=V20 Test",
            "-c",
            "user.email=v20-test@example.invalid",
            "commit",
            "-q",
            "-m",
            "baseline",
        ],
        cwd=repository,
        check=True,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    started = threading.Event()

    class BlockingAdapter:
        def execute(self, item, **kwargs):
            started.set()
            cancellation = kwargs["cancellation"]
            while not cancellation.is_set():
                time.sleep(0.001)
            return CodexExecutionReceipt(
                run_id=item.run_id,
                task_id=item.task_id,
                repository_revision=item.repository_revision,
                created_at=item.created_at,
                execution_id=kwargs["execution_id"],
                role=item.role,
                attempt=item.attempt,
                status=ExecutionStatus.CANCELLED,
                sandbox=item.permissions.sandbox,
                model=kwargs["model"],
                workspace=item.workspace,
                approval_mode="deny-all",
                authentication_type="chatgpt",
                permission_profile="docker-one-shot",
                started_at=NOW,
                finished_at=NOW,
                error_code="cancelled",
            )

    def runner(command, _workspace, _timeout):
        marker = command[1] if len(command) > 1 else None
        stdout = '{"sandboxes":[]}' if marker == "ls" else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    identifiers = iter(("run-001", "task-001"))
    platform = None

    def adapter_factory(repository_root, models):
        return DockerCodexRuntime(
            repository_root=repository_root,
            approved_models=models,
            executable="sbx-test",
            runner=runner,
            adapter_factory=lambda _name: BlockingAdapter(),
            control=platform.control,
            clock=lambda: NOW,
        )

    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        profiles_root=profiles,
        adapter_factory=adapter_factory,
        require_disposable_worktree=False,
        approved_workspace_relative_paths=(Path("exercise"),),
        clock=lambda: NOW,
        id_factory=lambda: next(identifiers),
    )
    create_result = {}
    worker = threading.Thread(
        target=lambda: create_result.setdefault(
            "payload",
            platform.create_run("Wait for cancellation.", str(workspace), revision),
        )
    )
    worker.start()
    assert started.wait(timeout=5)

    active = platform.list_active_runs()["active"]
    cancelled = platform.cancel_run("run-001", "operator cancelled active turn")
    worker.join(timeout=5)

    assert active[0]["run_id"] == "run-001"
    assert active[0]["active_execution"]["role"] == "v20-product"
    assert not worker.is_alive()
    assert cancelled["status"] == RunStatus.CANCELLED.value
    assert create_result["payload"]["status"] == RunStatus.CANCELLED.value
    assert platform.list_active_runs() == {"active": []}


def test_read_only_inspection_survives_removed_worktree_and_profile_catalog(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    (repository / "README.md").write_text("test repository\n", encoding="utf-8")
    create_knowledge_fixture(repository)
    subprocess.run(["git", "add", "README.md", "knowledge"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=V20 Test",
            "-c",
            "user.email=v20-test@example.invalid",
            "commit",
            "-q",
            "-m",
            "baseline",
        ],
        cwd=repository,
        check=True,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    profiles = repository / "profiles" / "native"
    shutil.copytree(REPOSITORY_ROOT / "profiles" / "native", profiles)
    copy_model_evaluation_fixture(repository)
    workspace = repository / "exercise"
    workspace.mkdir()
    identifiers = iter(
        (
            "run-001",
            "task-001",
            "candidate-product",
            "memory-product",
            "candidate-development",
            "memory-development",
            "candidate-risk",
            "memory-risk",
        )
    )
    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        profiles_root=profiles,
        adapter_factory=lambda repository_root, models: CompositionAdapter(),
        require_disposable_worktree=False,
        require_clean_worktree=False,
        approved_workspace_relative_paths=(Path("exercise"),),
        clock=lambda: NOW,
        id_factory=lambda: next(identifiers),
    )
    created = platform.create_run(
        "Create a harmless documentation marker.",
        str(workspace),
        revision,
        (
            "git-diff-check",
            "path-exists::M2-CONTROLLED-EXERCISE.md",
            "file-contains::M2-CONTROLLED-EXERCISE.md::V20 M2 controlled exercise",
        ),
    )
    repository.rename(tmp_path / "repo-retained-outside-runtime")

    assert platform.inspect_run("run-001")["status"] == "awaiting-approval"
    assert len(platform.list_receipts("run-001")["receipts"]) == 3
    assert platform.list_evidence("run-001")["evidence"]
    assert platform.list_pending_approvals()["pending"][0]["run_id"] == "run-001"
    with pytest.raises(RuntimeError):
        platform.resume_run("run-001")
    assert created["checkpoint_id"]


def test_production_service_rejects_revision_not_equal_to_worktree_head(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    (repository / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=V20 Test",
            "-c",
            "user.email=v20-test@example.invalid",
            "commit",
            "-q",
            "-m",
            "baseline",
        ],
        cwd=repository,
        check=True,
    )
    profiles = repository / "profiles" / "native"
    shutil.copytree(REPOSITORY_ROOT / "profiles" / "native", profiles)
    copy_model_evaluation_fixture(repository)
    workspace = repository / "exercise"
    workspace.mkdir()
    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        profiles_root=profiles,
        adapter_factory=lambda repository_root, models: CompositionAdapter(),
        require_disposable_worktree=False,
        require_clean_worktree=False,
        approved_workspace_relative_paths=(Path("exercise"),),
    )

    with pytest.raises(SpecialistRuntimeUnavailable, match="repository revision"):
        platform.create_run("Bounded task", str(workspace), "foreign-revision")


def test_production_service_rejects_platform_state_overlapping_repository(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    workspace = repository / "exercise"
    workspace.mkdir()
    profiles = repository / "profiles" / "native"
    shutil.copytree(REPOSITORY_ROOT / "profiles" / "native", profiles)
    copy_model_evaluation_fixture(repository)
    platform = LocalPlatformService(
        PlatformPaths.below(repository / ".v20-platform"),
        profiles_root=profiles,
        adapter_factory=lambda repository_root, models: CompositionAdapter(),
        require_disposable_worktree=False,
        require_clean_worktree=False,
        approved_workspace_relative_paths=(Path("exercise"),),
    )

    with pytest.raises(SpecialistRuntimeUnavailable, match="platform state"):
        platform.create_run("Bounded task", str(workspace), "unused")


def test_production_service_rejects_sensitive_repository_workspace_before_specialists(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    workspace = repository / "config"
    workspace.mkdir()
    profiles = repository / "profiles" / "native"
    shutil.copytree(REPOSITORY_ROOT / "profiles" / "native", profiles)
    copy_model_evaluation_fixture(repository)
    called = False

    def adapter_factory(_repository_root, _models):
        nonlocal called
        called = True
        return CompositionAdapter()

    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        profiles_root=profiles,
        adapter_factory=adapter_factory,
        require_disposable_worktree=False,
        require_clean_worktree=False,
    )

    with pytest.raises(SpecialistRuntimeUnavailable, match="documentation boundary"):
        platform.create_run("Unsafe workspace", str(workspace), "unused")

    assert called is False
