"""Lightweight canonical local paths for the V20 platform."""

from __future__ import annotations

import os
from pathlib import Path


def default_platform_root() -> Path:
    """Return the one local Windows platform root without creating it."""

    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        raise RuntimeError("LOCALAPPDATA is unavailable")
    return (Path(local_appdata) / "V20" / "agent-platform").resolve()
