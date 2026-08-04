from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from vesper.platform.tui.command_contracts import (
    COMMAND_SPECS,
    CommandRequest,
    ReceiptStatus,
)
from vesper.platform.tui.command_policy import (
    CommandContext,
    EvaluatedPrerequisites,
    canonical_request_hash,
)
from vesper.platform.tui.command_ports import PortResult
from vesper.platform.tui.command_registry import CommandRegistry
from vesper.platform.tui.compression import (
    COMPRESSION_THRESHOLD_TOKENS,
    MAX_INPUT_TOKENS,
    CompressedContext,
    CompressionInputs,
    CompressionPolicy,
    CompressionReceipt,
    ContextCompressor,
)
from vesper.platform.tui.conversations import ConversationStore
from vesper.platform.tui.views import CapabilityState, CapabilityView


NOW = datetime(2026, 8, 4, 14, 0, tzinfo=timezone.utc)
CONTROL_HASH = "7c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43"


class ContextSource:
    def read(self, agent_id: str) -> CompressionInputs:
        assert agent_id == "v20-product"
        return CompressionInputs(
            current_state=("Candidate review is active.",),
            unresolved_decisions=("Choose the next evaluation window.",),
            approvals=("approval:model-review",),
            evidence_ids=("evidence:walk-forward",),
            errors=("No fresh sector feed.",),
            blockers=("Waiting for validated data.",),
            applicable_rules=("AGENTS.md: fail closed",),
            core_memory_ids=("memory:v20-only",),
        )


class RecordingContextSource:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def read(self, agent_id: str) -> CompressionInputs:
        self.calls.append(agent_id)
        return CompressionInputs(
            current_state=(),
            unresolved_decisions=(),
            approvals=(),
            evidence_ids=(),
            errors=(),
            blockers=(),
            applicable_rules=(),
            core_memory_ids=(),
        )


class PlatformPort:
    def approve_run(self, *args: object, **kwargs: object) -> PortResult:
        raise AssertionError("platform port must not be called")

    def reject_run(self, *args: object, **kwargs: object) -> PortResult:
        raise AssertionError("platform port must not be called")

    def enqueue(self, *args: object, **kwargs: object) -> PortResult:
        raise AssertionError("platform port must not be called")

    def recover(self, *args: object, **kwargs: object) -> str:
        raise AssertionError("platform port must not be called")


class CompletionValidator:
    def validate_completion(
        self,
        *,
        validation_receipt_id: str,
        agent_id: str,
        message_id: str,
        raw_text_sha256: str,
    ) -> bool:
        del validation_receipt_id, agent_id, message_id, raw_text_sha256
        return True


class MemoryPort:
    def __init__(
        self,
        *,
        healthy: bool,
        crash_after_effect: bool = False,
        lookup_error: Exception | None = None,
    ) -> None:
        self.healthy = healthy
        self.calls: list[tuple[str, str]] = []
        self.lookup_calls: list[str] = []
        self._receipts: dict[str, CompressionReceipt] = {}
        self.return_override: CompressionReceipt | None = None
        self.crash_after_effect = crash_after_effect
        self.lookup_error = lookup_error
        self._crashed = False

    def compress_now(self, command_id: str, agent_id: str) -> CompressionReceipt:
        self.calls.append((command_id, agent_id))
        if self.return_override is not None:
            return self.return_override
        receipt = self._receipts.get(command_id)
        if receipt is None:
            receipt = CompressionReceipt(
                command_id=command_id,
                agent_id=agent_id,
                context_id=f"context:{command_id}",
                compressed_at_utc=NOW,
                raw_message_ids=("message:one",),
            )
            self._receipts[command_id] = receipt
        if self.crash_after_effect and not self._crashed:
            self._crashed = True
            raise RuntimeError("crash after durable compression effect")
        return receipt

    def lookup_receipt(self, command_id: str) -> CompressionReceipt | None:
        self.lookup_calls.append(command_id)
        if self.lookup_error is not None:
            raise self.lookup_error
        return self._receipts.get(command_id)


class MemoryPortWithoutLookup:
    healthy = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def compress_now(self, command_id: str, agent_id: str) -> CompressionReceipt:
        self.calls.append((command_id, agent_id))
        return CompressionReceipt(
            command_id=command_id,
            agent_id=agent_id,
            context_id="context:unsafe",
            compressed_at_utc=NOW,
            raw_message_ids=(),
        )


class MemoryPortWithBrokenCapability:
    healthy = True

    @property
    def compress_now(self) -> object:
        raise OSError("compression adapter unavailable")

    def lookup_receipt(self, command_id: str) -> CompressionReceipt | None:
        del command_id
        return None


class MutableClock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **changes: int) -> None:
        self.now += timedelta(**changes)


