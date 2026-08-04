from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from vesper.platform.tui.command_contracts import (
    CommandRequest,
    NoteAddPayload,
    ReceiptStatus,
)
from vesper.platform.tui.command_policy import (
    AuthorizationDecision,
    CommandContext,
    EvaluatedPrerequisites,
)
from vesper.platform.tui.command_store import (
    CommandClaimError,
    CommandConflict,
    CommandStateError,
    CommandStore,
    SafeRequestMetadata,
    canonical_request_json,
)
from vesper.platform.tui.notes import NoteStore, NoteTarget, NoteVisibility
from vesper.platform.tui.sqlite_ledger import LedgerCorruptionError, TuiLedger


NOW = datetime(2026, 8, 3, 16, 0, tzinfo=timezone.utc)
CONTROL_HASH = "7c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43"


def _request(
    command_id: str = "client:note:1",
    *,
    body: str = "Review concentration.",
    control_version: int = 19,
) -> CommandRequest:
    return CommandRequest(
        command_id=command_id,
        command_type="note.add",
        reviewed_control_version=control_version,
        reviewed_control_hash=CONTROL_HASH,
        reason=None,
        confirmation=None,
        payload=NoteAddPayload(
            target_type="stock",
            target_id="AAPL",
            body=body,
            visibility="private",
        ),
    )


def _context(
    *,
    control_version: int = 19,
    operator_id: str = "operator:windows",
    client_id: str = "client:console",
) -> CommandContext:
    return CommandContext(
        operator_id=operator_id,
        client_id=client_id,
        authenticated=True,
        owns_control_lease=True,
        control_version=control_version,
        control_hash=CONTROL_HASH,
        capabilities=(),
        prerequisites=EvaluatedPrerequisites(
            request_sha256="0" * 64,
            complete=True,
            checks=(),
        ),
    )


def _metadata(request: CommandRequest, context: CommandContext) -> SafeRequestMetadata:
    return SafeRequestMetadata(
        command_id=request.command_id,
        command_type=request.command_type,
        operator_id=context.operator_id,
        client_id=context.client_id,
        reviewed_control_version=request.reviewed_control_version,
        reviewed_control_hash=request.reviewed_control_hash,
    )


def _rejection(request_hash: str) -> AuthorizationDecision:
    del request_hash
    return AuthorizationDecision(
        allowed=False,
        code="locked",
        safe_message="Console session is locked.",
    )


def _request_hash(request: CommandRequest) -> str:
    return hashlib.sha256(canonical_request_json(request).encode("utf-8")).hexdigest()


def test_accept_is_canonical_durable_idempotent_and_conflict_safe(tmp_path) -> None:
    database = tmp_path / "commands.db"
    request = _request(control_version=2**64 - 1)
    context = _context(control_version=2**64 - 1)
    store = CommandStore(database)

    accepted = store.accept(request, context, "note.add", NOW)
    assert accepted.status is ReceiptStatus.ACCEPTED
    assert accepted.accepted_at_utc == NOW
    assert accepted.finished_at_utc is None
    assert store.accept(request, context, "note.add", NOW + timedelta(seconds=1)) == accepted

    conflicting = _request(body="Different content", control_version=2**64 - 1)
    with pytest.raises(CommandConflict, match="client:note:1"):
        store.accept(conflicting, context, "note.add", NOW)

    with store._ledger.read() as connection:
        row = connection.execute("SELECT * FROM commands").fetchone()
        event_count = connection.execute(
            "SELECT COUNT(*) FROM command_receipt_events"
        ).fetchone()[0]
    assert row["accepted_request_json"] == canonical_request_json(request)
    assert row["request_sha256"] == _request_hash(request)
    assert row["reviewed_control_version"] == str(2**64 - 1)
    assert row["operator_id"] == context.operator_id
    assert row["client_id"] == context.client_id
    assert event_count == 1
    store.close()

    reopened = CommandStore(database)
    assert reopened.get(request.command_id) == accepted
    recovered = reopened.get_accepted(request.command_id)
    assert recovered is not None
    assert recovered.request == request
    assert recovered.handler_key == "note.add"
    reopened.close()


