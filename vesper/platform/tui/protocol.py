"""Bounded framing for the local V20 console protocol."""

from __future__ import annotations

import json
import struct

from pydantic import ValidationError

from vesper.platform.tui.contracts import (
    DiagnosticCallback,
    UntrustedProtocolDiagnostic,
    WireEnvelope,
    decode_envelope_json,
)

MAX_FRAME_BYTES = 1_048_576
_LENGTH = struct.Struct(">I")


class ProtocolViolation(Exception):
    """A protocol error safe to return to a local console client."""

    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class _DiagnosticCallbackFailure(Exception):
    """Keep callback failures out of parser and validation classification."""

    def __init__(self, error: BaseException) -> None:
        super().__init__("diagnostic callback failed")
        self.error = error


class FrameDecoder:
    """Incrementally decode complete, bounded wire frames in arrival order."""

    def __init__(self, on_untrusted: DiagnosticCallback | None = None) -> None:
        self._buffer = bytearray()
        self._on_untrusted = on_untrusted
        self._decode_depth = 0
        self._feed_depth = 0
        self._reentered_while_decoding = False

    def feed(self, chunk: bytes) -> tuple[WireEnvelope, ...]:
        """Accept one byte chunk and return each complete decoded envelope."""

        root_feed = self._feed_depth == 0
        if root_feed:
            self._reentered_while_decoding = False
        elif self._decode_depth:
            self._reentered_while_decoding = True
        self._feed_depth += 1
        try:
            decoded: list[WireEnvelope] = []
            remaining = memoryview(chunk)
            offset = 0
            while offset < len(remaining):
                if len(self._buffer) < _LENGTH.size:
                    header_bytes = min(_LENGTH.size - len(self._buffer), len(remaining) - offset)
                    self._buffer.extend(remaining[offset:offset + header_bytes])
                    offset += header_bytes
                    if len(self._buffer) < _LENGTH.size:
                        break
                size = _LENGTH.unpack_from(self._buffer)[0]
                if not 0 < size <= MAX_FRAME_BYTES:
                    self._fatal("frame-size", "Frame size is invalid.")
                frame_end = _LENGTH.size + size
                body_bytes = min(frame_end - len(self._buffer), len(remaining) - offset)
                self._buffer.extend(remaining[offset:offset + body_bytes])
                offset += body_bytes
                if len(self._buffer) < frame_end:
                    break
                body = bytes(self._buffer[_LENGTH.size:frame_end])
                del self._buffer[:frame_end]
                decoded.append(self._decode_body(body))
            if root_feed and self._reentered_while_decoding:
                self._fatal("reentrant-feed", "Message callback re-entered the decoder.")
            return tuple(decoded)
        except BaseException:
            self._buffer.clear()
            raise
        finally:
            self._feed_depth -= 1
            if root_feed:
                self._reentered_while_decoding = False

    def _decode_body(self, body: bytes) -> WireEnvelope:
        self._decode_depth += 1
        try:
            try:
                body.decode("utf-8")
            except UnicodeDecodeError:
                self._fatal("invalid-utf8", "Message text is invalid.")
            try:
                raw_value = json.loads(body)
            except (
                TypeError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                RecursionError,
                ValueError,
            ):
                self._fatal("invalid-json", "Message JSON is invalid.")
            untrusted_seen = False

            def report(diagnostic: UntrustedProtocolDiagnostic) -> None:
                nonlocal untrusted_seen
                untrusted_seen = True
                if self._on_untrusted is not None:
                    try:
                        self._on_untrusted(diagnostic)
                    except BaseException as error:
                        raise _DiagnosticCallbackFailure(error) from None

            callback_error: BaseException | None = None
            try:
                return decode_envelope_json(body, report)
            except _DiagnosticCallbackFailure as failure:
                callback_error = failure.error
            except ValidationError:
                if untrusted_seen:
                    self._fatal("unknown-field", "Message contains unsupported fields.")
                if isinstance(raw_value, dict) and raw_value.get("schema_version") != 1:
                    self._fatal("schema-version", "Message schema version is unsupported.")
                try:
                    WireEnvelope.model_validate_json(body)
                except ValidationError:
                    self._fatal("invalid-envelope", "Message envelope is invalid.")
                self._fatal("invalid-payload", "Message payload is invalid.")
            except (
                TypeError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                RecursionError,
                ValueError,
            ):
                self._fatal("invalid-json", "Message JSON is invalid.")
            if callback_error is not None:
                raise callback_error
        finally:
            self._decode_depth -= 1

    def _fatal(self, code: str, safe_message: str) -> None:
        self._buffer.clear()
        raise ProtocolViolation(code, safe_message)


def encode_frame(envelope: WireEnvelope) -> bytes:
    """Serialize one strict wire envelope inside its bounded length prefix."""

    body = envelope.model_dump_json().encode("utf-8")
    if not 0 < len(body) <= MAX_FRAME_BYTES:
        raise ProtocolViolation("frame-size", "Frame size is invalid.")
    return _LENGTH.pack(len(body)) + body
