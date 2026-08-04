"""Bounded, structured conversation context without a model adapter."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated, Literal, Protocol

from pydantic import Field, StringConstraints, TypeAdapter, field_validator

from vesper.platform.contracts import AgentRole

from .conversations import ConversationStore
from .views import SafeId, Sha256Hex, StrictModel, UtcDateTime


MAX_INPUT_TOKENS = 65_536
COMPRESSION_THRESHOLD_TOKENS = (MAX_INPUT_TOKENS * 80) // 100
MAX_CONTEXT_MESSAGES = 100
_ContextLine = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4_096)
]
_Objective = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8_000)
]
_ContextLines = Annotated[tuple[_ContextLine, ...], Field(max_length=100)]
_ContextIds = Annotated[tuple[SafeId, ...], Field(max_length=100)]
_SAFE_ID = TypeAdapter(SafeId)
_OBJECTIVE = TypeAdapter(_Objective)


class CompressionInputs(StrictModel):
    """Controller-vetted facts allowed in a compact agent context."""

    current_state: _ContextLines
    unresolved_decisions: _ContextLines
    approvals: _ContextIds
    evidence_ids: _ContextIds
    errors: _ContextLines
    blockers: _ContextLines
    applicable_rules: _ContextLines
    core_memory_ids: _ContextIds


class RawMessagePointer(StrictModel):
    message_id: SafeId
    role: Literal["human", "agent"]
    status: Literal["draft", "complete", "interrupted"]
    created_at_utc: UtcDateTime
    validation_receipt_id: SafeId | None
    token_count: Annotated[int, Field(ge=0, le=2**63 - 1)] | None
    text_sha256: Sha256Hex


class CompressedContext(StrictModel):
    context_id: SafeId
    agent_id: SafeId
    objective: _Objective
    current_state: _ContextLines
    unresolved_decisions: _ContextLines
    approvals: _ContextIds
    evidence_ids: _ContextIds
    errors: _ContextLines
    blockers: _ContextLines
    applicable_rules: _ContextLines
    core_memory_ids: _ContextIds
    raw_message_pointers: Annotated[
        tuple[RawMessagePointer, ...], Field(max_length=MAX_CONTEXT_MESSAGES)
    ]
    created_at_utc: UtcDateTime


class CompressionReceipt(StrictModel):
    command_id: SafeId
    agent_id: SafeId
    context_id: SafeId
    compressed_at_utc: UtcDateTime
    raw_message_ids: Annotated[tuple[SafeId, ...], Field(max_length=MAX_CONTEXT_MESSAGES)]

    @field_validator("raw_message_ids")
    @classmethod
    def require_unique_raw_messages(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("raw_message_ids must be unique")
        return value


class ContextSource(Protocol):
    def read(self, agent_id: SafeId) -> CompressionInputs: ...


class CompressionPolicy:
    """Start compression at exactly 80 percent of the configured context."""

    def __init__(self, max_input_tokens: int = MAX_INPUT_TOKENS) -> None:
        if type(max_input_tokens) is not int:
            raise TypeError("max_input_tokens must be an integer")
        if max_input_tokens <= 0:
            raise ValueError("max_input_tokens must be positive")
        self.max_input_tokens = max_input_tokens
        self.threshold_tokens = (max_input_tokens * 80) // 100

    def should_compress(self, prompt_tokens: int) -> bool:
        if type(prompt_tokens) is not int:
            raise TypeError("prompt_tokens must be an integer")
        if prompt_tokens < 0:
            raise ValueError("prompt_tokens cannot be negative")
        return prompt_tokens >= self.threshold_tokens


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_id_factory() -> str:
    return f"context:{secrets.token_hex(16)}"


class ContextCompressor:
    """Build controller-vetted compact context while retaining raw messages."""

    def __init__(
        self,
        store: ConversationStore,
        source: ContextSource,
        *,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = _default_id_factory,
    ) -> None:
        if type(store) is not ConversationStore:
            raise TypeError("store must be ConversationStore")
        if not callable(getattr(source, "read", None)):
            raise TypeError("source must provide read(agent_id)")
        if not callable(clock) or not callable(id_factory):
            raise TypeError("clock and id_factory must be callable")
        self._store = store
        self._source = source
        self._clock = clock
        self._id_factory = id_factory

    def build(self, agent_id: SafeId, objective: str) -> CompressedContext:
        safe_agent = _SAFE_ID.validate_python(agent_id, strict=True)
        try:
            checked_agent = AgentRole(safe_agent).value
        except ValueError as exc:
            raise ValueError("agent_id must name an approved V20 agent") from exc
        checked_objective = _OBJECTIVE.validate_python(objective, strict=True)
        inputs = self._source.read(checked_agent)
        if type(inputs) is not CompressionInputs:
            raise TypeError("context source must return CompressionInputs")
        history = tuple(reversed(self._store.history(checked_agent, MAX_CONTEXT_MESSAGES, None)))
        pointers = tuple(
            RawMessagePointer(
                message_id=message.message_id,
                role=message.role,
                status=message.status,
                created_at_utc=message.created_at_utc,
                validation_receipt_id=message.validation_receipt_id,
                token_count=message.token_count,
                text_sha256=hashlib.sha256(message.text.encode("utf-8")).hexdigest(),
            )
            for message in history
        )
        context = CompressedContext(
            context_id=self._id_factory(),
            agent_id=checked_agent,
            objective=checked_objective,
            current_state=inputs.current_state,
            unresolved_decisions=inputs.unresolved_decisions,
            approvals=inputs.approvals,
            evidence_ids=inputs.evidence_ids,
            errors=inputs.errors,
            blockers=inputs.blockers,
            applicable_rules=inputs.applicable_rules,
            core_memory_ids=inputs.core_memory_ids,
            raw_message_pointers=pointers,
            created_at_utc=self._clock(),
        )
        canonical = json.dumps(
            context.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        self._store.record_context_summary(
            context.context_id,
            context.agent_id,
            context.objective,
            context.created_at_utc,
            tuple(pointer.message_id for pointer in pointers),
            hashlib.sha256(canonical).hexdigest(),
        )
        return context
