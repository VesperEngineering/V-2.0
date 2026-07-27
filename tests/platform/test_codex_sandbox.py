from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.platform.codex import (
    ModelNotApprovedError,
    PermissionDeniedError,
    WorkspaceDeniedError,
)
from vesper.platform.codex_sandbox import (
    DOCKER_CODEX_DEFAULT_MODEL,
    DockerCodexAdapter,
    DockerSandboxBoundaryError,
    DockerSandboxPolicyError,
    DockerSandboxTerminationError,
    _OutputLimitExceeded,
    _run_execution,
)
from vesper.platform.contracts import (
    ExecutionStatus,
    PermissionSet,
    SandboxMode,
    SpecialistInput,
    SpecialistRole,
)


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)
NETWORK_HOSTS = ("api.openai.com", "chatgpt.com", "openai.com")


def specialist_input(workspace: Path, *, mode: SandboxMode = SandboxMode.WORKSPACE_WRITE):
    writable = mode is SandboxMode.WORKSPACE_WRITE
    return SpecialistInput(
        run_id="run-001",
        task_id="task-001",
        repository_revision="b5263eb",
        created_at=NOW,
        role=SpecialistRole.DEVELOPMENT,
        attempt=1,
        instructions="Make the bounded change.",
        workspace=str(workspace),
        memory_namespace=("profiles", "v20-development", "episodes"),
        permissions=PermissionSet(
            sandbox=mode,
            read_paths=(str(workspace),),
            write_paths=(str(workspace),) if writable else (),
            allowed_tools=("read", "search", "write", "test") if writable else ("read", "search"),
        ),
    )


def completed_output(response: str = "Finished the bounded task.") -> str:
    events = (
        {"type": "thread.started", "thread_id": "thread-001"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": response}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
    )
    return "\n".join(json.dumps(event) for event in events) + "\n"


class FakeBoundary:
    def __init__(self, repository_root: Path):
        self.repository_root = repository_root.resolve()
        self.metadata_calls: list[list[str]] = []
        self.execution_calls: list[tuple[list[str], Path, float]] = []
        self.network_hosts = NETWORK_HOSTS
        self.inspect_workspace = str(self.repository_root)
        self.inspect_state = "stopped"
        self.removed = False
        self.remove_returncode = 0
        self.retain_after_remove = False
        self.workspaces = [str(self.repository_root)]
        self.ports = []
        self.mounts = (
            f"bind-workspace on {self._sandbox_path(self.repository_root)} "
            "type virtiofs (rw,relatime)\n"
            "bind-resolv on /etc/resolv.conf type virtiofs (ro,relatime)\n"
            "bind-hosts on /etc/hosts type virtiofs (ro,relatime)\n"
        )
        self.execution_result = subprocess.CompletedProcess(
            [], 0, stdout=completed_output(), stderr=""
        )

    def metadata(self, command, workspace, timeout_seconds):
        self.metadata_calls.append(command)
        if command[1:3] == ["inspect", "v20-codex"]:
            output = {
                "name": "v20-codex",
                "agent": "codex",
                "state": self.inspect_state,
                "auth_mode": "oauth · openai",
                "workspace": self.inspect_workspace,
                "network_policy": {"scope": "sandbox"},
                "mcp_gateway": False,
                "kits": [],
                "sessions": 0,
            }
        elif command[1:3] == ["ls", "--json"]:
            output = {
                "sandboxes": []
                if self.removed
                else [
                    {
                        "name": "v20-codex",
                        "agent": "codex",
                        "status": self.inspect_state,
                        "workspaces": self.workspaces,
                    }
                ]
            }
        elif command[1:4] == ["ports", "v20-codex", "--json"]:
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(self.ports), stderr="")
        elif command[1:4] == ["policy", "ls", "v20-codex"]:
            output = {
                "rules": [
                    {
                        "scope": "sandbox:v20-codex",
                        "resource_type": "network",
                        "decision": "allow",
                        "resources": [host],
                        "status": "active",
                    }
                    for host in self.network_hosts
                ]
            }
        elif command[1:4] == ["policy", "check", "network"]:
            target = command[-1]
            allowed = target in self.network_hosts
            output = {
                "allowed": allowed,
                "context": "sandbox:v20-codex",
                "deny_kind": None if allowed else "implicit",
                "reason": "allowed" if allowed else "No matching allow rule (default deny)",
            }
            if not allowed:
                return subprocess.CompletedProcess(command, 1, stdout=json.dumps(output), stderr="")
        elif command[1:4] == ["rm", "--force", "v20-codex"]:
            self.removed = not self.retain_after_remove
            return subprocess.CompletedProcess(
                command, self.remove_returncode, stdout="", stderr="remove failed"
            )
        elif command[1:5] == ["exec", "v20-codex", "sh", "-lc"]:
            return subprocess.CompletedProcess(command, 0, stdout=self.mounts, stderr="")
        else:
            raise AssertionError(f"unexpected metadata command: {command}")
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(output), stderr="")

    def execute(self, command, workspace, timeout_seconds, cancelled, max_output_bytes):
        self.execution_calls.append((command, workspace, timeout_seconds))
        return self.execution_result

    @staticmethod
    def _sandbox_path(path: Path) -> str:
        return f"/{path.drive[0].lower()}{path.as_posix()[2:]}"


