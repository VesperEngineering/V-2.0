from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
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
from vesper.platform.opencode import (
    CredentialUnavailableError,
    ModelNotApprovedError,
    OpenCodeGateway,
    WorkspaceDeniedError,
    _ProcessCancelled,
    _process_identity,
    _run_process,
)
from vesper.platform.control import RuntimeControl


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)


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


def gateway(tmp_path, runner, *, credential_environment_keys=None, control=None) -> OpenCodeGateway:
    return OpenCodeGateway(
        repository_root=tmp_path,
        approved_models=("openai/gpt-approved",),
        credential_environment_keys=credential_environment_keys,
        protected_paths=(tmp_path / ".git", tmp_path / "profiles"),
        control=control,
        executable="opencode-test",
        runner=runner,
        clock=lambda: NOW,
    )


def execute(instance, item, *, model="openai/gpt-approved"):
    return instance.execute(
        item,
        prompt="Return the typed result.",
        model=model,
        timeout_seconds=300,
        execution_id="turn-001",
        reasoning_effort="medium",
        output_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
    )


def event_output(text="model response"):
    return "\n".join(
        json.dumps(event)
        for event in (
            {"type": "step_start", "sessionID": "session-001", "part": {"type": "step-start"}},
            {
                "type": "text",
                "sessionID": "session-001",
                "part": {"type": "text", "text": text},
            },
            {"type": "step_finish", "sessionID": "session-001", "part": {"type": "step-finish"}},
        )
    )


