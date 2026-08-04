from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

import pytest

from vesper.platform.tui.conversations import (
    ConversationConflict,
    ConversationCorruptionError,
    ConversationError,
    ConversationSequenceError,
    ConversationStateError,
    ConversationStore,
)


NOW = datetime(2026, 8, 4, 14, 0, tzinfo=timezone.utc)


class CompletionValidator:
    def __init__(self, *, approved: bool = True) -> None:
        self.approved = approved
        self.calls: list[tuple[str, str, str, str]] = []

    def validate_completion(
        self,
        *,
        validation_receipt_id: str,
        agent_id: str,
        message_id: str,
        raw_text_sha256: str,
    ) -> bool:
        self.calls.append((validation_receipt_id, agent_id, message_id, raw_text_sha256))
        return self.approved


class ReentrantCloseValidator:
    def __init__(self) -> None:
        self.store: ConversationStore | None = None

    def validate_completion(
        self,
        *,
        validation_receipt_id: str,
        agent_id: str,
        message_id: str,
        raw_text_sha256: str,
    ) -> bool:
        del validation_receipt_id, agent_id, message_id, raw_text_sha256
        assert self.store is not None
        self.store.close()
        return True


def _store(
    path: Path,
    *,
    validator: CompletionValidator | None = None,
) -> ConversationStore:
    message_ids = iter(
        (
            "message:human-risk",
            "message:agent-risk",
            "message:human-product",
            "message:agent-product",
        )
    )
    return ConversationStore(
        path,
        id_factory=lambda: next(message_ids),
        validator=CompletionValidator() if validator is None else validator,
    )