def _conversation_store(path: Path) -> ConversationStore:
    return ConversationStore(
        path,
        id_factory=lambda: "message:agent-output",
        validator=CompletionValidator(),
    )


def _memory_request(*, agent_id: str = "v20-product") -> CommandRequest:
    return CommandRequest.model_validate(
        {
            "command_id": "client:compress:one",
            "command_type": "memory.compress-now",
            "reviewed_control_version": 19,
            "reviewed_control_hash": CONTROL_HASH,
            "reason": None,
            "confirmation": None,
            "payload": {"agent_id": agent_id},
        },
        strict=True,
    )


def _context(request: CommandRequest) -> CommandContext:
    return CommandContext(
        operator_id="operator:windows",
        client_id="client:console",
        authenticated=True,
        owns_control_lease=True,
        control_version=request.reviewed_control_version,
        control_hash=request.reviewed_control_hash,
        capabilities=(
            CapabilityView(
                capability_id="memory.compress-now",
                state=CapabilityState.ENABLED,
                reason=None,
            ),
        ),
        prerequisites=EvaluatedPrerequisites(
            request_sha256=canonical_request_hash(request),
            complete=True,
            checks=(),
        ),
    )


def test_compression_policy_starts_at_floor_of_eighty_percent() -> None:
    policy = CompressionPolicy()

    assert MAX_INPUT_TOKENS == 65_536
    assert COMPRESSION_THRESHOLD_TOKENS == 52_428
    assert not policy.should_compress(52_427)
    assert policy.should_compress(52_428)
    with pytest.raises(ValueError, match="prompt_tokens"):
        policy.should_compress(-1)


def test_compression_preserves_raw_chat_and_required_context(tmp_path: Path) -> None:
    store = _conversation_store(tmp_path / "conversations.sqlite3")
    message = store.start_message("v20-product", "agent", NOW)
    store.append_chunk(message.message_id, 1, "raw output", token_count=2)
    store.complete(
        message.message_id,
        "validation:one",
        NOW + timedelta(seconds=1),
    )
    compressor = ContextCompressor(
        store,
        ContextSource(),
        clock=lambda: NOW + timedelta(seconds=2),
        id_factory=lambda: "context:one",
    )

    context = compressor.build("v20-product", "objective")

    assert isinstance(context, CompressedContext)
    assert context.objective == "objective"
    assert context.current_state == ("Candidate review is active.",)
    assert context.unresolved_decisions == ("Choose the next evaluation window.",)
    assert context.approvals == ("approval:model-review",)
    assert context.evidence_ids == ("evidence:walk-forward",)
    assert context.errors == ("No fresh sector feed.",)
    assert context.blockers == ("Waiting for validated data.",)
    assert context.applicable_rules == ("AGENTS.md: fail closed",)
    assert context.core_memory_ids == ("memory:v20-only",)
    assert [pointer.message_id for pointer in context.raw_message_pointers] == [message.message_id]
    assert context.raw_message_pointers[0].text_sha256
    stored = store.history("v20-product", 10, None)[0]
    assert stored.text == "raw output"
    assert stored.context_summary_ids == ("context:one",)
    store.close()


def test_compressor_rejects_non_agent_id_before_reading_context_source(tmp_path: Path) -> None:
    store = _conversation_store(tmp_path / "conversations.sqlite3")
    source = RecordingContextSource()
    compressor = ContextCompressor(store, source, clock=lambda: NOW)

    with pytest.raises(ValueError, match="approved V20 agent"):
        compressor.build("AAPL", "Stock symbols are not agent conversations.")

    assert source.calls == []
    store.close()


def test_compression_contract_rejects_chain_of_thought_fields() -> None:
    with pytest.raises(ValidationError, match="chain_of_thought"):
        CompressionInputs.model_validate(
            {
                "current_state": (),
                "unresolved_decisions": (),
                "approvals": (),
                "evidence_ids": (),
                "errors": (),
                "blockers": (),
                "applicable_rules": (),
                "core_memory_ids": (),
                "chain_of_thought": "private reasoning",
            },
            strict=True,
        )


@pytest.mark.parametrize("memory_port", (None, MemoryPort(healthy=False)))
def test_memory_command_stays_disabled_without_a_healthy_injected_port(
    tmp_path: Path,
    memory_port: MemoryPort | None,
) -> None:
    registry = CommandRegistry(
        tmp_path / f"disabled-{memory_port is None}.sqlite3",
        PlatformPort(),
        memory_port=memory_port,
        clock=lambda: NOW,
    )
    request = _memory_request()

    receipt = registry.execute(_context(request), request)

    assert receipt.status is ReceiptStatus.REJECTED
    assert receipt.code == "capability-disabled"
    assert "memory.compress-now" not in registry.enabled_command_types
    if memory_port is not None:
        assert memory_port.calls == []
    registry.close()


