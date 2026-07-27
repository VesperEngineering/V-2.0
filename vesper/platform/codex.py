"""Narrow, lazy boundary around the local Python OpenAI Codex SDK."""

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .contracts import (
    CodexExecutionReceipt,
    ExecutionStatus,
    SandboxMode,
    SpecialistInput,
)

_READ_ONLY_TOOLS = frozenset({"read", "search"})
_WORKSPACE_TOOLS = _READ_ONLY_TOOLS | {"write", "test"}


class CodexBoundaryError(RuntimeError):
    """Base error for controller-side Codex policy failures."""


class ModelNotApprovedError(CodexBoundaryError):
    """The requested model is outside the controller allowlist."""


class WorkspaceDeniedError(CodexBoundaryError):
    """The requested working directory is outside the authorized repository."""


class PermissionDeniedError(CodexBoundaryError):
    """The requested tool permissions exceed the selected sandbox."""


@dataclass(frozen=True, slots=True)
class _Outcome:
    status: ExecutionStatus
    thread_id: str | None = None
    final_response: str | None = None
    events: tuple[dict[str, object], ...] = ()
    error_code: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_sdk_factory():
    from openai_codex import Codex

    return Codex()


def _sandbox_value(mode: SandboxMode):
    from openai_codex import Sandbox

    if mode is SandboxMode.READ_ONLY:
        return Sandbox.read_only
    return Sandbox.workspace_write


