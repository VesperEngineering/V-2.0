"""Strict read-only projection of the legacy saved engine state file."""

from __future__ import annotations

import json
import ctypes
import math
import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, BinaryIO

from pydantic import ValidationError

from vesper.platform.tui.ports import (
    LegacyPositionFact,
    OrderFacts,
    PortfolioFacts,
    RiskFacts,
    SourceSample,
    UnavailablePort,
)
from vesper.platform.tui.views import CircuitBreakerView, Freshness


_SOURCE = "legacy saved engine state"
_SCHEMA_KEYS = {
    "ts",
    "session_date",
    "daily_pnl",
    "starting_equity",
    "peak_equity",
    "breaker_tripped",
    "positions",
}
_POSITION_KEYS = {"qty", "entry", "price"}
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")
_MAX_DECIMAL_DIGITS = 128
_MAX_DECIMAL_ADJUSTED_EXPONENT = 128
_PROTECTED_SEQUENCES = (
    ("vesper", "data", "massive"),
    ("vesper", "data", "model_research"),
)


class _ProjectionError(ValueError):
    pass


class _StrictJsonError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _ValidatedStatePath:
    path: Path
    root: Path
    signature: tuple[int, int, int, int, int]


class LegacyStateProjection:
    """Read one configured state file without constructing legacy runtime objects."""

    def __init__(
        self,
        configured_root: Path,
        state_path: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        stale_after: timedelta = timedelta(minutes=5),
        max_bytes: int = 64 * 1024,
        max_positions: int = 10_000,
    ) -> None:
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        if type(max_positions) is not int or max_positions <= 0:
            raise ValueError("max_positions must be a positive integer")
        if stale_after < timedelta(0):
            raise ValueError("stale_after cannot be negative")
        self._configured_root = Path(os.path.abspath(configured_root))
        self._state_path = Path(state_path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._stale_after = stale_after
        self._max_bytes = max_bytes
        self._max_positions = max_positions
        self.portfolio_port: UnavailablePort[PortfolioFacts] = UnavailablePort(
            "Legacy saved state cannot prove asset type, cash, weights, rank, or reconciliation.",
            source=_SOURCE,
        )
        self.order_port: UnavailablePort[OrderFacts] = UnavailablePort(
            "Legacy saved state contains no typed order history.",
            source=_SOURCE,
        )

    def read(self) -> SourceSample[RiskFacts]:
        try:
            path = self._validated_path()
            raw_bytes = self._read_bounded(path)
            payload = self._decode_strict_json(raw_bytes)
            now = self._utc_now()
            observed_at = self._timestamp(payload)
            if observed_at > now:
                raise _ProjectionError("Legacy saved engine state timestamp is in the future.")
            facts = self._risk_facts(payload, observed_at)
        except _ProjectionError as exc:
            return self._unavailable(str(exc))

        if now - observed_at > self._stale_after:
            seconds = self._stale_after.total_seconds()
            rendered = str(int(seconds)) if seconds.is_integer() else f"{seconds:g}"
            return SourceSample[RiskFacts](
                value=facts,
                freshness=Freshness.STALE,
                observed_at_utc=observed_at,
                source=_SOURCE,
                error=f"Legacy saved engine state is older than {rendered} seconds.",
            )
        return SourceSample[RiskFacts](
            value=facts,
            freshness=Freshness.FRESH,
            observed_at_utc=observed_at,
            source=_SOURCE,
            error=None,
        )

    def _validated_path(self) -> _ValidatedStatePath:
        if self._state_path.is_absolute():
            candidate = Path(os.path.abspath(self._state_path))
        else:
            candidate = Path(os.path.abspath(self._configured_root / self._state_path))
        try:
            relative = candidate.relative_to(self._configured_root)
        except ValueError as exc:
            raise _ProjectionError(
                "Legacy state path is outside its configured root."
            ) from exc
        if _has_protected_sequence(candidate):
            raise _ProjectionError("Legacy state path targets protected data.")

        current = self._configured_root
        for part in (Path(), *relative.parts):
            if part != Path():
                current /= part
            try:
                status = current.lstat()
            except (FileNotFoundError, NotADirectoryError, OSError) as exc:
                raise _ProjectionError("Legacy saved engine state is unavailable.") from exc
            if _is_reparse(status):
                raise _ProjectionError(
                    "Legacy state path is a symlink or reparse point."
                )

        try:
            root_resolved = self._configured_root.resolve(strict=True)
            candidate_resolved = candidate.resolve(strict=True)
            candidate_resolved.relative_to(root_resolved)
            if _has_protected_sequence(root_resolved) or _has_protected_sequence(
                candidate_resolved
            ):
                raise _ProjectionError("Legacy state path targets protected data.")
            candidate_status = candidate_resolved.stat()
        except _ProjectionError:
            raise
        except ValueError as exc:
            raise _ProjectionError(
                "Legacy state path is outside its configured root."
            ) from exc
        except OSError as exc:
            raise _ProjectionError("Legacy saved engine state is unavailable.") from exc
        if not stat.S_ISREG(candidate_status.st_mode):
            raise _ProjectionError("Legacy state path is not a regular file.")
        if candidate_status.st_nlink != 1:
            raise _ProjectionError("Legacy state path has multiple hard links.")
        return _ValidatedStatePath(
            path=candidate_resolved,
            root=root_resolved,
            signature=_stat_signature(candidate_status),
        )

    def _read_bounded(self, validated: _ValidatedStatePath) -> bytes:
        try:
            with validated.path.open("rb") as handle:
                status = os.fstat(handle.fileno())
                if not stat.S_ISREG(status.st_mode) or _is_reparse(status):
                    raise _ProjectionError(
                        "Legacy state path is a symlink or reparse point."
                    )
                if status.st_nlink != 1:
                    raise _ProjectionError("Legacy state path has multiple hard links.")
                if _stat_signature(status) != validated.signature:
                    raise _ProjectionError(
                        "Legacy saved engine state changed while it was read."
                    )
                self._validate_opened_handle(handle, validated)
                if status.st_size > self._max_bytes:
                    raise _ProjectionError(
                        f"Legacy saved engine state exceeds the {self._max_bytes}-byte limit."
                    )
                raw = handle.read(self._max_bytes + 1)
                final_status = os.fstat(handle.fileno())
                if (
                    _stat_signature(final_status) != validated.signature
                    or len(raw) != final_status.st_size
                ):
                    raise _ProjectionError(
                        "Legacy saved engine state changed while it was read."
                    )
        except _ProjectionError:
            raise
        except OSError as exc:
            raise _ProjectionError("Legacy saved engine state is unavailable.") from exc
        if len(raw) > self._max_bytes:
            raise _ProjectionError(
                f"Legacy saved engine state exceeds the {self._max_bytes}-byte limit."
            )
        return raw

    @staticmethod
    def _validate_opened_handle(
        handle: BinaryIO,
        validated: _ValidatedStatePath,
    ) -> None:
        if os.name != "nt":
            return
        opened_path = _opened_handle_path(handle)
        if opened_path is None:
            raise _ProjectionError(
                "Legacy saved engine state handle could not be verified."
            )
        try:
            opened_path.relative_to(validated.root)
        except ValueError as exc:
            raise _ProjectionError(
                "Legacy state opened outside its configured root."
            ) from exc
        if _has_protected_sequence(opened_path):
            raise _ProjectionError("Legacy state path targets protected data.")
        if _normalized_path(opened_path) != _normalized_path(validated.path):
            raise _ProjectionError(
                "Legacy saved engine state changed while it was read."
            )

    @staticmethod
    def _decode_strict_json(raw_bytes: bytes) -> dict[str, Any]:
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _ProjectionError(
                "Legacy saved engine state is not valid UTF-8."
            ) from exc
        try:
            value = json.loads(
                text,
                object_pairs_hook=_unique_object,
                parse_float=Decimal,
                parse_int=Decimal,
                parse_constant=_reject_constant,
            )
        except (json.JSONDecodeError, _StrictJsonError, InvalidOperation, RecursionError) as exc:
            raise _ProjectionError(
                "Legacy saved engine state is not valid strict JSON."
            ) from exc
        if type(value) is not dict:
            raise _ProjectionError("Legacy saved engine state schema is invalid.")
        return value

    def _utc_now(self) -> datetime:
        try:
            now = self._clock()
        except Exception as exc:
            raise _ProjectionError("Legacy projection clock did not return UTC.") from exc
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise _ProjectionError("Legacy projection clock did not return UTC.")
        return now

    @staticmethod
    def _timestamp(payload: dict[str, Any]) -> datetime:
        raw = payload.get("ts")
        if not isinstance(raw, str) or not raw or len(raw) > 64:
            raise _ProjectionError("Legacy saved engine state schema is invalid.")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise _ProjectionError("Legacy saved engine state schema is invalid.") from exc
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        if parsed.utcoffset() != timedelta(0):
            raise _ProjectionError("Legacy saved engine state timestamp must be UTC.")
        return parsed.astimezone(timezone.utc)

    def _risk_facts(self, payload: dict[str, Any], observed_at: datetime) -> RiskFacts:
        try:
            if set(payload) != _SCHEMA_KEYS:
                raise ValueError("unexpected fields")
            session_date = _session_date(payload["session_date"])
            daily_pnl = _finite_float(_decimal(payload["daily_pnl"]))
            starting_equity = _finite_float(
                _decimal(payload["starting_equity"], nonnegative=True)
            )
            peak_equity = _finite_float(
                _decimal(payload["peak_equity"], nonnegative=True)
            )
            breaker = payload["breaker_tripped"]
            if type(breaker) is not bool:
                raise ValueError("breaker_tripped must be boolean")
            raw_positions = payload["positions"]
            if type(raw_positions) is not dict or len(raw_positions) > self._max_positions:
                raise ValueError("positions must be a bounded mapping")
            positions: list[LegacyPositionFact] = []
            for symbol in sorted(raw_positions):
                raw_position = raw_positions[symbol]
                if not isinstance(symbol, str) or type(raw_position) is not dict:
                    raise ValueError("position is invalid")
                if set(raw_position) != _POSITION_KEYS:
                    raise ValueError("position has unexpected fields")
                positions.append(
                    LegacyPositionFact(
                        symbol=symbol,
                        quantity=_decimal_text(
                            _decimal(raw_position["qty"], nonnegative=True)
                        ),
                        entry_price=_decimal_text(
                            _decimal(raw_position["entry"], nonnegative=True)
                        ),
                        current_price=_decimal_text(
                            _decimal(raw_position["price"], nonnegative=True)
                        ),
                    )
                )
            return RiskFacts(
                session_date=session_date,
                daily_pnl=daily_pnl,
                starting_equity=starting_equity,
                peak_equity=peak_equity,
                breaker_tripped=breaker,
                positions=tuple(positions),
                broker_reconciled=False,
                blocked_actions=None,
                blocked_actions_error="Legacy risk state does not include blocked-action detail.",
                circuit_breaker=CircuitBreakerView(
                    state="tripped" if breaker else "armed",
                    reason="Legacy breaker is tripped." if breaker else None,
                    observed_at_utc=observed_at,
                ),
                circuit_breaker_error=None,
            )
        except (KeyError, TypeError, ValueError, InvalidOperation, ValidationError, OverflowError) as exc:
            raise _ProjectionError("Legacy saved engine state schema is invalid.") from exc

    @staticmethod
    def _unavailable(reason: str) -> SourceSample[RiskFacts]:
        return SourceSample[RiskFacts](
            value=None,
            freshness=Freshness.UNAVAILABLE,
            observed_at_utc=None,
            source=_SOURCE,
            error=reason,
        )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _StrictJsonError("duplicate key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise _StrictJsonError("non-finite number")


def _session_date(value: Any) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("session_date must be ISO date or null")
    return date.fromisoformat(value)


def _decimal(value: Any, *, nonnegative: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("boolean is not numeric")
    if isinstance(value, Decimal):
        result = value
    elif (
        isinstance(value, str)
        and len(value) <= _MAX_DECIMAL_DIGITS
        and _DECIMAL_PATTERN.fullmatch(value)
    ):
        result = Decimal(value)
    else:
        raise ValueError("value must be a strict decimal")
    if (
        not result.is_finite()
        or len(result.as_tuple().digits) > _MAX_DECIMAL_DIGITS
        or abs(result.adjusted()) > _MAX_DECIMAL_ADJUSTED_EXPONENT
        or (nonnegative and result < 0)
    ):
        raise ValueError("value must be finite and nonnegative when required")
    return result


def _finite_float(value: Decimal) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("value is outside finite float range")
    return result


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _stat_signature(status: os.stat_result | Any) -> tuple[int, int, int, int, int]:
    return (
        int(status.st_dev),
        int(status.st_ino),
        int(status.st_nlink),
        int(status.st_size),
        int(status.st_mtime_ns),
    )


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _opened_handle_path(handle: BinaryIO) -> Path | None:
    if os.name != "nt":
        return None
    try:
        import msvcrt

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_final_path = kernel32.GetFinalPathNameByHandleW
        get_final_path.restype = ctypes.c_uint32
        buffer = ctypes.create_unicode_buffer(32_768)
        os_handle = msvcrt.get_osfhandle(handle.fileno())
        length = get_final_path(
            ctypes.c_void_p(os_handle),
            buffer,
            len(buffer),
            0,
        )
    except (AttributeError, OSError, ValueError):
        return None
    if length == 0 or length >= len(buffer):
        return None
    rendered = buffer.value
    if rendered.startswith("\\\\?\\UNC\\"):
        rendered = "\\\\" + rendered[8:]
    elif rendered.startswith("\\\\?\\"):
        rendered = rendered[4:]
    path = Path(rendered)
    return path if path.is_absolute() else None


def _has_protected_sequence(path: Path) -> bool:
    parts = tuple(part.casefold() for part in path.parts)
    return any(
        parts[index : index + len(sequence)] == sequence
        for sequence in _PROTECTED_SEQUENCES
        for index in range(len(parts))
    )


def _is_reparse(status: os.stat_result) -> bool:
    if stat.S_ISLNK(status.st_mode):
        return True
    attributes = getattr(status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)