def test_memory_command_requires_durable_receipt_lookup(tmp_path: Path) -> None:
    port = MemoryPortWithoutLookup()
    registry = CommandRegistry(
        tmp_path / "missing-lookup.sqlite3",
        PlatformPort(),
        memory_port=port,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )
    request = _memory_request()

    receipt = registry.execute(_context(request), request)

    assert receipt.status is ReceiptStatus.REJECTED
    assert receipt.code == "capability-disabled"
    assert port.calls == []
    registry.close()


def test_memory_capability_fails_closed_when_adapter_introspection_raises(
    tmp_path: Path,
) -> None:
    registry = CommandRegistry(
        tmp_path / "broken-capability.sqlite3",
        PlatformPort(),
        memory_port=MemoryPortWithBrokenCapability(),  # type: ignore[arg-type]
        clock=lambda: NOW,
    )
    request = _memory_request()

    assert "memory.compress-now" not in registry.enabled_command_types
    receipt = registry.execute(_context(request), request)

    assert receipt.status is ReceiptStatus.REJECTED
    assert receipt.code == "capability-disabled"
    registry.close()


def test_memory_command_strictly_revalidates_model_copy_receipt(tmp_path: Path) -> None:
    port = MemoryPort(healthy=True)
    valid = CompressionReceipt(
        command_id="client:compress:one",
        agent_id="v20-product",
        context_id="context:valid",
        compressed_at_utc=NOW,
        raw_message_ids=("message:one",),
    )
    port.return_override = valid.model_copy(update={"raw_message_ids": ("not a safe id!",)})
    registry = CommandRegistry(
        tmp_path / "invalid-receipt.sqlite3",
        PlatformPort(),
        memory_port=port,
        clock=lambda: NOW,
    )
    request = _memory_request()

    with pytest.raises(ValidationError, match="raw_message_ids"):
        registry.execute(_context(request), request)
    with registry.ledger.read() as connection:
        stored_status = connection.execute(
            "SELECT status FROM commands WHERE command_id = ?",
            (request.command_id,),
        ).fetchone()
    assert stored_status is not None
    assert stored_status[0] == "running"
    registry.close()


def test_memory_command_rejects_duplicate_raw_message_receipt(tmp_path: Path) -> None:
    port = MemoryPort(healthy=True)
    valid = CompressionReceipt(
        command_id="client:compress:one",
        agent_id="v20-product",
        context_id="context:valid",
        compressed_at_utc=NOW,
        raw_message_ids=("message:one",),
    )
    port.return_override = valid.model_copy(
        update={"raw_message_ids": ("message:one", "message:one")}
    )
    registry = CommandRegistry(
        tmp_path / "duplicate-raw-message.sqlite3",
        PlatformPort(),
        memory_port=port,
        clock=lambda: NOW,
    )
    request = _memory_request()

    with pytest.raises(ValidationError, match="raw_message_ids"):
        registry.execute(_context(request), request)

    assert port.calls == [(request.command_id, "v20-product")]
    registry.close()


def test_memory_command_rejects_non_agent_id_before_port_effect(tmp_path: Path) -> None:
    port = MemoryPort(healthy=True)
    registry = CommandRegistry(
        tmp_path / "non-agent-memory.sqlite3",
        PlatformPort(),
        memory_port=port,
        clock=lambda: NOW,
    )
    request = _memory_request(agent_id="AAPL")

    with pytest.raises(ValueError, match="approved V20 agent"):
        registry.execute(_context(request), request)

    assert port.calls == []
    registry.close()


def test_memory_command_strictly_revalidates_model_copy_request(tmp_path: Path) -> None:
    port = MemoryPort(healthy=True)
    registry = CommandRegistry(
        tmp_path / "invalid-request-copy.sqlite3",
        PlatformPort(),
        memory_port=port,
        clock=lambda: NOW,
    )
    valid = _memory_request()
    forged = valid.model_copy(update={"payload": {"agent_id": 7}})

    with pytest.raises(ValidationError, match="agent_id"):
        registry.execute(_context(valid), forged)

    assert port.calls == []
    registry.close()


def test_memory_command_strictly_revalidates_model_copy_context(tmp_path: Path) -> None:
    port = MemoryPort(healthy=True)
    registry = CommandRegistry(
        tmp_path / "invalid-context-copy.sqlite3",
        PlatformPort(),
        memory_port=port,
        clock=lambda: NOW,
    )
    request = _memory_request()
    forged = _context(request).model_copy(update={"authenticated": "yes"})

    with pytest.raises(ValidationError, match="authenticated"):
        registry.execute(forged, request)

    assert port.calls == []
    registry.close()


