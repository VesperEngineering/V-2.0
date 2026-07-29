"""Side-effect-free Typer control surface for the native platform."""

from __future__ import annotations

import json
import os
import tempfile
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
            help="Specialist runtime: docker-codex or opencode.",
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