@pytest.mark.parametrize(
    ("context_field", "changed_value"),
    (
        ("operator_id", "operator:other"),
        ("client_id", "client:other"),
    ),
)
def test_accepted_replay_conflicts_across_operator_or_client_context(
    tmp_path,
    context_field: str,
    changed_value: str,
) -> None:
    store = CommandStore(tmp_path / "commands.db")
    request = _request()
    store.accept(request, _context(), "note.add", NOW)
    changed_context = _context(**{context_field: changed_value})

    with pytest.raises(CommandConflict, match="replay context"):
        store.accept(request, changed_context, "note.add", NOW)
    store.close()


def test_accepted_replay_binds_handler_key(tmp_path) -> None:
    store = CommandStore(tmp_path / "commands.db")
    request = _request()
    store.accept(request, _context(), "note.add", NOW)

    with pytest.raises(CommandConflict, match="replay context"):
        store.accept(request, _context(), "other.handler", NOW)
    store.close()


def test_rejection_stores_only_safe_audit_metadata_and_replays(tmp_path) -> None:
    request = _request(body="PRIVATE-PAYLOAD-MARKER")
    context = _context()
    request_hash = _request_hash(request)
    store = CommandStore(tmp_path / "commands.db")

    rejected = store.reject(
        request_hash,
        _metadata(request, context),
        _rejection(request_hash),
        NOW,
    )
    assert rejected.status is ReceiptStatus.REJECTED
    assert rejected.accepted_at_utc is None
    assert rejected.finished_at_utc == NOW
    assert (
        store.reject(
            request_hash,
            _metadata(request, context),
            _rejection(request_hash),
            NOW + timedelta(minutes=1),
        )
        == rejected
    )

    with store._ledger.read() as connection:
        row = connection.execute("SELECT * FROM commands").fetchone()
        columns = tuple(row.keys())
        events = connection.execute(
            "SELECT status, code, safe_message FROM command_receipt_events"
        ).fetchall()
    assert row["accepted_request_json"] is None
    assert row["handler_key"] is None
    assert row["operator_id"] == "operator:windows"
    assert row["client_id"] == "client:console"
    assert row["reviewed_control_version"] == "19"
    assert row["reviewed_control_hash"] == CONTROL_HASH
    assert row["request_sha256"] == request_hash
    assert not {"payload", "reason", "confirmation"} & set(columns)
    assert [tuple(event) for event in events] == [
        ("rejected", "locked", "Console session is locked.")
    ]
    assert "PRIVATE-PAYLOAD-MARKER" not in json.dumps(dict(row))
    store.close()


@pytest.mark.parametrize(
    ("context_field", "changed_value"),
    (
        ("operator_id", "operator:other"),
        ("client_id", "client:other"),
    ),
)
def test_rejected_replay_conflicts_across_operator_or_client_context(
    tmp_path,
    context_field: str,
    changed_value: str,
) -> None:
    request = _request()
    request_hash = _request_hash(request)
    store = CommandStore(tmp_path / "commands.db")
    store.reject(
        request_hash,
        _metadata(request, _context()),
        _rejection(request_hash),
        NOW,
    )
    changed_context = _context(**{context_field: changed_value})

    with pytest.raises(CommandConflict, match="replay context"):
        store.reject(
            request_hash,
            _metadata(request, changed_context),
            _rejection(request_hash),
            NOW,
        )
    store.close()


@pytest.mark.parametrize(
    "metadata_change",
    (
        {"command_type": "alert.dismiss"},
        {"reviewed_control_version": 20},
        {"reviewed_control_hash": "8" * 64},
    ),
)
def test_rejected_replay_binds_command_and_control_identity(
    tmp_path,
    metadata_change: dict[str, object],
) -> None:
    request = _request()
    request_hash = _request_hash(request)
    metadata = _metadata(request, _context())
    store = CommandStore(tmp_path / "commands.db")
    store.reject(request_hash, metadata, _rejection(request_hash), NOW)

    with pytest.raises(CommandConflict, match="replay context"):
        store.reject(
            request_hash,
            metadata.model_copy(update=metadata_change),
            _rejection(request_hash),
            NOW,
        )
    store.close()


