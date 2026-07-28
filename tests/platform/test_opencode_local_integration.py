from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.platform.contracts import (
    ExecutionStatus,
    PermissionSet,
    RunStatus,
    SandboxMode,
    SpecialistInput,
    SpecialistRole,
)
from vesper.platform.opencode import OpenCodeGateway
from vesper.platform.persistence import PlatformPaths
from vesper.platform.service import LocalPlatformService


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILES_ROOT = REPOSITORY_ROOT / "profiles" / "native"


pytestmark = [
    pytest.mark.local_opencode,
    pytest.mark.skipif(
        os.environ.get("V20_ENABLE_OPENCODE_INTEGRATION") != "1",
        reason="requires explicit operator opt-in and a locally usable OpenCode provider",
    ),
]


def _credential_environment_keys(model: str) -> dict[str, str] | None:
    key = os.environ.get("V20_OPENCODE_INTEGRATION_CREDENTIAL_KEY")
    return None if key is None else {model.split("/", maxsplit=1)[0]: key}


def _copy_model_evaluation_fixture(repository: Path) -> None:
    config = repository / "config"
    config.mkdir()
    (config / "settings.yaml").write_text(
        "strategy:\n  params:\n    model_path: models/xgb_ranker.json\n",
        encoding="utf-8",
    )
    models = repository / "models"
    models.mkdir()
    shutil.copy2(REPOSITORY_ROOT / "models" / "xgb_ranker.json", models)
    shutil.copy2(REPOSITORY_ROOT / "models" / "xgb_ranker.metadata.json", models)


def test_real_opencode_boundary_is_read_only(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    now = datetime.now(timezone.utc)
    request = SpecialistInput(
        run_id="opencode-local-integration",
        task_id="opencode-local-integration",
        repository_revision="operator-enabled",
        created_at=now,
        role=SpecialistRole.RISK_REVIEW,
        attempt=1,
        instructions="Reply with the single word ready without changing files.",
        workspace=str(workspace),
        memory_namespace=("profiles", "v20-risk-review", "risk-decisions"),
        permissions=PermissionSet(
            sandbox=SandboxMode.READ_ONLY,
            read_paths=(str(workspace),),
            allowed_tools=("read",),
        ),
    )
    model = os.environ["V20_OPENCODE_INTEGRATION_MODEL"]
    gateway = OpenCodeGateway(
        repository_root=tmp_path,
        approved_models=(model,),
        credential_environment_keys=_credential_environment_keys(model),
    )

    receipt = gateway.execute(
        request,
        prompt="Reply with the single word ready without changing files.",
        model=model,
        timeout_seconds=90,
        execution_id="opencode-local-integration",
        reasoning_effort=None,
        output_schema=None,
    )

    assert receipt.status is ExecutionStatus.COMPLETED
    assert receipt.final_response == "ready"
    assert list(workspace.iterdir()) == []


def test_real_opencode_completes_controlled_workflow_to_human_approval(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    profiles = repository / "profiles" / "native"
    shutil.copytree(PROFILES_ROOT, profiles)
    _copy_model_evaluation_fixture(repository)
    workspace = repository / "docs" / "m2-controlled-exercise"
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text("# Controlled exercise\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=V20 OpenCode Test",
            "-c",
            "user.email=v20-opencode@example.invalid",
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
    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        profiles_root=profiles,
        specialist_runtime="opencode",
        opencode_model=os.environ["V20_OPENCODE_INTEGRATION_MODEL"],
        opencode_credential_environment_key=os.environ.get(
            "V20_OPENCODE_INTEGRATION_CREDENTIAL_KEY"
        ),
        require_disposable_worktree=False,
    )

    created = platform.create_run(
        "Create only OPENCODE-CONTROLLED.md containing the exact line "
        "'OpenCode controlled workflow'.",
        str(workspace),
        revision,
        (
            "git-diff-check",
            "path-exists::OPENCODE-CONTROLLED.md",
            "file-contains::OPENCODE-CONTROLLED.md::OpenCode controlled workflow",
        ),
    )

    assert created["status"] == RunStatus.AWAITING_APPROVAL.value
    assert created["data_research"]["available"] is True
    assert created["model_evaluation"]["evaluation_passed"] is True
    assert (workspace / "OPENCODE-CONTROLLED.md").read_text(encoding="utf-8").strip() == (
        "OpenCode controlled workflow"
    )
    receipts = platform.list_receipts(str(created["run_id"]))["receipts"]
    roles = [receipt["role"] for receipt in receipts]
    assert roles[0] == SpecialistRole.PRODUCT.value
    assert roles[-1] == SpecialistRole.RISK_REVIEW.value
    assert set(roles) == {role.value for role in SpecialistRole}
    assert 1 <= roles.count(SpecialistRole.DEVELOPMENT.value) <= 3
    assert len(receipts) <= 7
    assert all(receipt["status"] == ExecutionStatus.COMPLETED.value for receipt in receipts)
    assert platform.list_pending_approvals()["pending"][0]["run_id"] == created["run_id"]


def test_real_opencode_modifies_code_in_disposable_clone_root(tmp_path):
    origin = tmp_path / "origin.git"
    repository = tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(repository)], check=True)
    subprocess.run(["git", "switch", "-q", "-c", "m2/root-code"], cwd=repository, check=True)
    profiles = repository / "profiles" / "native"
    shutil.copytree(PROFILES_ROOT, profiles)
    _copy_model_evaluation_fixture(repository)
    source = repository / "calculator.py"
    source.write_text("def add(left, right):\n    return 0\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=V20 OpenCode Test",
            "-c",
            "user.email=v20-opencode@example.invalid",
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
    git_config_before = (repository / ".git" / "config").read_bytes()
    profile_before = (profiles / "v20-development" / "profile.yaml").read_bytes()
    platform = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        profiles_root=profiles,
        specialist_runtime="opencode",
        opencode_model=os.environ["V20_OPENCODE_INTEGRATION_MODEL"],
        opencode_credential_environment_key=os.environ.get(
            "V20_OPENCODE_INTEGRATION_CREDENTIAL_KEY"
        ),
        allow_repository_root_workspace=True,
    )

    created = platform.create_run(
        "Fix calculator.py so add(left, right) returns left + right. Modify no other file.",
        str(repository),
        revision,
        (
            "git-diff-check",
            "file-contains::calculator.py::return left + right",
        ),
    )

    assert created["status"] == RunStatus.AWAITING_APPROVAL.value
    assert created["data_research"]["available"] is True
    assert created["data_research"]["ticker_count"] > 0
    assert created["model_evaluation"]["evaluation_passed"] is True
    assert "return left + right" in source.read_text(encoding="utf-8")
    assert (repository / ".git" / "config").read_bytes() == git_config_before
    assert (profiles / "v20-development" / "profile.yaml").read_bytes() == profile_before
    changed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert changed == ["calculator.py"]
    evidence_ids = {
        item["artifact_id"] for item in platform.list_evidence(str(created["run_id"]))["evidence"]
    }
    assert {"data-research", "model-evaluation"}.issubset(evidence_ids)
    assert platform.list_pending_approvals()["pending"][0]["run_id"] == created["run_id"]