def adapter(
    tmp_path,
    boundary: FakeBoundary,
    *,
    sandbox_workspace: Path | None = None,
) -> DockerCodexAdapter:
    (tmp_path / ".git").mkdir(exist_ok=True)
    return DockerCodexAdapter(
        repository_root=tmp_path,
        sandbox_workspace=sandbox_workspace,
        sandbox_name="v20-codex",
        approved_models=("gpt-approved",),
        approved_network_hosts=NETWORK_HOSTS,
        executable="sbx-test",
        metadata_runner=boundary.metadata,
        execution_runner=boundary.execute,
        revision_reader=lambda _root: "b5263eb",
        clock=lambda: NOW,
    )


def test_workspace_write_uses_verified_outer_sandbox_and_parses_json_receipt(tmp_path):
    boundary = FakeBoundary(tmp_path)

    receipt = adapter(tmp_path, boundary).execute(
        specialist_input(tmp_path),
        prompt="Implement the task.",
        model="gpt-approved",
        timeout_seconds=12,
        execution_id="execution-001",
    )

    command, workspace, timeout = boundary.execution_calls[0]
    assert command == [
        "sbx-test",
        "exec",
        "v20-codex",
        "codex",
        "exec",
        "--ignore-rules",
        "--ephemeral",
        "--json",
        "--color",
        "never",
        "--model",
        "gpt-approved",
        "--config",
        "mcp_servers={}",
        "--config",
        'web_search="disabled"',
        "--config",
        "skills.config=[]",
        "--disable",
        "apps",
        "--disable",
        "hooks",
        "--disable",
        "memories",
        "--disable",
        "multi_agent",
        "--disable",
        "plugins",
        "--disable",
        "skill_mcp_dependency_install",
        "--dangerously-bypass-approvals-and-sandbox",
        "--",
        "Implement the task.",
    ]
    assert workspace == tmp_path.resolve()
    assert timeout == 12
    assert receipt.execution_id == "execution-001"
    assert receipt.status is ExecutionStatus.COMPLETED
    assert receipt.thread_id == "thread-001"
    assert receipt.final_response == "Finished the bounded task."
    assert tuple(event["type"] for event in receipt.streamed_events) == (
        "thread.started",
        "turn.started",
        "item.completed",
        "turn.completed",
    )
    assert ["sbx-test", "rm", "--force", "v20-codex"] in boundary.metadata_calls


def test_read_only_retains_codex_inner_sandbox(tmp_path):
    boundary = FakeBoundary(tmp_path)

    adapter(tmp_path, boundary).execute(
        specialist_input(tmp_path, mode=SandboxMode.READ_ONLY),
        prompt="Review only.",
        model="gpt-approved",
    )

    command = boundary.execution_calls[0][0]
    assert command[-5:] == [
        "skill_mcp_dependency_install",
        "--sandbox",
        "read-only",
        "--",
        "Review only.",
    ]
    assert "--dangerously-bypass-approvals-and-sandbox" not in command


