from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.platform.contracts import (
    ExecutionStatus,
    PermissionSet,
    SandboxMode,
    SpecialistInput,
    SpecialistRole,
)
from vesper.platform.evidence import FilesystemEvidenceStore
from vesper.platform.opencode import ModelNotApprovedError, OpenCodeGateway, WorkspaceDeniedError
from vesper.platform.profiles import ProfileCatalog


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILES_ROOT = REPOSITORY_ROOT / "profiles" / "native"


def request(
    workspace: Path, *, role: SpecialistRole = SpecialistRole.DEVELOPMENT
) -> SpecialistInput:
    permissions = PermissionSet(
        sandbox=SandboxMode.WORKSPACE_WRITE,
        read_paths=(str(workspace),),
        write_paths=(str(workspace),),
        allowed_tools=("read", "search", "write", "test"),
    )
    if role is not SpecialistRole.DEVELOPMENT:
        permissions = PermissionSet(
            sandbox=SandboxMode.READ_ONLY,
            read_paths=(str(workspace),),
            allowed_tools=("read", "search"),
        )
    return SpecialistInput(
        run_id="run-001",
        task_id="task-001",
        repository_revision="b5263eb",
        created_at=NOW,
        role=role,
        attempt=1,
        instructions="Implement the bounded change.",
        workspace=str(workspace),
        memory_namespace=("profiles", role.value, "episodes"),
        permissions=permissions,
    )


def gateway(tmp_path, runner) -> OpenCodeGateway:
    return OpenCodeGateway(
        repository_root=tmp_path,
        profiles=ProfileCatalog(PROFILES_ROOT),
        evidence=FilesystemEvidenceStore(tmp_path / "evidence"),
        approved_models=("openai/gpt-approved",),
        executable="opencode-test",
        runner=runner,
        clock=lambda: NOW,
    )


def test_gateway_runs_exact_model_with_scrubbed_environment_and_metadata_evidence(tmp_path):
    captured: dict[str, object] = {}

    def runner(command, workspace, environment, timeout_seconds):
        captured["command"] = command
        captured["workspace"] = workspace
        captured["environment"] = environment
        captured["timeout"] = timeout_seconds
        captured["config"] = json.loads(
            Path(environment["OPENCODE_CONFIG"]).read_text(encoding="utf-8")
        )
        return subprocess.CompletedProcess(command, 0, stdout="model response", stderr="")

    receipt = gateway(tmp_path, runner).execute(request(tmp_path), model="openai/gpt-approved")

    command = captured["command"]
    assert command[:8] == [
        "opencode-test",
        "run",
        "--pure",
        "--format",
        "json",
        "--model",
        "openai/gpt-approved",
        "--dir",
    ]
    assert captured["workspace"] == tmp_path.resolve()
    assert captured["timeout"] == 300
    assert captured["config"] == {
        "share": "disabled",
        "autoupdate": False,
        "enabled_providers": ["openai"],
        "tools": {"write": True, "edit": True, "bash": True, "webfetch": False, "websearch": False},
    }
    environment = captured["environment"]
    assert "OPENAI_API_KEY" not in environment
    assert environment["OPENCODE_DISABLE_DEFAULT_PLUGINS"] == "true"
    assert receipt.status is ExecutionStatus.COMPLETED
    assert receipt.final_response is None
    evidence = gateway(tmp_path, runner)._evidence.read_verified(receipt.evidence[0])
    assert b"model response" not in evidence
    assert json.loads(evidence)["output_bytes"] == len(b"model response\n")


def test_gateway_rejects_unapproved_models_before_process_spawn(tmp_path):
    invoked = False

    def runner(*_args):
        nonlocal invoked
        invoked = True
        raise AssertionError("runner must not be called")

    with pytest.raises(ModelNotApprovedError):
        gateway(tmp_path, runner).execute(request(tmp_path), model="openrouter/kimi")

    assert invoked is False


def test_gateway_rejects_workspace_outside_authorized_repository(tmp_path):
    outside = tmp_path.parent / "outside"
    outside.mkdir()

    with pytest.raises(WorkspaceDeniedError):
        gateway(tmp_path, lambda *_args: None).execute(
            request(outside), model="openai/gpt-approved"
        )


@pytest.mark.parametrize(
    ("returncode", "output", "status", "error_code"),
    [
        (1, "usage limit reached", ExecutionStatus.USAGE_LIMITED, "usage-limit"),
        (1, "permission denied", ExecutionStatus.PERMISSION_DENIED, "permission-denied"),
        (2, "other failure", ExecutionStatus.FAILED, "opencode-exit-2"),
    ],
)
def test_gateway_maps_non_success_results_to_non_acceptance_receipts(
    tmp_path, returncode, output, status, error_code
):
    def runner(command, *_args):
        return subprocess.CompletedProcess(command, returncode, stdout="", stderr=output)

    receipt = gateway(tmp_path, runner).execute(request(tmp_path), model="openai/gpt-approved")

    assert receipt.status is status
    assert receipt.error_code == error_code
    assert "accepted" not in receipt.__class__.model_fields


def test_read_only_profile_disables_write_edit_and_shell_tools(tmp_path):
    captured: dict[str, object] = {}

    def runner(command, _workspace, environment, _timeout):
        captured["config"] = json.loads(
            Path(environment["OPENCODE_CONFIG"]).read_text(encoding="utf-8")
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    gateway(tmp_path, runner).execute(
        request(tmp_path, role=SpecialistRole.RISK_REVIEW), model="openai/gpt-approved"
    )

    assert captured["config"]["tools"] == {
        "write": False,
        "edit": False,
        "bash": False,
        "webfetch": False,
        "websearch": False,
    }