def test_same_context_replay_never_changes_the_original_admission_effect(tmp_path) -> None:
    store = CommandStore(tmp_path / "commands.db")
    context = _context()
    rejected_request = _request("client:note:rejected")
    rejected_hash = _request_hash(rejected_request)
    rejected = store.reject(
        rejected_hash,
        _metadata(rejected_request, context),
        _rejection(rejected_hash),
        NOW,
    )
    assert store.accept(rejected_request, context, "note.add", NOW) == rejected
    assert (
        store.claim(
            rejected_request.command_id,
            "worker:one",
            NOW,
            NOW + timedelta(minutes=1),
        )
        is None
    )

    accepted_request = _request("client:note:accepted")
    accepted = store.accept(accepted_request, context, "note.add", NOW)
    accepted_hash = _request_hash(accepted_request)
    assert (
        store.reject(
            accepted_hash,
            _metadata(accepted_request, context),
            _rejection(accepted_hash),
            NOW,
        )
        == accepted
    )
    with store.ledger.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM command_receipt_events"
        ).fetchone()[0] == 2
    store.close()


def test_claim_expiry_reclaim_and_terminal_finish_require_current_token(tmp_path) -> None:
    request = _request()
    store = CommandStore(tmp_path / "commands.db")
    store.accept(request, _context(), "note.add", NOW)

    first = store.claim(
        request.command_id,
        "worker:one",
        NOW + timedelta(seconds=1),
        NOW + timedelta(seconds=11),
    )
    assert first is not None
    assert first.receipt.status is ReceiptStatus.RUNNING
    assert len(first.claim_token) == 64
    with store.ledger.read() as connection:
        stored_token = connection.execute(
            "SELECT claim_token_sha256 FROM commands WHERE command_id = ?",
            (request.command_id,),
        ).fetchone()[0]
    assert stored_token == hashlib.sha256(first.claim_token.encode("ascii")).hexdigest()
    assert stored_token != first.claim_token
    assert (
        store.claim(
            request.command_id,
            "worker:two",
            NOW + timedelta(seconds=10),
            NOW + timedelta(seconds=20),
        )
        is None
    )

    second = store.claim(
        request.command_id,
        "worker:two",
        NOW + timedelta(seconds=11),
        NOW + timedelta(seconds=21),
    )
    assert second is not None
    assert second.claim_token != first.claim_token
    with pytest.raises(CommandClaimError, match="claim"):
        store.finish(
            request.command_id,
            first.claim_token,
            ReceiptStatus.COMPLETED,
            None,
            NOW + timedelta(seconds=12),
        )

    completed = store.finish(
        request.command_id,
        second.claim_token,
        ReceiptStatus.COMPLETED,
        {"count": 1},
        NOW + timedelta(seconds=12),
    )
    assert completed.status is ReceiptStatus.COMPLETED
    assert completed.result == {"count": 1}
    assert (
        store.finish(
            request.command_id,
            second.claim_token,
            ReceiptStatus.COMPLETED,
            {"count": 1},
            NOW + timedelta(seconds=12),
        )
        == completed
    )
    with pytest.raises(CommandStateError, match="terminal"):
        store.finish(
            request.command_id,
            second.claim_token,
            ReceiptStatus.COMPLETED,
            {"count": 1},
            NOW + timedelta(seconds=13),
        )
    with pytest.raises(CommandStateError, match="terminal"):
        store.finish(
            request.command_id,
            second.claim_token,
            ReceiptStatus.FAILED,
            None,
            NOW + timedelta(seconds=13),
        )
    with pytest.raises(CommandClaimError, match="stale or unknown"):
        store.finish(
            request.command_id,
            "b" * 64,
            ReceiptStatus.COMPLETED,
            {"count": 1},
            NOW + timedelta(seconds=13),
        )
    assert store.claim(
        request.command_id,
        "worker:three",
        NOW + timedelta(seconds=22),
        NOW + timedelta(seconds=32),
    ) is None
    store.close()