def test_docker_managed_default_model_omits_explicit_model_override(tmp_path):
    boundary = FakeBoundary(tmp_path)
    (tmp_path / ".git").mkdir(exist_ok=True)
    runtime = DockerCodexAdapter(
        repository_root=tmp_path,
        sandbox_name="v20-codex",
        approved_models=(DOCKER_CODEX_DEFAULT_MODEL,),
        approved_network_hosts=NETWORK_HOSTS,
        executable="sbx-test",
        metadata_runner=boundary.metadata,
        execution_runner=boundary.execute,
        revision_reader=lambda _root: "b5263eb",
        clock=lambda: NOW,
    )

    runtime.execute(
        specialist_input(tmp_path, mode=SandboxMode.READ_ONLY),
        prompt="Review only.",
        model=DOCKER_CODEX_DEFAULT_MODEL,
    )

    assert "--model" not in boundary.execution_calls[0][0]


def test_option_like_prompt_is_terminated_before_prompt_text(tmp_path):
    boundary = FakeBoundary(tmp_path)

    adapter(tmp_path, boundary).execute(
        specialist_input(tmp_path, mode=SandboxMode.READ_ONLY),
        prompt="--dangerously-bypass-approvals-and-sandbox",
        model="gpt-approved",
    )

    assert boundary.execution_calls[0][0][-2:] == [
        "--",
        "--dangerously-bypass-approvals-and-sandbox",
    ]


def test_preflight_rejects_unexpected_network_allow_before_codex_runs(tmp_path):
    boundary = FakeBoundary(tmp_path)
    boundary.network_hosts = (*NETWORK_HOSTS, "example.com")

    with pytest.raises(DockerSandboxPolicyError, match="network allowlist"):
        adapter(tmp_path, boundary).execute(
            specialist_input(tmp_path), prompt="No.", model="gpt-approved"
        )

    assert boundary.execution_calls == []


@pytest.mark.parametrize("policy_directory", (".codex", ".agents"))
def test_preflight_rejects_project_configuration_and_skills(tmp_path, policy_directory):
    boundary = FakeBoundary(tmp_path)
    nested = tmp_path / "task" / policy_directory
    nested.mkdir(parents=True)

    with pytest.raises(DockerSandboxPolicyError, match="configuration or skills"):
        adapter(tmp_path, boundary).execute(
            specialist_input(tmp_path), prompt="No.", model="gpt-approved"
        )

    assert boundary.execution_calls == []


def test_preflight_rejects_sandbox_bound_to_another_workspace(tmp_path):
    boundary = FakeBoundary(tmp_path)
    boundary.inspect_workspace = str(tmp_path / "other")

    with pytest.raises(DockerSandboxPolicyError, match="workspace"):
        adapter(tmp_path, boundary).execute(
            specialist_input(tmp_path), prompt="No.", model="gpt-approved"
        )

    assert boundary.execution_calls == []


def test_preflight_rejects_extra_workspace_mounts_and_shared_skills(tmp_path):
    boundary = FakeBoundary(tmp_path)
    boundary.workspaces.append(str(tmp_path.parent / "other"))

    with pytest.raises(DockerSandboxPolicyError, match="workspace mounts"):
        adapter(tmp_path, boundary).execute(
            specialist_input(tmp_path), prompt="No.", model="gpt-approved"
        )

    boundary = FakeBoundary(tmp_path)
    boundary.mounts += "bind-skills on /home/agent/.agents/skills type virtiofs (rw,relatime)\n"
    with pytest.raises(DockerSandboxPolicyError, match="host mounts"):
        adapter(tmp_path, boundary).execute(
            specialist_input(tmp_path), prompt="No.", model="gpt-approved"
        )


def test_unapproved_model_and_outside_workspace_fail_before_sandbox_preflight(tmp_path):
    boundary = FakeBoundary(tmp_path)
    runtime = adapter(tmp_path, boundary)

    with pytest.raises(ModelNotApprovedError):
        runtime.execute(specialist_input(tmp_path), prompt="No.", model="other")

    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir(exist_ok=True)
    with pytest.raises(WorkspaceDeniedError):
        runtime.execute(specialist_input(outside), prompt="No.", model="gpt-approved")

    assert boundary.metadata_calls == []


