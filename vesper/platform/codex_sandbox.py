"""Codex subprocess boundary enforced by Docker Sandboxes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .codex import (
    ModelNotApprovedError,
    PermissionDeniedError,
    WorkspaceDeniedError,
)
from .contracts import CodexExecutionReceipt, ExecutionStatus, SandboxMode, SpecialistInput

_READ_ONLY_TOOLS = frozenset({"read", "search"})
_WORKSPACE_TOOLS = _READ_ONLY_TOOLS | {"write", "test"}
_DEFAULT_DENY_PROBE = "v20-deny.invalid"
_OPENAI_NETWORK_HOSTS = frozenset({"api.openai.com", "chatgpt.com", "openai.com"})
_OPENAI_OAUTH_TOKENS = ("oauth", "openai")
DOCKER_CODEX_DEFAULT_MODEL = "docker-codex-default"
_VIRTIOFS_MOUNT = re.compile(r"^\S+ on (?P<path>.+) type virtiofs \((?P<options>[^)]*)\)$")


class DockerSandboxBoundaryError(RuntimeError):
    """Base error for Docker sandbox availability or policy failures."""


class DockerSandboxPolicyError(DockerSandboxBoundaryError):
    """The named sandbox does not match the controller-approved boundary."""


class DockerSandboxTerminationError(DockerSandboxBoundaryError):
    """A timed-out or cancelled sandbox could not be confirmed stopped."""


MetadataRunner = Callable[
    [list[str], Path, float],
    subprocess.CompletedProcess[str],
]
ExecutionRunner = Callable[
    [list[str], Path, float, Callable[[], bool], int],
    subprocess.CompletedProcess[str],
]
RevisionReader = Callable[[Path], str]


@dataclass(frozen=True, slots=True)
class _Outcome:
    status: ExecutionStatus
    thread_id: str | None = None
    final_response: str | None = None
    events: tuple[dict[str, object], ...] = ()
    error_code: str | None = None


class _OutputLimitExceeded(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _run_metadata(
    command: list[str],
    workspace: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=workspace,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout_seconds,
    )


def _run_execution(
    command: list[str],
    workspace: Path,
    timeout_seconds: float,
    cancelled: Callable[[], bool],
    max_output_bytes: int,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        cwd=workspace,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    output_lock = threading.Lock()
    output_size = 0
    output_exceeded = threading.Event()
    stdout_parts: list[bytes] = []
    stderr_parts: list[bytes] = []

    def drain(stream, parts: list[bytes]) -> None:
        nonlocal output_size
        while chunk := stream.read(65536):
            with output_lock:
                remaining = max_output_bytes - output_size
                if remaining <= 0:
                    output_exceeded.set()
                    return
                retained = chunk[:remaining]
                parts.append(retained)
                output_size += len(retained)
                if len(retained) != len(chunk):
                    output_exceeded.set()
                    return

    assert process.stdout is not None and process.stderr is not None
    readers = (
        threading.Thread(target=drain, args=(process.stdout, stdout_parts), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, stderr_parts), daemon=True),
    )
    for reader in readers:
        reader.start()

    def terminate() -> None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    deadline = time.monotonic() + timeout_seconds
    while process.poll() is None:
        if output_exceeded.is_set():
            terminate()
            break
        if cancelled():
            terminate()
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            terminate()
            for reader in readers:
                reader.join(timeout=2)
            raise subprocess.TimeoutExpired(command, timeout_seconds)
        time.sleep(min(0.05, remaining))
    for reader in readers:
        reader.join(timeout=2)
    if any(reader.is_alive() for reader in readers):
        raise RuntimeError("sandbox output readers did not terminate")
    if output_exceeded.is_set():
        raise _OutputLimitExceeded
    return subprocess.CompletedProcess(
        command,
        process.returncode,
        b"".join(stdout_parts).decode("utf-8", errors="replace"),
        b"".join(stderr_parts).decode("utf-8", errors="replace"),
    )


def _read_revision(repository_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise DockerSandboxPolicyError("workspace revision could not be verified")
    return completed.stdout.strip()


class DockerCodexAdapter:
    """Execute one specialist turn inside a pre-provisioned Docker sandbox."""

    def __init__(
        self,
        *,
        repository_root: Path,
        sandbox_name: str,
        approved_models: tuple[str, ...],
        approved_network_hosts: tuple[str, ...],
        executable: str = "sbx",
        metadata_runner: MetadataRunner = _run_metadata,
        execution_runner: ExecutionRunner = _run_execution,
        revision_reader: RevisionReader = _read_revision,
        clock: Callable[[], datetime] = _utc_now,
        max_events: int = 500,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.sandbox_name = sandbox_name
        self.approved_models = frozenset(approved_models)
        self.approved_network_hosts = frozenset(approved_network_hosts)
        if self.approved_network_hosts != _OPENAI_NETWORK_HOSTS:
            raise ValueError("Docker Codex network hosts must match the approved OpenAI boundary")
        self._executable = executable
        self._metadata_runner = metadata_runner
        self._execution_runner = execution_runner
        self._revision_reader = revision_reader
        self._clock = clock
        self._max_events = max_events
        self._max_output_bytes = max_output_bytes
        self._execution_lock = threading.Lock()
        self._active_lock = threading.Lock()
        self._active: dict[str, threading.Event] = {}

    def execute(
        self,
        request: SpecialistInput,
        *,
        prompt: str,
        model: str,
        timeout_seconds: float = 300,
        cancellation: threading.Event | None = None,
        execution_id: str | None = None,
    ) -> CodexExecutionReceipt:
        if model not in self.approved_models:
            raise ModelNotApprovedError(f"model is not controller-approved: {model}")
        if request.thread_id is not None:
            raise DockerSandboxPolicyError(
                "ephemeral Docker Codex execution does not support thread resume"
            )
        workspace = self._authorized_workspace(request.workspace)
        self._validate_permissions(request, workspace)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        identifier = execution_id or str(uuid.uuid4())
        started_at = self._clock()
        external_cancel = cancellation or threading.Event()
        if not self._execution_lock.acquire(blocking=False):
            raise DockerSandboxBoundaryError("sandbox already has an active execution")
        internal_cancel = threading.Event()
        with self._active_lock:
            if identifier in self._active:
                self._execution_lock.release()
                raise ValueError(f"execution is already active: {identifier}")
            self._active[identifier] = internal_cancel

        cancelled = lambda: external_cancel.is_set() or internal_cancel.is_set()
        command = self._command(request, workspace, prompt, model)
        git_before = None
        outcome = _Outcome(ExecutionStatus.FAILED, error_code="execution-not-started")
        try:
            if cancelled():
                outcome = _Outcome(ExecutionStatus.CANCELLED, error_code="cancelled")
            else:
                self._verify_workspace_links()
                git_before = self._git_fingerprint()
                self._verify_revision(request)
                self._verify_sandbox()
                if cancelled():
                    outcome = _Outcome(ExecutionStatus.CANCELLED, error_code="cancelled")
                else:
                    self._verify_mounts()
                    self._verify_workspace_links()
                    self._verify_revision(request)
                    if self._git_fingerprint() != git_before:
                        raise DockerSandboxPolicyError(
                            "Git metadata changed during sandbox preflight"
                        )
                    if cancelled():
                        outcome = _Outcome(ExecutionStatus.CANCELLED, error_code="cancelled")
                    else:
                        completed = self._execution_runner(
                            command,
                            workspace,
                            timeout_seconds,
                            cancelled,
                            self._max_output_bytes,
                        )
                        outcome = (
                            _Outcome(ExecutionStatus.CANCELLED, error_code="cancelled")
                            if cancelled()
                            else self._outcome(completed)
                        )
        except FileNotFoundError:
            outcome = _Outcome(ExecutionStatus.FAILED, error_code="sbx-not-found")
        except subprocess.TimeoutExpired:
            outcome = _Outcome(ExecutionStatus.TIMEOUT, error_code="timeout")
        except _OutputLimitExceeded:
            outcome = _Outcome(ExecutionStatus.FAILED, error_code="output-limit-exceeded")
        except DockerSandboxBoundaryError:
            raise
        except Exception as exc:
            outcome = _Outcome(
                ExecutionStatus.FAILED,
                error_code=type(exc).__name__.lower(),
            )
        finally:
            try:
                self._remove_sandbox()
            finally:
                with self._active_lock:
                    self._active.pop(identifier, None)
                self._execution_lock.release()
        if git_before is not None and self._git_fingerprint() != git_before:
            outcome = _Outcome(
                ExecutionStatus.PERMISSION_DENIED,
                error_code="git-metadata-mutated",
            )
        return self._receipt(request, identifier, started_at, outcome)

    def cancel(self, execution_id: str) -> bool:
        with self._active_lock:
            cancellation = self._active.get(execution_id)
            if cancellation is None:
                return False
            cancellation.set()
        return True

    def _authorized_workspace(self, requested: str) -> Path:
        path = Path(requested)
        if not path.is_absolute():
            path = self.repository_root / path
        resolved = path.resolve()
        if not resolved.is_dir() or resolved != self.repository_root:
            raise WorkspaceDeniedError(
                "workspace must be the exact sandbox-bound repository: " + requested
            )
        git_directory = resolved / ".git"
        if self._is_reparse_point(git_directory) or not git_directory.is_dir():
            raise WorkspaceDeniedError("workspace must be a standalone Git repository")
        return resolved

    @staticmethod
    def _validate_permissions(request: SpecialistInput, workspace: Path) -> None:
        maximum = (
            _READ_ONLY_TOOLS
            if request.permissions.sandbox is SandboxMode.READ_ONLY
            else _WORKSPACE_TOOLS
        )
        if set(request.permissions.allowed_tools) != maximum:
            raise PermissionDeniedError(
                "requested tools must match the effective Docker Codex capability set"
            )

        def resolve_paths(values: tuple[str, ...]) -> tuple[Path, ...]:
            result = []
            for value in values:
                path = Path(value)
                if not path.is_absolute():
                    path = workspace / path
                result.append(path.resolve())
            return tuple(result)

        read_paths = resolve_paths(request.permissions.read_paths)
        write_paths = resolve_paths(request.permissions.write_paths)
        expected_write = (
            (workspace,) if request.permissions.sandbox is SandboxMode.WORKSPACE_WRITE else ()
        )
        if read_paths != (workspace,) or write_paths != expected_write:
            raise PermissionDeniedError(
                "requested paths must match the effective Docker Codex workspace boundary"
            )
        for path in (*read_paths, *write_paths):
            if not path.is_relative_to(workspace):
                raise PermissionDeniedError("requested path exceeds the authorized workspace")

    def _verify_revision(self, request: SpecialistInput) -> None:
        if self._revision_reader(self.repository_root) != request.repository_revision:
            raise DockerSandboxPolicyError(
                "request revision does not match the sandbox-bound repository"
            )
        project_config = self.repository_root / ".codex"
        if project_config.exists() or self._is_reparse_point(project_config):
            raise DockerSandboxPolicyError(
                "project-local Codex configuration is not allowed in the isolated workspace"
            )

    def _verify_sandbox(self) -> None:
        inspect = self._metadata_json(
            [self._executable, "inspect", self.sandbox_name, "--json"],
            "sandbox inspection",
        )
        auth_mode = tuple(re.findall(r"[a-z0-9]+", str(inspect.get("auth_mode", "")).lower()))
        network_policy = inspect.get("network_policy")
        if (
            inspect.get("name") != self.sandbox_name
            or inspect.get("agent") != "codex"
            or inspect.get("state") != "stopped"
            or auth_mode != _OPENAI_OAUTH_TOKENS
            or inspect.get("mcp_gateway") is not False
            or inspect.get("kits") != []
            or inspect.get("sessions") != 0
            or not isinstance(network_policy, dict)
            or network_policy.get("scope") != "sandbox"
        ):
            raise DockerSandboxPolicyError(
                "sandbox must be Codex, OpenAI OAuth-backed, MCP-disabled, and sandbox-scoped"
            )
        inspected_workspace = inspect.get("workspace")
        if not isinstance(inspected_workspace, str) or (
            Path(inspected_workspace).resolve() != self.repository_root
        ):
            raise DockerSandboxPolicyError(
                "sandbox workspace does not match the authorized repository"
            )
        listed = self._metadata_json(
            [self._executable, "ls", "--json"],
            "sandbox inventory",
        )
        sandboxes = listed.get("sandboxes")
        matching = (
            []
            if not isinstance(sandboxes, list)
            else [
                item
                for item in sandboxes
                if isinstance(item, dict) and item.get("name") == self.sandbox_name
            ]
        )
        if (
            len(matching) != 1
            or matching[0].get("agent") != "codex"
            or matching[0].get("workspaces") != [str(self.repository_root)]
        ):
            raise DockerSandboxPolicyError(
                "sandbox workspace mounts differ from the exact authorized repository"
            )
        ports = self._metadata_value(
            [self._executable, "ports", self.sandbox_name, "--json"],
            "sandbox port inventory",
        )
        if ports != []:
            raise DockerSandboxPolicyError("sandbox must not publish host ports")

        policy = self._metadata_json(
            [self._executable, "policy", "ls", self.sandbox_name, "--json"],
            "sandbox policy",
        )
        rules = policy.get("rules")
        if not isinstance(rules, list):
            raise DockerSandboxPolicyError("sandbox policy omitted its rules")
        network_rules: list[dict[str, object]] = [
            rule
            for rule in rules
            if isinstance(rule, dict)
            and rule.get("resource_type") == "network"
            and rule.get("status") == "active"
        ]
        actual_hosts = set()
        for rule in network_rules:
            resources = rule.get("resources")
            if (
                rule.get("decision") != "allow"
                or rule.get("scope") != f"sandbox:{self.sandbox_name}"
                or not isinstance(resources, list)
                or len(resources) != 1
                or not isinstance(resources[0], str)
            ):
                raise DockerSandboxPolicyError("sandbox has an unsupported active network rule")
            actual_hosts.add(resources[0])
        if actual_hosts != self.approved_network_hosts or len(network_rules) != len(
            self.approved_network_hosts
        ):
            raise DockerSandboxPolicyError(
                "sandbox network allowlist differs from the controller-approved hosts"
            )
        for host in sorted(self.approved_network_hosts):
            self._require_network_decision(host, allowed=True)
        self._require_network_decision(_DEFAULT_DENY_PROBE, allowed=False)

    def _require_network_decision(self, host: str, *, allowed: bool) -> None:
        result = self._metadata_json(
            [
                self._executable,
                "policy",
                "check",
                "network",
                "--sandbox",
                self.sandbox_name,
                "--json",
                host,
            ],
            f"network policy check for {host}",
            allowed_returncodes=(0,) if allowed else (0, 1),
        )
        if result.get("context") != f"sandbox:{self.sandbox_name}" or (
            result.get("allowed") is not allowed
        ):
            raise DockerSandboxPolicyError(f"unexpected effective network policy for {host}")
        if not allowed and result.get("deny_kind") != "implicit":
            raise DockerSandboxPolicyError("sandbox network policy is not implicit default-deny")

    def _metadata_json(
        self,
        command: list[str],
        label: str,
        *,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> dict[str, object]:
        value = self._metadata_value(
            command,
            label,
            allowed_returncodes=allowed_returncodes,
        )
        if not isinstance(value, dict):
            raise DockerSandboxPolicyError(f"{label} returned an invalid payload")
        return value

    def _metadata_value(
        self,
        command: list[str],
        label: str,
        *,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> object:
        try:
            completed = self._metadata_runner(command, self.repository_root, 30)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise DockerSandboxPolicyError(f"{label} was unavailable") from exc
        if completed.returncode not in allowed_returncodes:
            raise DockerSandboxPolicyError(f"{label} failed")
        try:
            value = json.loads(completed.stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            raise DockerSandboxPolicyError(f"{label} returned malformed JSON") from exc
        return value

    def _verify_mounts(self) -> None:
        command = [self._executable, "exec", self.sandbox_name, "sh", "-lc", "mount"]
        try:
            completed = self._metadata_runner(command, self.repository_root, 30)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise DockerSandboxPolicyError("sandbox mount inventory was unavailable") from exc
        if completed.returncode != 0:
            raise DockerSandboxPolicyError("sandbox mount inventory failed")
        mounts = {}
        for line in completed.stdout.splitlines():
            match = _VIRTIOFS_MOUNT.fullmatch(line.strip())
            if match is not None:
                mounts[match.group("path")] = set(match.group("options").split(","))
        expected = {
            self._sandbox_path(self.repository_root): "rw",
            "/etc/resolv.conf": "ro",
            "/etc/hosts": "ro",
        }
        if set(mounts) != set(expected) or any(
            mode not in mounts[path] for path, mode in expected.items()
        ):
            raise DockerSandboxPolicyError(
                "sandbox host mounts are not limited to the authorized workspace"
            )

    @staticmethod
    def _sandbox_path(path: Path) -> str:
        if path.drive:
            return f"/{path.drive[0].lower()}{path.as_posix()[2:]}"
        return path.as_posix()

    def _command(
        self,
        request: SpecialistInput,
        workspace: Path,
        prompt: str,
        model: str,
    ) -> list[str]:
        command = [
            self._executable,
            "exec",
            self.sandbox_name,
            "codex",
            "exec",
            "--ignore-rules",
            "--ephemeral",
            "--json",
            "--color",
            "never",
        ]
        if model != DOCKER_CODEX_DEFAULT_MODEL:
            command.extend(("--model", model))
        command.extend(
            (
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
            )
        )
        if request.permissions.sandbox is SandboxMode.READ_ONLY:
            command.extend(("--sandbox", "read-only"))
        else:
            command.append("--dangerously-bypass-approvals-and-sandbox")
        command.extend(("--", prompt))
        return command

    def _git_fingerprint(self) -> str:
        digest = hashlib.sha256()
        git_directory = self.repository_root / ".git"

        def visit(directory: Path) -> None:
            with os.scandir(directory) as entries:
                ordered = sorted(entries, key=lambda entry: entry.name)
            for entry in ordered:
                path = Path(entry.path)
                if self._is_reparse_point(path):
                    raise DockerSandboxPolicyError(
                        "Git metadata contains a symbolic link or Windows reparse point"
                    )
                relative = path.relative_to(git_directory).as_posix().encode("utf-8")
                digest.update(len(relative).to_bytes(8, "big"))
                digest.update(relative)
                if entry.is_dir(follow_symlinks=False):
                    digest.update(b"directory\0")
                    visit(path)
                elif entry.is_file(follow_symlinks=False):
                    digest.update(b"file\0")
                    digest.update(path.read_bytes())
                else:
                    digest.update(b"other\0")

        visit(git_directory)
        return digest.hexdigest()

    def _verify_workspace_links(self) -> None:
        stack = [self.repository_root]
        while stack:
            directory = stack.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if self._is_reparse_point(path):
                        raise DockerSandboxPolicyError(
                            "workspace contains a symbolic link or Windows reparse point"
                        )
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(path)

    @staticmethod
    def _is_reparse_point(path: Path) -> bool:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return False
        attributes = getattr(metadata, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)

    def _outcome(self, completed: subprocess.CompletedProcess[str]) -> _Outcome:
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if len(stdout.encode("utf-8")) + len(stderr.encode("utf-8")) > self._max_output_bytes:
            return _Outcome(ExecutionStatus.FAILED, error_code="output-limit-exceeded")
        if completed.returncode != 0:
            description = f"{stdout}\n{stderr}".lower()
            if any(term in description for term in ("usage limit", "rate limit", "quota")):
                return _Outcome(ExecutionStatus.USAGE_LIMITED, error_code="usage-limit")
            if "permission" in description or "denied" in description:
                return _Outcome(ExecutionStatus.PERMISSION_DENIED, error_code="permission-denied")
            return _Outcome(
                ExecutionStatus.FAILED,
                error_code=f"codex-exit-{completed.returncode}",
            )

        events = []
        thread_id = None
        final_response = None
        turn_completed = False
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                return _Outcome(ExecutionStatus.FAILED, error_code="malformed-jsonl")
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                return _Outcome(ExecutionStatus.FAILED, error_code="malformed-jsonl")
            if len(events) < self._max_events:
                events.append(self._summarize_event(event))
            if event["type"] == "thread.started" and isinstance(event.get("thread_id"), str):
                thread_id = event["thread_id"]
            if event["type"] == "turn.completed":
                turn_completed = True
            item = event.get("item")
            if (
                event["type"] == "item.completed"
                and isinstance(item, dict)
                and item.get("type") in {"agent_message", "agentMessage"}
                and isinstance(item.get("text"), str)
            ):
                final_response = item["text"]
            if event["type"] in {"turn.failed", "error"}:
                return _Outcome(
                    ExecutionStatus.FAILED,
                    thread_id=thread_id,
                    events=tuple(events),
                    error_code="codex-turn-failed",
                )
        if (
            thread_id is None
            or len(thread_id) > 200
            or not turn_completed
            or final_response is None
            or len(final_response.encode("utf-8")) > self._max_output_bytes
        ):
            return _Outcome(
                ExecutionStatus.FAILED,
                thread_id=thread_id if thread_id and len(thread_id) <= 200 else None,
                events=tuple(events),
                error_code="incomplete-jsonl",
            )
        return _Outcome(
            ExecutionStatus.COMPLETED,
            thread_id=thread_id,
            final_response=final_response,
            events=tuple(events),
        )

    @staticmethod
    def _summarize_event(event: dict[str, object]) -> dict[str, object]:
        summary = {"type": event["type"]}
        if event["type"] == "turn.completed" and isinstance(event.get("usage"), dict):
            summary["usage"] = event["usage"]
        return summary

    def _remove_sandbox(self) -> None:
        try:
            completed = self._metadata_runner(
                [self._executable, "rm", "--force", self.sandbox_name],
                self.repository_root,
                30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise DockerSandboxTerminationError("sandbox removal could not be confirmed") from exc
        if completed.returncode != 0:
            raise DockerSandboxTerminationError("sandbox removal could not be confirmed")
        try:
            listed = self._metadata_json(
                [self._executable, "ls", "--json"],
                "post-removal sandbox inventory",
            )
        except DockerSandboxPolicyError as exc:
            raise DockerSandboxTerminationError("sandbox removal could not be confirmed") from exc
        sandboxes = listed.get("sandboxes")
        if (
            not isinstance(sandboxes, list)
            or any(
                not isinstance(item, dict) or not isinstance(item.get("name"), str)
                for item in sandboxes
            )
            or any(item["name"] == self.sandbox_name for item in sandboxes)
        ):
            raise DockerSandboxTerminationError("sandbox removal could not be confirmed")

    def _receipt(
        self,
        request: SpecialistInput,
        execution_id: str,
        started_at: datetime,
        outcome: _Outcome,
    ) -> CodexExecutionReceipt:
        return CodexExecutionReceipt(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            execution_id=execution_id,
            role=request.role,
            attempt=request.attempt,
            status=outcome.status,
            sandbox=request.permissions.sandbox,
            started_at=started_at,
            finished_at=self._clock(),
            thread_id=outcome.thread_id,
            final_response=outcome.final_response,
            streamed_events=outcome.events,
            error_code=outcome.error_code,
        )