class CodexSdkAdapter:
    """Execute one bounded specialist turn without owning task acceptance."""

    def __init__(
        self,
        *,
        repository_root: Path,
        approved_models: tuple[str, ...],
        sdk_factory: Callable[[], object] | None = None,
        clock: Callable[[], datetime] = _utc_now,
        max_events: int = 500,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.approved_models = frozenset(approved_models)
        self._sdk_factory = sdk_factory or _default_sdk_factory
        self._clock = clock
        self._max_events = max_events
        self._active_lock = threading.Lock()
        self._active: dict[str, tuple[threading.Event, object | None]] = {}

    @staticmethod
    def sdk_available() -> bool:
        try:
            import openai_codex  # noqa: F401
        except ImportError:
            return False
        return True

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
        workspace = self._authorized_workspace(request.workspace)
        self._validate_permissions(request)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        identifier = execution_id or str(uuid.uuid4())
        started_at = self._clock()
        external_cancel = cancellation or threading.Event()
        internal_cancel = threading.Event()
        if external_cancel.is_set():
            return self._receipt(
                request,
                identifier,
                started_at,
                _Outcome(ExecutionStatus.CANCELLED, error_code="cancelled"),
            )

        outcomes: queue.Queue[_Outcome] = queue.Queue(maxsize=1)
        sandbox = _sandbox_value(request.permissions.sandbox)
        with self._active_lock:
            if identifier in self._active:
                raise ValueError(f"execution is already active: {identifier}")
            self._active[identifier] = (internal_cancel, None)

        worker = threading.Thread(
            target=self._run_worker,
            args=(
                outcomes,
                identifier,
                request,
                prompt,
                model,
                workspace,
                sandbox,
                internal_cancel,
            ),
            name=f"v20-codex-{identifier}",
            daemon=True,
        )
        worker.start()
        deadline = time.monotonic() + timeout_seconds

        while True:
            if external_cancel.is_set() or internal_cancel.is_set():
                internal_cancel.set()
                self._interrupt(identifier)
                outcome = _Outcome(ExecutionStatus.CANCELLED, error_code="cancelled")
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                internal_cancel.set()
                self._interrupt(identifier)
                outcome = _Outcome(ExecutionStatus.TIMEOUT, error_code="timeout")
                break
            try:
                outcome = outcomes.get(timeout=min(0.05, remaining))
                break
            except queue.Empty:
                continue

        with self._active_lock:
            self._active.pop(identifier, None)
        return self._receipt(request, identifier, started_at, outcome)

    def cancel(self, execution_id: str) -> bool:
        with self._active_lock:
            active = self._active.get(execution_id)
            if active is None:
                return False
            active[0].set()
        self._interrupt(execution_id)
        return True

    def _run_worker(
        self,
        outcomes: queue.Queue[_Outcome],
        execution_id: str,
        request: SpecialistInput,
        prompt: str,
        model: str,
        workspace: Path,
        sandbox,
        cancellation: threading.Event,
    ) -> None:
        sdk = None
        thread_id = request.thread_id
        outcome: _Outcome
        try:
            sdk = self._sdk_factory()
            start_options = {
                "cwd": str(workspace),
                "model": model,
                "sandbox": sandbox,
                "developer_instructions": self._permission_instructions(request),
            }
            if request.thread_id is None:
                thread = sdk.thread_start(**start_options)
            else:
                thread = sdk.thread_resume(request.thread_id, **start_options)
            thread_id = thread.id
            handle = thread.turn(prompt, cwd=str(workspace), model=model, sandbox=sandbox)
            with self._active_lock:
                active = self._active.get(execution_id)
                if active is not None:
                    self._active[execution_id] = (active[0], handle)
            if cancellation.is_set():
                handle.interrupt()

            events: list[dict[str, object]] = []
            final_response = None
            error = None
            for event in handle.stream():
                if len(events) < self._max_events:
                    events.append(self._summarize_event(event))
                response, event_error = self._completed_fields(event)
                if response is not None:
                    final_response = response
                if event_error is not None:
                    error = event_error
            if error is not None:
                outcome = self._classify_exception(error, thread_id, tuple(events))
            else:
                outcome = _Outcome(
                    ExecutionStatus.COMPLETED,
                    thread_id=thread_id,
                    final_response=final_response,
                    events=tuple(events),
                )
        except BaseException as exc:
            outcome = self._classify_exception(exc, thread_id)
        finally:
            if sdk is not None:
                try:
                    sdk.close()
                except Exception:
                    pass
        outcomes.put(outcome)

    def _interrupt(self, execution_id: str) -> None:
        with self._active_lock:
            active = self._active.get(execution_id)
            handle = None if active is None else active[1]
        if handle is not None:
            try:
                handle.interrupt()
            except Exception:
                pass

    def _authorized_workspace(self, requested: str) -> Path:
        path = Path(requested)
        if not path.is_absolute():
            path = self.repository_root / path
        resolved = path.resolve()
        if not resolved.is_dir() or not resolved.is_relative_to(self.repository_root):
            raise WorkspaceDeniedError(
                f"workspace is outside the authorized repository: {requested}"
            )
        return resolved

    @staticmethod
    def _validate_permissions(request: SpecialistInput) -> None:
        allowed = set(request.permissions.allowed_tools)
        maximum = (
            _READ_ONLY_TOOLS
            if request.permissions.sandbox is SandboxMode.READ_ONLY
            else _WORKSPACE_TOOLS
        )
        if not allowed <= maximum:
            raise PermissionDeniedError("requested tools exceed the selected sandbox")

    @staticmethod
    def _permission_instructions(request: SpecialistInput) -> str:
        permissions = request.permissions
        return (
            "V20 controller permissions: "
            f"tools={','.join(permissions.allowed_tools) or 'none'}; "
            f"read_paths={','.join(permissions.read_paths) or 'none'}; "
            f"write_paths={','.join(permissions.write_paths) or 'none'}; "
            "network=denied; trading=denied. "
            "Do not exceed these permissions and do not treat completion as acceptance."
        )

    @staticmethod
    def _summarize_event(event) -> dict[str, object]:
        if isinstance(event, dict):
            method = event.get("method", "unknown")
        else:
            method = getattr(event, "method", "unknown")
        return {"method": str(method)}

    @staticmethod
    def _completed_fields(event) -> tuple[str | None, BaseException | object | None]:
        method = event.get("method") if isinstance(event, dict) else getattr(event, "method", None)
        if method != "turn/completed":
            return None, None
        payload = (
            event.get("payload") if isinstance(event, dict) else getattr(event, "payload", None)
        )
        turn = payload.get("turn") if isinstance(payload, dict) else getattr(payload, "turn", None)
        if turn is None:
            return None, RuntimeError("completed Codex event omitted the turn result")
        if isinstance(turn, dict):
            return turn.get("final_response"), turn.get("error")
        return getattr(turn, "final_response", None), getattr(turn, "error", None)

    @staticmethod
    def _classify_exception(
        exc: BaseException | object,
        thread_id: str | None,
        events: tuple[dict[str, object], ...] = (),
    ) -> _Outcome:
        description = f"{type(exc).__name__} {exc}".lower()
        if any(term in description for term in ("usage limit", "rate limit", "quota")):
            return _Outcome(
                ExecutionStatus.USAGE_LIMITED,
                thread_id=thread_id,
                events=events,
                error_code="usage_limit",
            )
        if "permission" in description or "denied" in description:
            return _Outcome(
                ExecutionStatus.PERMISSION_DENIED,
                thread_id=thread_id,
                events=events,
                error_code="permission_denied",
            )
        return _Outcome(
            ExecutionStatus.FAILED,
            thread_id=thread_id,
            events=events,
            error_code=type(exc).__name__.lower(),
        )

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
