from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vesper.platform.cli import CliConfig, build_app


@dataclass
class FakeService:
    calls: list[tuple] = field(default_factory=list)

    def create_run(self, objective, workspace, repository_revision, acceptance_checks=None):
        self.calls.append(("create", objective, workspace, repository_revision, acceptance_checks))
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

    def list_active_runs(self):
        self.calls.append(("active",))
        return {"active": [{"run_id": "run-001", "status": "running"}]}

    def approve_run(self, run_id, checkpoint_id, operator_id, reason):
        self.calls.append(("approve", run_id, checkpoint_id, operator_id, reason))
        return {"run_id": run_id, "status": "awaiting-resume"}

    def reject_run(self, run_id, checkpoint_id, operator_id, reason):
        self.calls.append(("reject", run_id, checkpoint_id, operator_id, reason))
        return {"run_id": run_id, "status": "rejected"}

    def cancel_run(self, run_id, reason):
        self.calls.append(("cancel", run_id, reason))
        return {"run_id": run_id, "status": "cancelled"}

    def sync_knowledge(self):
        self.calls.append(("knowledge-sync",))
        return {"added": 1, "updated": 0, "unchanged": 0, "deleted": 0}

    def search_knowledge(self, query, role):
        self.calls.append(("knowledge-search", query, role))
        return {"query": query, "role": role, "results": []}

    def knowledge_status(self):
        self.calls.append(("knowledge-status",))
        return {"documents": 1, "memory": 0, "skill": 1}

    def agent_roster(self):
        self.calls.append(("agent-roster",))
        return {"count": 8, "agents": []}

    def run_agent(self, role, session_id, objective, revision, evidence, prior_date):
        self.calls.append(
            ("agent-run", role, session_id, objective, revision, evidence, prior_date)
        )
        return {"run_id": "agent-run-1", "role": role}

    def render_agent_digest(self, session_date):
        self.calls.append(("agent-digest", session_date))
        return {"session_date": session_date, "sha256": "a" * 64}

    def acknowledge_agent_digest(self, session_date, operator_id):
        self.calls.append(("agent-review", session_date, operator_id))
        return {"session_date": session_date, "acknowledged": True}

    def agent_gate_status(self, prior_session_date):
        self.calls.append(("agent-gate", prior_session_date))
        return {"prior_session_date": prior_session_date, "new_proposals_admitted": False}


def test_cli_exposes_manual_agent_controls_without_scheduler(cli):
    runner, app, service, _ = cli
    commands = (
        (["agent-roster"], ("agent-roster",)),
        (["agent-digest", "2026-08-01"], ("agent-digest", "2026-08-01")),
        (["agent-review", "2026-08-01", "operator"], ("agent-review", "2026-08-01", "operator")),
        (["agent-gate", "2026-08-01"], ("agent-gate", "2026-08-01")),
    )
    for arguments, expected in commands:
        result = runner.invoke(app, arguments)
        assert result.exit_code == 0, result.output
        assert service.calls.pop(0) == expected


