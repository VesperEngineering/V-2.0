from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from vesper.platform.tui.command_contracts import (
    ApprovalPayload,
    CommandRequest,
    ConfirmationProof,
    NoteAddPayload,
    ReceiptStatus,
)
from vesper.platform.tui.command_policy import CommandContext, EvaluatedPrerequisites
from vesper.platform.tui.command_store import CommandClaimError, CommandStore
from vesper.platform.tui.operator_decisions import (
    OperatorDecisionConflict,
    OperatorDecisionError,
    OperatorDecisionStore,
)
from vesper.platform.tui.sqlite_ledger import LedgerCorruptionError, TuiLedger


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
CONTROL_HASH = "7c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43"


def _request(*, reason: str = "Keep the approval pending.") -> CommandRequest:
    return CommandRequest(
        command_id="client:hold:1",
        command_type="approval.hold",
        reviewed_control_version=19,
        reviewed_control_hash=CONTROL_HASH,
        reason=reason,
        confirmation=ConfirmationProof(first_confirmed=True),
        payload=ApprovalPayload(run_id="run:1", checkpoint_id="checkpoint:1"),
    )


def _context(
    *,
    operator_id: str = "operator:windows",
    client_id: str = "client:console",
    authenticated: bool = True,
    owns_control_lease: bool = True,
    control_version: int = 19,
    control_hash: str = CONTROL_HASH,
) -> CommandContext:
    return CommandContext(
        operator_id=operator_id,
        client_id=client_id,
        authenticated=authenticated,
        owns_control_lease=owns_control_lease,
        control_version=control_version,
        control_hash=control_hash,
        capabilities=(),
        prerequisites=EvaluatedPrerequisites(
            request_sha256="0" * 64,
            complete=True,
            checks=(),
        ),
    )


def _accepted_claim(ledger: TuiLedger):
    commands = CommandStore(ledger, token_factory=lambda: "a" * 64)
    request = _request()
    context = _context()
    commands.accept(request, context, "approval.hold", NOW)
    claim = commands.claim(
        request.command_id,
        "worker:controls",
        NOW + timedelta(seconds=1),
        NOW + timedelta(minutes=1),
    )
    assert claim is not None
    return commands, request, context, claim


