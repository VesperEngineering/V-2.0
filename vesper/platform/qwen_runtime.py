"""Serialized controller loop for qwen:64k."""

from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

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
        audit: Callable[[dict[str, str | int]], None] | None = None,
    ) -> QwenTurnResult:
        agent_role = AgentRole(role)
        messages: list[dict[str, object]] = [{"role": "user", "content": prompt}]
        used = 0
        observed = 0
        schemas = self._tool_schemas(agent_role, allowed_tools)
        permitted_tools = {schema["function"]["name"] for schema in schemas}
        with inference_lease(self.state_root, wait_seconds=self.wait_seconds):
            while True:
                response = self.client.chat(messages, tools=schemas)
                observed = response.prompt_tokens
                self.guard.validate(
                    prompt_tokens=observed, tool_calls=used + len(response.tool_calls)
                )
                if not response.tool_calls:
                    return QwenTurnResult(response.content, observed, used)
                messages.append(
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
                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": call.name,
                            "content": json.dumps(result.model_dump()),
                        }
                    )

    @staticmethod
    def _tool_schemas(
        role: AgentRole, allowed_tools: Sequence[str] | None = None
    ) -> tuple[dict[str, object], ...]:
        names = ["read_file", "search_text"]
        if role is AgentRole.DEVELOPMENT:
            names.extend(("write_file", "git_diff_check"))
        if allowed_tools is not None:
            unknown = set(allowed_tools) - set(names)
            if unknown:
                raise ValueError(
                    f"role tool allowlist contains unsupported tools: {sorted(unknown)}"
                )
            names = [name for name in names if name in allowed_tools]
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
        return tuple(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": "Controller-mediated bounded local tool.",
                    "parameters": parameters[name],
                },
            }
            for name in names
        )