def test_cli_routes_bounded_agent_run_json(cli):
    runner, app, service, _ = cli
    result = runner.invoke(
        app,
        [
            "agent-run",
            "--role",
            "v20-model-researcher",
            "--session-id",
            "s1",
            "--objective",
            "Inspect",
            "--repository-revision",
            "abc123",
            "--evidence-json",
            '{"artifact":{"available":true}}',
            "--prior-session-date",
            "2026-08-01",
        ],
    )
    assert result.exit_code == 0, result.output
    assert service.calls == [
        (
            "agent-run",
            "v20-model-researcher",
            "s1",
            "Inspect",
            "abc123",
            {"artifact": {"available": True}},
            "2026-08-01",
        )
    ]


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
                "--acceptance-check",
                "git-diff-check",
            ],
            ("create", "Build offline slice", ".", "abc123", ("git-diff-check",)),
        ),
        (["status", "run-001"], ("status", "run-001")),
        (["resume", "run-001"], ("resume", "run-001")),
        (["receipts", "run-001"], ("receipts", "run-001")),
        (["evidence", "run-001"], ("evidence", "run-001")),
        (["approvals"], ("approvals",)),
        (["active"], ("active",)),
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
        (["knowledge-sync"], ("knowledge-sync",)),
        (
            [
                "knowledge-search",
                "--query",
                "documentation marker",
                "--role",
                "v20-development",
            ],
            ("knowledge-search", "documentation marker", "v20-development"),
        ),
        (["knowledge-status"], ("knowledge-status",)),
    ],
)
def test_cli_routes_explicit_commands_to_injected_service(cli, arguments, expected_call):
    runner, app, service, configs = cli

    result = runner.invoke(app, ["--json", *arguments])

    assert result.exit_code == 0, result.output
    assert service.calls == [expected_call]
    assert len(configs) == 1
    assert '"status"' in result.output or arguments[0] in {
        "receipts",
        "evidence",
        "approvals",
        "active",
        "knowledge-sync",
        "knowledge-search",
        "knowledge-status",
    }


def test_read_only_help_does_not_construct_service(cli):
    runner, app, service, configs = cli
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "create" in result.output
    assert "approve" in result.output
    assert "cancel" in result.output
    assert "active" in result.output
    assert "knowledge-sync" in result.output
    assert "knowledge-search" in result.output
    assert "knowledge-status" in result.output
    assert service.calls == []
    assert configs == []


def test_cli_does_not_expose_host_mcp_configuration_flags(cli):
    runner, app, service, configs = cli

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "configured-mcp" not in result.output
    assert "confirm-no-mcp" not in result.output
    assert service.calls == []
    assert configs == []


def test_cli_passes_explicit_opencode_runtime_boundary_to_service(cli):
    runner, app, service, configs = cli

    result = runner.invoke(
        app,
        [
            "--runtime",
            "opencode",
            "--model",
            "openrouter/approved-model",
            "--credential-environment-key",
            "OPENROUTER_API_KEY",
            "--allow-repository-root-workspace",
            "--research-data-root",
            "D:/vesper/vesper_data/massive",
            "--knowledge-root",
            "knowledge",
            "status",
            "run-001",
        ],
    )

    assert result.exit_code == 0, result.output
    assert service.calls == [("status", "run-001")]
    assert configs[0].runtime == "opencode"
    assert configs[0].model == "openrouter/approved-model"
    assert configs[0].credential_environment_key == "OPENROUTER_API_KEY"
    assert configs[0].allow_repository_root_workspace is True
    assert configs[0].research_data_root == Path("D:/vesper/vesper_data/massive")
    assert configs[0].knowledge_root == Path("knowledge")


def test_default_state_and_evidence_paths_are_outside_the_current_repository(monkeypatch, tmp_path):
    local_app_data = tmp_path / "local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.chdir(tmp_path)
    service = FakeService()
    configs = []

    def factory(config):
        configs.append(config)
        return service

    runner = CliRunner()
    app = build_app(service_factory=factory)

    result = runner.invoke(
        app,
        [
            "create",
            "--objective",
            "Bounded task",
            "--workspace",
            ".",
            "--repository-revision",
            "abc123",
        ],
    )

    assert result.exit_code == 0, result.output
    assert service.calls
    assert configs[0].state_db.is_relative_to(local_app_data)
    assert configs[0].evidence_root.is_relative_to(local_app_data)
    assert configs[0].research_data_root == (
        Path(__file__).resolve().parents[2] / "vesper" / "data" / "massive"
    )
    assert configs[0].knowledge_root == Path("knowledge")


@pytest.mark.parametrize("command", ("approve", "reject"))
def test_approval_actions_require_checkpoint_operator_and_reason(cli, command):
    runner, app, service, _ = cli
    result = runner.invoke(app, [command, "run-001"])

    assert result.exit_code == 2
    assert service.calls == []
