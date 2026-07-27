from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from typer.testing import CliRunner

from vesper.platform.cli import CliConfig, build_app


@dataclass
class FakeService:
    calls: list[tuple] = field(default_factory=list)

    def create_run(self, objective, workspace, repository_revision):
        self.calls.append(("create", objective, workspace, repository_revision))
        return {"run_id": "run-001", "status": "awaiting-approval"}

    def inspect_run(self, run_id):
        self.calls.append(("status", run_id))
        return {"run_id": run_id, "status": "interrupted"}

    def resume_run(self, run_id):
        self.calls.append(("resume", run_id))
        return {"run_id": run_id, "status": "completed"}

    def list_receipts(self, run_id):
        self.calls.append(("receipts", run_id))
        return {"run_id": run_id, "receipts": []}

    def list_evidence(self, run_id):
        self.calls.append(("evidence", run_id))
        return {"run_id": run_id, "evidence": []}

    def list_pending_approvals(self):
        self.calls.append(("approvals",))
        return {"pending": [{"run_id": "run-001", "status": "awaiting-approval"}]}

    def approve_run(self, run_id, checkpoint_id, operator_id, reason):
        self.calls.append(("approve", run_id, checkpoint_id, operator_id, reason))
        return {"run_id": run_id, "status": "awaiting-resume"}

    def reject_run(self, run_id, checkpoint_id, operator_id, reason):
        self.calls.append(("reject", run_id, checkpoint_id, operator_id, reason))
        return {"run_id": run_id, "status": "rejected"}

    def cancel_run(self, run_id, reason):
        self.calls.append(("cancel", run_id, reason))
        return {"run_id": run_id, "status": "cancelled"}


@pytest.fixture
def cli():
    service = FakeService()
    seen_configs: list[CliConfig] = []

    def factory(config):
        seen_configs.append(config)
        return service

    return CliRunner(), build_app(service_factory=factory), service, seen_configs


@pytest.mark.parametrize(
    ("arguments", "expected_call"),
    [
        (
            [
                "create",
                "--objective",
                "Build offline slice",
                "--workspace",
                ".",
                "--repository-revision",
                "abc123",
            ],
            ("create", "Build offline slice", ".", "abc123"),
        ),
        (["status", "run-001"], ("status", "run-001")),
        (["resume", "run-001"], ("resume", "run-001")),
        (["receipts", "run-001"], ("receipts", "run-001")),
        (["evidence", "run-001"], ("evidence", "run-001")),
        (["approvals"], ("approvals",)),
        (
            [
                "approve",
                "run-001",
                "--checkpoint-id",
                "cp-1",
                "--operator-id",
                "operator",
                "--reason",
                "Reviewed",
            ],
            ("approve", "run-001", "cp-1", "operator", "Reviewed"),
        ),
        (
            [
                "reject",
                "run-001",
                "--checkpoint-id",
                "cp-1",
                "--operator-id",
                "operator",
                "--reason",
                "Insufficient",
            ],
            ("reject", "run-001", "cp-1", "operator", "Insufficient"),
        ),
        (
            ["cancel", "run-001", "--reason", "Operator cancelled"],
            ("cancel", "run-001", "Operator cancelled"),
        ),
    ],
)
def test_cli_routes_explicit_commands_to_injected_service(cli, arguments, expected_call):
    runner, app, service, configs = cli

    result = runner.invoke(app, ["--json", *arguments])

    assert result.exit_code == 0, result.output
    assert service.calls == [expected_call]
    assert len(configs) == 1
    assert '"status"' in result.output or arguments[0] in {"receipts", "evidence", "approvals"}


def test_read_only_help_does_not_construct_service(cli):
    runner, app, service, configs = cli
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "create" in result.output
    assert "approve" in result.output
    assert "cancel" in result.output
    assert service.calls == []
    assert configs == []


@pytest.mark.parametrize("command", ("approve", "reject"))
def test_approval_actions_require_checkpoint_operator_and_reason(cli, command):
    runner, app, service, _ = cli
    result = runner.invoke(app, [command, "run-001"])

    assert result.exit_code == 2
    assert service.calls == []
