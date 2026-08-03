"""Local password verification and explicit console-control ownership."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Lock

from .contracts import SafeId

_SALT_BYTES = 16
_DKLEN = 32
_MAX_PASSWORD_BYTES = 1024
_RECORD_VERSION = 1
_SCRYPT_N = 32768
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 67108864
_RECORD_FIELDS = frozenset({"version", "salt", "n", "r", "p", "dklen", "verifier"})
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class LeaseStatus(StrEnum):
    """The result of an explicit session lease request."""

    CONTROLLER = "controller"
    VIEWER = "viewer"
    TRANSFERRED = "transferred"


@dataclass(frozen=True)
class _VerifierRecord:
    salt: bytes
    verifier: bytes


class PasswordStore:
    """Persist only a scrypt verifier; malformed records always deny access."""

    _path_locks: dict[Path, Lock] = {}
    _path_locks_lock = Lock()

    def __init__(self, path: Path) -> None:
        self._path = path

    def setup(self, password: str, confirmation: str) -> None:
        """Create the first local password verifier atomically."""

        password_bytes = self._validated_password_bytes(password)
        confirmation_bytes = self._validated_password_bytes(confirmation)
        if password_bytes != confirmation_bytes:
            raise ValueError("password confirmation does not match")

        with self._setup_lock_for(self._path):
            if os.path.lexists(self._path):
                raise ValueError("password verifier is already configured")
            salt = os.urandom(_SALT_BYTES)
            verifier = self._derive(password_bytes, salt)
            record = {
                "version": _RECORD_VERSION,
                "salt": base64.b64encode(salt).decode("ascii"),
                "n": _SCRYPT_N,
                "r": _SCRYPT_R,
                "p": _SCRYPT_P,
                "dklen": _DKLEN,
                "verifier": base64.b64encode(verifier).decode("ascii"),
            }
            self._write_record(record)

    def verify(self, password: str) -> bool:
        """Return true only for a valid password and an exact valid verifier record."""

        try:
            password_bytes = self._validated_password_bytes(password)
            record = self._read_record_fail_closed()
            actual = self._derive(password_bytes, record.salt)
        except (OSError, TypeError, ValueError, MemoryError):
            return False
        return hmac.compare_digest(actual, record.verifier)

    @staticmethod
    def _validated_password_bytes(password: str) -> bytes:
        if not isinstance(password, str):
            raise ValueError("password must be text")
        encoded = password.encode("utf-8")
        if not encoded or len(encoded) > _MAX_PASSWORD_BYTES:
            raise ValueError("password must be 1 to 1024 UTF-8 bytes")
        return encoded

    @staticmethod
    def _derive(password: bytes, salt: bytes) -> bytes:
        return hashlib.scrypt(
            password,
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_DKLEN,
            maxmem=_SCRYPT_MAXMEM,
        )

    def _read_record_fail_closed(self) -> _VerifierRecord:
        try:
            raw = self._path.read_text(encoding="utf-8")
            body = json.loads(raw, object_pairs_hook=_reject_duplicate_object_pairs)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("invalid password verifier") from error
        if not isinstance(body, dict) or set(body) != _RECORD_FIELDS:
            raise ValueError("invalid password verifier")
        if (
            type(body["version"]) is not int
            or body["version"] != _RECORD_VERSION
            or type(body["n"]) is not int
            or body["n"] != _SCRYPT_N
            or type(body["r"]) is not int
            or body["r"] != _SCRYPT_R
            or type(body["p"]) is not int
            or body["p"] != _SCRYPT_P
            or type(body["dklen"]) is not int
            or body["dklen"] != _DKLEN
            or not isinstance(body["salt"], str)
            or not isinstance(body["verifier"], str)
        ):
            raise ValueError("invalid password verifier")
        try:
            salt = base64.b64decode(body["salt"], validate=True)
            verifier = base64.b64decode(body["verifier"], validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("invalid password verifier") from error
        if len(salt) != _SALT_BYTES or len(verifier) != _DKLEN:
            raise ValueError("invalid password verifier")
        return _VerifierRecord(salt=salt, verifier=verifier)

    def _write_record(self, record: dict[str, int | str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.", suffix=".tmp", dir=self._path.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(payload)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_name, self._path)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass

    @classmethod
    def _setup_lock_for(cls, path: Path) -> Lock:
        resolved_path = path.resolve()
        with cls._path_locks_lock:
            lock = cls._path_locks.get(resolved_path)
            if lock is None:
                lock = Lock()
                cls._path_locks[resolved_path] = lock
            return lock


def _reject_duplicate_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    body: dict[str, object] = {}
    for key, value in pairs:
        if key in body:
            raise ValueError("duplicate password verifier key")
        body[key] = value
    return body


class ControlLease:
    """In-memory, no-timeout control lease for one controller and many viewers."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._controller_id: str | None = None
        self._viewer_ids: set[str] = set()

    @property
    def controller_id(self) -> str | None:
        with self._lock:
            return self._controller_id

    def acquire(self, client_id: SafeId) -> LeaseStatus:
        """Claim an available lease only through this explicit request."""

        self._validate_client_id(client_id)
        with self._lock:
            if client_id == self._controller_id:
                return LeaseStatus.CONTROLLER
            if self._controller_id is not None:
                self._viewer_ids.add(client_id)
                return LeaseStatus.VIEWER

            was_viewer = client_id in self._viewer_ids
            self._viewer_ids.discard(client_id)
            self._controller_id = client_id
            return LeaseStatus.TRANSFERRED if was_viewer else LeaseStatus.CONTROLLER

    def release(self, client_id: SafeId) -> None:
        """Release a session's lease; this never promotes another viewer."""

        self._validate_client_id(client_id)
        with self._lock:
            if self._controller_id == client_id:
                self._controller_id = None
            self._viewer_ids.discard(client_id)

    @staticmethod
    def _validate_client_id(client_id: str) -> None:
        if not isinstance(client_id, str) or client_id in {".", ".."} or not _SAFE_ID.fullmatch(client_id):
            raise ValueError("client ID is not safe")