def test_hold_is_canonical_atomic_durable_and_exactly_idempotent(tmp_path) -> None:
    database = tmp_path / "controls.db"
    ledger = TuiLedger(database)
    commands, request, context, claim = _accepted_claim(ledger)
    decisions = OperatorDecisionStore(ledger)

    decision, receipt = decisions.hold(
        request,
        context,
        claim.claim_token,
        NOW + timedelta(seconds=2),
    )
    expected_id = "tui-decision:" + hashlib.sha256(
        request.command_id.encode("utf-8")
    ).hexdigest()
    assert decision.decision_id == expected_id
    assert decision.command_id == request.command_id
    assert decision.run_id == "run:1"
    assert decision.checkpoint_id == "checkpoint:1"
    assert decision.operator_id == context.operator_id
    assert decision.reason == request.reason
    assert decision.decision == "hold"
    assert decision.decided_at_utc == NOW + timedelta(seconds=2)
    assert receipt.status is ReceiptStatus.COMPLETED
    assert receipt.result == {"decision_id": expected_id}
    assert decisions.hold(
        request,
        context,
        "not-a-live-token",
        NOW + timedelta(days=1),
    ) == (decision, receipt)

    with ledger.read() as connection:
        row = connection.execute("SELECT * FROM operator_decisions").fetchone()
        content = json.loads(row["content_json"])
        decision_count = connection.execute(
            "SELECT COUNT(*) FROM operator_decisions"
        ).fetchone()[0]
        terminal_count = connection.execute(
            "SELECT COUNT(*) FROM command_receipt_events WHERE status = 'completed'"
        ).fetchone()[0]
    assert content == decision.model_dump(mode="json")
    assert row["content_json"] == json.dumps(
        content,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert decision_count == terminal_count == 1
    decisions.close()
    commands.close()
    ledger.close()

    reopened = OperatorDecisionStore(database)
    assert reopened.get(request.command_id) == decision
    reopened.close()


@pytest.mark.parametrize(
    "changed",
    ("request", "operator", "client", "version", "hash", "auth", "lease"),
)
def test_hold_rejects_any_non_exact_replay(tmp_path, changed: str) -> None:
    ledger = TuiLedger(tmp_path / "controls.db")
    commands, request, context, claim = _accepted_claim(ledger)
    decisions = OperatorDecisionStore(ledger)
    decisions.hold(request, context, claim.claim_token, NOW + timedelta(seconds=2))

    replay_request = request
    replay_context = context
    if changed == "request":
        replay_request = _request(reason="Different reason.")
    elif changed == "operator":
        replay_context = _context(operator_id="operator:other")
    elif changed == "client":
        replay_context = _context(client_id="client:other")
    elif changed == "version":
        replay_context = _context(control_version=20)
    elif changed == "hash":
        replay_context = _context(control_hash="1" * 64)
    elif changed == "auth":
        replay_context = _context(authenticated=False)
    else:
        replay_context = _context(owns_control_lease=False)

    with pytest.raises(OperatorDecisionConflict):
        decisions.hold(
            replay_request,
            replay_context,
            claim.claim_token,
            NOW + timedelta(seconds=2),
        )
    assert decisions.list() == (decisions.get(request.command_id),)
    decisions.close()
    commands.close()
    ledger.close()


def test_hold_requires_exact_accepted_hold_request_and_live_claim(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "controls.db")
    commands = CommandStore(ledger, token_factory=lambda: "a" * 64)
    context = _context()
    note_request = CommandRequest(
        command_id="client:hold:1",
        command_type="note.add",
        reviewed_control_version=19,
        reviewed_control_hash=CONTROL_HASH,
        reason=None,
        confirmation=None,
        payload=NoteAddPayload(
            target_type="approval",
            target_id="run:1",
            body="context",
            visibility="private",
        ),
    )
    commands.accept(note_request, context, "note.add", NOW)
    claim = commands.claim(
        note_request.command_id,
        "worker:controls",
        NOW + timedelta(seconds=1),
        NOW + timedelta(minutes=1),
    )
    assert claim is not None
    decisions = OperatorDecisionStore(ledger)

    with pytest.raises(OperatorDecisionError, match="approval.hold"):
        decisions.hold(
            note_request,
            context,
            claim.claim_token,
            NOW + timedelta(seconds=2),
        )
    with pytest.raises(OperatorDecisionConflict, match="accepted request"):
        decisions.hold(
            _request(),
            context,
            claim.claim_token,
            NOW + timedelta(seconds=2),
        )
    assert decisions.list() == ()
    decisions.close()
    commands.close()
    ledger.close()


def test_hold_rolls_back_decision_when_terminal_receipt_fails(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "controls.db")
    commands, request, context, claim = _accepted_claim(ledger)
    decisions = OperatorDecisionStore(ledger)

    with pytest.raises((TypeError, ValueError)):
        decisions.hold(
            request,
            context,
            "not-a-valid-token",
            NOW + timedelta(seconds=2),
        )
    assert decisions.list() == ()
    assert commands.get(request.command_id).status is ReceiptStatus.RUNNING

    with pytest.raises(CommandClaimError, match="expired"):
        decisions.hold(
            request,
            context,
            claim.claim_token,
            NOW + timedelta(minutes=1),
        )
    assert decisions.list() == ()
    assert commands.get(request.command_id).status is ReceiptStatus.RUNNING
    decisions.close()
    commands.close()
    ledger.close()


def test_operator_decisions_are_immutable_and_corruption_fails_reopen(tmp_path) -> None:
    database = tmp_path / "controls.db"
    ledger = TuiLedger(database)
    commands, request, context, claim = _accepted_claim(ledger)
    decisions = OperatorDecisionStore(ledger)
    decisions.hold(request, context, claim.claim_token, NOW + timedelta(seconds=2))

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with ledger.transaction() as connection:
            connection.execute("UPDATE operator_decisions SET reason = 'changed'")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with ledger.transaction() as connection:
            connection.execute("DELETE FROM operator_decisions")
    decisions.close()
    commands.close()
    ledger.close()

    with sqlite3.connect(database) as connection:
        triggers = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_schema WHERE name IN "
                "('operator_decisions_no_update', 'operator_decisions_no_delete')"
            )
        }
        connection.execute("DROP TRIGGER operator_decisions_no_update")
        connection.execute("UPDATE operator_decisions SET reason = 'changed'")
        connection.execute(triggers["operator_decisions_no_update"])

    with pytest.raises(LedgerCorruptionError, match="decision content"):
        TuiLedger(database)


