"""Fail-closed environment policy for local LangGraph execution."""

from __future__ import annotations

import os


def enforce_offline_runtime_environment() -> None:
    """Disable LangSmith tracing before any LangGraph runtime import."""
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGSMITH_TRACING_V2"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGGRAPH_CLI_NO_ANALYTICS"] = "1"


def langsmith_tracing_disabled() -> bool:
    return os.environ.get("LANGSMITH_TRACING", "").lower() == "false"


enforce_offline_runtime_environment()
