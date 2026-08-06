from pathlib import Path

import pytest

from vesper.platform.agent_tools import AgentToolRequest, ToolPermissionError
from vesper.platform.chat import (
    CHAT_ROLE,
    QWEN_MODEL,
    ChatService,
    ChatToolGateway,
    load_chat_context,
    validate_chat_options,
    validate_skill_path,
)
from vesper.platform.contracts import AgentRole
from vesper.platform.ollama import OllamaClient


def test_chat_policy_is_qwen_only_and_write_gated():
    assert validate_chat_options(
        role=CHAT_ROLE, model=QWEN_MODEL, tools=("read_file",), allow_write=False
    ) == ("read_file",)
    with pytest.raises(ValueError, match="qwen:64k"):
        validate_chat_options(role=CHAT_ROLE, model="other", tools=(), allow_write=False)
    with pytest.raises(ValueError, match="allow-write"):
        validate_chat_options(
            role=CHAT_ROLE, model=QWEN_MODEL, tools=("write_file",), allow_write=False
        )


def test_skill_path_cannot_escape_approved_directory(tmp_path):
    skills = tmp_path / "knowledge" / "skills"
    skills.mkdir(parents=True)
    skill = skills / "engineering.md"
    skill.write_text("rules", encoding="utf-8")
    assert validate_skill_path(tmp_path, "knowledge/skills/engineering.md") == skill
    with pytest.raises(ValueError, match="knowledge/skills"):
        validate_skill_path(tmp_path, "knowledge/other.md")


def test_context_loads_nested_rules_and_task_matching_skills(tmp_path):
    repository = tmp_path / "repo"
    workspace = repository / "TUI testing" / "component"
    skills = repository / "knowledge" / "skills"
    workspace.mkdir(parents=True)
    skills.mkdir(parents=True)
    (repository / "AGENTS.md").write_text("root rules", encoding="utf-8")
    (workspace.parent / "AGENTS.md").write_text("TUI rules", encoding="utf-8")
    (skills / "v20-engineering.md").write_text(
        "---\nvesper_status: approved\nvesper_scope: v20-development\ntags: [engineering]\n---\nengineering skill",
        encoding="utf-8",
    )
    (skills / "quant.md").write_text(
        "---\nvesper_status: approved\nvesper_scope: shared\ntags: [quant, factors, models]\n---\nquant skill",
        encoding="utf-8",
    )
    (skills / "handoff.md").write_text(
        "---\nvesper_status: approved\nvesper_scope: shared\ntags: [handoff]\n---\nhandoff skill",
        encoding="utf-8",
    )

    context = load_chat_context(
        repository,
        (),
        workspace_root=workspace,
        task_hint="check the factor model backtest",
    )

    assert "root rules" in context
    assert "TUI rules" in context
    assert "engineering skill" in context
    assert "quant skill" in context
    assert "handoff skill" not in context


def test_chat_gateway_keeps_workspace_tools_narrow(tmp_path):
    repository = tmp_path / "repo"
    workspace = repository / "TUI testing"
    workspace.mkdir(parents=True)
    (workspace / "notes.md").write_text("tui", encoding="utf-8")
    gateway = ChatToolGateway(repository, workspace)
    result = gateway.execute(
        AgentRole.DEVELOPMENT,
        AgentToolRequest(name="read_file", arguments={"path": "notes.md"}),
    )
    assert result.output == "tui"
    with pytest.raises(ToolPermissionError):
        gateway.execute(
            AgentRole.DEVELOPMENT,
            AgentToolRequest(name="read_file", arguments={"path": "../outside.txt"}),
        )


