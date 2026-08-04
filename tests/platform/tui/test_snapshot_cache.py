from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.platform.tui.auth import PasswordStore
from vesper.platform.tui.command_contracts import COMMAND_SPECS
from vesper.platform.tui.contracts import (
    AuthResultPayload,
    MessageType,
    SnapshotPayload,
    WireEnvelope,
    decode_payload,
)
from vesper.platform.tui.gateway import Gateway
from vesper.platform.tui.snapshot_cache import (
    CACHE_LABEL,
    CachedSnapshot,
    SnapshotCache,
    SnapshotCacheError,
)
from vesper.platform.tui.views import CapabilityState, ConsoleSnapshot, Freshness


FIXTURE = (
    Path(__file__).parents[3]
    / "TUI testing"
    / "contracts"
    / "v1"
    / "console_snapshot_empty_command_specs.json"
)


class _Protection:
    def __init__(self, user: str = "user-a") -> None:
        self.user = user

    def protect(self, plaintext: bytes) -> bytes:
        return self.user.encode() + b"\0" + plaintext[::-1]

    def unprotect(self, ciphertext: bytes) -> bytes:
        prefix = self.user.encode() + b"\0"
        if not ciphertext.startswith(prefix):
            raise ValueError("wrong Windows user")
        return ciphertext[len(prefix) :][::-1]


def _snapshot() -> ConsoleSnapshot:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    spec = COMMAND_SPECS[0]
    payload["command_specs"] = [spec.model_dump(mode="json")]
    payload["shell"]["capabilities"] = [
        {
            "capability_id": spec.capability_id,
            "state": "enabled",
            "reason": None,
        }
    ]
    return ConsoleSnapshot.model_validate_json(json.dumps(payload), strict=True)


