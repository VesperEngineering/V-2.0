from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone

import pytest

from vesper.platform.codex import WorkspaceDeniedError
from vesper.platform.codex_sandbox import (
    DOCKER_CODEX_DEFAULT_MODEL,
    DockerSandboxTerminationError,
)
from vesper.platform.contracts import (
    CodexExecutionReceipt,
    ExecutionStatus,
    PermissionSet,
    SandboxMode,
    SpecialistInput,
    SpecialistRole,
)
from vesper.platform.sandbox_runtime import DockerCodexRuntime, OPENAI_NETWORK_HOSTS


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)


def request(workspace) -> SpecialistInput:
    return SpecialistInput(
        run_id="run-001",
        task_id="task-001",
        repository_revision="revision-001",
        created_at=NOW,
        role=SpecialistRole.DEVELOPMENT,
        attempt=1,
        instructions="Make the bounded change.",
        workspace=str(workspace),
        memory_namespace=("profiles", "v20-development", "development-episodes"),
        permissions=PermissionSet(
            sandbox=SandboxMode.WORKSPACE_WRITE,
            read_paths=(str(workspace),),
            write_paths=(str(workspace),),
            allowed_tools=("read", "search", "write", "test"),
        ),
    )


class FakeAdapter:
    def __init__(self, sandbox_name, calls):
        self.sandbox_name = sandbox_name
        self.calls = calls

    def execute(self, item, **kwargs):
        self.calls.append((self.sandbox_name, item, kwargs))
        return CodexExecutionReceipt(
            run_id=item.run_id,
            task_id=item.task_id,
            repository_revision=item.repository_revision,
            created_at=item.created_at,
            execution_id=kwargs["execution_id"],
            role=item.role,
            attempt=item.attempt,
            status=ExecutionStatus.COMPLETED,
            sandbox=item.permissions.sandbox,
            started_at=NOW,
            finished_at=NOW,
            final_response='{"ready":true}',
        )


def runtime(tmp_path, *, failure_at=None):
    workspace = tmp_path / "task"
    workspace.mkdir(exist_ok=True)
    commands = []
    adapter_calls = []

    def runner(command, _workspace, _timeout):
        commands.append(command)
        marker = command[1] if len(command) > 1 else None
        failures = (failure_at,) if isinstance(failure_at, str) else (failure_at or ())
        returncode = 1 if marker in failures else 0
        stdout = '{"sandboxes":[]}' if marker == "ls" else ""
        return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")

    instance = DockerCodexRuntime(
        repository_root=tmp_path,
        executable="sbx-test",
        runner=runner,
        adapter_factory=lambda name: FakeAdapter(name, adapter_calls),
        clock=lambda: NOW,
        id_factory=lambda: "execution-001",
    )
    return instance, workspace, commands, adapter_calls


def test_runtime_provisions_exact_one_shot_boundary_before_delegating(tmp_path):
    instance, workspace, commands, adapter_calls = runtime(tmp_path)

    receipt = instance.execute(
        request(workspace),
        prompt="Implement.",
        model=DOCKER_CODEX_DEFAULT_MODEL,
        timeout_seconds=60,
        reasoning_effort="medium",
        output_schema={"type": "object"},
    )

    sandbox_name = "v20-development-" + hashlib.sha256(b"execution-001").hexdigest()[:16]
    assert commands == [
        [
            "sbx-test",
            "create",
            "--no-share-skills",
            "--name",
            sandbox_name,
            "codex",
            str(workspace.resolve()),
        ],
        [
            "sbx-test",
            "policy",
            "allow",
            "network",
            "--sandbox",
            sandbox_name,
            ",".join(OPENAI_NETWORK_HOSTS),
        ],
        ["sbx-test", "stop", sandbox_name],
    ]
    assert adapter_calls[0][0] == sandbox_name
    assert adapter_calls[0][2]["reasoning_effort"] == "medium"
    assert adapter_calls[0][2]["output_schema"] == {"type": "object"}
    assert receipt.status is ExecutionStatus.COMPLETED


def test_policy_failure_returns_receipt_and_force_removes_created_sandbox(tmp_path):
    instance, workspace, commands, adapter_calls = runtime(tmp_path, failure_at="policy")

    receipt = instance.execute(
        request(workspace),
        prompt="No.",
        model=DOCKER_CODEX_DEFAULT_MODEL,
        timeout_seconds=60,
    )

    assert receipt.status is ExecutionStatus.PERMISSION_DENIED
    assert receipt.error_code == "sandbox-policy-failed"
    assert commands[-2][1:3] == ["rm", "--force"]
    assert commands[-1][1:] == ["ls", "--json"]
    assert adapter_calls == []


def test_create_failure_returns_structured_infrastructure_receipt(tmp_path):
    instance, workspace, commands, adapter_calls = runtime(tmp_path, failure_at="create")

    receipt = instance.execute(
        request(workspace),
        prompt="No.",
        model=DOCKER_CODEX_DEFAULT_MODEL,
        timeout_seconds=60,
    )

    assert receipt.status is ExecutionStatus.FAILED
    assert receipt.error_code == "sandbox-create-failed"
    assert len(commands) == 1
    assert adapter_calls == []


def test_cleanup_failure_blocks_a_normal_provisioning_failure(tmp_path):
    instance, workspace, _commands, _adapter_calls = runtime(
        tmp_path,
        failure_at=("policy", "ls"),
    )

    with pytest.raises(DockerSandboxTerminationError, match="could not be confirmed"):
        instance.execute(
            request(workspace),
            prompt="No.",
            model=DOCKER_CODEX_DEFAULT_MODEL,
            timeout_seconds=60,
        )


def test_runtime_rejects_mounting_the_repository_root(tmp_path):
    instance, workspace, commands, _adapter_calls = runtime(tmp_path)
    root_request = request(workspace).model_copy(
        update={
            "workspace": str(tmp_path),
            "permissions": PermissionSet(
                sandbox=SandboxMode.WORKSPACE_WRITE,
                read_paths=(str(tmp_path),),
                write_paths=(str(tmp_path),),
                allowed_tools=("read", "search", "write", "test"),
            ),
        }
    )

    with pytest.raises(WorkspaceDeniedError, match="dedicated subdirectory"):
        instance.execute(
            root_request,
            prompt="No.",
            model=DOCKER_CODEX_DEFAULT_MODEL,
            timeout_seconds=60,
        )

    assert commands == []