def _make_symlink(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unavailable: {error}")


def test_database_rejects_broken_leaf_symlink_without_creating_target(tmp_path: Path) -> None:
    target_root = tmp_path / "redirect-target"
    target_root.mkdir()
    target = target_root / "outside.sqlite3"
    link = tmp_path / "conversations.sqlite3"
    _make_symlink(link, target)

    with pytest.raises(ConversationError, match="safe regular file"):
        ConversationStore(link)

    assert not target.exists()


def test_database_rejects_symlinked_parent_without_creating_target(tmp_path: Path) -> None:
    target_root = tmp_path / "redirect-target"
    target_root.mkdir()
    linked_parent = tmp_path / "redirected-parent"
    _make_symlink(linked_parent, target_root, directory=True)

    with pytest.raises(ConversationError, match="safe regular file"):
        ConversationStore(linked_parent / "conversations.sqlite3")

    assert not (target_root / "conversations.sqlite3").exists()


def test_schema_with_matching_columns_but_removed_constraints_is_rejected(
    tmp_path: Path,
) -> None:
    database = tmp_path / "forged-schema.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE conversation_messages (
                message_sequence INTEGER,
                message_id TEXT,
                agent_id TEXT,
                role TEXT,
                created_at_utc TEXT
            );
            CREATE TABLE conversation_chunks (
                message_id TEXT,
                chunk_sequence INTEGER,
                text TEXT,
                token_count INTEGER,
                text_sha256 TEXT
            );
            CREATE TABLE conversation_terminals (
                message_id TEXT,
                status TEXT,
                occurred_at_utc TEXT,
                validation_receipt_id TEXT,
                raw_text_sha256 TEXT
            );
            CREATE TABLE conversation_summaries (
                summary_sequence INTEGER,
                summary_id TEXT,
                agent_id TEXT,
                objective TEXT,
                created_at_utc TEXT,
                context_sha256 TEXT
            );
            CREATE TABLE conversation_summary_messages (
                summary_id TEXT,
                message_id TEXT,
                message_position INTEGER
            );
            PRAGMA application_id = 1446134600;
            PRAGMA user_version = 1;
            """
        )

    with pytest.raises(ConversationCorruptionError, match="schema"):
        ConversationStore(database)


def test_threads_are_separate_and_roles_are_only_human_or_agent(tmp_path: Path) -> None:
    store = _store(tmp_path / "conversations.sqlite3")
    risk = store.start_message("v20-risk-review", "human", NOW)
    product = store.start_message("v20-product", "agent", NOW + timedelta(seconds=1))
    store.append_chunk(risk.message_id, 1, "Review portfolio risk.", token_count=4)
    store.append_chunk(product.message_id, 1, "Product status.", token_count=3)

    assert [message.text for message in store.history("v20-risk-review", 10, None)] == [
        "Review portfolio risk."
    ]
    assert [message.text for message in store.history("v20-product", 10, None)] == [
        "Product status."
    ]
    assert store.history("v20-risk-review", 10, None)[0].token_count == 4
    with pytest.raises(ValueError, match="role"):
        store.start_message("v20-risk-review", "system", NOW)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="approved V20 agent"):
        store.start_message("AAPL", "human", NOW)
    store.close()


def test_chunks_are_ordered_immutable_and_terminal_output_cannot_change(
    tmp_path: Path,
) -> None:
    validator = CompletionValidator()
    store = _store(tmp_path / "conversations.sqlite3", validator=validator)
    message = store.start_message("v20-risk-review", "agent", NOW)

    first = store.append_chunk(message.message_id, 1, "raw ", token_count=1)
    assert store.append_chunk(message.message_id, 1, "raw ", token_count=1) == first
    with pytest.raises(ConversationConflict, match="chunk"):
        store.append_chunk(message.message_id, 1, "changed", token_count=1)
    with pytest.raises(ConversationSequenceError, match="next chunk sequence is 2"):
        store.append_chunk(message.message_id, 3, "late", token_count=1)

    store.append_chunk(message.message_id, 2, "output", token_count=2)
    complete = store.complete(
        message.message_id,
        "validation:agent-output",
        NOW + timedelta(seconds=2),
    )
    assert complete.status == "complete"
    assert complete.text == "raw output"
    assert complete.token_count == 3
    assert validator.calls == [
        (
            "validation:agent-output",
            "v20-risk-review",
            message.message_id,
            hashlib.sha256(b"raw output").hexdigest(),
        )
    ]
    assert (
        store.complete(
            message.message_id,
            "validation:agent-output",
            NOW + timedelta(seconds=2),
        )
        == complete
    )
    assert len(validator.calls) == 1
    with pytest.raises(ConversationStateError, match="terminal"):
        store.append_chunk(message.message_id, 3, "mutation")
    with pytest.raises(ConversationStateError, match="already complete"):
        store.interrupt(message.message_id, NOW + timedelta(seconds=3))
    store.close()


def test_exact_chunk_replay_after_terminal_is_idempotent_but_conflicts_fail(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "conversations.sqlite3")
    message = store.start_message("v20-risk-review", "agent", NOW)
    store.append_chunk(message.message_id, 1, "finished", token_count=1)
    completed = store.complete(
        message.message_id,
        "validation:finished",
        NOW + timedelta(seconds=1),
    )

    assert store.append_chunk(message.message_id, 1, "finished", token_count=1) == completed
    with pytest.raises(ConversationConflict, match="chunk"):
        store.append_chunk(message.message_id, 1, "changed", token_count=1)
    with pytest.raises(ConversationStateError, match="terminal"):
        store.append_chunk(message.message_id, 2, "new", token_count=1)
    store.close()


def test_complete_fails_closed_without_authoritative_validator(tmp_path: Path) -> None:
    store = ConversationStore(
        tmp_path / "conversations.sqlite3",
        id_factory=lambda: "message:unvalidated",
    )
    message = store.start_message("v20-risk-review", "agent", NOW)
    store.append_chunk(message.message_id, 1, "unvalidated")

    with pytest.raises(ConversationStateError, match="validator unavailable"):
        store.complete(
            message.message_id,
            "validation:missing",
            NOW + timedelta(seconds=1),
        )
    assert store.history("v20-risk-review", 10, None)[0].status == "draft"
    store.close()


def test_complete_rejects_validator_that_does_not_bind_exact_raw_message(
    tmp_path: Path,
) -> None:
    validator = CompletionValidator(approved=False)
    store = _store(tmp_path / "conversations.sqlite3", validator=validator)
    message = store.start_message("v20-risk-review", "agent", NOW)
    store.append_chunk(message.message_id, 1, "exact raw text")

    with pytest.raises(ConversationStateError, match="binding rejected"):
        store.complete(
            message.message_id,
            "validation:mismatch",
            NOW + timedelta(seconds=1),
        )
    assert validator.calls == [
        (
            "validation:mismatch",
            "v20-risk-review",
            message.message_id,
            hashlib.sha256(b"exact raw text").hexdigest(),
        )
    ]
    assert store.history("v20-risk-review", 10, None)[0].status == "draft"
    store.close()


def test_completion_validator_cannot_close_store_inside_active_transaction(
    tmp_path: Path,
) -> None:
    validator = ReentrantCloseValidator()
    store = ConversationStore(
        tmp_path / "conversations.sqlite3",
        id_factory=lambda: "message:reentrant-close",
        validator=validator,
    )
    validator.store = store
    message = store.start_message("v20-risk-review", "agent", NOW)
    store.append_chunk(message.message_id, 1, "still durable")

    with pytest.raises(ConversationError, match="active transaction"):
        store.complete(
            message.message_id,
            "validation:reentrant-close",
            NOW + timedelta(seconds=1),
        )

    persisted = store.history("v20-risk-review", 10, None)[0]
    assert persisted.status == "draft"
    assert persisted.text == "still durable"
    store.close()


def test_concurrent_streams_are_serialized_across_threads(tmp_path: Path) -> None:
    message_ids = iter(("message:thread-risk", "message:thread-product"))
    store = ConversationStore(
        tmp_path / "conversations.sqlite3",
        id_factory=lambda: next(message_ids),
    )
    risk = store.start_message("v20-risk-review", "agent", NOW)
    product = store.start_message("v20-product", "agent", NOW)
    barrier = Barrier(3)

    def append(message_id: str, text: str) -> str:
        barrier.wait(timeout=5)
        return store.append_chunk(message_id, 1, text).text

    with ThreadPoolExecutor(max_workers=2) as pool:
        risk_result = pool.submit(append, risk.message_id, "risk stream")
        product_result = pool.submit(append, product.message_id, "product stream")
        barrier.wait(timeout=5)
        assert risk_result.result(timeout=5) == "risk stream"
        assert product_result.result(timeout=5) == "product stream"

    assert store.history("v20-risk-review", 10, None)[0].text == "risk stream"
    assert store.history("v20-product", 10, None)[0].text == "product stream"
    store.close()


def test_disconnect_interrupts_only_open_messages_for_selected_agent(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "conversations.sqlite3")
    risk_human = store.start_message("v20-risk-review", "human", NOW)
    risk_agent = store.start_message("v20-risk-review", "agent", NOW + timedelta(seconds=1))
    product = store.start_message("v20-product", "human", NOW + timedelta(seconds=2))
    store.append_chunk(risk_agent.message_id, 1, "partial")

    interrupted = store.interrupt_drafts("v20-risk-review", NOW + timedelta(seconds=3))

    assert {message.message_id for message in interrupted} == {
        risk_human.message_id,
        risk_agent.message_id,
    }
    assert all(message.status == "interrupted" for message in interrupted)
    assert store.history("v20-product", 10, None)[0].message_id == product.message_id
    assert store.history("v20-product", 10, None)[0].status == "draft"
    store.close()


def test_history_cursor_is_agent_bound_and_exclusive(tmp_path: Path) -> None:
    store = _store(tmp_path / "conversations.sqlite3")
    oldest = store.start_message("v20-risk-review", "human", NOW)
    newest = store.start_message("v20-risk-review", "agent", NOW + timedelta(seconds=1))
    other = store.start_message("v20-product", "human", NOW + timedelta(seconds=2))

    assert store.history("v20-risk-review", 1, None) == (newest,)
    assert store.history("v20-risk-review", 10, newest.message_id) == (oldest,)
    with pytest.raises(ValueError, match="cursor does not belong"):
        store.history("v20-risk-review", 10, other.message_id)
    store.close()


def test_export_history_preserves_exact_chunks_and_terminal_events(tmp_path: Path) -> None:
    store = _store(tmp_path / "conversations.sqlite3")
    human = store.start_message("v20-risk-review", "human", NOW)
    store.append_chunk(human.message_id, 1, "Review ", token_count=1)
    store.append_chunk(human.message_id, 2, "risk.", token_count=None)
    store.complete(human.message_id, "validation:human", NOW + timedelta(seconds=1))
    agent = store.start_message("v20-risk-review", "agent", NOW + timedelta(seconds=2))
    store.append_chunk(agent.message_id, 1, "Working", token_count=2)
    store.interrupt(agent.message_id, NOW + timedelta(seconds=3))

    page = store.export_history("v20-risk-review", 2, None)

    assert page.agent_id == "v20-risk-review"
    assert page.next_cursor is None
    assert [event.operation for event in page.events] == [
        "chunk",
        "chunk",
        "complete",
        "chunk",
        "interrupted",
    ]
    assert [event.message_id for event in page.events] == [
        human.message_id,
        human.message_id,
        human.message_id,
        agent.message_id,
        agent.message_id,
    ]
    assert [event.text for event in page.events] == ["Review ", "risk.", None, "Working", None]
    assert [event.token_count for event in page.events] == [1, None, None, 2, None]
    assert page.events[0].message_created_at_utc == NOW
    assert page.events[0].occurred_at_utc is None
    assert page.events[2].validation_receipt_id == "validation:human"
    assert page.events[2].raw_text_sha256 == hashlib.sha256(b"Review risk.").hexdigest()
    assert page.events[4].occurred_at_utc == NOW + timedelta(seconds=3)
    assert page.events[4].validation_receipt_id is None
    assert page.events[4].raw_text_sha256 is None
    store.close()


def test_export_history_pages_newest_messages_but_emits_each_page_chronologically(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "conversations.sqlite3")
    oldest = store.start_message("v20-risk-review", "human", NOW)
    middle = store.start_message("v20-risk-review", "agent", NOW + timedelta(seconds=1))
    newest = store.start_message("v20-risk-review", "human", NOW + timedelta(seconds=2))
    store.append_chunk(oldest.message_id, 1, "oldest")
    store.append_chunk(middle.message_id, 1, "middle")
    store.append_chunk(newest.message_id, 1, "newest")

    first = store.export_history("v20-risk-review", 2, None)
    second = store.export_history("v20-risk-review", 2, first.next_cursor)

    assert [(event.message_id, event.text) for event in first.events] == [
        (middle.message_id, "middle"),
        (newest.message_id, "newest"),
    ]
    assert first.next_cursor == middle.message_id
    assert [(event.message_id, event.text) for event in second.events] == [
        (oldest.message_id, "oldest")
    ]
    assert second.next_cursor is None
    store.close()


def test_export_history_replay_has_stable_unique_event_ids(tmp_path: Path) -> None:
    store = _store(tmp_path / "conversations.sqlite3")
    message = store.start_message("v20-risk-review", "agent", NOW)
    store.append_chunk(message.message_id, 1, "one")
    store.append_chunk(message.message_id, 2, "two")
    store.complete(message.message_id, "validation:stable", NOW + timedelta(seconds=1))

    first = store.export_history("v20-risk-review", 1, None)
    second = store.export_history("v20-risk-review", 1, None)

    assert first == second
    event_ids = [event.event_id for event in first.events]
    assert len(event_ids) == len(set(event_ids)) == 3
    assert all(event_id.startswith("chat:") for event_id in event_ids)
    store.close()


def test_export_history_fails_closed_on_corrupt_stored_chunk(tmp_path: Path) -> None:
    database = tmp_path / "conversations.sqlite3"
    store = _store(database)
    message = store.start_message("v20-risk-review", "agent", NOW)
    store.append_chunk(message.message_id, 1, "trusted")
    store.close()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE conversation_chunks SET text = 'tampered' WHERE message_id = ?",
            (message.message_id,),
        )

    reopened = ConversationStore(database)
    with pytest.raises(ConversationCorruptionError, match="stored conversation"):
        reopened.export_history("v20-risk-review", 1, None)
    reopened.close()


def test_export_history_reports_stored_chunk_outside_wire_limit_as_corruption(
    tmp_path: Path,
) -> None:
    database = tmp_path / "conversations.sqlite3"
    store = _store(database)
    message = store.start_message("v20-risk-review", "agent", NOW)
    store.append_chunk(message.message_id, 1, "valid")
    store.close()
    oversized = "x" * (64 * 1024 + 1)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE conversation_chunks SET text = ?, text_sha256 = ?
            WHERE message_id = ?
            """,
            (
                oversized,
                hashlib.sha256(oversized.encode()).hexdigest(),
                message.message_id,
            ),
        )

    reopened = ConversationStore(database)
    with pytest.raises(ConversationCorruptionError, match="wire event"):
        reopened.export_history("v20-risk-review", 1, None)
    reopened.close()