def test_expired_claim_cannot_finish_before_or_after_reclaim(tmp_path) -> None:
    request = _request()
    store = CommandStore(tmp_path / "commands.db")
    store.accept(request, _context(), "note.add", NOW)
    claim = store.claim(
        request.command_id,
        "worker:one",
        NOW,
        NOW + timedelta(seconds=5),
    )
    assert claim is not None

    with pytest.raises(CommandClaimError, match="expired"):
        store.finish(
            request.command_id,
            claim.claim_token,
            ReceiptStatus.COMPLETED,
            None,
            NOW + timedelta(seconds=5),
        )
    assert store.expired_running(NOW + timedelta(seconds=5)) == (claim.receipt,)
    store.close()


def test_finish_can_store_exact_safe_terminal_override_and_replay(tmp_path) -> None:
    request = _request()
    database = tmp_path / "commands.db"
    store = CommandStore(database)
    store.accept(request, _context(), "note.add", NOW)
    claim = store.claim(
        request.command_id,
        "worker:recovery",
        NOW,
        NOW + timedelta(minutes=1),
    )
    assert claim is not None

    receipt = store.finish(
        request.command_id,
        claim.claim_token,
        ReceiptStatus.FAILED,
        None,
        NOW + timedelta(seconds=1),
        code="manual-intervention-required",
        safe_message="Recovery state is unknown; inspect before retrying.",
    )
    assert receipt.code == "manual-intervention-required"
    assert receipt.safe_message == "Recovery state is unknown; inspect before retrying."
    assert (
        store.finish(
            request.command_id,
            claim.claim_token,
            ReceiptStatus.FAILED,
            None,
            NOW + timedelta(seconds=1),
            code="manual-intervention-required",
            safe_message="Recovery state is unknown; inspect before retrying.",
        )
        == receipt
    )
    with store.ledger.read() as connection:
        command = connection.execute(
            "SELECT code, safe_message FROM commands WHERE command_id = ?",
            (request.command_id,),
        ).fetchone()
        event = connection.execute(
            "SELECT code, safe_message FROM command_receipt_events "
            "WHERE command_id = ? ORDER BY event_sequence DESC LIMIT 1",
            (request.command_id,),
        ).fetchone()
    assert tuple(command) == tuple(event) == (
        "manual-intervention-required",
        "Recovery state is unknown; inspect before retrying.",
    )

    with pytest.raises(CommandStateError, match="terminal"):
        store.finish(
            request.command_id,
            claim.claim_token,
            ReceiptStatus.FAILED,
            None,
            NOW + timedelta(seconds=1),
            code="different-code",
            safe_message="Recovery state is unknown; inspect before retrying.",
        )
    with pytest.raises(CommandStateError, match="terminal"):
        store.finish(
            request.command_id,
            claim.claim_token,
            ReceiptStatus.FAILED,
            None,
            NOW + timedelta(seconds=1),
            code="manual-intervention-required",
            safe_message="A different recovery message.",
        )
    store.close()

    reopened = CommandStore(database)
    assert reopened.get(request.command_id) == receipt
    reopened.close()


@pytest.mark.parametrize(
    ("code", "safe_message"),
    (
        ("bad code", "Safe."),
        ("manual-intervention-required", ""),
        ("manual-intervention-required", "x" * 513),
        (1, "Safe."),
        ("manual-intervention-required", 1),
    ),
)
def test_finish_rejects_invalid_terminal_overrides(
    tmp_path,
    code: object,
    safe_message: object,
) -> None:
    request = _request()
    store = CommandStore(tmp_path / "commands.db")
    store.accept(request, _context(), "note.add", NOW)
    claim = store.claim(
        request.command_id,
        "worker:recovery",
        NOW,
        NOW + timedelta(minutes=1),
    )
    assert claim is not None

    with pytest.raises((TypeError, ValueError)):
        store.finish(
            request.command_id,
            claim.claim_token,
            ReceiptStatus.FAILED,
            None,
            NOW + timedelta(seconds=1),
            code=code,  # type: ignore[arg-type]
            safe_message=safe_message,  # type: ignore[arg-type]
        )
    assert store.get(request.command_id).status is ReceiptStatus.RUNNING
    store.close()


