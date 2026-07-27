from __future__ import annotations

import importlib
import os


def test_langgraph_runtime_forces_langsmith_tracing_off(monkeypatch):
    for name in (
        "LANGSMITH_TRACING",
        "LANGSMITH_TRACING_V2",
        "LANGCHAIN_TRACING_V2",
    ):
        monkeypatch.setenv(name, "true")
    monkeypatch.setenv("LANGGRAPH_CLI_NO_ANALYTICS", "0")
    import vesper.platform.runtime_env as runtime_env

    importlib.reload(runtime_env)

    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert os.environ["LANGSMITH_TRACING_V2"] == "false"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
    assert os.environ["LANGGRAPH_CLI_NO_ANALYTICS"] == "1"
    assert runtime_env.langsmith_tracing_disabled() is True
