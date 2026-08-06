"""Bounded interactive Qwen chat for V20 development work."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .agent_tools import AgentToolGateway, AgentToolRequest, AgentToolResult, ToolPermissionError
from .contracts import AgentRole
from .context_budget import MAX_CONTEXT_TOKENS, MAX_INPUT_TOKENS, OUTPUT_RESERVE_TOKENS
from .ollama import OllamaClient, QWEN_MODEL
from .qwen_runtime import QwenTurnRunner
from .dreaming import DreamGate
from .knowledge import KnowledgeSyncError, load_approved_documents
from .session_recorder import SessionRecorder

CHAT_ROLE = "v20-development"
DEFAULT_CHAT_MODE = "coding"
CHAT_MODES = {
    "coding": (
        "Coding mode: inspect current source, make the smallest safe change, and run a focused check. "
        "Keep explanations and tool arguments concise."
    ),
    "daily": (
        "Daily mode: help with concise planning, notes, explanations, and routine work. "
        "Do not edit code unless the user explicitly asks."
    ),
}
CHAT_TOOLS = (
    "read_file",
    "search_text",
    "codegraph_query",
    "codegraph_explore",
    "codegraph_node",
    "codegraph_affected",
    "write_file",
    "git_diff_check",
    "run_test",
)
READ_ONLY_CHAT_TOOLS = (
    "read_file",
    "search_text",
    "codegraph_query",
    "codegraph_explore",
    "codegraph_node",
    "codegraph_affected",
    "git_diff_check",
)
WRITE_CHAT_TOOLS = ("write_file", "run_test")
SLASH_COMMANDS = (
    "/help",
    "/status",
    "/model",
    "/mode",
    "/skills",
    "/tools",
    "/clear",
    "/compact",
    "/dream",
    "/diff",
    "/search",
    "/graph",
    "/test",
    "/quit",
)
DEFAULT_CHAT_SKILL = "knowledge/skills/v20-engineering.md"
MAX_COMMAND_OUTPUT = 32_000
MAX_CONTEXT_FILE = 24_000
MAX_CONTEXT_TOTAL = 45_000
MAX_ACTIVE_MEMORY_CONTEXT = 12_000
_WORD = re.compile(r"[a-z0-9]+")


def _tokens(value: str) -> set[str]:
    words = set(_WORD.findall(value.casefold()))
    return words | {word[:-1] for word in words if len(word) > 3 and word.endswith("s")}


def validate_chat_options(
    *, role: str, model: str, tools: Sequence[str], allow_write: bool
) -> tuple[str, ...]:
    if role != CHAT_ROLE:
        raise ValueError(f"chat role must be {CHAT_ROLE}")
    if model != QWEN_MODEL:
        raise ValueError(f"chat model must be {QWEN_MODEL}")
    unknown = set(tools) - set(CHAT_TOOLS)
    if unknown:
        raise ValueError(f"unsupported chat tools: {sorted(unknown)}")
    if not allow_write and set(tools) & set(WRITE_CHAT_TOOLS):
        raise ValueError("write/test tools require --allow-write")
    if len(set(tools)) != len(tuple(tools)):
        raise ValueError("chat tools must not be repeated")
    return tuple(tools)


def validate_skill_path(repository_root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts or not path.as_posix().startswith("knowledge/skills/"):
        raise ValueError("skills must be repository-relative paths under knowledge/skills")
    candidate = (repository_root / path).resolve()
    skills_root = (repository_root / "knowledge" / "skills").resolve()
    if candidate != skills_root and skills_root not in candidate.parents:
        raise ValueError("skill path escapes knowledge/skills")
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError(f"skill file is missing: {raw}")
    return candidate


def _instruction_paths(repository_root: Path, workspace_root: Path) -> tuple[Path, ...]:
    if workspace_root != repository_root and repository_root not in workspace_root.parents:
        raise ValueError("workspace escapes repository")
    ancestors = [workspace_root, *workspace_root.parents]
    paths = [
        path / "AGENTS.md"
        for path in reversed(ancestors)
        if path == repository_root or repository_root in path.parents
    ]
    return tuple(path for path in paths if path.is_file() and not path.is_symlink())


def _skill_metadata(path: Path) -> Mapping[str, object]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines or lines[0].strip() != "---":
            return {}
        boundary = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
        raw = yaml.safe_load("\n".join(lines[1:boundary]))
    except (OSError, StopIteration, yaml.YAMLError):
        return {}
    return raw if isinstance(raw, Mapping) else {}


def discover_applicable_skills(
    repository_root: Path,
    workspace_root: Path,
    task_hint: str,
    explicit_skills: Sequence[str],
) -> tuple[Path, ...]:
    skills_root = (repository_root / "knowledge" / "skills").resolve()
    tokens = _tokens(f"{workspace_root.name} {task_hint}")
    selected: list[Path] = [validate_skill_path(repository_root, DEFAULT_CHAT_SKILL)]
    selected.extend(validate_skill_path(repository_root, raw) for raw in explicit_skills)
    if skills_root.is_dir():
        for candidate in sorted(skills_root.rglob("*.md")):
            if candidate.is_symlink():
                continue
            relative = candidate.relative_to(repository_root).as_posix()
            if relative == DEFAULT_CHAT_SKILL or relative.endswith("/00-index.md"):
                continue
            metadata = _skill_metadata(candidate)
            if metadata.get("vesper_status") != "approved":
                continue
            scope = str(metadata.get("vesper_scope", "shared"))
            raw_tags = metadata.get("tags", ())
            if isinstance(raw_tags, str):
                raw_tags = (raw_tags,)
            tags = _tokens(" ".join(str(tag) for tag in raw_tags if isinstance(tag, str)))
            filename_words = _tokens(candidate.stem)
            if scope == "v20-development" or tokens & (tags | filename_words):
                selected.append(candidate)
    return tuple(dict.fromkeys(selected))


def load_chat_context(
    repository_root: Path,
    skills: Sequence[str],
    *,
    workspace_root: Path | None = None,
    task_hint: str = "",
    mode: str = DEFAULT_CHAT_MODE,
) -> str:
    if mode not in CHAT_MODES:
        raise ValueError(f"unknown chat mode: {mode}")
    workspace = repository_root if workspace_root is None else workspace_root.resolve()
    paths = _instruction_paths(repository_root, workspace)
    skill_paths = discover_applicable_skills(repository_root, workspace, task_hint, skills)
    sections: list[str] = [
        "You are the V20 development chat controller's local Qwen assistant.",
        f"Active mode: {mode}. {CHAT_MODES[mode]}",
        "Use only the supplied controller tools. Do not invent tool results.",
        "Work only inside the selected workspace. Protected files and arbitrary shell are unavailable.",
    ]
    total = 0
    knowledge_root = repository_root / "knowledge"
    if knowledge_root.is_dir():
        try:
            active_documents = load_approved_documents(knowledge_root)
        except KnowledgeSyncError:
            active_documents = ()
        memory_text = "\n\n".join(
            f"--- {document.source_path} ---\n{document.content}"
            for document in active_documents
        )[:MAX_ACTIVE_MEMORY_CONTEXT]
        if memory_text:
            sections.append(f"\n\n--- approved V20 memory ---\n{memory_text}")
            total += len(memory_text)
    for path in (*paths, *skill_paths):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")[:MAX_CONTEXT_FILE]
        section = f"\n\n--- {path.relative_to(repository_root).as_posix()} ---\n{text}"
        if total + len(section) > MAX_CONTEXT_TOTAL:
            break
        sections.append(section)
        total += len(section)
    return "".join(sections)


class ChatToolGateway:
    """Expose fixed local tools while keeping file scope and command scope separate."""

    def __init__(self, repository_root: Path, workspace_root: Path) -> None:
        self.repository_root = repository_root.resolve()
        self.workspace_root = workspace_root.resolve()
        self.files = AgentToolGateway(self.workspace_root)

    def execute(self, role: AgentRole, request: AgentToolRequest) -> AgentToolResult:
        if request.name in {"read_file", "search_text", "write_file", "git_diff_check"}:
            return self.files.execute(role, request)
        if request.name.startswith("codegraph_"):
            return self._codegraph(request)
        if request.name == "run_test":
            return self._run_test(role, request)
        raise ToolPermissionError(f"unknown chat tool: {request.name}")

    def _codegraph(self, request: AgentToolRequest) -> AgentToolResult:
        command_name = {
            "codegraph_query": "query",
            "codegraph_explore": "explore",
            "codegraph_node": "node",
            "codegraph_affected": "affected",
        }.get(request.name)
        if command_name is None:
            raise ToolPermissionError(f"unknown CodeGraph tool: {request.name}")
        executable = shutil.which("codegraph.cmd" if os.name == "nt" else "codegraph")
        if executable is None:
            raise ToolPermissionError("CodeGraph is not installed")
        args = [executable, command_name]
        if request.name == "codegraph_query":
            args.extend([self._arg(request, "search"), "--limit", str(self._int_arg(request, "limit", 10))])
        elif request.name == "codegraph_explore":
            args.extend([self._arg(request, "search"), "--max-files", str(self._int_arg(request, "max_files", 20))])
        elif request.name == "codegraph_node":
            if request.arguments.get("symbol"):
                args.extend([str(request.arguments["symbol"])])
            if request.arguments.get("file"):
                args.extend(["--file", self._repo_relative(request.arguments["file"])])
            if request.arguments.get("offset") is not None:
                args.extend(["--offset", str(self._int_arg(request, "offset", 0))])
            args.extend(["--limit", str(self._int_arg(request, "limit", 20))])
        else:
            files = self._arg(request, "files")
            for raw in files.split(","):
                args.append(self._repo_relative(raw.strip()))
            args.extend(["--depth", str(self._int_arg(request, "depth", 1))])
            if request.arguments.get("filter"):
                args.extend(["--filter", str(request.arguments["filter"])])
        args.extend(["--path", str(self.repository_root)])
        completed = subprocess.run(
            args,
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        output = (completed.stdout + completed.stderr).strip()
        if len(output) > MAX_COMMAND_OUTPUT:
            output = output[:MAX_COMMAND_OUTPUT] + "\n[OUTPUT TRUNCATED]"
        return AgentToolResult(name=request.name, output=output or f"exit={completed.returncode}", truncated=len(output) >= MAX_COMMAND_OUTPUT)

    def _run_test(self, role: AgentRole, request: AgentToolRequest) -> AgentToolResult:
        if role is not AgentRole.DEVELOPMENT:
            raise ToolPermissionError("tool is Development-only")
        kind = self._arg(request, "kind")
        target = self._repo_relative(self._arg(request, "target"))
        if kind == "pytest":
            command = ["uv", "run", "--locked", "python", "-m", "pytest", target]
        elif kind == "cargo":
            if not target.casefold().endswith("cargo.toml"):
                raise ToolPermissionError("cargo tests require a Cargo.toml target")
            command = ["cargo", "test", "--manifest-path", target]
        else:
            raise ToolPermissionError("test kind must be pytest or cargo")
        completed = subprocess.run(
            command,
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        output = (completed.stdout + completed.stderr).strip()
        if len(output) > MAX_COMMAND_OUTPUT:
            output = output[:MAX_COMMAND_OUTPUT] + "\n[OUTPUT TRUNCATED]"
        return AgentToolResult(name=request.name, output=output or f"exit={completed.returncode}", truncated=len(output) >= MAX_COMMAND_OUTPUT)

    @staticmethod
    def _arg(request: AgentToolRequest, name: str) -> str:
        value = request.arguments.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ToolPermissionError(f"tool argument {name} is required")
        return value.strip()

    @staticmethod
    def _int_arg(request: AgentToolRequest, name: str, default: int) -> int:
        value = request.arguments.get(name, default)
        if type(value) is not int or not 1 <= value <= 100:
            raise ToolPermissionError(f"tool argument {name} must be an integer from 1 to 100")
        return value

    def _repo_relative(self, raw: object) -> str:
        if not isinstance(raw, str) or not raw.strip():
            raise ToolPermissionError("repository path is required")
        path = Path(raw.strip())
        if path.is_absolute() or ".." in path.parts:
            raise ToolPermissionError("path must be repository-relative")
        candidate = (self.repository_root / path).resolve(strict=False)
        if candidate != self.repository_root and self.repository_root not in candidate.parents:
            raise ToolPermissionError("path escapes repository")
        if AgentToolGateway._is_protected(path):
            raise ToolPermissionError("protected path is unavailable")
        return path.as_posix()


class ChatService:
    def __init__(
        self,
        repository_root: Path,
        state_root: Path,
        knowledge_root: Path,
        *,
        client=None,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.state_root = state_root.resolve()
        self.knowledge_root = knowledge_root.resolve()
        self.client = client or OllamaClient()
        self.input_fn = input_fn
        self.output_fn = output_fn
        self.clock = clock

    def run(
        self,
        *,
        role: str,
        model: str,
        workspace: str,
        skills: Sequence[str],
        tools: Sequence[str] | None,
        allow_write: bool,
        session_id: str,
        json_output: bool,
    ) -> dict[str, object]:
        selected_tools = tuple(tools or (READ_ONLY_CHAT_TOOLS + (WRITE_CHAT_TOOLS if allow_write else ())))
        validate_chat_options(role=role, model=model, tools=selected_tools, allow_write=allow_write)
        workspace_path = self._workspace(workspace, allow_write=allow_write)
        gateway = ChatToolGateway(self.repository_root, workspace_path)
        runner = QwenTurnRunner(self.client, gateway, self.state_root, wait_seconds=900)
        recorder = SessionRecorder(self.knowledge_root, clock=self.clock)
        revision = self._revision()
        run_id = f"chat-{session_id}"
        state: dict[str, object] = {
            "history": None,
            "system_prompt": None,
            "mode": DEFAULT_CHAT_MODE,
            "instructions": _instruction_paths(self.repository_root, workspace_path),
            "skills": discover_applicable_skills(self.repository_root, workspace_path, "", skills),
        }
        events = 0
        if not json_output:
            self._render_header(state, model, workspace_path)
        while True:
            try:
                prompt = self.input_fn("" if json_output else "you> ")
            except (EOFError, KeyboardInterrupt):
                if not json_output:
                    self.output_fn("bye")
                break
            if not prompt.strip():
                continue
            if prompt.lstrip().startswith("/"):
                if self._handle_slash_command(
                    prompt,
                    state=state,
                    role=role,
                    model=model,
                    workspace_path=workspace_path,
                    session_id=session_id,
                    selected_tools=selected_tools,
                    allow_write=allow_write,
                    skills=skills,
                    gateway=gateway,
                    json_output=json_output,
                ):
                    break
                continue
            history = state["history"]
            if history is None:
                state["skills"] = discover_applicable_skills(
                    self.repository_root, workspace_path, prompt, skills
                )
                if not json_output:
                    self.output_fn(
                        f"context loaded: rules={len(state['instructions'])} skills={len(state['skills'])}"
                    )
            system_prompt = (
                load_chat_context(
                    self.repository_root,
                    skills,
                    workspace_root=workspace_path,
                    task_hint=prompt,
                    mode=str(state["mode"]),
                )
                if history is None
                else None
            )
            state["system_prompt"] = system_prompt
            recorder.record_event(
                role=role, session_id=session_id, run_id=run_id, task_id=run_id,
                repository_revision=revision, speaker="user", event_type="message", content=prompt,
            )
            try:
                result = runner.run(
                    AgentRole.DEVELOPMENT,
                    prompt,
                    allowed_tools=selected_tools,
                    extra_tool_schemas=CHAT_TOOL_SCHEMAS,
                    system_prompt=system_prompt,
                    messages=history,
                    on_event=lambda event: self._render_runtime_event(
                        event, state=state, json_output=json_output
                    ),
                )
            except BaseException:
                raise
            state["history"] = result.messages
            for event in result.transcript_events:
                events += 1
                speaker = str(event.get("speaker", "runtime"))
                event_type = str(event.get("event_type", "runtime"))
                event_content = event.get("content", "")
                event_metadata = event.get("metadata") if isinstance(event.get("metadata"), Mapping) else None
                if not (isinstance(event_content, str) and not event_content.strip() and event_metadata is None):
                    recorder.record_event(
                        role=role, session_id=session_id, run_id=run_id, task_id=run_id,
                        repository_revision=revision,
                        speaker=speaker if speaker in {"assistant", "tool", "runtime"} else "runtime",
                        event_type=event_type if event_type in {"message", "tool_call", "tool_result", "runtime"} else "runtime",
                        content=event_content, metadata=event_metadata,
                    )
                if json_output:
                    if event_type in {"tool_call", "tool_result"}:
                        continue
                    self.output_fn(json.dumps(event, sort_keys=True, default=str))
                elif speaker == "assistant" and event_type == "message" and event.get("content"):
                    self.output_fn(f"qwen> {event['content']}")
            if not json_output:
                if result.content.strip():
                    if not result.transcript_events:
                        self.output_fn(f"qwen> {result.content}")
                else:
                    self.output_fn("qwen> [empty response; try again]")
        return {"role": role, "model": model, "session_id": session_id, "events": events}

    def _run_dream(self, session_id: str, *, json_output: bool) -> None:
        try:
            report = DreamGate(
                self.knowledge_root,
                client=self.client,
                clock=self.clock,
                id_factory=lambda: f"dream-{session_id}",
            ).run()
        except Exception as exc:
            message = f"dream failed: {exc}"
            self._command_output(json_output, "dream", message)
            return
        self._command_output(
            json_output,
            "dream",
            f"saved {report.dream_id}; applied {len(report.applied_changes)} memory changes",
        )

    def _render_header(self, state: Mapping[str, object], model: str, workspace_path: Path) -> None:
        self.output_fn(
            f"V20 Qwen | model: {model} | mode: {state['mode']} | "
            f"context_window: {MAX_CONTEXT_TOKENS} | input_budget: {MAX_INPUT_TOKENS} | "
            f"output_reserve: {OUTPUT_RESERVE_TOKENS}"
        )
        self.output_fn(
            f"workspace: {workspace_path.relative_to(self.repository_root)} | "
            f"rules: {len(state['instructions'])} | skills: {len(state['skills'])} | "
            "Ctrl-C or /quit to exit"
        )

    def _render_runtime_event(
        self, event: Mapping[str, object], *, state: Mapping[str, object], json_output: bool
    ) -> None:
        if json_output:
            self.output_fn(json.dumps(dict(event), sort_keys=True, default=str))
            return
        event_type = event.get("event_type")
        if event_type == "model_response":
            prompt_tokens = int(event.get("prompt_tokens", 0))
            completion_tokens = int(event.get("completion_tokens", 0))
            left = max(0, MAX_INPUT_TOKENS - prompt_tokens)
            self.output_fn(
                f"  ctx: {prompt_tokens}/{MAX_INPUT_TOKENS} | left: {left} | "
                f"generated: {completion_tokens} | tool calls: {event.get('tool_calls', 0)}"
            )
            return
        if event_type == "tool_call":
            metadata = event.get("metadata")
            calls = metadata.get("tool_calls", ()) if isinstance(metadata, Mapping) else ()
            for call in calls:
                if isinstance(call, Mapping):
                    name = str(call.get("name", "unknown"))
                    arguments = SessionRecorder.redact_payload(call.get("arguments", {}))
                    rendered = json.dumps(arguments, sort_keys=True, default=str)
                    self.output_fn(f"  -> tool: {name} {rendered[:240]}")
            return
        if event_type == "tool_result":
            content = event.get("content")
            name = content.get("name", "unknown") if isinstance(content, Mapping) else "unknown"
            self.output_fn(f"  [ok] tool complete: {name}")

    def _handle_slash_command(
        self,
        raw: str,
        *,
        state: dict[str, object],
        role: str,
        model: str,
        workspace_path: Path,
        session_id: str,
        selected_tools: Sequence[str],
        allow_write: bool,
        skills: Sequence[str],
        gateway: ChatToolGateway,
        json_output: bool,
    ) -> bool:
        parts = raw.strip().split(maxsplit=1)
        command = parts[0].casefold()
        argument = parts[1].strip() if len(parts) == 2 else ""
        if command in {"/quit", "/exit"}:
            self._command_output(json_output, command, "bye")
            return True
        if command == "/help":
            self._command_output(
                json_output,
                command,
                "\n".join(
                    [
                        "Slash commands:",
                        "  /help                 show this help",
                        "  /status               show session/workspace state",
                        "  /model [mode]         show/select coding or daily mode",
                        "  /mode [mode]          alias for /model",
                        "  /skills               show loaded skills/rules",
                        "  /tools                show available controller tools",
                        "  /clear                clear Qwen conversation history",
                        "  /compact              keep only recent conversation history",
                        "  /dream                run one Dream Gate pass",
                        "  /diff                 run git diff check",
                        "  /search <text>        search the workspace",
                        "  /graph <text>         query CodeGraph",
                        "  /test <kind> <path>   run pytest or cargo (write mode)",
                        "  /quit                 exit chat",
                    ]
                ),
            )
            return False
        if command == "/status":
            history = state["history"]
            history_count = 0 if not history else len(history)
            self._command_output(
                json_output,
                command,
                f"role: {role}\nmodel: {model}\nmode: {state['mode']}\ncontext_window: {MAX_CONTEXT_TOKENS}\nworkspace: {workspace_path.relative_to(self.repository_root)}\nsession: {session_id}\nhistory_messages: {history_count}\nwrite_mode: {'on' if allow_write else 'off'}",
            )
            return False
        if command in {"/model", "/mode"}:
            if argument:
                if argument not in CHAT_MODES:
                    self._command_output(
                        json_output,
                        command,
                        f"unknown mode: {argument}; choose coding or daily",
                    )
                    return False
                state["mode"] = argument
                state["history"] = None
                state["system_prompt"] = None
                state["instructions"] = _instruction_paths(
                    self.repository_root, workspace_path
                )
                state["skills"] = discover_applicable_skills(
                    self.repository_root, workspace_path, "", skills
                )
                self._command_output(
                    json_output,
                    command,
                    f"mode: {argument}\nhistory cleared\nmodel: {model}",
                )
                return False
            mode = str(state["mode"])
            self._command_output(
                json_output,
                command,
                f"model: {model}\nmode: {mode}\ncontext_window: {MAX_CONTEXT_TOKENS}\ninput_budget: {MAX_INPUT_TOKENS}\noutput_reserve: {OUTPUT_RESERVE_TOKENS}",
            )
            return False
        if command == "/skills":
            instructions = state.get("instructions", ())
            skills = state.get("skills", ())
            rules_text = "\n".join(
                path.relative_to(self.repository_root).as_posix() for path in instructions
            ) or "(none)"
            skills_text = "\n".join(
                path.relative_to(self.repository_root).as_posix() for path in skills
            ) or "(none)"
            self._command_output(
                json_output, command, f"Rules:\n{rules_text}\n\nSkills:\n{skills_text}"
            )
            return False
        if command == "/tools":
            self._command_output(json_output, command, "\n".join(selected_tools))
            return False
        if command == "/clear":
            state["history"] = None
            state["system_prompt"] = None
            state["instructions"] = _instruction_paths(self.repository_root, workspace_path)
            state["skills"] = discover_applicable_skills(
                self.repository_root, workspace_path, "", skills
            )
            self._command_output(json_output, command, "conversation cleared")
            return False
        if command == "/compact":
            history = state.get("history")
            if not history:
                self._command_output(json_output, command, "nothing to compact")
            else:
                state["history"] = self._compact_history(history)
                self._command_output(
                    json_output,
                    command,
                    f"history compacted to {len(state['history'])} messages",
                )
            return False
        if command == "/dream":
            self._run_dream(session_id, json_output=json_output)
            return False
        if command == "/diff":
            self._run_command_tool(
                json_output, command, "git_diff_check", {}, selected_tools, gateway
            )
            return False
        if command in {"/search", "/graph"}:
            if not argument:
                self._command_output(json_output, command, f"usage: {command} <text>")
                return False
            tool = "search_text" if command == "/search" else "codegraph_query"
            argument_name = "query" if tool == "search_text" else "search"
            self._run_command_tool(
                json_output,
                command,
                tool,
                {argument_name: argument},
                selected_tools,
                gateway,
            )
            return False
        if command == "/test":
            if not allow_write:
                self._command_output(json_output, command, "test commands require --allow-write")
                return False
            test_parts = argument.split(maxsplit=1)
            if len(test_parts) != 2 or test_parts[0] not in {"pytest", "cargo"}:
                self._command_output(json_output, command, "usage: /test pytest <path> or /test cargo <Cargo.toml>")
                return False
            self._run_command_tool(
                json_output,
                command,
                "run_test",
                {"kind": test_parts[0], "target": test_parts[1].strip('"')},
                selected_tools,
                gateway,
            )
            return False
        self._command_output(json_output, command, f"unknown command: {command}; use /help")
        return False

    def _command_output(self, json_output: bool, command: str, content: str) -> None:
        if json_output:
            self.output_fn(json.dumps({"event_type": "command", "command": command, "content": content}))
        else:
            self.output_fn(content)

    def _command_tool_output(
        self, json_output: bool, command: str, result: AgentToolResult
    ) -> None:
        self._command_output(json_output, command, result.output or "(no output)")

    def _run_command_tool(
        self,
        json_output: bool,
        command: str,
        tool: str,
        arguments: Mapping[str, str | int | None],
        selected_tools: Sequence[str],
        gateway: ChatToolGateway,
    ) -> None:
        if tool not in selected_tools:
            self._command_output(json_output, command, f"tool is not enabled: {tool}")
            return
        try:
            result = gateway.execute(
                AgentRole.DEVELOPMENT,
                AgentToolRequest(name=tool, arguments=dict(arguments)),
            )
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            self._command_output(json_output, command, f"command failed: {exc}")
            return
        self._command_tool_output(json_output, command, result)

    @staticmethod
    def _compact_history(
        history: Sequence[Mapping[str, object]], keep_messages: int = 8
    ) -> tuple[dict[str, object], ...]:
        messages = [dict(message) for message in history]
        system = messages[:1] if messages and messages[0].get("role") == "system" else []
        body = messages[1:] if system else messages
        return tuple(system + body[-keep_messages:])

    def _workspace(self, raw: str, *, allow_write: bool) -> Path:
        path = Path(raw)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("workspace must be repository-relative")
        candidate = (self.repository_root / path).resolve()
        if candidate != self.repository_root and self.repository_root not in candidate.parents:
            raise ValueError("workspace escapes repository")
        if not candidate.is_dir():
            raise ValueError("workspace directory does not exist")
        if allow_write and candidate == self.repository_root:
            raise ValueError("--allow-write requires a narrower workspace than repository root")
        return candidate

    def _revision(self) -> str:
        try:
            value = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], cwd=self.repository_root, text=True, timeout=10
            ).strip()
        except (OSError, subprocess.SubprocessError):
            value = "working-tree"
        return value or "working-tree"


def _schema(name: str, properties: Mapping[str, object], required: Sequence[str] = ()) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "Controller-mediated bounded local V20 tool.",
            "parameters": {
                "type": "object", "properties": dict(properties),
                "required": list(required), "additionalProperties": False,
            },
        },
    }


CHAT_TOOL_SCHEMAS = {
    "codegraph_query": _schema("codegraph_query", {"search": {"type": "string"}, "limit": {"type": "integer"}}, ("search",)),
    "codegraph_explore": _schema("codegraph_explore", {"search": {"type": "string"}, "max_files": {"type": "integer"}}, ("search",)),
    "codegraph_node": _schema("codegraph_node", {"symbol": {"type": "string"}, "file": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}}),
    "codegraph_affected": _schema("codegraph_affected", {"files": {"type": "string"}, "depth": {"type": "integer"}, "filter": {"type": "string"}}, ("files",)),
    "run_test": _schema("run_test", {"kind": {"type": "string", "enum": ["pytest", "cargo"]}, "target": {"type": "string"}}, ("kind", "target")),
}