def test_cache_is_encrypted_and_read_projection_never_authorizes(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.cache"
    cache = SnapshotCache(path, protection=_Protection())
    source = _snapshot()

    receipt = cache.write(source)
    cached = cache.read_after_unlock()

    assert receipt.state_version == source.shell.state_version
    assert b"risk-on" not in path.read_bytes()
    assert cached is not None
    assert cached.label == CACHE_LABEL == "STALE CACHE"
    assert cached.command_specs == ()
    assert all(cap.state is CapabilityState.DISABLED for cap in cached.capabilities)
    assert all(cap.reason == "Cached state cannot authorize actions." for cap in cached.capabilities)
    assert cached.snapshot.portfolio.freshness is Freshness.STALE
    assert cached.snapshot.portfolio.error == "Cached state; connect for current data."
    assert cached.snapshot.shell.header.qwen_state == CACHE_LABEL


def test_cached_projection_uses_restart_safe_zero_state_version() -> None:
    payload = _snapshot().model_dump(mode="json")
    payload["shell"]["state_version"] = 42
    source = ConsoleSnapshot.model_validate_json(json.dumps(payload), strict=True)

    cached = CachedSnapshot.from_snapshot(source)

    assert source.shell.state_version == 42
    assert cached.snapshot.shell.state_version == 0


def test_missing_cache_returns_none(tmp_path: Path) -> None:
    cache = SnapshotCache(tmp_path / "missing.cache", protection=_Protection())

    assert cache.read_after_unlock() is None


def test_wrong_user_and_corruption_fail_closed_without_plaintext(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.cache"
    SnapshotCache(path, protection=_Protection("user-a")).write(_snapshot())

    with pytest.raises(SnapshotCacheError, match="cache-unavailable"):
        SnapshotCache(path, protection=_Protection("user-b")).read_after_unlock()

    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(data)
    with pytest.raises(SnapshotCacheError, match="cache-unavailable"):
        SnapshotCache(path, protection=_Protection("user-a")).read_after_unlock()


def test_atomic_replace_failure_preserves_previous_cache(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.cache"
    cache = SnapshotCache(path, protection=_Protection())
    first = _snapshot()
    cache.write(first)
    original = path.read_bytes()

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("replace failed")

    failing = SnapshotCache(path, protection=_Protection(), atomic_replace=fail_replace)
    with pytest.raises(SnapshotCacheError, match="cache-write-failed"):
        failing.write(first)

    assert path.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []


def test_cache_path_symlink_is_rejected_without_touching_target(tmp_path: Path) -> None:
    target = tmp_path / "outside.cache"
    target.write_bytes(b"outside")
    link = tmp_path / "snapshot.cache"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")

    cache = SnapshotCache(link, protection=_Protection())

    with pytest.raises(SnapshotCacheError, match="unsafe-cache-path"):
        cache.write(_snapshot())
    assert target.read_bytes() == b"outside"


def test_repeated_write_is_deterministic_with_deterministic_test_protection(
    tmp_path: Path,
) -> None:
    path = tmp_path / "snapshot.cache"
    cache = SnapshotCache(path, protection=_Protection())
    snapshot = _snapshot()

    first = cache.write(snapshot)
    first_bytes = path.read_bytes()
    second = cache.write(snapshot)

    assert path.read_bytes() == first_bytes
    assert first.plaintext_sha256 == second.plaintext_sha256
    assert first.ciphertext_sha256 == second.ciphertext_sha256


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_current_windows_user_dpapi_round_trip(tmp_path: Path) -> None:
    cache = SnapshotCache(tmp_path / "dpapi.cache")

    cache.write(_snapshot())
    restored = cache.read_after_unlock()

    assert restored is not None
    assert restored.label == CACHE_LABEL
    assert restored.command_specs == ()


def _envelope(message_type: MessageType, sequence: int, payload: dict[str, object]) -> WireEnvelope:
    return WireEnvelope(
        schema_version=1,
        message_id=f"client:{sequence}",
        sequence=sequence,
        state_version=0,
        timestamp_utc=datetime(2026, 8, 4, 16, 0, tzinfo=timezone.utc),
        message_type=message_type,
        payload=payload,
    )


def test_gateway_hides_cache_until_unlock_then_replaces_it_with_fresh_state(
    tmp_path: Path,
) -> None:
    source = _snapshot()
    cache = SnapshotCache(tmp_path / "snapshot.cache", protection=_Protection())
    cache.write(source)
    PasswordStore(tmp_path / "password-verifier.json").setup("password", "password")
    gateway = Gateway(
        tmp_path,
        snapshot_cache=cache,
        logon_sid_provider=lambda: "S-1-5-21",
    )
    client_id = "client:cache-test"

    assert gateway.cached_snapshot(client_id) is None
    hello = gateway.handle(
        client_id,
        _envelope(
            MessageType.CLIENT_HELLO,
            1,
            {"client_version": "0.1.0", "supported_schema_versions": [1]},
        ),
    )[0]
    assert hello.message_type is MessageType.SERVER_HELLO
    assert gateway.cached_snapshot(client_id) is None

    auth = gateway.handle(
        client_id,
        _envelope(MessageType.AUTH_UNLOCK, 2, {"password": "password"}),
    )[0]
    assert decode_payload(auth) == AuthResultPayload(
        success=True,
        access_state="viewer",
        reason=None,
    )
    cached = gateway.cached_snapshot(client_id)
    assert cached is not None
    assert cached.label == CACHE_LABEL

    response = gateway.handle(
        client_id,
        _envelope(MessageType.SNAPSHOT_REQUEST, 3, {}),
    )[0]
    payload = decode_payload(response)
    assert isinstance(payload, SnapshotPayload)
    assert payload.snapshot.command_specs == ()
    assert all(
        capability.state is CapabilityState.DISABLED
        for capability in payload.snapshot.shell.capabilities
    )

    gateway.publish_snapshot(source)

    assert gateway.cached_snapshot(client_id) is None
    assert gateway.snapshot().shell.header.qwen_state != CACHE_LABEL