def test_effective_permissions_must_match_declared_permissions_and_resume_is_rejected(tmp_path):
    boundary = FakeBoundary(tmp_path)
    runtime = adapter(tmp_path, boundary)
    narrowed = specialist_input(tmp_path).model_copy(
        update={
            "permissions": PermissionSet(
                sandbox=SandboxMode.WORKSPACE_WRITE,
                read_paths=(str(tmp_path),),
                write_paths=(str(tmp_path),),
                allowed_tools=("read",),
            )
        }
    )

    with pytest.raises(PermissionDeniedError, match="capability set"):
        runtime.execute(narrowed, prompt="No.", model="gpt-approved")
    with pytest.raises(DockerSandboxPolicyError, match="thread resume"):
        runtime.execute(
            specialist_input(tmp_path).model_copy(update={"thread_id": "thread-old"}),
            prompt="No.",
            model="gpt-approved",
        )

    assert boundary.metadata_calls == []


def test_subdirectory_workspace_is_the_exact_sandbox_mount(tmp_path):
    boundary = FakeBoundary(tmp_path)
    child = tmp_path / "task"
    child.mkdir()
    boundary.inspect_workspace = str(child)
    boundary.workspaces = [str(child)]
    boundary.mounts = boundary.mounts.replace(
        boundary._sandbox_path(tmp_path.resolve()),
        boundary._sandbox_path(child.resolve()),
    )

    adapter(tmp_path, boundary, sandbox_workspace=child).execute(
        specialist_input(child), prompt="Run.", model="gpt-approved"
    )

    command = boundary.execution_calls[0][0]
    assert "--cd" not in command


def test_reasoning_effort_and_output_schema_are_transient_controller_inputs(tmp_path):
    boundary = FakeBoundary(tmp_path)

    adapter(tmp_path, boundary).execute(
        specialist_input(tmp_path),
        prompt="Return JSON.",
        model="gpt-approved",
        reasoning_effort="high",
        output_schema={"type": "object", "properties": {"ready": {"type": "boolean"}}},
        execution_id="schema-execution",
    )

    command = boundary.execution_calls[0][0]
    assert 'model_reasoning_effort="high"' in command
    schema_argument = command[command.index("--output-schema") + 1]
    assert schema_argument.endswith(".json")
    assert not tuple(tmp_path.glob(".v20-schema-*.json"))


def test_git_metadata_mutation_fails_and_removes_disposable_sandbox(tmp_path):
    boundary = FakeBoundary(tmp_path)

    def mutate_git(command, workspace, timeout_seconds, cancelled, max_output_bytes):
        boundary.execution_calls.append((command, workspace, timeout_seconds))
        (workspace / ".git" / "config").write_text("mutated", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout=completed_output(), stderr="")

    boundary.execute = mutate_git
    receipt = adapter(tmp_path, boundary).execute(
        specialist_input(tmp_path), prompt="Run.", model="gpt-approved"
    )

    assert receipt.status is ExecutionStatus.PERMISSION_DENIED
    assert receipt.error_code == "git-metadata-mutated"
    assert ["sbx-test", "rm", "--force", "v20-codex"] in boundary.metadata_calls


def test_controller_lease_file_is_outside_the_guest_git_fingerprint(tmp_path):
    boundary = FakeBoundary(tmp_path)
    runtime = adapter(tmp_path, boundary)
    lease = tmp_path / ".git" / "v20-controller.lock"
    lease.write_bytes(b"\0")

    before = runtime._git_fingerprint()
    lease.write_bytes(b"controller-owned-state")

    assert runtime._git_fingerprint() == before


def test_timeout_removes_sandbox_and_returns_structured_receipt(tmp_path):
    boundary = FakeBoundary(tmp_path)

    def timeout(*_args):
        raise subprocess.TimeoutExpired(["sbx-test"], 0.01)

    boundary.execute = timeout
    receipt = adapter(tmp_path, boundary).execute(
        specialist_input(tmp_path), prompt="Wait.", model="gpt-approved", timeout_seconds=0.01
    )

    assert receipt.status is ExecutionStatus.TIMEOUT
    assert receipt.error_code == "timeout"
    assert ["sbx-test", "rm", "--force", "v20-codex"] in boundary.metadata_calls