def test_terminal_result_is_recursively_redacted_before_storage(tmp_path) -> None:
    request = _request()
    store = CommandStore(tmp_path / "commands.db")
    store.accept(request, _context(), "note.add", NOW)
    claim = store.claim(
        request.command_id,
        "worker:one",
        NOW,
        NOW + timedelta(minutes=1),
    )
    assert claim is not None
    receipt = store.finish(
        request.command_id,
        claim.claim_token,
        ReceiptStatus.COMPLETED,
        {
            "safe": 1,
            "password": "remove",
            "nested": {
                "api_key": "remove",
                "items": [
                    {"accessToken": "remove", "keep": True},
                    {
                        "credential_value": "remove",
                        "API KEY": "remove",
                        "api.key": "remove",
                        "ＡＰＩ　ＫＥＹ": "remove",
                        "name": "ok",
                    },
                ],
            },
            "secret_hint": "remove",
        },
        NOW + timedelta(seconds=1),
    )
    assert receipt.result == {
        "safe": 1,
        "nested": {"items": [{"keep": True}, {"name": "ok"}]},
    }
    with store._ledger.read() as connection:
        stored = connection.execute(
            "SELECT result_json FROM commands WHERE command_id = ?",
            (request.command_id,),
        ).fetchone()[0]
    assert stored == '{"nested":{"items":[{"keep":true},{"name":"ok"}]},"safe":1}'
    store.close()


def test_list_paginates_by_admission_and_recovery_lists_only_expired_running(
    tmp_path,
) -> None:
    store = CommandStore(tmp_path / "commands.db")
    context = _context()
    receipts = []
    for index in range(3):
        request = _request(f"client:note:{index}")
        receipts.append(store.accept(request, context, "note.add", NOW + timedelta(seconds=index)))

    first_page = store.list(2, None)
    assert [row.command_id for row in first_page] == ["client:note:2", "client:note:1"]
    second_page = store.list(2, first_page[-1].command_id)
    assert [row.command_id for row in second_page] == ["client:note:0"]
    assert [row.command_id for row in store.recoverable(NOW + timedelta(seconds=3))] == [
        "client:note:0",
        "client:note:1",
        "client:note:2",
    ]

    claim = store.claim(
        "client:note:0",
        "worker:one",
        NOW + timedelta(seconds=3),
        NOW + timedelta(seconds=8),
    )
    assert claim is not None
    assert store.expired_running(NOW + timedelta(seconds=7)) == ()
    assert store.expired_running(NOW + timedelta(seconds=8)) == (claim.receipt,)
    assert [row.command_id for row in store.recoverable(NOW + timedelta(seconds=7))] == [
        "client:note:1",
        "client:note:2",
    ]
    assert [row.command_id for row in store.recoverable(NOW + timedelta(seconds=8))] == [
        "client:note:0",
        "client:note:1",
        "client:note:2",
    ]
    for invalid in (0, 101, True):
        with pytest.raises((TypeError, ValueError)):
            store.list(invalid, None)  # type: ignore[arg-type]
    store.close()


