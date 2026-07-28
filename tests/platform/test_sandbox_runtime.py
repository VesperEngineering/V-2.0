from __future__ import annotations

import hashlib
import subprocess
import threading
import time
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
from vesper.platform.control import RuntimeControl
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


def runtime(tmp_path, *, failure_at=None, control=None):
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
        control=control,
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


def test_create_failure_returns_receipt_and_confirms_sandbox_absence(tmp_path):
    instance, workspace, commands, adapter_calls = runtime(tmp_path, failure_at="create")

    receipt = instance.execute(
        request(workspace),
        prompt="No.",
        model=DOCKER_CODEX_DEFAULT_MODEL,
        timeout_seconds=60,
    )

    assert receipt.status is ExecutionStatus.FAILED
    assert receipt.error_code == "sandbox-create-failed"
    assert commands[-2][1:3] == ["rm", "--force"]
    assert commands[-1][1:] == ["ls", "--json"]
    assert adapter_calls == []


def test_timed_out_create_preserves_active_record_when_cleanup_is_unconfirmed(tmp_path):
    control = RuntimeControl(tmp_path / "control")
    instance, workspace, _commands, _adapter_calls = runtime(
        tmp_path,
        failure_at="ls",
        control=control,
    )
    original_runner = instance._runner
    first = True

    def runner(command, repository_root, timeout):
        nonlocal first
        if first:
            first = False
            raise subprocess.TimeoutExpired(command, timeout)
        return original_runner(command, repository_root, timeout)

    instance._runner = runner

    with pytest.raises(DockerSandboxTerminationError):
        instance.execute(
            request(workspace),
            prompt="No.",
            model=DOCKER_CODEX_DEFAULT_MODEL,
            timeout_seconds=60,
        )

    assert control.active_execution("run-001") is not None


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


def test_unconfirmed_cleanup_preserves_active_reconciliation_record(tmp_path):
    control = RuntimeControl(tmp_path / "control")
    instance, workspace, _commands, _adapter_calls = runtime(
        tmp_path,
        failure_at=("policy", "ls"),
        control=control,
    )

    with pytest.raises(DockerSandboxTerminationError):
        instance.execute(
            request(workspace),
            prompt="No.",
            model=DOCKER_CODEX_DEFAULT_MODEL,
            timeout_seconds=60,
        )

    active = control.active_execution("run-001")
    assert active is not None
    assert active["sandbox_name"] == DockerCodexRuntime.expected_sandbox_name(
        "v20-development",
        "execution-001",
    )


def test_runtime_reconciles_stale_sandbox_and_confirms_inventory_absence(tmp_path):
    instance, _workspace, commands, _adapter_calls = runtime(tmp_path)

    instance.reconcile_sandbox("v20-stale")

    assert commands == [
        ["sbx-test", "rm", "--force", "v20-stale"],
        ["sbx-test", "ls", "--json"],
    ]


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


def test_cross_process_cancellation_signal_reaches_active_adapter(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    control = RuntimeControl(tmp_path / "control")
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
                started_at=NOW,
                finished_at=NOW,
                error_code="cancelled",
            )

    def runner(command, _workspace, _timeout):
        marker = command[1] if len(command) > 1 else None
        stdout = '{"sandboxes":[]}' if marker == "ls" else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    instance = DockerCodexRuntime(
        repository_root=tmp_path,
        executable="sbx-test",
        runner=runner,
        adapter_factory=lambda _name: BlockingAdapter(),
        control=control,
        clock=lambda: NOW,
        id_factory=lambda: "execution-001",
    )
    result = {}
    worker = threading.Thread(
        target=lambda: result.setdefault(
            "receipt",
            instance.execute(
                request(workspace),
                prompt="Wait.",
                model=DOCKER_CODEX_DEFAULT_MODEL,
                timeout_seconds=60,
            ),
        )
    )
    worker.start()
    assert started.wait(timeout=2)
    assert control.active_execution("run-001")["execution_id"] == "execution-001"

    control.request_cancel("run-001", "operator requested cancellation")
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert result["receipt"].status is ExecutionStatus.CANCELLED
    assert control.active_execution("run-001") is None
