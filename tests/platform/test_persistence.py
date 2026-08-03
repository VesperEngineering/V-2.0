from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import InvalidNamespaceError

from vesper.platform.persistence import AtomicCreatePlan, PlatformPaths, open_persistence


class CounterState(TypedDict):
    count: int


def counter_graph(checkpointer):
    builder = StateGraph(CounterState)
    builder.add_node("increment", lambda state: {"count": state["count"] + 1})
    builder.add_edge(START, "increment")
    builder.add_edge("increment", END)
    return builder.compile(checkpointer=checkpointer)


def test_sqlite_checkpoint_survives_close_and_reopen(tmp_path):
    paths = PlatformPaths.below(tmp_path)
    config = {"configurable": {"thread_id": "thread-001"}}

    with open_persistence(paths) as persistence:
        graph = counter_graph(persistence.checkpointer)
        assert graph.invoke({"count": 0}, config) == {"count": 1}
        checkpoint = graph.get_state(config)
        assert checkpoint.values["count"] == 1

    with open_persistence(paths) as reopened:
        graph = counter_graph(reopened.checkpointer)
        recovered = graph.get_state(config)

    assert recovered.values["count"] == 1
    assert recovered.config["configurable"]["thread_id"] == "thread-001"


def test_sqlite_store_survives_close_and_reopen(tmp_path):
    paths = PlatformPaths.below(tmp_path)
    namespace = ("profiles", "v20-development", "development-episodes")

    with open_persistence(paths) as persistence:
        persistence.store.put(namespace, "memory-001", {"content": "persisted"})
        assert persistence.store.get(namespace, "memory-001") == {"content": "persisted"}

    with open_persistence(paths) as reopened:
        assert reopened.store.get(namespace, "memory-001") == {"content": "persisted"}
        assert reopened.store.search(namespace) == ({"content": "persisted"},)


def test_store_duplicate_key_is_deterministic_last_write(tmp_path):
    paths = PlatformPaths.below(tmp_path)
    namespace = ("shared", "repository-facts")
    with open_persistence(paths) as persistence:
        persistence.store.put(namespace, "key", {"version": 1})
        persistence.store.put(namespace, "key", {"version": 2})

        assert persistence.store.get(namespace, "key") == {"version": 2}
        assert persistence.store.search(namespace) == ({"version": 2},)


def test_store_serializes_concurrent_writes_on_one_connection(tmp_path):
    paths = PlatformPaths.below(tmp_path)
    namespace = ("programs", "task-001", "state")
    with open_persistence(paths) as persistence:

        def put(index: int):
            persistence.store.put(namespace, f"key-{index:02}", {"index": index})

        with ThreadPoolExecutor(max_workers=4) as executor:
            tuple(executor.map(put, range(20)))

        values = persistence.store.search(namespace, limit=25)

    assert {value["index"] for value in values} == set(range(20))


def test_persistence_creates_only_explicit_local_paths(tmp_path):
    paths = PlatformPaths.below(tmp_path / "platform")

    with open_persistence(paths):
        pass

    assert paths.checkpoint_db.is_file()
    assert paths.store_db.is_file()
    assert paths.knowledge_index_db.is_file()
    assert paths.evidence_root.is_dir()
    assert {path.name for path in paths.root.iterdir()} <= {
        "checkpoints.sqlite3",
        "knowledge-index.sqlite3",
        "store.sqlite3",
        "evidence",
    }


def _install_deferred_store_failure(connection, trigger_operation: str, prefix: str) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("CREATE TABLE commit_parent (id INTEGER PRIMARY KEY)")
    connection.execute(
        "CREATE TABLE commit_child ("
        "parent_id INTEGER REFERENCES commit_parent(id) DEFERRABLE INITIALLY DEFERRED)"
    )
    connection.execute(
        f"CREATE TRIGGER reject_store_commit AFTER {trigger_operation} ON store "
        f"WHEN NEW.prefix = '{prefix}' BEGIN "
        "INSERT INTO commit_child(parent_id) VALUES (1); END"
    )


def test_atomic_create_rolls_back_when_commit_fails(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        connection = persistence.langgraph_store.conn
        namespace = ("atomic", "create")
        _install_deferred_store_failure(connection, "INSERT", ".".join(namespace))

        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            persistence.store.atomic_create(
                namespace,
                "item",
                lambda _records, _existing: AtomicCreatePlan({"version": 1}),
            )

        assert connection.in_transaction is False
        assert persistence.store.get(namespace, "item") is None
        connection.execute("DROP TRIGGER reject_store_commit")
        stored, created = persistence.store.atomic_create(
            namespace,
            "item",
            lambda _records, _existing: AtomicCreatePlan({"version": 1}),
        )
        assert (stored, created) == ({"version": 1}, True)


def test_atomic_replace_rolls_back_when_commit_fails(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        connection = persistence.langgraph_store.conn
        namespace = ("atomic", "replace")
        persistence.store.put(namespace, "item", {"version": 1})
        _install_deferred_store_failure(connection, "UPDATE", ".".join(namespace))

        def replace(_records):
            return "item", {"version": 2}

        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            persistence.store.atomic_replace(namespace, replace)

        assert connection.in_transaction is False
        assert persistence.store.get(namespace, "item") == {"version": 1}
        connection.execute("DROP TRIGGER reject_store_commit")
        assert persistence.store.atomic_replace(namespace, replace) == {"version": 2}


@pytest.mark.parametrize(
    "operation",
    ("search_exact_records", "scan_subtree_records", "atomic_replace", "atomic_create"),
)
def test_direct_sql_store_operations_preserve_namespace_validation(tmp_path, operation):
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        namespace = ("invalid.label",)

        with pytest.raises(InvalidNamespaceError, match="cannot contain periods"):
            if operation == "atomic_replace":
                persistence.store.atomic_replace(
                    namespace,
                    lambda _records: ("item", {"version": 2}),
                )
            elif operation == "atomic_create":
                persistence.store.atomic_create(
                    namespace,
                    "item",
                    lambda _records, _existing: AtomicCreatePlan({"version": 1}),
                )
            else:
                getattr(persistence.store, operation)(namespace)

        assert persistence.langgraph_store.conn.in_transaction is False
