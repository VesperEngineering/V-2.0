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
