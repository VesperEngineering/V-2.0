from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.platform.codex import CodexSdkAdapter, ModelNotApprovedError, WorkspaceDeniedError
from vesper.platform.contracts import (
    ExecutionStatus,
    PermissionSet,
    SandboxMode,
    SpecialistInput,
    SpecialistRole,
)


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)


@dataclass
class FakeTurn:
    id: str
    final_response: str | None
    status: str = "completed"
    error: object | None = None


@dataclass
class FakePayload:
    turn: FakeTurn


@dataclass
class FakeEvent:
    method: str
    payload: FakePayload | None = None


class FakeHandle:
    def __init__(self, events, *, release: threading.Event | None = None):
        self.events = events
        self.release = release
        self.interrupted = False

    def stream(self):
        if self.release is not None:
            self.release.wait(2)
        yield from self.events

    def interrupt(self):
        self.interrupted = True
        if self.release is not None:
            self.release.set()


class FakeThread:
    def __init__(self, thread_id: str, handle: FakeHandle, calls: list):
        self.id = thread_id
        self.handle = handle
        self.calls = calls

    def turn(self, prompt, **kwargs):
        self.calls.append(("turn", prompt, kwargs))
        return self.handle


class FakeSdk:
    def __init__(self, handle: FakeHandle):
        self.handle = handle
        self.calls: list = []
        self.closed = False

    def thread_start(self, **kwargs):
        self.calls.append(("start", kwargs))
        return FakeThread("thread-new", self.handle, self.calls)

    def thread_resume(self, thread_id, **kwargs):
        self.calls.append(("resume", thread_id, kwargs))
        return FakeThread(thread_id, self.handle, self.calls)

    def close(self):
        self.closed = True


class UsageLimitSdk(FakeSdk):
    def thread_start(self, **kwargs):
        raise RuntimeError("Codex usage limit reached")


def specialist_input(workspace: Path, *, thread_id: str | None = None) -> SpecialistInput:
    return SpecialistInput(
        run_id="run-001",
        task_id="task-001",
        repository_revision="9f9df7f",
        created_at=NOW,
        role=SpecialistRole.DEVELOPMENT,
        attempt=1,
        instructions="Make the bounded change.",
        workspace=str(workspace),
        memory_namespace=("profiles", "v20-development", "development-episodes"),
        permissions=PermissionSet(
            sandbox=SandboxMode.WORKSPACE_WRITE,
            read_paths=(str(workspace),),
            write_paths=(str(workspace / "vesper"),),
            allowed_tools=("read", "write", "test"),
        ),
        thread_id=thread_id,
    )


def completed_handle():
    return FakeHandle(
        [
            FakeEvent("item/started"),
            FakeEvent(
                "turn/completed",
                FakePayload(FakeTurn("turn-001", "Finished the requested work.")),
            ),
        ]
    )


def test_adapter_starts_thread_with_explicit_model_workspace_and_sandbox(tmp_path):
    sdk = FakeSdk(completed_handle())
    adapter = CodexSdkAdapter(
        repository_root=tmp_path,
        approved_models=("gpt-approved",),
        sdk_factory=lambda: sdk,
        clock=lambda: NOW,
    )

    receipt = adapter.execute(
        specialist_input(tmp_path),
        prompt="Implement the task.",
        model="gpt-approved",
        timeout_seconds=1,
    )

    assert receipt.status is ExecutionStatus.COMPLETED
    assert receipt.thread_id == "thread-new"
    assert receipt.final_response == "Finished the requested work."
    assert tuple(event["method"] for event in receipt.streamed_events) == (
        "item/started",
        "turn/completed",
    )
    assert sdk.calls[0][0] == "start"
    assert sdk.calls[0][1]["cwd"] == str(tmp_path.resolve())
    assert sdk.calls[0][1]["model"] == "gpt-approved"
    assert str(sdk.calls[0][1]["sandbox"]) == "Sandbox.workspace_write"
    assert sdk.closed is True