def test_gateway_runs_exact_model_with_scrubbed_environment_and_structured_receipt(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "unbound-secret")
    captured: dict[str, object] = {}

    def runner(command, workspace, environment, timeout_seconds, _cancellation, _on_start):
        captured["command"] = command
        captured["workspace"] = workspace
        captured["environment"] = environment
        captured["timeout"] = timeout_seconds
        captured["config"] = json.loads(
            Path(environment["OPENCODE_CONFIG"]).read_text(encoding="utf-8")
        )
        return subprocess.CompletedProcess(command, 0, stdout=event_output(), stderr="")

    receipt = execute(gateway(tmp_path, runner), request(tmp_path))

    command = captured["command"]
    assert command[:10] == [
        "opencode-test",
        "run",
        "--pure",
        "--format",
        "json",
        "--model",
        "openai/gpt-approved",
        "--agent",
        "v20",
        "--dir",
    ]
    assert captured["workspace"] == tmp_path.resolve()
    assert captured["timeout"] == 300
    workspace_rules = {
        "*": "allow",
        "**/.git": "deny",
        "**/.git/**": "deny",
        "**/.state": "deny",
        "**/.state/**": "deny",
        "*.env": "deny",
        "*.env.*": "deny",
        "**/*.env": "deny",
        "**/*.env.*": "deny",
        ".git": "deny",
        ".git/**": "deny",
        "profiles": "deny",
        "profiles/**": "deny",
    }
    permission = {
        "read": workspace_rules,
        "edit": workspace_rules,
        "bash": "deny",
        "glob": "deny",
        "grep": "deny",
        "list": "deny",
        "task": "deny",
        "skill": "deny",
        "lsp": "deny",
        "webfetch": "deny",
        "websearch": "deny",
        "todowrite": "deny",
        "question": "deny",
        "external_directory": "deny",
    }
    assert captured["config"] == {
        "share": "disabled",
        "autoupdate": False,
        "snapshot": False,
        "formatter": False,
        "lsp": False,
        "instructions": [],
        "mcp": {},
        "enabled_providers": ["openai"],
        "tools": {
            "read": True,
            "glob": False,
            "grep": False,
            "list": False,
            "write": True,
            "edit": True,
            "apply_patch": False,
            "bash": False,
            "task": False,
            "skill": False,
            "lsp": False,
            "webfetch": False,
            "websearch": False,
        },
        "permission": permission,
        "agent": {"v20": {"mode": "primary", "permission": permission}},
    }
    environment = captured["environment"]
    assert "OPENAI_API_KEY" not in environment
    assert environment["OPENCODE_DISABLE_DEFAULT_PLUGINS"] == "true"
    assert environment["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"
    assert environment["USERPROFILE"].endswith("home")
    assert environment["XDG_CONFIG_HOME"].endswith("xdg-config")
    assert receipt.status is ExecutionStatus.COMPLETED
    assert receipt.execution_id == "turn-001"
    assert receipt.thread_id == "session-001"
    assert receipt.final_response == "model response"
    assert receipt.authentication_type == "opencode-local"
    assert receipt.permission_profile == "opencode-host"
    assert len(receipt.streamed_events) == 3
    assert "Output schema:" in command[-1]
    assert "Never write that response" in command[-1]


def test_gateway_passes_only_selected_provider_credential_without_persisting_it(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-secret")
    captured: dict[str, object] = {}

    def runner(command, _workspace, environment, _timeout, _cancellation, _on_start):
        captured["command"] = command
        captured["environment"] = environment
        captured["config"] = Path(environment["OPENCODE_CONFIG"]).read_text(encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout=event_output("ok"), stderr="")

    instance = gateway(
        tmp_path,
        runner,
        credential_environment_keys={
            "openai": "OPENAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        },
    )
    receipt = execute(instance, request(tmp_path))

    environment = captured["environment"]
    assert environment["OPENAI_API_KEY"] == "openai-secret"
    assert "OPENROUTER_API_KEY" not in environment
    assert "openai-secret" not in json.dumps(captured["command"])
    assert "openai-secret" not in captured["config"]
    assert "openai-secret" not in receipt.model_dump_json()
    assert json.loads(captured["config"])["tools"]["bash"] is False


def test_gateway_configures_bound_moonshot_as_openai_compatible_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "moonshot-secret")
    captured: dict[str, object] = {}

    def runner(command, _workspace, environment, _timeout, _cancellation, _on_start):
        captured["command"] = command
        captured["environment"] = environment
        captured["config"] = json.loads(
            Path(environment["OPENCODE_CONFIG"]).read_text(encoding="utf-8")
        )
        return subprocess.CompletedProcess(command, 0, stdout=event_output("ok"), stderr="")

    instance = OpenCodeGateway(
        repository_root=tmp_path,
        approved_models=("moonshot/kimi-k3",),
        credential_environment_keys={"moonshot": "KIMI_API_KEY"},
        executable="opencode-test",
        runner=runner,
        clock=lambda: NOW,
    )
    receipt = execute(instance, request(tmp_path), model="moonshot/kimi-k3")

    assert captured["config"]["provider"] == {
        "moonshot": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Moonshot AI",
            "options": {
                "baseURL": "https://api.moonshot.ai/v1",
                "apiKey": "{env:KIMI_API_KEY}",
            },
            "models": {"kimi-k3": {"name": "Kimi K3"}},
        }
    }
    assert captured["environment"]["KIMI_API_KEY"] == "moonshot-secret"
    assert "moonshot-secret" not in json.dumps(captured["command"])
    assert "moonshot-secret" not in json.dumps(captured["config"])
    assert "moonshot-secret" not in receipt.model_dump_json()


@pytest.mark.parametrize("credential_key", ["OPENAI_API_KEY", ""])
def test_gateway_rejects_missing_bound_credential_before_process_spawn(
    tmp_path, monkeypatch, credential_key
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    invoked = False

    def runner(*_args):
        nonlocal invoked
        invoked = True
        raise AssertionError("runner must not be called")

    with pytest.raises(CredentialUnavailableError, match="openai"):
        execute(
            gateway(
                tmp_path,
                runner,
                credential_environment_keys={"openai": credential_key},
            ),
            request(tmp_path),
        )

    assert invoked is False


def test_gateway_rejects_unapproved_models_before_process_spawn(tmp_path):
    invoked = False

    def runner(*_args):
        nonlocal invoked
        invoked = True
        raise AssertionError("runner must not be called")

    with pytest.raises(ModelNotApprovedError):
        execute(gateway(tmp_path, runner), request(tmp_path), model="openrouter/kimi")

    assert invoked is False


def test_gateway_rejects_workspace_outside_authorized_repository(tmp_path):
    outside = tmp_path.parent / "outside"
    outside.mkdir()

    with pytest.raises(WorkspaceDeniedError):
        execute(gateway(tmp_path, lambda *_args: None), request(outside))


def test_subdirectory_workspace_denies_controller_protected_file_inside_it(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    protected = workspace / "README.md"
    protected.write_text("controller owned\n", encoding="utf-8")
    captured = {}

    def runner(command, _workspace, environment, *_args):
        captured["config"] = json.loads(
            Path(environment["OPENCODE_CONFIG"]).read_text(encoding="utf-8")
        )
        return subprocess.CompletedProcess(command, 0, stdout=event_output(), stderr="")

    instance = OpenCodeGateway(
        repository_root=tmp_path,
        approved_models=("openai/gpt-approved",),
        protected_paths=(protected,),
        executable="opencode-test",
        runner=runner,
        clock=lambda: NOW,
    )

    execute(instance, request(workspace))

    rules = captured["config"]["permission"]["edit"]
    assert rules["task/**"] == "allow"
    assert rules["task/README.md"] == "deny"


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

    receipt = execute(gateway(tmp_path, runner), request(tmp_path))

    assert receipt.status is status
    assert receipt.error_code == error_code
    assert "accepted" not in receipt.__class__.model_fields


def test_gateway_fails_closed_on_malformed_success_output(tmp_path):
    def runner(command, *_args):
        return subprocess.CompletedProcess(command, 0, stdout="not-json", stderr="")

    receipt = execute(gateway(tmp_path, runner), request(tmp_path))

    assert receipt.status is ExecutionStatus.FAILED
    assert receipt.error_code == "invalid-opencode-output"


def test_gateway_tracks_and_cooperatively_cancels_active_process(tmp_path):
    control = RuntimeControl(tmp_path / "control")
    started = threading.Event()
    result = {}

    def runner(command, _workspace, _environment, _timeout, cancellation, on_start):
        on_start(os.getpid())
        started.set()
        while not cancellation.is_set():
            time.sleep(0.001)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="cancelled")

    instance = gateway(tmp_path, runner, control=control)
    worker = threading.Thread(
        target=lambda: result.setdefault("receipt", execute(instance, request(tmp_path)))
    )
    worker.start()
    assert started.wait(timeout=5)
    active = control.active_execution("run-001")

    control.request_cancel("run-001", "operator cancelled host turn")
    worker.join(timeout=5)

    assert active["runtime"] == "opencode"
    assert active["process_id"] == os.getpid()
    assert not worker.is_alive()
    assert result["receipt"].status is ExecutionStatus.CANCELLED
    assert result["receipt"].error_code == "cancelled"
    assert control.active_execution("run-001") is None


def test_default_process_runner_terminates_cancelled_child(tmp_path):
    cancellation = threading.Event()
    started = threading.Event()
    result = {}

    def run():
        try:
            _run_process(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                tmp_path,
                os.environ,
                30,
                cancellation,
                lambda _process_id: started.set(),
            )
        except BaseException as exc:
            result["error"] = exc

    worker = threading.Thread(target=run)
    worker.start()
    assert started.wait(timeout=5)
    cancellation.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert isinstance(result["error"], _ProcessCancelled)


def test_default_process_runner_terminates_child_when_tracking_fails(tmp_path):
    process_id = None

    def fail_tracking(value):
        nonlocal process_id
        process_id = value
        raise RuntimeError("active record unavailable")

    with pytest.raises(RuntimeError, match="active record unavailable"):
        _run_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path,
            os.environ,
            30,
            None,
            fail_tracking,
        )

    assert process_id is not None
    assert _process_identity(process_id) is None


def test_default_process_runner_terminates_descendant_tree_on_cancellation(tmp_path):
    cancellation = threading.Event()
    started = threading.Event()
    child_pid_path = tmp_path / "child.pid"
    result = {}
    script = (
        "import pathlib, subprocess, sys, time; "
        f"child=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        "time.sleep(30)"
    )

    def run():
        try:
            _run_process(
                [sys.executable, "-c", script],
                tmp_path,
                os.environ,
                30,
                cancellation,
                lambda _process_id: started.set(),
            )
        except BaseException as exc:
            result["error"] = exc

    worker = threading.Thread(target=run)
    worker.start()
    assert started.wait(timeout=5)
    deadline = time.monotonic() + 5
    while not child_pid_path.is_file() and time.monotonic() < deadline:
        time.sleep(0.01)
    child_pid = int(child_pid_path.read_text())

    cancellation.set()
    worker.join(timeout=10)

    assert not worker.is_alive()
    assert isinstance(result["error"], _ProcessCancelled)
    assert _process_identity(child_pid) is None


def test_gateway_unwraps_one_complete_json_code_fence(tmp_path):
    def runner(command, *_args):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=event_output('Brief result:\n```json\n{"summary":"ok"}\n```'),
            stderr="",
        )

    receipt = execute(gateway(tmp_path, runner), request(tmp_path))

    assert receipt.final_response == '{"summary":"ok"}'


def test_read_only_profile_disables_write_edit_and_shell_tools(tmp_path):
    captured: dict[str, object] = {}

    def runner(command, _workspace, environment, _timeout, _cancellation, _on_start):
        captured["config"] = json.loads(
            Path(environment["OPENCODE_CONFIG"]).read_text(encoding="utf-8")
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    execute(gateway(tmp_path, runner), request(tmp_path, role=SpecialistRole.RISK_REVIEW))

    assert captured["config"]["tools"] == {
        "read": False,
        "glob": False,
        "grep": False,
        "list": False,
        "write": False,
        "edit": False,
        "apply_patch": False,
        "bash": False,
        "task": False,
        "skill": False,
        "lsp": False,
        "webfetch": False,
        "websearch": False,
    }
    assert captured["config"]["permission"]["read"] == "deny"