def test_receipt_events_and_command_admissions_cannot_be_deleted(tmp_path) -> None:
    request = _request()
    store = CommandStore(tmp_path / "commands.db")
    store.accept(request, _context(), "note.add", NOW)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with store._ledger.transaction() as connection:
            connection.execute("UPDATE command_receipt_events SET code = 'changed'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with store._ledger.transaction() as connection:
            connection.execute("DELETE FROM command_receipt_events")
    with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
        with store._ledger.transaction() as connection:
            connection.execute("DELETE FROM commands")
    store.close()


def test_database_triggers_reject_identity_and_illegal_status_tampering(tmp_path) -> None:
    request = _request()
    store = CommandStore(tmp_path / "commands.db")
    store.accept(request, _context(), "note.add", NOW)
    with pytest.raises(sqlite3.IntegrityError, match="admission is immutable"):
        with store._ledger.transaction() as connection:
            connection.execute(
                "UPDATE commands SET command_id = 'client:changed' "
                "WHERE command_id = ?",
                (request.command_id,),
            )
    with pytest.raises(sqlite3.IntegrityError, match="invalid command status transition"):
        with store._ledger.transaction() as connection:
            connection.execute(
                "UPDATE commands SET status = 'completed' WHERE command_id = ?",
                (request.command_id,),
            )
    claim = store.claim(
        request.command_id,
        "worker:one",
        NOW,
        NOW + timedelta(minutes=1),
    )
    assert claim is not None
    with pytest.raises(sqlite3.IntegrityError, match="invalid command status transition"):
        with store._ledger.transaction() as connection:
            connection.execute(
                "UPDATE commands SET safe_message = 'tampered' WHERE command_id = ?",
                (request.command_id,),
            )
    store.close()


def test_reclaim_trigger_uses_exact_microsecond_expiry(tmp_path) -> None:
    request = _request()
    store = CommandStore(tmp_path / "commands.db")
    store.accept(request, _context(), "note.add", NOW)
    claim = store.claim(
        request.command_id,
        "worker:one",
        NOW,
        NOW + timedelta(microseconds=5),
    )
    assert claim is not None
    with pytest.raises(sqlite3.IntegrityError, match="invalid command status transition"):
        with store.ledger.transaction() as connection:
            connection.execute(
                """
                UPDATE commands
                SET claim_worker_id = 'worker:two', claim_token_sha256 = ?,
                    claimed_at_utc = ?, claim_expires_at_utc = ?
                WHERE command_id = ?
                """,
                (
                    "f" * 64,
                    (NOW + timedelta(microseconds=4)).isoformat().replace("+00:00", "Z"),
                    (NOW + timedelta(microseconds=10)).isoformat().replace("+00:00", "Z"),
                    request.command_id,
                ),
            )
    store.close()


def test_reopen_rejects_tampered_canonical_accepted_request(tmp_path) -> None:
    database = tmp_path / "commands.db"
    store = CommandStore(database)
    store.accept(_request(), _context(), "note.add", NOW)
    store.close()
    with sqlite3.connect(database) as connection:
        triggers = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_schema "
                "WHERE name IN ('commands_admission_immutable', 'commands_status_transition')"
            )
        }
        connection.execute("DROP TRIGGER commands_admission_immutable")
        connection.execute("DROP TRIGGER commands_status_transition")
        connection.execute(
            "UPDATE commands SET accepted_request_json = '{}' "
            "WHERE command_id = 'client:note:1'"
        )
        connection.execute(triggers["commands_admission_immutable"])
        connection.execute(triggers["commands_status_transition"])

    with pytest.raises(LedgerCorruptionError, match="command content"):
        CommandStore(database)


def test_reopen_rejects_unknown_rejected_command_type(tmp_path) -> None:
    database = tmp_path / "commands.db"
    request = _request()
    store = CommandStore(database)
    store.reject(
        _request_hash(request),
        _metadata(request, _context()),
        _rejection(_request_hash(request)),
        NOW,
    )
    store.close()
    with sqlite3.connect(database) as connection:
        trigger_sql = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_schema WHERE name IN "
                "('commands_admission_immutable', 'commands_terminal_immutable')"
            )
        }
        connection.execute("DROP TRIGGER commands_admission_immutable")
        connection.execute("DROP TRIGGER commands_terminal_immutable")
        connection.execute("UPDATE commands SET command_type = 'unknown.command'")
        connection.execute(trigger_sql["commands_admission_immutable"])
        connection.execute(trigger_sql["commands_terminal_immutable"])

    with pytest.raises(LedgerCorruptionError, match="command content"):
        CommandStore(database)