def test_hold_replay_and_reopen_reject_nonstandard_success_receipt(tmp_path) -> None:
    database = tmp_path / "controls.db"
    ledger = TuiLedger(database)
    commands, request, context, claim = _accepted_claim(ledger)
    decisions = OperatorDecisionStore(ledger)
    decisions.hold(request, context, claim.claim_token, NOW + timedelta(seconds=2))

    with ledger.transaction() as connection:
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
        connection.execute(
            "UPDATE commands SET code = 'manual-intervention-required', "
            "safe_message = 'Inspect manually.' WHERE command_id = ?",
            (request.command_id,),
        )
        connection.execute(
            "UPDATE command_receipt_events SET code = 'manual-intervention-required', "
            "safe_message = 'Inspect manually.' WHERE command_id = ? "
            "AND status = 'completed'",
            (request.command_id,),
        )
        for statement in trigger_sql.values():
            connection.execute(statement)

    with pytest.raises(OperatorDecisionConflict, match="receipt"):
        decisions.hold(request, context, "fresh-token", NOW + timedelta(days=1))
    decisions.close()
    commands.close()
    ledger.close()

    with pytest.raises(LedgerCorruptionError, match="decision content"):
        TuiLedger(database)


def test_reopen_rejects_hold_bound_to_wrong_handler(tmp_path) -> None:
    database = tmp_path / "controls.db"
    ledger = TuiLedger(database)
    commands, request, context, claim = _accepted_claim(ledger)
    decisions = OperatorDecisionStore(ledger)
    decisions.hold(request, context, claim.claim_token, NOW + timedelta(seconds=2))
    decisions.close()
    commands.close()
    ledger.close()

    with sqlite3.connect(database) as connection:
        trigger_sql = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_schema WHERE name IN "
                "('commands_admission_immutable', 'commands_terminal_immutable')"
            )
        }
        for trigger_name in trigger_sql:
            connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.execute("UPDATE commands SET handler_key = 'other.handler'")
        for statement in trigger_sql.values():
            connection.execute(statement)

    with pytest.raises(LedgerCorruptionError, match="decision content"):
        TuiLedger(database)


def test_reopen_rejects_completed_hold_without_operator_decision(tmp_path) -> None:
    database = tmp_path / "controls.db"
    ledger = TuiLedger(database)
    commands, request, _context_value, claim = _accepted_claim(ledger)
    commands.finish(
        request.command_id,
        claim.claim_token,
        ReceiptStatus.COMPLETED,
        None,
        NOW + timedelta(seconds=2),
    )
    commands.close()
    ledger.close()

    with pytest.raises(LedgerCorruptionError, match="decision content"):
        TuiLedger(database)


def test_reopen_rejects_completed_hold_with_forged_handler_and_no_decision(
    tmp_path,
) -> None:
    database = tmp_path / "controls.db"
    ledger = TuiLedger(database)
    commands, request, _context_value, claim = _accepted_claim(ledger)
    commands.finish(
        request.command_id,
        claim.claim_token,
        ReceiptStatus.COMPLETED,
        None,
        NOW + timedelta(seconds=2),
    )
    commands.close()
    ledger.close()

    with sqlite3.connect(database) as connection:
        trigger_sql = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_schema WHERE name IN "
                "('commands_admission_immutable', 'commands_terminal_immutable')"
            )
        }
        for trigger_name in trigger_sql:
            connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.execute("UPDATE commands SET handler_key = 'other.handler'")
        for statement in trigger_sql.values():
            connection.execute(statement)

    with pytest.raises(LedgerCorruptionError, match="decision content"):
        TuiLedger(database)
