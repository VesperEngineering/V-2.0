"""Narrow OpenCode subprocess boundary for V20 specialist execution."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .contracts import ExecutionStatus, SandboxMode, SpecialistInput, SpecialistReceipt
from .evidence import FilesystemEvidenceStore
from .profiles import ProfileCatalog

_ENVIRONMENT_KEYS = (
    "APPDATA",
    "COMSPEC",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
)


class OpenCodeGatewayError(RuntimeError):
    """V20 rejected an OpenCode request before starting a child process."""


class ModelNotApprovedError(OpenCodeGatewayError):
    """The requested OpenCode provider/model is not controller-approved."""


class WorkspaceDeniedError(OpenCodeGatewayError):
    """The requested workspace is outside the authorized repository."""


ProcessRunner = Callable[
    [list[str], Path, Mapping[str, str], float], subprocess.CompletedProcess[str]
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _run_process(
    command: list[str],
    workspace: Path,
    environment: Mapping[str, str],
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=workspace,
        env=dict(environment),
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout_seconds,
    )


class OpenCodeGateway:
    """Run one V20 specialist turn through a locally installed OpenCode executable."""

    def __init__(
        self,
        *,
        repository_root: Path,
        profiles: ProfileCatalog,
        evidence: FilesystemEvidenceStore,
        approved_models: tuple[str, ...],
        executable: str = "opencode",
        runner: ProcessRunner = _run_process,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository_root = repository_root.resolve()
        self._profiles = profiles
        self._evidence = evidence
        self._approved_models = frozenset(approved_models)
        self._executable = executable
        self._runner = runner
        self._clock = clock

    def execute(
        self,
        request: SpecialistInput,
        *,
        model: str,
        timeout_seconds: float = 300,
    ) -> SpecialistReceipt:
        if model not in self._approved_models:
            raise ModelNotApprovedError(f"model is not controller-approved: {model}")
        if "/" not in model:
            raise ModelNotApprovedError("model must use provider/model form")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        workspace = self._workspace(request.workspace)
        profile = self._profiles.load(request.role)
        with tempfile.TemporaryDirectory(prefix="v20-opencode-") as temporary:
            config_path = Path(temporary) / "opencode.json"
            config_path.write_text(
                json.dumps(self._config(model, request), separators=(",", ":")),
                encoding="utf-8",
            )
            environment = self._environment(config_path)
            command = [
                self._executable,
                "run",
                "--pure",
                "--format",
                "json",
                "--model",
                model,
                "--dir",
                str(workspace),
                self._prompt(profile.system_instructions, profile.soul, request),
            ]
            try:
                completed = self._runner(command, workspace, environment, timeout_seconds)
            except FileNotFoundError:
                return self._receipt(request, ExecutionStatus.FAILED, "opencode-not-found", b"")
            except subprocess.TimeoutExpired as exc:
                output = self._output_bytes(exc.stdout, exc.stderr)
                return self._receipt(request, ExecutionStatus.TIMEOUT, "timeout", output)

        output = self._output_bytes(completed.stdout, completed.stderr)
        status, error_code = self._status(completed.returncode, output)
        return self._receipt(request, status, error_code, output)

    def _workspace(self, value: str) -> Path:
        workspace = Path(value).resolve()
        if not workspace.is_dir() or not workspace.is_relative_to(self._repository_root):
            raise WorkspaceDeniedError(f"workspace is outside the authorized repository: {value}")
        return workspace

    @staticmethod
    def _config(model: str, request: SpecialistInput) -> dict[str, object]:
        provider = model.split("/", maxsplit=1)[0]
        writable = request.permissions.sandbox is SandboxMode.WORKSPACE_WRITE
        return {
            "share": "disabled",
            "autoupdate": False,
            "enabled_providers": [provider],
            "tools": {
                "write": writable,
                "edit": writable,
                "bash": "test" in request.permissions.allowed_tools,
                "webfetch": False,
                "websearch": False,
            },
        }

    @staticmethod
    def _environment(config_path: Path) -> dict[str, str]:
        environment = {key: os.environ[key] for key in _ENVIRONMENT_KEYS if key in os.environ}
        environment.update(
            {
                "OPENCODE_CONFIG": str(config_path),
                "OPENCODE_AUTO_SHARE": "false",
                "OPENCODE_DISABLE_AUTOUPDATE": "true",
                "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
                "OPENCODE_DISABLE_MODELS_FETCH": "true",
            }
        )
        return environment

    @staticmethod
    def _prompt(system_instructions: str, soul: str, request: SpecialistInput) -> str:
        return "\n\n".join(
            (
                system_instructions,
                soul,
                "Controller request:\n"
                + json.dumps(request.model_dump(mode="json"), sort_keys=True),
                "Completion is not task acceptance. Do not access credentials, providers, brokers, "
                "schedulers, protected data, or any path outside the granted workspace.",
            )
        )

    @staticmethod
    def _output_bytes(stdout: str | bytes | None, stderr: str | bytes | None) -> bytes:
        def normalize(value: str | bytes | None) -> bytes:
            if value is None:
                return b""
            return value if isinstance(value, bytes) else value.encode("utf-8", errors="replace")

        return normalize(stdout) + b"\n" + normalize(stderr)

    @staticmethod
    def _status(returncode: int, output: bytes) -> tuple[ExecutionStatus, str | None]:
        if returncode == 0:
            return ExecutionStatus.COMPLETED, None
        description = output.decode("utf-8", errors="replace").lower()
        if any(term in description for term in ("usage limit", "rate limit", "quota")):
            return ExecutionStatus.USAGE_LIMITED, "usage-limit"
        if "permission" in description or "denied" in description:
            return ExecutionStatus.PERMISSION_DENIED, "permission-denied"
        return ExecutionStatus.FAILED, f"opencode-exit-{returncode}"

    def _receipt(
        self,
        request: SpecialistInput,
        status: ExecutionStatus,
        error_code: str | None,
        output: bytes,
    ) -> SpecialistReceipt:
        metadata = json.dumps(
            {
                "runtime": "opencode",
                "role": request.role.value,
                "attempt": request.attempt,
                "status": status.value,
                "error_code": error_code,
                "output_bytes": len(output),
                "output_sha256": hashlib.sha256(output).hexdigest(),
                "recorded_at": self._clock().isoformat(),
            },
            sort_keys=True,
        ).encode("utf-8")
        evidence = self._evidence.put_bytes(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            artifact_id=f"opencode-{request.role.value}-{request.attempt}",
            body=metadata,
            media_type="application/json",
            suffix=".json",
        )
        return SpecialistReceipt(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            receipt_id=f"opencode:{request.role.value}:{request.attempt}:{request.run_id}",
            role=request.role,
            attempt=request.attempt,
            status=status,
            evidence=(evidence,),
            error_code=error_code,
        )