def test_healthy_memory_port_uses_command_id_once_and_replays_durable_receipt(
    tmp_path: Path,
) -> None:
    database = tmp_path / "commands.sqlite3"
    port = MemoryPort(healthy=True)
    request = _memory_request()
    context = _context(request)
    registry = CommandRegistry(
        database,
        PlatformPort(),
        memory_port=port,
        clock=lambda: NOW,
    )

    first = registry.execute(context, request)
    second = registry.execute(context, request)

    assert "memory.compress-now" in registry.enabled_command_types
    assert first.status is ReceiptStatus.COMPLETED
    assert second == first
    assert first.result == {
        "agent_id": "v20-product",
        "command_id": request.command_id,
        "compressed_at_utc": "2026-08-04T14:00:00Z",
        "context_id": f"context:{request.command_id}",
        "raw_message_ids": ["message:one"],
    }
    assert port.calls == [(request.command_id, "v20-product")]
    registry.close()

    reopened = CommandRegistry(
        database,
        PlatformPort(),
        memory_port=port,
        clock=lambda: NOW,
    )
    assert reopened.execute(context, request) == first
    assert port.calls == [(request.command_id, "v20-product")]
    reopened.close()


def test_stale_running_memory_command_uses_durable_receipt_without_second_context(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    port = MemoryPort(healthy=True, crash_after_effect=True)
    request = _memory_request()
    registry = CommandRegistry(
        tmp_path / "crash-window.sqlite3",
        PlatformPort(),
        memory_port=port,
        clock=clock,
    )

    with pytest.raises(RuntimeError, match="crash after durable"):
        registry.execute(_context(request), request)
    clock.advance(seconds=31)
    recovered = registry.recover_running(clock.now)

    assert len(recovered) == 1
    assert recovered[0].status is ReceiptStatus.COMPLETED
    assert recovered[0].result == {
        "agent_id": "v20-product",
        "command_id": request.command_id,
        "compressed_at_utc": "2026-08-04T14:00:00Z",
        "context_id": f"context:{request.command_id}",
        "raw_message_ids": ["message:one"],
    }
    assert port.calls == [(request.command_id, "v20-product")]
    assert port.lookup_calls == [request.command_id]
    registry.close()


def test_stale_memory_lookup_error_fails_without_second_context(tmp_path: Path) -> None:
    clock = MutableClock()
    port = MemoryPort(
        healthy=True,
        crash_after_effect=True,
        lookup_error=OSError("receipt store unavailable"),
    )
    request = _memory_request()
    registry = CommandRegistry(
        tmp_path / "lookup-error.sqlite3",
        PlatformPort(),
        memory_port=port,
        clock=clock,
    )
    with pytest.raises(RuntimeError, match="crash after durable"):
        registry.execute(_context(request), request)
    clock.advance(seconds=31)

    recovered = registry.recover_running(clock.now)

    assert len(recovered) == 1
    assert recovered[0].status is ReceiptStatus.FAILED
    assert recovered[0].code == "manual-intervention-required"
    assert port.calls == [(request.command_id, "v20-product")]
    assert port.lookup_calls == [request.command_id]
    registry.close()


@pytest.mark.parametrize(
    "receipt_update",
    (
        {"agent_id": "v20-risk-review"},
        {"raw_message_ids": ("not a safe id!",)},
    ),
    ids=("wrong-agent", "invalid-model-copy"),
)
def test_conflicting_durable_memory_receipt_fails_without_second_context(
    tmp_path: Path,
    receipt_update: dict[str, object],
) -> None:
    clock = MutableClock()
    port = MemoryPort(healthy=True, crash_after_effect=True)
    request = _memory_request()
    registry = CommandRegistry(
        tmp_path / "conflicting-receipt.sqlite3",
        PlatformPort(),
        memory_port=port,
        clock=clock,
    )
    with pytest.raises(RuntimeError, match="crash after durable"):
        registry.execute(_context(request), request)
    stored = port._receipts[request.command_id]
    port._receipts[request.command_id] = stored.model_copy(update=receipt_update)
    clock.advance(seconds=31)

    recovered = registry.recover_running(clock.now)

    assert len(recovered) == 1
    assert recovered[0].status is ReceiptStatus.FAILED
    assert recovered[0].code == "manual-intervention-required"
    assert port.calls == [(request.command_id, "v20-product")]
    assert port.lookup_calls == [request.command_id]
    registry.close()


def test_command_catalog_stays_canonical_when_memory_port_is_added(tmp_path: Path) -> None:
    registry = CommandRegistry(
        tmp_path / "commands.sqlite3",
        PlatformPort(),
        memory_port=MemoryPort(healthy=True),
        clock=lambda: NOW,
    )
    assert registry.specs == COMMAND_SPECS
    registry.close()