def test_adapter_resumes_existing_thread(tmp_path):
    sdk = FakeSdk(completed_handle())
    adapter = CodexSdkAdapter(
        repository_root=tmp_path,
        approved_models=("gpt-approved",),
        sdk_factory=lambda: sdk,
        clock=lambda: NOW,
    )
    receipt = adapter.execute(
        specialist_input(tmp_path, thread_id="thread-existing"),
        prompt="Continue.",
        model="gpt-approved",
    )

    assert receipt.thread_id == "thread-existing"
    assert sdk.calls[0][0:2] == ("resume", "thread-existing")


def test_adapter_rejects_unapproved_model_before_sdk_start(tmp_path):
    constructed = False

    def factory():
        nonlocal constructed
        constructed = True
        return FakeSdk(completed_handle())

    adapter = CodexSdkAdapter(
        repository_root=tmp_path,
        approved_models=("gpt-approved",),
        sdk_factory=factory,
    )
    with pytest.raises(ModelNotApprovedError):
        adapter.execute(
            specialist_input(tmp_path),
            prompt="No.",
            model="gpt-unapproved",
        )
    assert constructed is False


def test_adapter_rejects_workspace_outside_repository(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    adapter = CodexSdkAdapter(
        repository_root=repository,
        approved_models=("gpt-approved",),
        sdk_factory=lambda: FakeSdk(completed_handle()),
    )

    with pytest.raises(WorkspaceDeniedError):
        adapter.execute(
            specialist_input(outside),
            prompt="No.",
            model="gpt-approved",
        )


def test_usage_limit_is_a_structured_non_success_receipt(tmp_path):
    adapter = CodexSdkAdapter(
        repository_root=tmp_path,
        approved_models=("gpt-approved",),
        sdk_factory=lambda: UsageLimitSdk(completed_handle()),
        clock=lambda: NOW,
    )

    receipt = adapter.execute(
        specialist_input(tmp_path),
        prompt="Try bounded work.",
        model="gpt-approved",
    )

    assert receipt.status is ExecutionStatus.USAGE_LIMITED
    assert receipt.error_code == "usage_limit"


def test_timeout_interrupts_active_turn(tmp_path):
    release = threading.Event()
    handle = FakeHandle([], release=release)
    sdk = FakeSdk(handle)
    adapter = CodexSdkAdapter(
        repository_root=tmp_path,
        approved_models=("gpt-approved",),
        sdk_factory=lambda: sdk,
        clock=lambda: NOW,
    )

    receipt = adapter.execute(
        specialist_input(tmp_path),
        prompt="Block.",
        model="gpt-approved",
        timeout_seconds=0.05,
    )

    assert receipt.status is ExecutionStatus.TIMEOUT
    assert receipt.error_code == "timeout"
    assert handle.interrupted is True


def test_cancellation_is_distinct_from_timeout(tmp_path):
    cancelled = threading.Event()
    cancelled.set()
    adapter = CodexSdkAdapter(
        repository_root=tmp_path,
        approved_models=("gpt-approved",),
        sdk_factory=lambda: FakeSdk(completed_handle()),
        clock=lambda: NOW,
    )

    receipt = adapter.execute(
        specialist_input(tmp_path),
        prompt="Cancel.",
        model="gpt-approved",
        cancellation=cancelled,
    )

    assert receipt.status is ExecutionStatus.CANCELLED
    assert receipt.error_code == "cancelled"


def test_completed_codex_receipt_never_represents_task_acceptance(tmp_path):
    adapter = CodexSdkAdapter(
        repository_root=tmp_path,
        approved_models=("gpt-approved",),
        sdk_factory=lambda: FakeSdk(completed_handle()),
        clock=lambda: NOW,
    )
    receipt = adapter.execute(
        specialist_input(tmp_path),
        prompt="Complete specialist work only.",
        model="gpt-approved",
    )
    assert receipt.status is ExecutionStatus.COMPLETED
    assert "accepted" not in receipt.__class__.model_fields
