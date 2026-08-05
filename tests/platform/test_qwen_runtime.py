import multiprocessing
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.platform.agent_tools import AgentToolGateway, AgentToolRequest, ToolPermissionError
from vesper.platform.context_budget import ContextBudgetExceeded, ContextBudgetGuard
from vesper.platform.contracts import (
    AgentRole,
    PermissionSet,
    SandboxMode,
    SpecialistInput,
    SpecialistRole,
)
from vesper.platform.ollama import OllamaClient, OllamaProtocolError, QwenSpecialistAdapter
from vesper.platform.persistence import PlatformPaths
from vesper.platform.qwen_runtime import InferenceBusyError, QwenTurnRunner, inference_lease
from vesper.platform.service import LocalPlatformService


def _hold_inference_lease(state_root, ready, release) -> None:
    with inference_lease(Path(state_root)):
        ready.set()
        if not release.wait(timeout=30):
            raise RuntimeError("parent did not release the test inference lease")


def test_context_budget_reserves_full_output_window():
    guard = ContextBudgetGuard()
    guard.validate(prompt_tokens=49_152, tool_calls=8)
    with pytest.raises(ContextBudgetExceeded):
        guard.validate(prompt_tokens=49_153, tool_calls=0)
    with pytest.raises(ContextBudgetExceeded):
        guard.validate(prompt_tokens=1, tool_calls=9)


def test_inference_lease_blocks_another_process_then_releases(tmp_path):
    state_root = tmp_path / "state"
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    holder = context.Process(
        target=_hold_inference_lease,
        args=(str(state_root), ready, release),
    )
    holder.start()
    try:
        assert ready.wait(timeout=10), "child did not acquire the inference lease"
        with pytest.raises(InferenceBusyError, match="already active"):
            with inference_lease(state_root):
                pass

        release.set()
        holder.join(timeout=10)
        assert holder.exitcode == 0

        with inference_lease(state_root):
            pass
    finally:
        release.set()
        holder.join(timeout=2)
        if holder.is_alive():
            holder.terminate()
            holder.join(timeout=5)


def test_ollama_client_pins_model_context_and_loopback_endpoint():
    calls = []

    def transport(url, payload, timeout):
        calls.append((url, payload, timeout))
        return {"message": {"content": "done", "tool_calls": []}, "prompt_eval_count": 12}

    response = OllamaClient(transport=transport).chat([{"role": "user", "content": "hello"}])
    url, payload, _ = calls[0]
    assert url == "http://127.0.0.1:11434/api/chat"
    assert payload["model"] == "qwen:64k"
    assert payload["options"]["num_ctx"] == 65_536
    assert response.prompt_tokens == 12


def test_ollama_client_rejects_missing_observed_usage():
    client = OllamaClient(transport=lambda *_: {"message": {"content": "no usage"}})
    with pytest.raises(OllamaProtocolError):
        client.chat([{"role": "user", "content": "hello"}])


def test_tool_gateway_enforces_role_and_protected_paths(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "notes.txt").write_text("alpha beta", encoding="utf-8")
    gateway = AgentToolGateway(root)
    read = gateway.execute(
        AgentRole.MODEL_RESEARCHER,
        AgentToolRequest(name="read_file", arguments={"path": "notes.txt"}),
    )
    assert read.output == "alpha beta"
    with pytest.raises(ToolPermissionError):
        gateway.execute(
            AgentRole.MODEL_RESEARCHER,
            AgentToolRequest(name="write_file", arguments={"path": "new.txt", "content": "x"}),
        )
    (root / ".env.local").write_text("TOKEN=hidden", encoding="utf-8")
    with pytest.raises(ToolPermissionError):
        gateway.execute(
            AgentRole.PRODUCT,
            AgentToolRequest(name="read_file", arguments={"path": ".env.local"}),
        )
    with pytest.raises(ToolPermissionError):
        gateway.execute(
            AgentRole.DEVELOPMENT,
            AgentToolRequest(
                name="write_file", arguments={"path": "vesper/data/massive/x", "content": "x"}
            ),
        )


