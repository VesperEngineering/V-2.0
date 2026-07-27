import importlib
import importlib.metadata

import pytest


@pytest.mark.parametrize(
    ("distribution", "module"),
    [
        ("langgraph", "langgraph.graph"),
        ("langgraph-checkpoint-sqlite", "langgraph.checkpoint.sqlite"),
        ("langgraph-checkpoint-sqlite", "langgraph.store.sqlite"),
        ("openai-codex", "openai_codex"),
        ("pydantic", "pydantic"),
        ("typer", "typer"),
    ],
)
def test_platform_dependencies_expose_the_required_public_modules(distribution, module):
    assert importlib.metadata.version(distribution)
    assert importlib.import_module(module)


def test_platform_dependencies_expose_required_public_types():
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import StateGraph
    from langgraph.store.sqlite import SqliteStore
    from openai_codex import Codex, Sandbox
    from pydantic import BaseModel
    from typer import Typer

    assert all((SqliteSaver, SqliteStore, StateGraph, Codex, Sandbox, BaseModel, Typer))
