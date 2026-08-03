"""Tests for local console password and controller ownership."""

from __future__ import annotations

import json
import os
from threading import Barrier, Thread

import pytest

from vesper.platform.tui.auth import ControlLease, LeaseStatus, PasswordStore


def test_password_store_keeps_only_verifier(tmp_path) -> None:
    store = PasswordStore(tmp_path / "auth.json")

    store.setup("correct horse", "correct horse")

    assert store.verify("correct horse") is True
    assert store.verify("wrong") is False
    body = (tmp_path / "auth.json").read_text(encoding="utf-8")
    assert "correct horse" not in body
    record = json.loads(body)
    assert set(record) == {"version", "salt", "n", "r", "p", "dklen", "verifier"}
    assert {key: record[key] for key in ("version", "n", "r", "p", "dklen")} == {
        "version": 1,
        "n": 32768,
        "r": 8,
        "p": 1,
        "dklen": 32,
    }


def test_password_store_requires_setup_before_verification(tmp_path) -> None:
    assert PasswordStore(tmp_path / "auth.json").verify("anything") is False


@pytest.mark.parametrize(
    ("password", "confirmation"),
    [
        ("", ""),
        ("one", "two"),
        ("a" * 1025, "a" * 1025),
        ("\u00e9" * 513, "\u00e9" * 513),
    ],
)
def test_password_store_rejects_invalid_setup(tmp_path, password: str, confirmation: str) -> None:
    store = PasswordStore(tmp_path / "auth.json")

    with pytest.raises(ValueError):
        store.setup(password, confirmation)

    assert not (tmp_path / "auth.json").exists()


def test_password_store_writes_first_verifier_atomically(tmp_path, monkeypatch) -> None:
    path = tmp_path / "auth.json"
    store = PasswordStore(path)
    replaced: list[tuple[str, str]] = []
    real_replace = os.replace

    def capture_replace(source: str, destination: str) -> None:
        assert os.path.exists(source)
        replaced.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr("vesper.platform.tui.auth.os.replace", capture_replace)
    store.setup("first password", "first password")

    assert len(replaced) == 1
    assert os.path.exists(replaced[0][0]) is False
    assert replaced[0][1] == path
    assert store.verify("first password") is True
    assert not list(tmp_path.glob(".auth.json.*.tmp"))


def test_password_store_setup_cannot_replace_existing_verifier(tmp_path) -> None:
    path = tmp_path / "auth.json"
    store = PasswordStore(path)
    store.setup("first password", "first password")

    with pytest.raises(ValueError, match="already configured"):
        store.setup("second password", "second password")

    assert store.verify("first password") is True
    assert store.verify("second password") is False


def test_concurrent_first_run_setup_allows_one_winner(tmp_path) -> None:
    store = PasswordStore(tmp_path / "auth.json")
    barrier = Barrier(2)
    successes: list[str] = []
    failures: list[Exception] = []

    def attempt(password: str) -> None:
        barrier.wait()
        try:
            store.setup(password, password)
        except ValueError as error:
            failures.append(error)
        else:
            successes.append(password)

    first = Thread(target=attempt, args=("first contender",))
    second = Thread(target=attempt, args=("second contender",))
    first.start()
    second.start()
    first.join()
    second.join()

    assert len(successes) == 1
    assert len(failures) == 1
    assert store.verify(successes[0]) is True
    assert store.verify("first contender") is (successes[0] == "first contender")
    assert store.verify("second contender") is (successes[0] == "second contender")


def test_password_store_corrupt_record_fails_closed(tmp_path) -> None:
    path = tmp_path / "auth.json"
    path.write_text('{"version":1,"salt":"bad"}', encoding="utf-8")

    assert PasswordStore(path).verify("anything") is False


@pytest.mark.parametrize("duplicate_key", ["version", "verifier"])
def test_password_store_rejects_duplicate_record_keys(tmp_path, duplicate_key: str) -> None:
    path = tmp_path / "auth.json"
    store = PasswordStore(path)
    store.setup("duplicate key", "duplicate key")
    record = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(
        json.dumps(record, separators=(",", ":"))[:-1]
        + f',"{duplicate_key}":{json.dumps(record[duplicate_key])}}}',
        encoding="utf-8",
    )

    assert store.verify("duplicate key") is False


def test_password_is_required_after_each_console_reopen(tmp_path) -> None:
    path = tmp_path / "auth.json"
    PasswordStore(path).setup("reopen password", "reopen password")

    reopened = PasswordStore(path)
    assert reopened.verify("reopen password") is True
    assert reopened.verify("wrong") is False


def test_control_lease_keeps_one_controller_and_viewers() -> None:
    lease = ControlLease()

    assert lease.acquire("client-a") is LeaseStatus.CONTROLLER
    assert lease.acquire("client-b") is LeaseStatus.VIEWER
    assert lease.acquire("client-c") is LeaseStatus.VIEWER
    assert lease.acquire("client-a") is LeaseStatus.CONTROLLER


def test_control_lease_never_transfers_implicitly_and_requires_explicit_acquire() -> None:
    lease = ControlLease()
    assert lease.acquire("client-a") is LeaseStatus.CONTROLLER
    assert lease.acquire("client-b") is LeaseStatus.VIEWER

    lease.release("client-a")

    # Releasing control is the manual-lock action. It does not promote a viewer.
    assert lease.controller_id is None
    assert lease.acquire("client-b") is LeaseStatus.TRANSFERRED
    assert lease.controller_id == "client-b"


def test_control_lease_has_no_idle_timeout_and_ignores_non_controller_release() -> None:
    lease = ControlLease()
    assert lease.acquire("client-a") is LeaseStatus.CONTROLLER
    assert lease.acquire("client-b") is LeaseStatus.VIEWER

    lease.release("client-b")

    assert lease.controller_id == "client-a"
    assert lease.acquire("client-a") is LeaseStatus.CONTROLLER


@pytest.mark.parametrize("client_id", ["", ".", "..", "has space", "x" * 129])
def test_control_lease_rejects_unsafe_client_ids(client_id: str) -> None:
    with pytest.raises(ValueError):
        ControlLease().acquire(client_id)
