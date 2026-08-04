import importlib
import importlib.metadata
import tomllib
from pathlib import Path

import pytest


def test_tui_windows_transport_is_pinned() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = tuple(project["project"]["dependencies"])
    assert "pywin32==312; sys_platform == 'win32'" in dependencies


def test_tui_notification_dependencies_are_windows_only() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = set(project["project"]["dependencies"])
    required = {
        "winrt-runtime==3.2.1; sys_platform == 'win32'",
        "winrt-Windows.Data.Xml.Dom==3.2.1; sys_platform == 'win32'",
        "winrt-Windows.UI.Notifications==3.2.1; sys_platform == 'win32'",
    }
    assert required.issubset(dependencies)


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
