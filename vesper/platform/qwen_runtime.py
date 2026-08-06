"""Serialized controller loop for qwen:64k."""

from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .agent_tools import AgentToolGateway, ToolPermissionError
from .context_budget import ContextBudgetGuard, MAX_TOOL_CALLS
from .contracts import AgentRole, SpecialistRole


class InferenceBusyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class QwenTurnResult:
    content: str
    prompt_tokens: int
    tool_calls_used: int
    transcript_events: tuple[dict[str, object], ...] = ()
    messages: tuple[dict[str, object], ...] = ()
    completion_tokens: int = 0


@contextmanager
def inference_lease(state_root: Path, *, wait_seconds: float = 0):
    state_root.mkdir(parents=True, exist_ok=True)
    path = state_root / "qwen-inference.lock"
    handle = path.open("a+b")
    if path.stat().st_size == 0:
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)
    deadline = time.monotonic() + wait_seconds
    locked = False
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise InferenceBusyError("qwen:64k inference is already active") from exc
                time.sleep(0.05)
                handle.seek(0)
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


class QwenTurnRunner:
    def __init__(
        self,
        client,
        tools: AgentToolGateway,
        state_root: Path,
        *,
        wait_seconds: float = 0,
    ) -> None:
        self.client = client
        self.tools = tools
        self.state_root = state_root
        self.guard = ContextBudgetGuard()
        self.wait_seconds = wait_seconds

    def run(
        self,
        role: AgentRole | SpecialistRole | str,
        prompt: str,
        *,
        allowed_tools: Sequence[str] | None = None,
        response_format: Mapping[str, object] | None = None,
        audit: Callable[[dict[str, str | int]], None] | None = None,
        messages: Sequence[Mapping[str, object]] | None = None,
        system_prompt: str | None = None,
        extra_tool_schemas: Mapping[str, Mapping[str, object]] | None = None,
        on_event: Callable[[dict[str, object]], None] | None = None,
    ) -> QwenTurnResult:
        agent_role = AgentRole(role)
        conversation: list[dict[str, object]] = [dict(message) for message in (messages or ())]
        if not conversation and system_prompt:
            conversation.append({"role": "system", "content": system_prompt})
        conversation.append({"role": "user", "content": prompt})
        used = 0
        observed = 0
        transcript_events: list[dict[str, object]] = []
        schemas = self._tool_schemas(agent_role, allowed_tools, extra_tool_schemas)
        permitted_tools = {schema["function"]["name"] for schema in schemas}
        with inference_lease(self.state_root, wait_seconds=self.wait_seconds):
            while True:
                response = self.client.chat(conversation, tools=schemas)
                observed = response.prompt_tokens
                self.guard.validate(
                    prompt_tokens=observed, tool_calls=used + len(response.tool_calls)
                )
                if on_event is not None:
                    on_event(
                        {
                            "event_type": "model_response",
                            "prompt_tokens": observed,
                            "completion_tokens": getattr(response, "completion_tokens", 0),
                            "tool_calls": len(response.tool_calls),
                            "tool_calls_used": used,
                        }
                    )
                if not response.tool_calls:
                    if response_format is None:
                        transcript_events.append(
                            {
                                "speaker": "assistant",
                                "event_type": "message",
                                "content": response.content,
                            }
                        )
                        return QwenTurnResult(
                            response.content,
                            observed,
                            used,
                            tuple(transcript_events),
                            tuple(conversation + [{"role": "assistant", "content": response.content}]),
                            getattr(response, "completion_tokens", 0),
                        )
                    if response.content:
                        transcript_events.append(
                            {
                                "speaker": "assistant",
                                "event_type": "message",
                                "content": response.content,
                                "metadata": {"phase": "pre-structured"},
                            }
                        )
                    final = self.client.chat(conversation, response_format=response_format)
                    observed = final.prompt_tokens
                    self.guard.validate(
                        prompt_tokens=observed, tool_calls=used + len(final.tool_calls)
                    )
                    if on_event is not None:
                        on_event(
                            {
                                "event_type": "model_response",
                                "prompt_tokens": observed,
                                "completion_tokens": getattr(final, "completion_tokens", 0),
                                "tool_calls": 0,
                                "tool_calls_used": used,
                            }
                        )
                    if final.tool_calls:
                        raise ToolPermissionError(
                            "tools are disabled during the final structured response"
                        )
                    transcript_events.append(
                        {
                            "speaker": "assistant",
                            "event_type": "message",
                            "content": final.content,
                            "metadata": {"phase": "structured-final"},
                        }
                    )
                    return QwenTurnResult(
                        final.content,
                        observed,
                        used,
                        tuple(transcript_events),
                        tuple(conversation + [{"role": "assistant", "content": final.content}]),
                        getattr(final, "completion_tokens", 0),
                    )
                transcript_events.append(
                    {
                        "speaker": "assistant",
                        "event_type": "tool_call",
                        "content": response.content,
                        "metadata": {
                            "tool_calls": [
                                {"name": call.name, "arguments": call.arguments}
                                for call in response.tool_calls
                            ]
                        },
                    }
                )
                if on_event is not None:
                    on_event(transcript_events[-1])
                conversation.append(
                    {
                        "role": "assistant",
                        "content": response.content,
                        "tool_calls": [
                            {
                                "function": {
                                    "name": call.name,
                                    "arguments": call.arguments,
                                }
                            }
                            for call in response.tool_calls
                        ],
                    }
                )
                for call in response.tool_calls:
                    if call.name not in permitted_tools:
                        if audit is not None:
                            audit({"name": call.name, "status": "rejected-profile-tool"})
                        raise ToolPermissionError(
                            f"tool is not allowed by the active profile: {call.name}"
                        )
                    if used >= MAX_TOOL_CALLS:
                        self.guard.validate(prompt_tokens=observed, tool_calls=used + 1)
                    arguments_sha256 = hashlib.sha256(
                        json.dumps(call.arguments, sort_keys=True, separators=(",", ":")).encode(
                            "utf-8"
                        )
                    ).hexdigest()
                    try:
                        result = self.tools.execute(agent_role, call)
                    except Exception:
                        if audit is not None:
                            audit(
                                {
                                    "name": call.name,
                                    "status": "rejected",
                                    "arguments_sha256": arguments_sha256,
                                }
                            )
                        raise
                    used += 1
                    if audit is not None:
                        audit(
                            {
                                "name": call.name,
                                "status": "completed",
                                "arguments_sha256": arguments_sha256,
                                "output_sha256": hashlib.sha256(
                                    result.output.encode("utf-8")
                                ).hexdigest(),
                            }
                        )
                    conversation.append(
                        {
                            "role": "tool",
                            "tool_name": call.name,
                            "content": json.dumps(result.model_dump()),
                        }
                    )
                    transcript_events.append(
                        {
                            "speaker": "tool",
                            "event_type": "tool_result",
                            "content": result.model_dump(),
                            "metadata": {
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                        }
                    )
                    if on_event is not None:
                        on_event(transcript_events[-1])

    @staticmethod
    def _tool_schemas(
        role: AgentRole,
        allowed_tools: Sequence[str] | None = None,
        extra_tool_schemas: Mapping[str, Mapping[str, object]] | None = None,
    ) -> tuple[dict[str, object], ...]:
        names = ["read_file", "search_text"]
        if role is AgentRole.DEVELOPMENT:
            names.extend(("write_file", "git_diff_check"))
        parameters = {
            "read_file": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            "search_text": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            "write_file": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "expected_sha256": {"type": ["string", "null"]},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            "git_diff_check": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        }
        if extra_tool_schemas:
            names.extend(name for name in extra_tool_schemas if name not in names)
        if allowed_tools is not None:
            unknown = set(allowed_tools) - set(names)
            if unknown:
                raise ValueError(
                    f"role tool allowlist contains unsupported tools: {sorted(unknown)}"
                )
            names = [name for name in names if name in allowed_tools]
        extra = extra_tool_schemas or {}
        return tuple(
            dict(extra[name])
            if name in extra
            else {
                "type": "function",
                "function": {
                    "name": name,
                    "description": "Controller-mediated bounded local tool.",
                    "parameters": parameters[name],
                },
            }
            for name in names
        )