def test_reopen_rejects_result_outside_shared_json_integer_range(tmp_path) -> None:
    database = tmp_path / "commands.db"
    store = CommandStore(database)
    request = _request()
    store.accept(request, _context(), "note.add", NOW)
    claim = store.claim(
        request.command_id,
        "worker:one",
        NOW,
        NOW + timedelta(minutes=1),
    )
    assert claim is not None
    store.finish(
        request.command_id,
        claim.claim_token,
        ReceiptStatus.COMPLETED,
        {"count": 1},
        NOW + timedelta(seconds=1),
    )
    store.close()
    with sqlite3.connect(database) as connection:
        trigger_sql = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_schema WHERE name IN "
                "('commands_terminal_immutable', 'commands_status_transition', "
                "'command_receipt_events_no_update')"
            )
        }
        connection.execute("DROP TRIGGER commands_terminal_immutable")
        connection.execute("DROP TRIGGER commands_status_transition")
        connection.execute("DROP TRIGGER command_receipt_events_no_update")
        connection.execute(
            "UPDATE commands SET result_json = ?",
            ('{"count":18446744073709551616}',),
        )
        connection.execute(
            "UPDATE command_receipt_events SET result_json = ? "
            "WHERE status = 'completed'",
            ('{"count":18446744073709551616}',),
        )
        connection.execute(trigger_sql["commands_terminal_immutable"])
        connection.execute(trigger_sql["commands_status_transition"])
        connection.execute(trigger_sql["command_receipt_events_no_update"])

    with pytest.raises(LedgerCorruptionError, match="command content"):
        CommandStore(database)


def test_reopen_rejects_tampered_prior_receipt_event_semantics(tmp_path) -> None:
    database = tmp_path / "commands.db"
    store = CommandStore(database)
    request = _request()
    store.accept(request, _context(), "note.add", NOW)
    claim = store.claim(
        request.command_id,
        "worker:one",
        NOW + timedelta(seconds=1),
        NOW + timedelta(minutes=1),
    )
    assert claim is not None
    store.finish(
        request.command_id,
        claim.claim_token,
        ReceiptStatus.COMPLETED,
        None,
        NOW + timedelta(seconds=2),
    )
    store.close()
    with sqlite3.connect(database) as connection:
        trigger_sql = connection.execute(
            "SELECT sql FROM sqlite_schema "
            "WHERE name = 'command_receipt_events_no_update'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER command_receipt_events_no_update")
        connection.execute(
            "UPDATE command_receipt_events SET code = 'forged' "
            "WHERE status = 'accepted'"
        )
        connection.execute(trigger_sql)

    with pytest.raises(LedgerCorruptionError, match="command content"):
        CommandStore(database)


