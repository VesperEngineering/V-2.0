from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from vesper.platform.persistence import PlatformPaths, open_persistence


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
    assert paths.evidence_root.is_dir()
    assert {path.name for path in paths.root.iterdir()} <= {
        "checkpoints.sqlite3",
        "store.sqlite3",
        "evidence",
    }
