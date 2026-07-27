"""Controller-owned provisioning for one-shot Docker Codex turns."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Protocol

from .codex import ModelNotApprovedError, WorkspaceDeniedError
from .codex_sandbox import (
    DOCKER_CODEX_DEFAULT_MODEL,
    DockerCodexAdapter,
    DockerSandboxBoundaryError,
    DockerSandboxTerminationError,
)
from .contracts import CodexExecutionReceipt, ExecutionStatus, SpecialistInput

OPENAI_NETWORK_HOSTS = ("api.openai.com", "chatgpt.com", "openai.com")


class SpecialistTurnAdapter(Protocol):
    def execute(
        self,
        request: SpecialistInput,
        *,
        prompt: str,
        model: str,
        timeout_seconds: float,
        cancellation=None,
        execution_id: str | None = None,
        reasoning_effort: str | None = None,
        output_schema: Mapping[str, object] | None = None,
    ) -> CodexExecutionReceipt: ...


ProcessRunner = Callable[[list[str], Path, float], subprocess.CompletedProcess[str]]
AdapterFactory = Callable[[str], SpecialistTurnAdapter]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _run_process(
    command: list[str],
    workspace: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=workspace,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout_seconds,
    )


def default_sbx_executable() -> str:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "DockerSandboxes" / "bin" / "sbx.exe"
        if candidate.is_file():
            return str(candidate)
    return "sbx"


class DockerCodexRuntime:
    """Provision one unique sandbox for each specialist turn and never reuse it."""

    def __init__(
        self,
        *,
        repository_root: Path,
        approved_models: tuple[str, ...] = (DOCKER_CODEX_DEFAULT_MODEL,),
        executable: str | None = None,
        runner: ProcessRunner = _run_process,
        adapter_factory: AdapterFactory | None = None,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.approved_models = frozenset(approved_models)
        self.executable = executable or default_sbx_executable()
        self._runner = runner
        self._adapter_factory = adapter_factory
        self._clock = clock
        self._id_factory = id_factory

    def execute(
        self,
        request: SpecialistInput,
        *,
        prompt: str,
        model: str,
        timeout_seconds: float,
        cancellation=None,
        execution_id: str | None = None,
        reasoning_effort: str | None = None,
        output_schema: Mapping[str, object] | None = None,
    ) -> CodexExecutionReceipt:
        if model not in self.approved_models:
            raise ModelNotApprovedError(f"model is not controller-approved: {model}")
        workspace = Path(request.workspace).resolve()
        if not workspace.is_dir() or not workspace.is_relative_to(self.repository_root):
            raise WorkspaceDeniedError(
                f"workspace is outside the authorized repository: {request.workspace}"
            )
        if workspace == self.repository_root:
            raise WorkspaceDeniedError("sandbox workspace must be a dedicated subdirectory")

        identifier = execution_id or self._id_factory()
        started_at = self._clock()
        sandbox_name = self._sandbox_name(request, identifier)
        created = False
        delegated = False
        try:
            completed = self._run(
                [
                    self.executable,
                    "create",
                    "--no-share-skills",
                    "--name",
                    sandbox_name,
                    "codex",
                    str(workspace),
                ]
            )
            if completed.returncode != 0:
                return self._receipt(
                    request,
                    identifier,
                    started_at,
                    model,
                    ExecutionStatus.FAILED,
                    "sandbox-create-failed",
                )
            created = True
            completed = self._run(
                [
                    self.executable,
                    "policy",
                    "allow",
                    "network",
                    "--sandbox",
                    sandbox_name,
                    ",".join(OPENAI_NETWORK_HOSTS),
                ]
            )
            if completed.returncode != 0:
                return self._receipt(
                    request,
                    identifier,
                    started_at,
                    model,
                    ExecutionStatus.PERMISSION_DENIED,
                    "sandbox-policy-failed",
                )
            completed = self._run([self.executable, "stop", sandbox_name])
            if completed.returncode != 0:
                return self._receipt(
                    request,
                    identifier,
                    started_at,
                    model,
                    ExecutionStatus.FAILED,
                    "sandbox-stop-failed",
                )

            adapter = self._adapter(sandbox_name, workspace)
            receipt = adapter.execute(
                request,
                prompt=prompt,
                model=model,
                timeout_seconds=timeout_seconds,
                cancellation=cancellation,
                execution_id=identifier,
                reasoning_effort=reasoning_effort,
                output_schema=output_schema,
            )
            delegated = True
            return receipt
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return self._receipt(
                request,
                identifier,
                started_at,
                model,
                ExecutionStatus.FAILED,
                "sandbox-provisioner-unavailable",
            )
        except DockerSandboxBoundaryError as exc:
            return self._receipt(
                request,
                identifier,
                started_at,
                model,
                ExecutionStatus.PERMISSION_DENIED,
                type(exc).__name__.lower(),
            )
        finally:
            if created and not delegated:
                self._cleanup(sandbox_name)

    def _adapter(self, sandbox_name: str, workspace: Path) -> SpecialistTurnAdapter:
        if self._adapter_factory is not None:
            return self._adapter_factory(sandbox_name)
        return DockerCodexAdapter(
            repository_root=self.repository_root,
            sandbox_workspace=workspace,
            sandbox_name=sandbox_name,
            approved_models=tuple(sorted(self.approved_models)),
            approved_network_hosts=OPENAI_NETWORK_HOSTS,
            executable=self.executable,
            clock=self._clock,
        )

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return self._runner(command, self.repository_root, 120)

    def _cleanup(self, sandbox_name: str) -> None:
        try:
            self._run([self.executable, "rm", "--force", sandbox_name])
            listed = self._run([self.executable, "ls", "--json"])
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise DockerSandboxTerminationError("sandbox removal could not be confirmed") from exc
        try:
            payload = json.loads(listed.stdout)
        except (TypeError, ValueError) as exc:
            raise DockerSandboxTerminationError("sandbox removal could not be confirmed") from exc
        sandboxes = payload.get("sandboxes") if isinstance(payload, dict) else None
        if (
            listed.returncode != 0
            or not isinstance(sandboxes, list)
            or any(
                not isinstance(item, dict) or not isinstance(item.get("name"), str)
                for item in sandboxes
            )
            or any(item["name"] == sandbox_name for item in sandboxes)
        ):
            raise DockerSandboxTerminationError("sandbox removal could not be confirmed")

    @staticmethod
    def _sandbox_name(request: SpecialistInput, execution_id: str) -> str:
        digest = hashlib.sha256(execution_id.encode("utf-8")).hexdigest()[:16]
        role = request.role.value.removeprefix("v20-")
        return f"v20-{role}-{digest}"

    def _receipt(
        self,
        request: SpecialistInput,
        execution_id: str,
        started_at: datetime,
        model: str,
        status: ExecutionStatus,
        error_code: str,
    ) -> CodexExecutionReceipt:
        return CodexExecutionReceipt(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            execution_id=execution_id,
            role=request.role,
            attempt=request.attempt,
            status=status,
            sandbox=request.permissions.sandbox,
            model=model,
            workspace=request.workspace,
            approval_mode="deny-all",
            authentication_type="chatgpt",
            permission_profile="docker-one-shot",
            started_at=started_at,
            finished_at=self._clock(),
            error_code=error_code,
        )