def test_reopen_rejects_duplicate_current_running_receipt_event(tmp_path) -> None:
    database = tmp_path / "commands.db"
    store = CommandStore(database)
    request = _request()
    store.accept(request, _context(), "note.add", NOW)
    claim = store.claim(
        request.command_id,
        "worker:one",
        NOW + timedelta(seconds=1),
        NOW + timedelta(minutes=1),
    )
    assert claim is not None
    store.close()
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO command_receipt_events (
                command_id, status, code, safe_message, occurred_at_utc,
                worker_id, result_json
            )
            SELECT
                command_id, status, code, safe_message, occurred_at_utc,
                worker_id, result_json
            FROM command_receipt_events
            WHERE status = 'running'
            """
        )

    with pytest.raises(LedgerCorruptionError, match="command content"):
        CommandStore(database)


def test_reopen_rejects_unknown_rejection_decision_code(tmp_path) -> None:
    database = tmp_path / "commands.db"
    request = _request()
    store = CommandStore(database)
    store.reject(
        _request_hash(request),
        _metadata(request, _context()),
        _rejection(_request_hash(request)),
        NOW,
    )
    store.close()
    with sqlite3.connect(database) as connection:
        trigger_sql = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_schema WHERE name IN "
                "('commands_terminal_immutable', 'commands_status_transition', "
                "'command_receipt_events_no_update')"
            )
        }
        for trigger_name in trigger_sql:
            connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.execute("UPDATE commands SET code = 'forged'")
        connection.execute("UPDATE command_receipt_events SET code = 'forged'")
        for statement in trigger_sql.values():
            connection.execute(statement)

    with pytest.raises(LedgerCorruptionError, match="command content"):
        CommandStore(database)


def test_concurrent_accept_and_claim_have_one_admission_and_one_live_claim(tmp_path) -> None:
    database = tmp_path / "commands.db"
    CommandStore(database).close()
    barrier = threading.Barrier(2)

    def accept_once() -> object:
        store = CommandStore(database)
        barrier.wait()
        try:
            return store.accept(_request(), _context(), "note.add", NOW)
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted = tuple(pool.map(lambda _index: accept_once(), range(2)))
    assert accepted[0] == accepted[1]

    claim_barrier = threading.Barrier(2)

    def same_claim(worker: str) -> object:
        store = CommandStore(database)
        claim_barrier.wait()
        try:
            return store.claim("client:note:1", worker, NOW, NOW + timedelta(minutes=1))
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = tuple(pool.map(same_claim, ("worker:one", "worker:two")))
    assert sum(claim is not None for claim in claims) == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM command_receipt_events WHERE status = 'accepted'"
        ).fetchone()[0] == 1


def test_concurrent_same_id_with_different_hash_has_one_winner_and_one_conflict(
    tmp_path,
) -> None:
    database = tmp_path / "commands.db"
    CommandStore(database).close()
    barrier = threading.Barrier(2)

    def admit(body: str) -> str:
        store = CommandStore(database)
        barrier.wait()
        try:
            store.accept(_request(body=body), _context(), "note.add", NOW)
            return "accepted"
        except CommandConflict:
            return "conflict"
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(admit, ("first", "second")))
    assert sorted(outcomes) == ["accepted", "conflict"]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM command_receipt_events"
        ).fetchone()[0] == 1


def test_unclaimed_accepted_command_is_recoverable_after_reopen(tmp_path) -> None:
    database = tmp_path / "commands.db"
    first = CommandStore(database)
    accepted = first.accept(_request(), _context(), "note.add", NOW)
    first.close()

    reopened = CommandStore(database)
    assert reopened.recoverable(NOW + timedelta(days=1)) == (accepted,)
    assert reopened.get_accepted(accepted.command_id) is not None
    reopened.close()


def test_note_add_and_terminal_receipt_share_one_transaction_and_replay(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "commands.db")
    commands = CommandStore(ledger, token_factory=lambda: "a" * 64)
    notes = NoteStore(ledger, clock=lambda: NOW)
    request = _request()
    context = _context()
    target = NoteTarget(target_type="stock", target_id="AAPL")

    with pytest.raises(RuntimeError, match="rollback"):
        with ledger.transaction() as connection:
            commands.accept_in_transaction(connection, request, context, "note.add", NOW)
            claim = commands.claim_in_transaction(
                connection,
                request.command_id,
                "worker:one",
                NOW,
                NOW + timedelta(minutes=1),
            )
            assert claim is not None
            notes.add_for_command_in_transaction(
                connection,
                request.command_id,
                target,
                "Review concentration.",
                NoteVisibility.PRIVATE,
                "operator:windows",
            )
            commands.finish_in_transaction(
                connection,
                request.command_id,
                claim.claim_token,
                ReceiptStatus.COMPLETED,
                None,
                NOW + timedelta(seconds=1),
            )
            raise RuntimeError("rollback")
    assert commands.get(request.command_id) is None
    assert notes.list(target) == ()

    with ledger.transaction() as connection:
        commands.accept_in_transaction(connection, request, context, "note.add", NOW)
        claim = commands.claim_in_transaction(
            connection,
            request.command_id,
            "worker:one",
            NOW,
            NOW + timedelta(minutes=1),
        )
        assert claim is not None
        note = notes.add_for_command_in_transaction(
            connection,
            request.command_id,
            target,
            "Review concentration.",
            NoteVisibility.PRIVATE,
            "operator:windows",
        )
        receipt = commands.finish_in_transaction(
            connection,
            request.command_id,
            claim.claim_token,
            ReceiptStatus.COMPLETED,
            {"note_id": note.note_id},
            NOW + timedelta(seconds=1),
        )
    assert commands.accept(request, context, "note.add", NOW) == receipt
    assert notes.list(target) == (note,)
    with ledger.transaction() as connection:
        assert (
            notes.add_for_command_in_transaction(
                connection,
                request.command_id,
                target,
                "Review concentration.",
                NoteVisibility.PRIVATE,
                "operator:windows",
            )
            == note
        )
    assert notes.list(target) == (note,)
    ledger.close()