def test_turn_rejects_oversized_response_before_any_tool_executes(tmp_path):
    class Client:
        def chat(self, _messages, tools=()):
            return type(
                "Response",
                (),
                {
                    "content": "",
                    "prompt_tokens": 49_153,
                    "tool_calls": (
                        AgentToolRequest(name="read_file", arguments={"path": "notes.txt"}),
                    ),
                },
            )()

    root = tmp_path / "repo"
    root.mkdir()
    (root / "notes.txt").write_text("secret", encoding="utf-8")
    gateway = AgentToolGateway(root)
    calls = []
    original = gateway.execute

    def tracked(*args):
        calls.append(args)
        return original(*args)

    gateway.execute = tracked
    runner = QwenTurnRunner(Client(), gateway, tmp_path / "state")
    with pytest.raises(ContextBudgetExceeded):
        runner.run(AgentRole.PRODUCT, "inspect")
    assert calls == []


def test_turn_executes_allowlisted_tool_then_returns_content(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "notes.txt").write_text("bounded", encoding="utf-8")
    responses = iter(
        (
            type(
                "Response",
                (),
                {
                    "content": "",
                    "prompt_tokens": 20,
                    "tool_calls": (
                        AgentToolRequest(name="read_file", arguments={"path": "notes.txt"}),
                    ),
                },
            )(),
            type("Response", (), {"content": "final", "prompt_tokens": 30, "tool_calls": ()})(),
        )
    )

    class Client:
        def chat(self, _messages, tools=()):
            return next(responses)

    audit = []
    result = QwenTurnRunner(Client(), AgentToolGateway(root), tmp_path / "state").run(
        AgentRole.PRODUCT, "inspect", audit=audit.append
    )
    assert result.content == "final"
    assert result.tool_calls_used == 1
    assert audit[0]["name"] == "read_file"
    assert audit[0]["status"] == "completed"
    assert "output_sha256" in audit[0]


def test_turn_honors_narrower_profile_tool_allowlist(tmp_path):
    seen = []

    class Client:
        def chat(self, _messages, tools=()):
            seen.extend(tool["function"]["name"] for tool in tools)
            return type("Response", (), {"content": "done", "prompt_tokens": 5, "tool_calls": ()})()

    QwenTurnRunner(Client(), AgentToolGateway(tmp_path), tmp_path / "state").run(
        AgentRole.PRODUCT, "inspect", allowed_tools=("read_file",)
    )
    assert seen == ["read_file"]


def test_turn_rejects_model_invented_tool_outside_profile_allowlist(tmp_path):
    class Client:
        def chat(self, _messages, tools=()):
            return type(
                "Response",
                (),
                {
                    "content": "",
                    "prompt_tokens": 5,
                    "tool_calls": (AgentToolRequest(name="search_text", arguments={"query": "x"}),),
                },
            )()

    audit = []
    with pytest.raises(ToolPermissionError, match="active profile"):
        QwenTurnRunner(Client(), AgentToolGateway(tmp_path), tmp_path / "state").run(
            AgentRole.PRODUCT,
            "inspect",
            allowed_tools=("read_file",),
            audit=audit.append,
        )
    assert audit == [{"name": "search_text", "status": "rejected-profile-tool"}]


def test_qwen_specialist_adapter_returns_existing_receipt_contract(tmp_path):
    now = datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc)
    client = OllamaClient(
        transport=lambda *_: {
            "message": {"content": "{}", "tool_calls": []},
            "prompt_eval_count": 10,
        }
    )
    adapter = QwenSpecialistAdapter(tmp_path, tmp_path / "state", client=client, clock=lambda: now)
    request = SpecialistInput(
        run_id="run",
        task_id="task",
        repository_revision="abc",
        created_at=now,
        role=SpecialistRole.PRODUCT,
        attempt=1,
        instructions="Inspect",
        workspace=".",
        memory_namespace=("profiles", "v20-product"),
        permissions=PermissionSet(
            sandbox=SandboxMode.READ_ONLY, read_paths=(".",), allowed_tools=("read", "search")
        ),
    )
    receipt = adapter.execute(
        request,
        prompt="Return JSON",
        model="qwen:64k",
        timeout_seconds=10,
        execution_id="execution-1",
        reasoning_effort=None,
        output_schema={"type": "object"},
    )
    assert receipt.model == "qwen:64k"
    assert receipt.authentication_type == "local-ollama"
    assert receipt.final_response == "{}"


def test_service_accepts_qwen_runtime_without_fallback(tmp_path):
    service = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"), specialist_runtime="ollama-qwen"
    )
    assert service._specialist_runtime == "ollama-qwen"
