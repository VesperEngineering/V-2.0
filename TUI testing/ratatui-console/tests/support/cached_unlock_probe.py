"""Disposable stdio adapter for the real Windows DPAPI cached-unlock path."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from vesper.platform.tui.auth import PasswordStore
from vesper.platform.tui.contracts import MessageType, WireEnvelope
from vesper.platform.tui.gateway import Gateway
from vesper.platform.tui.snapshot_cache import CACHE_LABEL, SnapshotCache
from vesper.platform.tui.views import ConsoleSnapshot

_REQUESTS_PER_CASE = (
    MessageType.CLIENT_HELLO,
    MessageType.AUTH_UNLOCK,
    MessageType.SNAPSHOT_REQUEST,
)


def _fixture() -> ConsoleSnapshot:
    repository = Path(__file__).resolve().parents[4]
    path = (
        repository
        / "TUI testing"
        / "contracts"
        / "v1"
        / "console_snapshot_empty_command_specs.json"
    )
    return ConsoleSnapshot.model_validate_json(path.read_bytes(), strict=True)


def _setup_password(line: str) -> str:
    value = json.loads(line)
    if type(value) is not dict or set(value) != {"setup_password"}:
        raise ValueError("probe setup is invalid")
    password = value["setup_password"]
    if type(password) is not str or not password:
        raise ValueError("probe password is invalid")
    return password


def _serve_case(source: ConsoleSnapshot, password: str) -> None:
    with tempfile.TemporaryDirectory(prefix="v20-cached-unlock-probe-") as temporary:
        state_root = Path(temporary).resolve()
        cache = SnapshotCache(state_root / "snapshot-cache.dpapi")
        cache.write(source)
        PasswordStore(state_root / "password-verifier.json").setup(password, password)
        gateway = Gateway(state_root, snapshot_cache=cache)
        client_id = "client:cached-unlock-probe"
        try:
            if gateway.cached_snapshot(client_id) is not None:
                raise RuntimeError("cache became visible before unlock")
            for expected in _REQUESTS_PER_CASE:
                request_line = sys.stdin.readline()
                if not request_line:
                    raise EOFError("probe request stream ended during a case")
                request = WireEnvelope.model_validate_json(request_line, strict=True)
                if request.message_type is not expected:
                    raise RuntimeError("probe request order is invalid")
                responses = gateway.handle(client_id, request)
                if len(responses) != 1:
                    raise RuntimeError("probe expected one gateway response")
                if expected is MessageType.AUTH_UNLOCK:
                    cached = gateway.cached_snapshot(client_id)
                    if cached is None or cached.label != CACHE_LABEL:
                        raise RuntimeError("real cache was not loaded after unlock")
                sys.stdout.write(responses[0].model_dump_json() + "\n")
                sys.stdout.flush()
        finally:
            gateway.disconnect(client_id)


def main() -> int:
    source = _fixture()
    while setup_line := sys.stdin.readline():
        _serve_case(source, _setup_password(setup_line))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
