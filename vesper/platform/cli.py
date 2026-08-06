"""Side-effect-free Typer control surface for the native platform."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol

import typer

_DEFAULT_RESEARCH_DATA_ROOT = Path(__file__).resolve().parents[2] / "vesper" / "data" / "massive"


@dataclass(frozen=True, slots=True)
class CliConfig:
    state_db: Path
    evidence_root: Path
    profiles_root: Path
    runtime: str = "docker-codex"
    model: str | None = None
    credential_environment_key: str | None = None
    allow_repository_root_workspace: bool = False
    research_data_root: Path = _DEFAULT_RESEARCH_DATA_ROOT
    knowledge_root: Path = Path("knowledge")


class PlatformService(Protocol):
    def chat(
        self,
        *,
        role: str,
        model: str,
        workspace: str,
        skills: tuple[str, ...],
        tools: tuple[str, ...] | None,
        allow_write: bool,
        session_id: str,
        json_output: bool,
    ): ...

    def create_run(
        self,
        objective: str,
        workspace: str,
        repository_revision: str,
        acceptance_checks: tuple[str, ...] | None = None,
    ): ...

    def inspect_run(self, run_id: str): ...

    def resume_run(self, run_id: str): ...

    def list_receipts(self, run_id: str): ...

    def list_evidence(self, run_id: str): ...

    def list_pending_approvals(self): ...

    def list_active_runs(self): ...

    def approve_run(self, run_id: str, checkpoint_id: str, operator_id: str, reason: str): ...

    def reject_run(self, run_id: str, checkpoint_id: str, operator_id: str, reason: str): ...

    def cancel_run(self, run_id: str, reason: str): ...

    def sync_knowledge(self): ...

    def search_knowledge(self, query: str, role: str): ...

    def knowledge_status(self): ...

    def knowledge_budget(self): ...

    def session_status(self): ...

    def run_dream(self, dry_run: bool = False): ...

    def working_memory_status(self, agent_id: str): ...

    def curate_working_memory(self, agent_id: str, candidates_json: str): ...

    def agent_roster(self): ...

    def run_agent(
        self,
        role: str,
        session_id: str,
        objective: str,
        repository_revision: str,
        evidence: dict[str, object],
        prior_session_date: str,
    ): ...

    def render_agent_digest(self, session_date: str): ...

    def acknowledge_agent_digest(self, session_date: str, operator_id: str): ...

    def agent_gate_status(self, prior_session_date: str): ...

    def enqueue_agent_work(self, role: str, session_id: str, objective: str, priority: int): ...

    def list_agent_work(self): ...

    def run_next_agent_work(
        self,
        worker_id: str,
        repository_revision: str,
        evidence: dict[str, object],
        prior_session_date: str,
    ): ...


class PlatformRuntimeUnavailable(RuntimeError):
    """A requested platform capability has no configured local runtime."""


def _default_platform_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = tempfile.gettempdir()
    return Path(base) / "V20" / "agent-platform"


@dataclass(frozen=True, slots=True)
class _Context:
    config: CliConfig
    json_output: bool
    service_factory: Callable[[CliConfig], PlatformService]


def _default_service_factory(config: CliConfig) -> PlatformService:
    from .persistence import PlatformPaths
    from .service import LocalPlatformService

    state_db = config.state_db.resolve()
    paths = PlatformPaths(
        root=state_db.parent,
        checkpoint_db=state_db,
        store_db=state_db.parent / "store.sqlite3",
        knowledge_index_db=state_db.parent / "knowledge-index.sqlite3",
        evidence_root=config.evidence_root.resolve(),
    )
    return LocalPlatformService(
        paths,
        profiles_root=config.profiles_root,
        specialist_runtime=config.runtime,
        opencode_model=config.model,
        opencode_credential_environment_key=config.credential_environment_key,
        allow_repository_root_workspace=config.allow_repository_root_workspace,
        knowledge_root=config.knowledge_root,
        research_data_root=config.research_data_root,
    )


def _emit(value: object, *, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(value, indent=2, sort_keys=True, default=str))
        return
    if isinstance(value, Mapping):
        run_id = value.get("run_id")
        status = value.get("status")
        if run_id is not None:
            typer.echo(f"run: {run_id}")
        if status is not None:
            typer.echo(f"status: {status}")
        for key, item in value.items():
            if key not in {"run_id", "status"}:
                typer.echo(f"{key}: {json.dumps(item, default=str)}")
        return
    typer.echo(str(value))


def _call(context: typer.Context, method: str, *args) -> None:
    settings: _Context = context.obj
    try:
        service = settings.service_factory(settings.config)
        result = getattr(service, method)(*args)
    except RuntimeError as exc:
        typer.echo(f"platform unavailable: {exc}", err=True)
        raise typer.Exit(code=4) from exc
    _emit(result, json_output=settings.json_output)


def _chat_call(context: typer.Context, **kwargs) -> None:
    settings: _Context = context.obj
    try:
        service = settings.service_factory(settings.config)
        service.chat(json_output=settings.json_output, **kwargs)
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"platform unavailable: {exc}", err=True)
        raise typer.Exit(code=4) from exc


def build_app(
    *,
    service_factory: Callable[[CliConfig], PlatformService] = _default_service_factory,
) -> typer.Typer:
    app = typer.Typer(
        name="vesper-agent",
        help="Inspect and control V20 native platform runs.",
        no_args_is_help=True,
    )

    @app.callback()
    def configure(
        context: typer.Context,
        state_db: Path = typer.Option(
            _default_platform_root() / "checkpoints.sqlite3",
            "--state-db",
            help="Local SQLite checkpoint database; opened only by a command.",
        ),
        evidence_root: Path = typer.Option(
            _default_platform_root() / "evidence",
            "--evidence-root",
            help="Local evidence root; opened only by a command.",
        ),
        profiles_root: Path = typer.Option(
            Path("profiles/native"),
            "--profiles-root",
            help="Native profile catalog.",
        ),
        runtime: str = typer.Option(
            "docker-codex",
            "--runtime",
            help="Specialist runtime: ollama-qwen, docker-codex, or opencode.",
        ),
        model: str | None = typer.Option(
            None,
            "--model",
            help="Exact provider/model required by the OpenCode runtime.",
        ),
        credential_environment_key: str | None = typer.Option(
            None,
            "--credential-environment-key",
            help="Environment variable name for the selected OpenCode provider credential.",
        ),
        allow_repository_root_workspace: bool = typer.Option(
            False,
            "--allow-repository-root-workspace",
            help="Allow OpenCode to work across a clean disposable clone root.",
        ),
        research_data_root: Path = typer.Option(
            _DEFAULT_RESEARCH_DATA_ROOT,
            "--research-data-root",
            help="Controller-owned read-only Massive data root.",
        ),
        knowledge_root: Path = typer.Option(
            Path("knowledge"),
            "--knowledge-root",
            help="Dedicated repository-owned Obsidian knowledge vault.",
        ),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        context.obj = _Context(
            config=CliConfig(
                state_db,
                evidence_root,
                profiles_root,
                runtime,
                model,
                credential_environment_key,
                allow_repository_root_workspace,
                research_data_root,
                knowledge_root,
            ),
            json_output=json_output,
            service_factory=service_factory,
        )

    @app.command("create")
    def create_run(
        context: typer.Context,
        objective: str = typer.Option(..., "--objective", help="Bounded task objective."),
        workspace: str = typer.Option(
            ..., "--workspace", help="Authorized subdirectory in a disposable standalone clone."
        ),
        repository_revision: str = typer.Option(
            ..., "--repository-revision", help="Revision the request is bound to."
        ),
        acceptance_check: list[str] | None = typer.Option(
            None,
            "--acceptance-check",
            help="Allowlisted deterministic check; repeat for multiple checks.",
        ),
    ) -> None:
        """Create a run and execute until a durable stop or interrupt."""
        checks = None if not acceptance_check else tuple(acceptance_check)
        _call(context, "create_run", objective, workspace, repository_revision, checks)

    @app.command("chat")
    def chat(
        context: typer.Context,
        role: str = typer.Option("v20-development", "--role", help="Bounded chat role."),
        model: str = typer.Option("qwen:64k", "--model", help="Pinned local Qwen model."),
        workspace: str = typer.Option("TUI testing", "--workspace", help="Narrow repository-relative workspace."),
        skill: list[str] | None = typer.Option(None, "--skill", help="Approved knowledge/skills file; repeatable."),
        tool: list[str] | None = typer.Option(None, "--tool", help="Controller tool; repeatable."),
        allow_write: bool = typer.Option(False, "--allow-write", help="Enable guarded writes and focused tests."),
        session_id: str | None = typer.Option(None, "--session-id", help="Redacted transcript identity."),
    ) -> None:
        """Chat with local qwen:64k through V20 controller tools."""
        _chat_call(
            context,
            role=role,
            model=model,
            workspace=workspace,
            skills=tuple(skill or ()),
            tools=None if tool is None else tuple(tool),
            allow_write=allow_write,
            session_id=session_id or f"interactive-{uuid.uuid4().hex[:12]}",
        )

    @app.command("status")
    def inspect_run(context: typer.Context, run_id: str) -> None:
        """Inspect status without initializing a specialist."""
        _call(context, "inspect_run", run_id)

    @app.command("resume")
    def resume_run(context: typer.Context, run_id: str) -> None:
        """Resume a persisted run from its current checkpoint."""
        _call(context, "resume_run", run_id)

    @app.command("receipts")
    def list_receipts(context: typer.Context, run_id: str) -> None:
        """View structured specialist and controller receipts."""
        _call(context, "list_receipts", run_id)

    @app.command("evidence")
    def list_evidence(context: typer.Context, run_id: str) -> None:
        """View hash-bound evidence references."""
        _call(context, "list_evidence", run_id)

    @app.command("approvals")
    def list_approvals(context: typer.Context) -> None:
        """List runs awaiting explicit operator approval."""
        _call(context, "list_pending_approvals")

    @app.command("active")
    def list_active_runs(context: typer.Context) -> None:
        """List running or crash-interrupted runs and active runtime metadata."""
        _call(context, "list_active_runs")

    @app.command("agent-roster")
    def agent_roster(context: typer.Context) -> None:
        """List all eight roles and their current runtime route."""
        _call(context, "agent_roster")

    @app.command("agent-run")
    def run_agent(
        context: typer.Context,
        role: str = typer.Option(..., "--role"),
        session_id: str = typer.Option(..., "--session-id"),
        objective: str = typer.Option(..., "--objective"),
        repository_revision: str = typer.Option(..., "--repository-revision"),
        evidence_json: str = typer.Option("{}", "--evidence-json"),
        prior_session_date: str = typer.Option(..., "--prior-session-date"),
    ) -> None:
        """Run one bounded quant agent through local qwen:64k; no scheduler."""
        try:
            evidence = json.loads(evidence_json)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter("evidence-json must be valid JSON") from exc
        if not isinstance(evidence, dict):
            raise typer.BadParameter("evidence-json must be a JSON object")
        _call(
            context,
            "run_agent",
            role,
            session_id,
            objective,
            repository_revision,
            evidence,
            prior_session_date,
        )

    @app.command("agent-digest")
    def render_agent_digest(context: typer.Context, session_date: str) -> None:
        """Render the immutable eight-role daily review digest."""
        _call(context, "render_agent_digest", session_date)

    @app.command("agent-review")
    def acknowledge_agent_digest(
        context: typer.Context, session_date: str, operator_id: str
    ) -> None:
        """Acknowledge a rendered daily digest as the operator."""
        _call(context, "acknowledge_agent_digest", session_date, operator_id)

    @app.command("agent-gate")
    def agent_gate_status(context: typer.Context, prior_session_date: str) -> None:
        """Show whether new proposals pass the prior-session review gate."""
        _call(context, "agent_gate_status", prior_session_date)

    @app.command("agent-enqueue")
    def enqueue_agent_work(
        context: typer.Context,
        role: str = typer.Option(..., "--role"),
        session_id: str = typer.Option(..., "--session-id"),
        objective: str = typer.Option(..., "--objective"),
        priority: int = typer.Option(50, "--priority", min=0, max=100),
    ) -> None:
        """Persist event-driven work; does not start an agent or scheduler."""
        _call(context, "enqueue_agent_work", role, session_id, objective, priority)

    @app.command("agent-queue")
    def list_agent_work(context: typer.Context) -> None:
        """List persisted agent work and claims."""
        _call(context, "list_agent_work")

    @app.command("agent-run-next")
    def run_next_agent_work(
        context: typer.Context,
        worker_id: str = typer.Option(..., "--worker-id"),
        repository_revision: str = typer.Option(..., "--repository-revision"),
        evidence_json: str = typer.Option("{}", "--evidence-json"),
        prior_session_date: str = typer.Option(..., "--prior-session-date"),
    ) -> None:
        """Claim one queued item and run it through the serialized Qwen lease."""
        try:
            evidence = json.loads(evidence_json)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter("evidence-json must be valid JSON") from exc
        if not isinstance(evidence, dict):
            raise typer.BadParameter("evidence-json must be a JSON object")
        _call(
            context,
            "run_next_agent_work",
            worker_id,
            repository_revision,
            evidence,
            prior_session_date,
        )

    @app.command("knowledge-sync")
    def sync_knowledge(context: typer.Context) -> None:
        """Synchronize approved Obsidian notes into the derived local index."""
        _call(context, "sync_knowledge")

    @app.command("knowledge-search")
    def search_knowledge(
        context: typer.Context,
        query: str = typer.Option(..., "--query", help="Terms to retrieve."),
        role: str = typer.Option(..., "--role", help="Specialist role and scope."),
    ) -> None:
        """Search approved knowledge visible to one specialist role."""
        _call(context, "search_knowledge", query, role)

    @app.command("knowledge-status")
    def knowledge_status(context: typer.Context) -> None:
        """Report the documents in the derived knowledge store."""
        _call(context, "knowledge_status")

    @app.command("knowledge-budget")
    def knowledge_budget(context: typer.Context) -> None:
        """Report the active knowledge line budget and compaction candidates."""
        _call(context, "knowledge_budget")

    @app.command("session-status")
    def session_status(context: typer.Context) -> None:
        """Report captured redacted sessions available to Dream Gate."""
        _call(context, "session_status")

    @app.command("dream-run")
    def run_dream(
        context: typer.Context,
        dry_run: bool = typer.Option(False, "--dry-run"),
    ) -> None:
        """Run one Dream Gate pass; ordinary memory and procedures are applied."""
        if dry_run:
            _call(context, "run_dream", True)
        else:
            _call(context, "run_dream")

    @app.command("memory-status")
    def working_memory_status(
        context: typer.Context,
        agent_id: str = typer.Option(..., "--agent-id"),
    ) -> None:
        """Show one agent's bounded working-memory status."""
        _call(context, "working_memory_status", agent_id)

    @app.command("memory-curate")
    def curate_working_memory(
        context: typer.Context,
        agent_id: str = typer.Option(..., "--agent-id"),
        candidates_json: str = typer.Option("[]", "--candidates-json"),
    ) -> None:
        """Curate submitted candidates into one bounded agent core."""
        _call(context, "curate_working_memory", agent_id, candidates_json)

    @app.command("approve")
    def approve_run(
        context: typer.Context,
        run_id: str,
        checkpoint_id: str = typer.Option(..., "--checkpoint-id"),
        operator_id: str = typer.Option(..., "--operator-id"),
        reason: str = typer.Option(..., "--reason"),
    ) -> None:
        """Persist explicit approval bound to the current checkpoint."""
        _call(context, "approve_run", run_id, checkpoint_id, operator_id, reason)

    @app.command("reject")
    def reject_run(
        context: typer.Context,
        run_id: str,
        checkpoint_id: str = typer.Option(..., "--checkpoint-id"),
        operator_id: str = typer.Option(..., "--operator-id"),
        reason: str = typer.Option(..., "--reason"),
    ) -> None:
        """Persist explicit rejection bound to the current checkpoint."""
        _call(context, "reject_run", run_id, checkpoint_id, operator_id, reason)

    @app.command("cancel")
    def cancel_run(
        context: typer.Context,
        run_id: str,
        reason: str = typer.Option(..., "--reason"),
    ) -> None:
        """Explicitly cancel a nonterminal run."""
        _call(context, "cancel_run", run_id, reason)

    return app


app = build_app()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