def test_export_history_fails_closed_instead_of_splitting_one_message(
    tmp_path: Path,
) -> None:
    store = ConversationStore(
        tmp_path / "conversations.sqlite3",
        id_factory=lambda: "message:too-many-events",
    )
    message = store.start_message("v20-risk-review", "agent", NOW)
    for sequence in range(1, 130):
        store.append_chunk(message.message_id, sequence, str(sequence))

    with pytest.raises(ConversationStateError, match="history page exceeds"):
        store.export_history("v20-risk-review", 1, None)
    store.close()


def test_export_history_can_represent_one_four_mib_message(tmp_path: Path) -> None:
    store = ConversationStore(
        tmp_path / "conversations.sqlite3",
        id_factory=lambda: "message:max-size",
        validator=CompletionValidator(),
    )
    message = store.start_message("v20-risk-review", "agent", NOW)
    chunk = "x" * (64 * 1024)
    for sequence in range(1, 65):
        store.append_chunk(message.message_id, sequence, chunk)
    store.complete(message.message_id, "validation:max-size", NOW + timedelta(seconds=1))

    page = store.export_history("v20-risk-review", 1, None)

    assert len(page.events) == 65
    assert page.events[0].text == chunk
    assert page.events[-1].operation == "complete"
    store.close()


def test_terminal_time_within_creation_second_uses_time_not_text_order(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "conversations.sqlite3")
    message = store.start_message("v20-risk-review", "agent", NOW)

    completed = store.complete(
        message.message_id,
        "validation:within-second",
        NOW + timedelta(milliseconds=100),
    )

    assert completed.status == "complete"
    store.close()


def test_schema_has_raw_chunks_and_no_chain_of_thought_fields(tmp_path: Path) -> None:
    database = tmp_path / "conversations.sqlite3"
    store = _store(database)
    message = store.start_message("v20-risk-review", "agent", NOW)
    store.append_chunk(message.message_id, 1, "raw text survives")
    store.close()

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")
        }
        assert "conversation_chunks" in tables
        raw = connection.execute(
            "SELECT text FROM conversation_chunks WHERE message_id = ?",
            (message.message_id,),
        ).fetchone()
        columns = " ".join(
            row[1] for table in tables for row in connection.execute(f"PRAGMA table_info({table})")
        ).casefold()
    assert raw == ("raw text survives",)
    assert "chain_of_thought" not in columns
    assert "reasoning" not in columns
    assert "thought" not in columns
