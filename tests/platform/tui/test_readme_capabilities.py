from __future__ import annotations

import re
from pathlib import Path

from vesper.platform.tui.command_contracts import COMMAND_SPECS
from vesper.platform.tui.command_ports import DISABLED_COMMAND_REASONS


README = Path("TUI testing/ratatui-console/README.md")
ROW = re.compile(
    r"^\| `(?P<command>[^`]+)` \| (?P<confirmation>[^|]+?) \| "
    r"(?P<state>[^|]+?) \| (?P<reason>.+) \|$"
)
CONDITIONAL = {
    "note.add",
    "alert.dismiss",
    "layout.reset",
    "approval.approve",
    "approval.hold",
    "approval.reject",
    "agent.enqueue",
}


def test_readme_lists_every_command_in_catalog_order_with_current_truth() -> None:
    rows = []
    for line in README.read_text(encoding="utf-8").splitlines():
        match = ROW.fullmatch(line)
        if match is not None:
            rows.append(match.groupdict())

    assert [row["command"] for row in rows] == [spec.command_type for spec in COMMAND_SPECS]
    assert len({row["command"] for row in rows}) == 31
    for row, spec in zip(rows, COMMAND_SPECS, strict=True):
        assert row["confirmation"] == spec.confirmation_level
        if row["command"] in CONDITIONAL:
            assert row["state"] == "Conditional"
            assert row["reason"].strip()
        else:
            assert row["state"] == "Disabled"
            assert row["reason"] == DISABLED_COMMAND_REASONS[row["command"]]
