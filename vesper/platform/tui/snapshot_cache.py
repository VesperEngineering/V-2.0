"""Current-user encrypted cache for stale, read-only console startup state."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, Protocol

from pydantic import Field, StringConstraints

from .views import (
    CapabilityState,
    CapabilityView,
    ConsoleSnapshot,
    NonEmptyStr,
    Sha256Hex,
    StrictModel,
    WireUInt,
)


CACHE_LABEL = "STALE CACHE"
CACHE_REASON = "Cached state; connect for current data."
DISABLED_REASON = "Cached state cannot authorize actions."
_MAGIC = b"V20SC1\0"
_MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
_MAX_CACHE_BYTES = 16 * 1024 * 1024
_DPAPI_DESCRIPTION = "Vesper V20 TUI snapshot cache"
_DPAPI_ENTROPY = b"Vesper.V20.TUI.snapshot-cache.v1"
_SCREEN_NAMES = (
    "impact",
    "portfolio",
    "orders",
    "agents",
    "models",
    "timeline",
    "risk",
    "data",
    "memory",
    "system",
)
_SnapshotJson = Annotated[str, StringConstraints(min_length=1, max_length=_MAX_SNAPSHOT_BYTES)]


class SnapshotCacheError(RuntimeError):
    """Encrypted cache input or storage failed closed."""


class DataProtectionPort(Protocol):
    def protect(self, plaintext: bytes) -> bytes: ...

    def unprotect(self, ciphertext: bytes) -> bytes: ...


class CurrentUserDataProtection:
    """Bind cache bytes to the current Windows account with DPAPI."""

    def protect(self, plaintext: bytes) -> bytes:
        import win32crypt

        return bytes(
            win32crypt.CryptProtectData(
                plaintext,
                _DPAPI_DESCRIPTION,
                _DPAPI_ENTROPY,
                None,
                None,
                0,
            )
        )

    def unprotect(self, ciphertext: bytes) -> bytes:
        import win32crypt

        description, plaintext = win32crypt.CryptUnprotectData(
            ciphertext,
            _DPAPI_ENTROPY,
            None,
            None,
            0,
        )
        if description != _DPAPI_DESCRIPTION:
            raise ValueError("snapshot cache description is invalid")
        return bytes(plaintext)


class _CacheEnvelope(StrictModel):
    version: Literal[1]
    snapshot_sha256: Sha256Hex
    snapshot_json: _SnapshotJson


class CacheReceipt(StrictModel):
    path: NonEmptyStr
    state_version: WireUInt
    plaintext_sha256: Sha256Hex
    ciphertext_sha256: Sha256Hex


class CachedSnapshot(StrictModel):
    label: Literal["STALE CACHE"]
    snapshot: ConsoleSnapshot

    @property
    def command_specs(self) -> tuple:
        return self.snapshot.command_specs

    @property
    def capabilities(self) -> tuple[CapabilityView, ...]:
        return self.snapshot.shell.capabilities

    @classmethod
    def from_snapshot(cls, snapshot: ConsoleSnapshot) -> CachedSnapshot:
        payload = snapshot.model_dump(mode="json")
        # Cached state is presentation-only. A runtime may restart its durable
        # counter below the cached value, so never let cache metadata block the
        # first fresh snapshot.
        payload["shell"]["state_version"] = 0
        payload["command_specs"] = []
        payload["shell"]["capabilities"] = [
            {
                "capability_id": capability.capability_id,
                "state": CapabilityState.DISABLED.value,
                "reason": DISABLED_REASON,
            }
            for capability in snapshot.shell.capabilities
        ]
        header = payload["shell"]["header"]
        if header["operating_mode_freshness"] in {"fresh", "stale"}:
            header["operating_mode_freshness"] = "stale"
            header["operating_mode_reason"] = CACHE_REASON
        if header["data_freshness"] in {"fresh", "stale"}:
            header["data_freshness"] = "stale"
        header["qwen_state"] = CACHE_LABEL
        for name in _SCREEN_NAMES:
            screen = payload[name]
            if screen["freshness"] in {"fresh", "stale"}:
                screen["freshness"] = "stale"
                screen["error"] = CACHE_REASON
        checked = ConsoleSnapshot.model_validate_json(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            strict=True,
        )
        return cls(label=CACHE_LABEL, snapshot=checked)


class SnapshotCache:
    """Persist full snapshots encrypted; reveal only disabled stale projections."""

    def __init__(
        self,
        path: Path,
        *,
        protection: DataProtectionPort | None = None,
        atomic_replace: Callable[[Path, Path], None] = os.replace,
    ) -> None:
        if not isinstance(path, Path) or not path.is_absolute():
            raise TypeError("snapshot cache path must be an absolute Path")
        selected = CurrentUserDataProtection() if protection is None else protection
        if not callable(getattr(selected, "protect", None)) or not callable(
            getattr(selected, "unprotect", None)
        ):
            raise TypeError("protection must provide protect and unprotect")
        if not callable(atomic_replace):
            raise TypeError("atomic_replace must be callable")
        self._path = path
        self._protection = selected
        self._atomic_replace = atomic_replace

    def write(self, snapshot: ConsoleSnapshot) -> CacheReceipt:
        if type(snapshot) is not ConsoleSnapshot:
            raise TypeError("snapshot must be a ConsoleSnapshot")
        self._prepare_parent()
        self._require_safe_file_if_present()
        snapshot_bytes = _canonical_json(snapshot.model_dump(mode="json"))
        if len(snapshot_bytes) > _MAX_SNAPSHOT_BYTES:
            raise SnapshotCacheError("cache-write-failed")
        snapshot_sha256 = _sha256(snapshot_bytes)
        envelope = _CacheEnvelope(
            version=1,
            snapshot_sha256=snapshot_sha256,
            snapshot_json=snapshot_bytes.decode("utf-8"),
        )
        plaintext = _canonical_json(envelope.model_dump(mode="json"))
        try:
            protected = self._protection.protect(plaintext)
            if type(protected) is not bytes or not protected:
                raise TypeError("protection returned invalid bytes")
            payload = _MAGIC + protected
            if len(payload) > _MAX_CACHE_BYTES:
                raise ValueError("encrypted cache exceeds size limit")
            self._atomic_write(payload)
            if self._path.read_bytes() != payload:
                raise OSError("snapshot cache verification failed")
        except SnapshotCacheError:
            raise
        except Exception as error:
            raise SnapshotCacheError("cache-write-failed") from error
        return CacheReceipt(
            path=str(self._path),
            state_version=snapshot.shell.state_version,
            plaintext_sha256=_sha256(plaintext),
            ciphertext_sha256=_sha256(payload),
        )

    def read_after_unlock(self) -> CachedSnapshot | None:
        if not os.path.lexists(self._path):
            return None
        try:
            self._require_safe_file_if_present()
            payload = self._path.read_bytes()
            if len(payload) > _MAX_CACHE_BYTES or not payload.startswith(_MAGIC):
                raise ValueError("encrypted cache framing is invalid")
            plaintext = self._protection.unprotect(payload[len(_MAGIC) :])
            if type(plaintext) is not bytes or len(plaintext) > _MAX_SNAPSHOT_BYTES * 2:
                raise ValueError("decrypted cache is invalid")
            envelope = _CacheEnvelope.model_validate_json(plaintext, strict=True)
            snapshot_bytes = envelope.snapshot_json.encode("utf-8")
            if _sha256(snapshot_bytes) != envelope.snapshot_sha256:
                raise ValueError("snapshot cache digest does not match")
            snapshot = ConsoleSnapshot.model_validate_json(snapshot_bytes, strict=True)
            return CachedSnapshot.from_snapshot(snapshot)
        except Exception as error:
            raise SnapshotCacheError("cache-unavailable") from error

    def _prepare_parent(self) -> None:
        current = Path(self._path.anchor)
        for part in self._path.parent.parts[1:]:
            current = current / part
            if os.path.lexists(current):
                if current.is_symlink() or not current.is_dir():
                    raise SnapshotCacheError("unsafe-cache-path")
            else:
                current.mkdir()

    def _require_safe_file_if_present(self) -> None:
        if os.path.lexists(self._path) and (
            self._path.is_symlink() or not self._path.is_file()
        ):
            raise SnapshotCacheError("unsafe-cache-path")

    def _atomic_write(self, payload: bytes) -> None:
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                dir=self._path.parent,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            self._atomic_replace(temp_path, self._path)
            temp_path = None
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