def test_active_cancellation_removes_sandbox_and_is_distinct_from_timeout(tmp_path):
    boundary = FakeBoundary(tmp_path)
    started = threading.Event()

    def blocking(command, workspace, timeout_seconds, cancelled, max_output_bytes):
        boundary.execution_calls.append((command, workspace, timeout_seconds))
        started.set()
        while not cancelled():
            time.sleep(0.001)
        return subprocess.CompletedProcess(command, -1, stdout="", stderr="cancelled")

    boundary.execute = blocking
    runtime = adapter(tmp_path, boundary)
    result = {}

    worker = threading.Thread(
        target=lambda: result.setdefault(
            "receipt",
            runtime.execute(
                specialist_input(tmp_path),
                prompt="Wait.",
                model="gpt-approved",
                execution_id="execution-cancel",
            ),
        )
    )
    worker.start()
    assert started.wait(1)
    with pytest.raises(DockerSandboxBoundaryError, match="active execution"):
        runtime.execute(
            specialist_input(tmp_path),
            prompt="Second.",
            model="gpt-approved",
            execution_id="execution-second",
        )
    assert runtime.cancel("execution-cancel") is True
    worker.join(1)

    assert not worker.is_alive()
    assert result["receipt"].status is ExecutionStatus.CANCELLED
    assert result["receipt"].error_code == "cancelled"
    assert ["sbx-test", "rm", "--force", "v20-codex"] in boundary.metadata_calls


def test_pre_cancelled_turn_consumes_one_shot_sandbox_without_starting_codex(tmp_path):
    boundary = FakeBoundary(tmp_path)
    cancelled = threading.Event()
    cancelled.set()

    receipt = adapter(tmp_path, boundary).execute(
        specialist_input(tmp_path),
        prompt="No.",
        model="gpt-approved",
        cancellation=cancelled,
    )

    assert receipt.status is ExecutionStatus.CANCELLED
    assert boundary.execution_calls == []
    assert ["sbx-test", "rm", "--force", "v20-codex"] in boundary.metadata_calls


@pytest.mark.parametrize("retain_after_remove", [False, True])
def test_unconfirmed_one_shot_removal_fails_closed(tmp_path, retain_after_remove):
    boundary = FakeBoundary(tmp_path)
    boundary.retain_after_remove = retain_after_remove
    if not retain_after_remove:
        boundary.remove_returncode = 1

    with pytest.raises(DockerSandboxTerminationError, match="removal could not be confirmed"):
        adapter(tmp_path, boundary).execute(
            specialist_input(tmp_path), prompt="Run.", model="gpt-approved"
        )


def test_default_runner_enforces_output_limit_before_process_completion(tmp_path):
    with pytest.raises(_OutputLimitExceeded):
        _run_execution(
            [sys.executable, "-c", "print('x' * 10000)"],
            tmp_path,
            5,
            lambda: False,
            100,
        )


def test_malformed_success_output_fails_closed(tmp_path):
    boundary = FakeBoundary(tmp_path)
    boundary.execution_result = subprocess.CompletedProcess([], 0, stdout="not-json\n", stderr="")

    receipt = adapter(tmp_path, boundary).execute(
        specialist_input(tmp_path), prompt="Run.", model="gpt-approved"
    )

    assert receipt.status is ExecutionStatus.FAILED
    assert receipt.error_code == "malformed-jsonl"
    assert receipt.final_response is None


def test_empty_success_output_and_revision_mismatch_fail_closed(tmp_path):
    boundary = FakeBoundary(tmp_path)
    boundary.execution_result = subprocess.CompletedProcess([], 0, stdout="", stderr="")

    receipt = adapter(tmp_path, boundary).execute(
        specialist_input(tmp_path), prompt="Run.", model="gpt-approved"
    )

    assert receipt.status is ExecutionStatus.FAILED
    assert receipt.error_code == "incomplete-jsonl"

    runtime = DockerCodexAdapter(
        repository_root=tmp_path,
        sandbox_name="v20-codex",
        approved_models=("gpt-approved",),
        approved_network_hosts=NETWORK_HOSTS,
        executable="sbx-test",
        metadata_runner=boundary.metadata,
        execution_runner=boundary.execute,
        revision_reader=lambda _root: "different-revision",
    )
    with pytest.raises(DockerSandboxPolicyError, match="revision"):
        runtime.execute(specialist_input(tmp_path), prompt="No.", model="gpt-approved")
