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

    def start_financial_research(
        self,
        event_type,
        objective,
        symbols,
        start_date,
        end_date,
        observed_metric,
        threshold,
    ):
        self.calls.append(
            (
                "financial-research-start",
                event_type,
                objective,
                symbols,
                start_date,
                end_date,
                observed_metric,
                threshold,
            )
        )
        return {"run_id": "financial-001", "status": "completed"}

    def inspect_financial_research(self, run_id):
        self.calls.append(("financial-research-status", run_id))
        return {"run_id": run_id, "status": "completed"}

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

    def observe_knowledge(self, concept_key, title, kind, scope, summary, source_ref, explicit):
        self.calls.append(
            ("knowledge-observe", concept_key, title, kind, scope, summary, source_ref, explicit)
        )
        return {"status": "candidate-created", "concept_key": concept_key}

    def knowledge_compaction_plan(self, target_lines):
        self.calls.append(("knowledge-compaction-plan", target_lines))
        return {"proposal_id": "compaction-001", "entries": []}

    def knowledge_reactivation_plan(self):
        self.calls.append(("knowledge-reactivation-plan",))
        return {"proposal_id": "reactivation-001", "entries": []}


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
        (
            [
                "financial-research-start",
                "--event-type",
                "direct-request",
                "--objective",
                "Check coverage",
                "--symbol",
                "SPY",
                "--symbol",
                "QQQ",
                "--start-date",
                "2026-01-01",
                "--end-date",
                "2026-01-31",
            ],
            (
                "financial-research-start",
                "direct-request",
                "Check coverage",
                ("SPY", "QQQ"),
                "2026-01-01",
                "2026-01-31",
                None,
                None,
            ),
        ),
        (
            ["financial-research-status", "financial-001"],
            ("financial-research-status", "financial-001"),
        ),
        (
            [
                "financial-research-start",
                "--event-type",
                "weak-model-result",
                "--objective",
                "Check weak coverage",
                "--symbol",
                "SPY",
                "--start-date",
                "2026-01-01",
                "--end-date",
                "2026-01-31",
                "--observed-metric",
                "0.01",
                "--threshold",
                "0.03",
            ],
            (
                "financial-research-start",
                "weak-model-result",
                "Check weak coverage",
                ("SPY",),
                "2026-01-01",
                "2026-01-31",
                0.01,
                0.03,
            ),
        ),
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
        (
            [
                "knowledge-observe",
                "--concept-key",
                "brief-writing",
                "--title",
                "Prefer brief writing",
                "--kind",
                "memory",
                "--scope",
                "shared",
                "--summary",
                "Prefer brief, direct wording.",
                "--source-ref",
                "codex-task-123",
                "--explicit",
            ],
            (
                "knowledge-observe",
                "brief-writing",
                "Prefer brief writing",
                "memory",
                "shared",
                "Prefer brief, direct wording.",
                "codex-task-123",
                True,
            ),
        ),
        (
            ["knowledge-compaction-plan", "--target-lines", "2800"],
            ("knowledge-compaction-plan", 2800),
        ),
        (["knowledge-compaction-plan"], ("knowledge-compaction-plan", 3000)),
        (["knowledge-reactivation-plan"], ("knowledge-reactivation-plan",)),
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
        "knowledge-observe",
        "knowledge-compaction-plan",
        "knowledge-reactivation-plan",
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
    assert "knowledge-observe" in result.output
    assert "knowledge-compaction-plan" in result.output
    assert "knowledge-reactivation-plan" in result.output
    assert service.calls == []
    assert configs == []


def test_cli_exposes_only_start_and_status_for_phase_one(cli):
    runner, app, service, configs = cli

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "financial-research-start" in result.stdout
    assert "financial-research-status" in result.stdout
    assert "financial-research-promote" not in result.stdout
    assert service.calls == []
    assert configs == []


@pytest.mark.parametrize(
    "arguments",
    (
        (
            "financial-research-start",
            "--event-type",
            "direct-request",
            "--objective",
            "Invalid metrics",
            "--symbol",
            "SPY",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
            "--observed-metric",
            "0.01",
            "--threshold",
            "0.03",
        ),
        (
            "financial-research-start",
            "--event-type",
            "weak-model-result",
            "--objective",
            "Missing metrics",
            "--symbol",
            "SPY",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
        ),
        (
            "financial-research-start",
            "--event-type",
            "unsupported",
            "--objective",
            "Unsupported event",
            "--symbol",
            "SPY",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
        ),
        (
            "financial-research-start",
            "--event-type",
            "direct-request",
            "--objective",
            "Reversed dates",
            "--symbol",
            "SPY",
            "--start-date",
            "2026-02-01",
            "--end-date",
            "2026-01-31",
        ),
        (
            "financial-research-start",
            "--event-type",
            "direct-request",
            "--objective",
            "Invalid date",
            "--symbol",
            "SPY",
            "--start-date",
            "2026-1-01",
            "--end-date",
            "2026-01-31",
        ),
    ),
)
def test_cli_rejects_invalid_financial_research_before_service(cli, arguments):
    runner, app, service, configs = cli

    result = runner.invoke(app, arguments)

    assert result.exit_code == 2
    assert service.calls == []
    assert configs == []


@pytest.mark.parametrize(
    ("arguments", "expected_phrase"),
    (
        (["knowledge-observe", "--help"], "candidate only"),
        (["knowledge-compaction-plan", "--help"], "proposal only"),
        (["knowledge-reactivation-plan", "--help"], "proposal only"),
    ),
)
def test_knowledge_lifecycle_command_help_does_not_construct_service(
    cli, arguments, expected_phrase
):
    runner, app, service, configs = cli

    result = runner.invoke(app, arguments)

    assert result.exit_code == 0
    assert expected_phrase in result.output
    assert "cannot approve or move knowledge" in " ".join(result.output.split())
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
