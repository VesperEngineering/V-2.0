"""Bounded, ordered outbound envelopes for one console connection."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .contracts import MessageType, ProtocolErrorPayload, WireEnvelope
from .protocol import MAX_FRAME_BYTES

MAX_OUTBOX_ENVELOPES = 256
MAX_OUTBOX_BYTES = 4 * 1024 * 1024
_OVERFLOW_MESSAGE = "Outbound state was not preserved; request a new snapshot."


class _Payload(Protocol):
    def model_dump(self, *, mode: str) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class _QueuedEnvelope:
    envelope: WireEnvelope
    size: int
    replace_key: tuple[str, ...] | None


class OutboundQueue:
    """Assign contiguous sequence numbers only to bounded admitted envelopes."""

    def __init__(
        self,
        *,
        max_envelopes: int = MAX_OUTBOX_ENVELOPES,
        max_bytes: int = MAX_OUTBOX_BYTES,
    ) -> None:
        if max_envelopes <= 0 or max_bytes <= 0:
            raise ValueError("outbox limits must be positive")
        self._max_envelopes = max_envelopes
        self._max_bytes = max_bytes
        self._items: list[_QueuedEnvelope] = []
        self._bytes = 0
        self._next_sequence = 0
        self._sent_sequence = 0
        self._terminal: WireEnvelope | None = None
        self._terminal_delivered = False
        self._closed_reason: str | None = None
        self._lock = threading.Lock()

    def admit(
        self,
        message_type: MessageType,
        payload: _Payload,
        state_version: int,
        timestamp_utc: datetime,
        *,
        replace_key: tuple[str, ...] | None = None,
    ) -> WireEnvelope:
        with self._lock:
            if self._closed_reason is not None:
                raise ConnectionAbortedError(self._closed_reason)
            if self._terminal is not None:
                if self._terminal_delivered:
                    raise ConnectionAbortedError("resnapshot-required")
                return self._terminal

            replacement_index = self._replacement_index(replace_key)
            sequence = (
                self._items[replacement_index].envelope.sequence
                if replacement_index is not None
                else self._next_sequence + 1
            )
            envelope = self._envelope(
                sequence,
                message_type,
                payload,
                state_version,
                timestamp_utc,
            )
            size = self._size(envelope)
            if replacement_index is not None:
                current = self._items[replacement_index]
                projected_bytes = self._bytes - current.size + size
                if size <= MAX_FRAME_BYTES and projected_bytes <= self._max_bytes:
                    self._items[replacement_index] = _QueuedEnvelope(
                        envelope,
                        size,
                        replace_key,
                    )
                    self._bytes = projected_bytes
                    return envelope
                return self._overflow(state_version, timestamp_utc)

            if (
                size > MAX_FRAME_BYTES
                or len(self._items) >= self._max_envelopes
                or self._bytes + size > self._max_bytes
            ):
                return self._overflow(state_version, timestamp_utc)
            self._items.append(_QueuedEnvelope(envelope, size, replace_key))
            self._bytes += size
            self._next_sequence = sequence
            return envelope

    def pop(self) -> WireEnvelope | None:
        with self._lock:
            if self._items:
                item = self._items.pop(0)
                self._bytes -= item.size
                self._sent_sequence = item.envelope.sequence
                if item.envelope is self._terminal:
                    self._terminal_delivered = True
                return item.envelope
            if self._terminal is not None and self._terminal_delivered:
                raise ConnectionAbortedError("resnapshot-required")
            if self._closed_reason is not None:
                raise ConnectionAbortedError(self._closed_reason)
            return None

    def close(self) -> None:
        with self._lock:
            self._items.clear()
            self._bytes = 0
            self._closed_reason = "connection-closed"

    @property
    def terminal(self) -> bool:
        with self._lock:
            return self._terminal is not None

    def _replacement_index(self, replace_key: tuple[str, ...] | None) -> int | None:
        if replace_key is None or not self._items:
            return None
        return len(self._items) - 1 if self._items[-1].replace_key == replace_key else None

    def _overflow(self, state_version: int, timestamp_utc: datetime) -> WireEnvelope:
        self._items.clear()
        self._bytes = 0
        sequence = self._sent_sequence + 1
        terminal = self._envelope(
            sequence,
            MessageType.PROTOCOL_ERROR,
            ProtocolErrorPayload(
                code="resnapshot-required",
                safe_message=_OVERFLOW_MESSAGE,
            ),
            state_version,
            timestamp_utc,
        )
        size = self._size(terminal)
        if size > MAX_FRAME_BYTES or size > self._max_bytes:
            self._closed_reason = "resnapshot-required"
            raise ConnectionAbortedError("resnapshot-required")
        self._terminal = terminal
        self._next_sequence = sequence
        self._items.append(_QueuedEnvelope(terminal, size, None))
        self._bytes = size
        return terminal

    @staticmethod
    def _envelope(
        sequence: int,
        message_type: MessageType,
        payload: _Payload,
        state_version: int,
        timestamp_utc: datetime,
    ) -> WireEnvelope:
        return WireEnvelope(
            schema_version=1,
            message_id=f"server:{sequence}",
            sequence=sequence,
            state_version=state_version,
            timestamp_utc=timestamp_utc,
            message_type=message_type,
            payload=payload.model_dump(mode="json"),
        )

    @staticmethod
    def _size(envelope: WireEnvelope) -> int:
        return len(envelope.model_dump_json().encode("utf-8"))
