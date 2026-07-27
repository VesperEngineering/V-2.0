"""Side-effect-free Typer control surface for the native platform."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol

import typer


@dataclass(frozen=True, slots=True)
class CliConfig:
    state_db: Path
    evidence_root: Path
    profiles_root: Path


class PlatformService(Protocol):
    def create_run(self, objective: str, workspace: str, repository_revision: str): ...

    def inspect_run(self, run_id: str): ...

    def resume_run(self, run_id: str): ...

    def list_receipts(self, run_id: str): ...

    def list_evidence(self, run_id: str): ...

    def list_pending_approvals(self): ...

    def approve_run(self, run_id: str, checkpoint_id: str, operator_id: str, reason: str): ...

    def reject_run(self, run_id: str, checkpoint_id: str, operator_id: str, reason: str): ...

    def cancel_run(self, run_id: str, reason: str): ...


class PlatformRuntimeUnavailable(RuntimeError):
    """A requested platform capability has no configured local runtime."""


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
        evidence_root=config.evidence_root.resolve(),
    )
    return LocalPlatformService(paths)


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
            Path(".v20-platform/checkpoints.sqlite3"),
            "--state-db",
            help="Local SQLite checkpoint database; opened only by a command.",
        ),
        evidence_root: Path = typer.Option(
            Path(".v20-platform/evidence"),
            "--evidence-root",
            help="Local evidence root; opened only by a command.",
        ),
        profiles_root: Path = typer.Option(
            Path("profiles/native"),
            "--profiles-root",
            help="Native profile catalog.",
        ),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        context.obj = _Context(
            config=CliConfig(state_db, evidence_root, profiles_root),
            json_output=json_output,
            service_factory=service_factory,
        )

    @app.command("create")
    def create_run(
        context: typer.Context,
        objective: str = typer.Option(..., "--objective", help="Bounded task objective."),
        workspace: str = typer.Option(..., "--workspace", help="Authorized repository/worktree."),
        repository_revision: str = typer.Option(
            ..., "--repository-revision", help="Revision the request is bound to."
        ),
    ) -> None:
        """Create a run and execute until a durable stop or interrupt."""
        _call(context, "create_run", objective, workspace, repository_revision)

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