def test_chat_service_persists_redacted_turn_and_returns_to_eof(tmp_path):
    repository = tmp_path / "repo"
    workspace = repository / "TUI testing"
    skills = repository / "knowledge" / "skills"
    workspace.mkdir(parents=True)
    skills.mkdir(parents=True)
    (repository / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    (skills / "v20-engineering.md").write_text("engineering rules", encoding="utf-8")
    (skills / "v20-engineering.md").write_text("engineering rules", encoding="utf-8")

    class Client:
        responses = iter(("done",))

        def chat(self, messages, tools=(), response_format=None):
            if response_format is not None:
                return type("Response", (), {"content": next(self.responses), "prompt_tokens": 12, "tool_calls": ()})()
            assert messages[-1]["role"] == "user"
            assert messages[0]["role"] == "system"
            return type("Response", (), {"content": next(self.responses), "prompt_tokens": 12, "tool_calls": ()})()

    prompts = iter(("show me the TUI",))
    output: list[str] = []

    def ask(_prompt):
        try:
            return next(prompts)
        except StopIteration as exc:
            raise EOFError from exc

    result = ChatService(
        repository,
        tmp_path / "state",
        repository / "knowledge",
        client=Client(),
        input_fn=ask,
        output_fn=output.append,
    ).run(
        role=CHAT_ROLE,
        model=QWEN_MODEL,
        workspace="TUI testing",
        skills=(),
        tools=("read_file",),
        allow_write=False,
        session_id="test-session",
        json_output=False,
    )
    assert result["events"] == 1
    transcript = next((repository / "knowledge" / "sessions").rglob("*.md"))
    assert "show me the TUI" in transcript.read_text(encoding="utf-8")
    assert "done" in transcript.read_text(encoding="utf-8")
    assert any("qwen> done" in line for line in output)


def test_chat_exit_does_not_run_dream_gate(monkeypatch, tmp_path):
    repository = tmp_path / "repo"
    workspace = repository / "TUI testing"
    skills = repository / "knowledge" / "skills"
    workspace.mkdir(parents=True)
    skills.mkdir(parents=True)
    (repository / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    (skills / "v20-engineering.md").write_text("engineering rules", encoding="utf-8")

    calls: list[str] = []

    def unexpected_dream(self):
        calls.append("dream")
        raise AssertionError("normal chat exit must not run Dream Gate")

    monkeypatch.setattr("vesper.platform.chat.DreamGate.run", unexpected_dream)

    class Client:
        def chat(self, messages, tools=(), response_format=None):
            return type("Response", (), {"content": "done", "prompt_tokens": 1, "tool_calls": ()})()

    prompts = iter(("hello", "/quit"))
    ChatService(
        repository,
        tmp_path / "state",
        repository / "knowledge",
        client=Client(),
        input_fn=lambda _prompt: next(prompts),
        output_fn=lambda _line: None,
    ).run(
        role=CHAT_ROLE,
        model=QWEN_MODEL,
        workspace="TUI testing",
        skills=(),
        tools=("read_file",),
        allow_write=False,
        session_id="no-dream-session",
        json_output=False,
    )

    assert calls == []


def test_chat_slash_commands_are_local_and_do_not_call_qwen(tmp_path):
    repository = tmp_path / "repo"
    workspace = repository / "TUI testing"
    skills = repository / "knowledge" / "skills"
    workspace.mkdir(parents=True)
    skills.mkdir(parents=True)
    (repository / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    (skills / "v20-engineering.md").write_text("engineering rules", encoding="utf-8")

    class Client:
        def chat(self, *_args, **_kwargs):
            raise AssertionError("slash commands must not call Qwen")

    prompts = iter(("/help", "/status", "/model", "/skills", "/tools", "/quit"))
    output: list[str] = []

    def ask(_prompt):
        return next(prompts)

    result = ChatService(
        repository,
        tmp_path / "state",
        repository / "knowledge",
        client=Client(),
        input_fn=ask,
        output_fn=output.append,
    ).run(
        role=CHAT_ROLE,
        model=QWEN_MODEL,
        workspace="TUI testing",
        skills=(),
        tools=("read_file",),
        allow_write=False,
        session_id="slash-session",
        json_output=False,
    )

    assert result["events"] == 0
    rendered = "\n".join(output)
    assert "/compact" in rendered
    assert "qwen:64k" in rendered
    assert "read_file" in rendered


def test_chat_loads_approved_dream_memory_on_next_session(tmp_path):
    repository = tmp_path / "repo"
    workspace = repository / "TUI testing"
    skills = repository / "knowledge" / "skills"
    memory = repository / "knowledge" / "memory" / "v20-core"
    workspace.mkdir(parents=True)
    skills.mkdir(parents=True)
    memory.mkdir(parents=True)
    (repository / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    (skills / "v20-engineering.md").write_text("engineering rules", encoding="utf-8")
    (memory / "dream.md").write_text(
        "---\nvesper_id: dream-note\nvesper_kind: memory\nvesper_status: approved\n"
        "vesper_scope: shared\ntitle: Dream note\n---\n\nDreamed fact.\n",
        encoding="utf-8",
    )
    seen: list[str] = []

    class Client:
        def chat(self, messages, tools=(), response_format=None):
            seen.append(str(messages[0]["content"]))
            return type("Response", (), {"content": "done", "prompt_tokens": 1, "tool_calls": ()})()

    prompts = iter(("hello", "/quit"))
    ChatService(
        repository,
        tmp_path / "state",
        repository / "knowledge",
        client=Client(),
        input_fn=lambda _prompt: next(prompts),
        output_fn=lambda _line: None,
    ).run(
        role=CHAT_ROLE,
        model=QWEN_MODEL,
        workspace="TUI testing",
        skills=(),
        tools=("read_file",),
        allow_write=False,
        session_id="memory-session",
        json_output=False,
    )

    assert "Dreamed fact." in seen[0]


def test_model_command_selects_daily_profile_and_reports_runtime_context(tmp_path):
    repository = tmp_path / "repo"
    workspace = repository / "TUI testing"
    skills = repository / "knowledge" / "skills"
    workspace.mkdir(parents=True)
    skills.mkdir(parents=True)
    (repository / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    (skills / "v20-engineering.md").write_text("engineering rules", encoding="utf-8")
    seen_messages: list[list[dict[str, object]]] = []

    class Client:
        def chat(self, messages, tools=(), response_format=None):
            seen_messages.append([dict(message) for message in messages])
            return type("Response", (), {"content": "done", "prompt_tokens": 12, "tool_calls": ()})()

    prompts = iter(("/model daily", "hello", "/model", "/quit"))
    output: list[str] = []

    def ask(_prompt):
        return next(prompts)

    ChatService(
        repository,
        tmp_path / "state",
        repository / "knowledge",
        client=Client(),
        input_fn=ask,
        output_fn=output.append,
    ).run(
        role=CHAT_ROLE,
        model=QWEN_MODEL,
        workspace="TUI testing",
        skills=(),
        tools=("read_file",),
        allow_write=False,
        session_id="daily-session",
        json_output=False,
    )

    rendered = "\n".join(output)
    assert "mode: daily" in rendered
    assert "model: qwen:64k" in rendered
    assert "context_window: 65536" in rendered
    assert "daily" in str(seen_messages[0][0]["content"])


def test_chat_shows_runtime_context_and_tool_activity_before_final_answer(tmp_path):
    repository = tmp_path / "repo"
    workspace = repository / "TUI testing"
    skills = repository / "knowledge" / "skills"
    workspace.mkdir(parents=True)
    skills.mkdir(parents=True)
    (repository / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    (skills / "v20-engineering.md").write_text("engineering rules", encoding="utf-8")
    (workspace / "notes.md").write_text("tool-visible note", encoding="utf-8")
    responses = iter(
        (
            type(
                "Response",
                (),
                {
                    "content": "",
                    "prompt_tokens": 120,
                    "completion_tokens": 6,
                    "tool_calls": (
                        AgentToolRequest(name="read_file", arguments={"path": "notes.md"}),
                    ),
                },
            )(),
            type(
                "Response",
                (),
                {
                    "content": "I checked it.",
                    "prompt_tokens": 180,
                    "completion_tokens": 5,
                    "tool_calls": (),
                },
            )(),
        )
    )

    class Client:
        def chat(self, _messages, tools=(), response_format=None):
            return next(responses)

    prompts = iter(("inspect the note", "/quit"))
    output: list[str] = []

    def ask(_prompt):
        return next(prompts)

    ChatService(
        repository,
        tmp_path / "state",
        repository / "knowledge",
        client=Client(),
        input_fn=ask,
        output_fn=output.append,
    ).run(
        role=CHAT_ROLE,
        model=QWEN_MODEL,
        workspace="TUI testing",
        skills=(),
        tools=("read_file",),
        allow_write=False,
        session_id="telemetry-session",
        json_output=False,
    )

    rendered = "\n".join(output)
    assert "context_window: 65536" in rendered
    assert "skills:" in rendered
    assert "ctx: 120/49152" in rendered
    assert "left: 49032" in rendered
    assert "tool: read_file" in rendered
    assert "tool complete: read_file" in rendered
    assert "qwen> I checked it." in rendered


def test_chat_keeps_running_when_tool_turn_has_empty_final_response(tmp_path):
    repository = tmp_path / "repo"
    workspace = repository / "TUI testing"
    skills = repository / "knowledge" / "skills"
    workspace.mkdir(parents=True)
    skills.mkdir(parents=True)
    (repository / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    (skills / "v20-engineering.md").write_text("engineering rules", encoding="utf-8")
    (workspace / "notes.md").write_text("tool-visible note", encoding="utf-8")
    responses = iter(
        (
            type(
                "Response",
                (),
                {
                    "content": "",
                    "prompt_tokens": 120,
                    "completion_tokens": 6,
                    "tool_calls": (
                        AgentToolRequest(name="read_file", arguments={"path": "notes.md"}),
                    ),
                },
            )(),
            type(
                "Response",
                (),
                {
                    "content": "",
                    "prompt_tokens": 180,
                    "completion_tokens": 5,
                    "tool_calls": (),
                },
            )(),
        )
    )

    class Client:
        def chat(self, _messages, tools=(), response_format=None):
            return next(responses)

    prompts = iter(("inspect the note", "/quit"))
    output: list[str] = []

    result = ChatService(
        repository,
        tmp_path / "state",
        repository / "knowledge",
        client=Client(),
        input_fn=lambda _prompt: next(prompts),
        output_fn=output.append,
    ).run(
        role=CHAT_ROLE,
        model=QWEN_MODEL,
        workspace="TUI testing",
        skills=(),
        tools=("read_file",),
        allow_write=False,
        session_id="empty-final-session",
        json_output=False,
    )

    assert result["events"] == 3
    assert any("empty response" in line for line in output)
    assert any("bye" == line for line in output)


def test_ollama_response_reports_completion_tokens():
    client = OllamaClient(
        transport=lambda *_: {
            "message": {"content": "done", "tool_calls": []},
            "prompt_eval_count": 10,
            "eval_count": 4,
        }
    )

    response = client.chat([{"role": "user", "content": "hello"}])

    assert response.prompt_tokens == 10
    assert response.completion_tokens == 4
