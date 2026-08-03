"""Loopback-only Ollama adapter pinned to qwen:64k."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .agent_tools import AgentToolRequest
from .context_budget import MAX_CONTEXT_TOKENS, OUTPUT_RESERVE_TOKENS
from .contracts import CodexExecutionReceipt, ExecutionStatus, SpecialistInput

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
QWEN_MODEL = "qwen:64k"


class OllamaProtocolError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OllamaResponse:
    content: str
    prompt_tokens: int
    tool_calls: tuple[AgentToolRequest, ...]


def _default_transport(
    url: str, payload: Mapping[str, object], timeout: float
) -> Mapping[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed loopback
        parsed = json.loads(response.read())
    if not isinstance(parsed, dict):
        raise OllamaProtocolError("Ollama response must be an object")
    return parsed


class OllamaClient:
    def __init__(
        self,
        *,
        transport: Callable[
            [str, Mapping[str, object], float], Mapping[str, object]
        ] = _default_transport,
        timeout_seconds: float = 300,
    ) -> None:
        self._transport = transport
        self._timeout = timeout_seconds

    def chat(
        self,
        messages: Sequence[Mapping[str, object]],
        tools: Sequence[Mapping[str, object]] = (),
        response_format: Mapping[str, object] | None = None,
    ) -> OllamaResponse:
        payload: dict[str, object] = {
            "model": QWEN_MODEL,
            "messages": list(messages),
            "stream": False,
            "options": {"num_ctx": MAX_CONTEXT_TOKENS, "num_predict": OUTPUT_RESERVE_TOKENS},
        }
        if tools:
            payload["tools"] = list(tools)
        if response_format is not None:
            payload["format"] = dict(response_format)
            payload["options"]["temperature"] = 0
        raw = self._transport(OLLAMA_CHAT_URL, payload, self._timeout)
        message = raw.get("message")
        prompt_tokens = raw.get("prompt_eval_count")
        if not isinstance(message, Mapping) or type(prompt_tokens) is not int:
            raise OllamaProtocolError("Ollama response lacks message or observed prompt usage")
        content = message.get("content", "")
        calls = message.get("tool_calls", ())
        if not isinstance(content, str) or not isinstance(calls, (list, tuple)):
            raise OllamaProtocolError("Ollama message is malformed")
        parsed_calls: list[AgentToolRequest] = []
        for call in calls:
            if not isinstance(call, Mapping) or not isinstance(call.get("function"), Mapping):
                raise OllamaProtocolError("Ollama tool call is malformed")
            function = call["function"]
            parsed_calls.append(
                AgentToolRequest(name=function.get("name"), arguments=function.get("arguments", {}))
            )
        return OllamaResponse(
            content=content, prompt_tokens=prompt_tokens, tool_calls=tuple(parsed_calls)
        )


class QwenSpecialistAdapter:
    """Adapt the controller Qwen loop to the existing specialist receipt port."""

    def __init__(
        self,
        repository_root: Path,
        state_root: Path,
        *,
        client=None,
        clock=None,
        journal=None,
    ) -> None:
        self._repository_root = repository_root.resolve()
        self._state_root = state_root
        self._client = client or OllamaClient()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._journal = journal

    def execute(
        self,
        request: SpecialistInput,
        *,
        prompt: str,
        model: str,
        timeout_seconds: float,
        execution_id: str | None,
        reasoning_effort: str | None,
        output_schema: Mapping[str, object] | None,
    ) -> CodexExecutionReceipt:
        del timeout_seconds, reasoning_effort
        if model != QWEN_MODEL or execution_id is None:
            raise OllamaProtocolError(
                "Qwen specialist runtime requires qwen:64k and an execution ID"
            )
        from .agent_tools import AgentToolGateway
        from .qwen_runtime import QwenTurnRunner

        workspace = Path(request.workspace)
        if not workspace.is_absolute():
            workspace = self._repository_root / workspace
        workspace = workspace.resolve()
        if workspace != self._repository_root and self._repository_root not in workspace.parents:
            raise OllamaProtocolError("specialist workspace escapes the repository")
        runner = QwenTurnRunner(self._client, AgentToolGateway(workspace), self._state_root)
        started_at = self._clock()
        schema_instruction = (
            ""
            if output_schema is None
            else "\nReturn only JSON matching:\n" + json.dumps(output_schema)
        )
        tool_index = 0

        def audit_tool(payload: dict[str, str | int]) -> None:
            nonlocal tool_index
            if self._journal is None:
                return
            from .contracts import AgentRole, JournalEventType

            tool_index += 1
            self._journal.append(
                event_id=(
                    f"{request.run_id}:{request.role.value}:tool:{request.attempt}:{tool_index}"
                ),
                role=AgentRole(request.role.value),
                session_id=request.run_id,
                run_id=request.run_id,
                task_id=request.task_id,
                repository_revision=request.repository_revision,
                created_at=request.created_at,
                event_type=JournalEventType.TOOL_RESULT,
                payload=payload,
            )

        tool_names = {
            "read": "read_file",
            "search": "search_text",
            "write": "write_file",
            "test": "git_diff_check",
        }
        result = runner.run(
            request.role.value,
            prompt + schema_instruction,
            allowed_tools=tuple(tool_names[tool] for tool in request.permissions.allowed_tools),
            response_format=output_schema,
            audit=audit_tool,
        )
        finished_at = self._clock()
        return CodexExecutionReceipt(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            execution_id=execution_id,
            role=request.role,
            attempt=request.attempt,
            status=ExecutionStatus.COMPLETED,
            sandbox=request.permissions.sandbox,
            model=QWEN_MODEL,
            workspace=request.workspace,
            approval_mode="deny-all",
            authentication_type="local-ollama",
            permission_profile="controller-tools",
            started_at=started_at,
            finished_at=finished_at,
            final_response=result.content,
            streamed_events=(
                {
                    "prompt_tokens": result.prompt_tokens,
                    "tool_calls_used": result.tool_calls_used,
                },
            ),
        )
