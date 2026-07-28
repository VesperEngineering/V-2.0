"""Narrow OpenCode subprocess boundary for V20 specialist execution."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .contracts import (
    CodexExecutionReceipt,
    ExecutionStatus,
    SandboxMode,
    SpecialistInput,
    SpecialistRole,
)
from .control import CancellationEvent, RuntimeControl

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
_MAX_OUTPUT_BYTES = 2_000_000
_CREATE_SUSPENDED = 0x00000004


def _default_executable() -> str:
    if os.name != "nt":
        return shutil.which("opencode") or "opencode"
    candidates = []
    if appdata := os.environ.get("APPDATA"):
        candidates.append(
            Path(appdata) / "npm" / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
        )
    if userprofile := os.environ.get("USERPROFILE"):
        candidates.append(Path(userprofile) / ".opencode" / "bin" / "opencode.exe")
    installed = next((path.resolve() for path in candidates if path.is_file()), None)
    if installed is not None:
        return str(installed)
    direct = shutil.which("opencode.exe")
    if direct and not Path(direct).resolve().is_relative_to(Path.cwd().resolve()):
        return str(Path(direct).resolve())
    system_root = Path(os.environ.get("SYSTEMROOT", "C:/Windows"))
    return str(system_root / "System32" / "v20-opencode-not-found.exe")


_DEFAULT_EXECUTABLE = _default_executable()


class OpenCodeGatewayError(RuntimeError):
    """V20 rejected an OpenCode request before starting a child process."""


class ModelNotApprovedError(OpenCodeGatewayError):
    """The requested OpenCode provider/model is not controller-approved."""


class CredentialUnavailableError(OpenCodeGatewayError):
    """The selected provider's explicitly bound credential is unavailable."""


class WorkspaceDeniedError(OpenCodeGatewayError):
    """The requested workspace is outside the authorized repository."""


class _ProcessCancelled(RuntimeError):
    pass


ProcessRunner = Callable[
    [
        list[str],
        Path,
        Mapping[str, str],
        float,
        CancellationEvent | None,
        Callable[[int], None] | None,
    ],
    subprocess.CompletedProcess[str],
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _run_process(
    command: list[str],
    workspace: Path,
    environment: Mapping[str, str],
    timeout_seconds: float,
    cancellation: CancellationEvent | None,
    on_start: Callable[[int], None] | None,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            command,
            cwd=workspace,
            env=dict(environment),
            stdout=stdout,
            stderr=stderr,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP | _CREATE_SUSPENDED if os.name == "nt" else 0
            ),
            start_new_session=os.name != "nt",
        )
        containment = _contain_process_tree(process)
        try:
            if on_start is not None:
                try:
                    on_start(process.pid)
                except BaseException:
                    _terminate_process(process)
                    raise
            deadline = time.monotonic() + timeout_seconds
            try:
                while process.poll() is None:
                    if cancellation is not None and cancellation.is_set():
                        _terminate_process(process)
                        raise _ProcessCancelled
                    if time.monotonic() >= deadline:
                        _terminate_process(process)
                        raise subprocess.TimeoutExpired(command, timeout_seconds)
                    time.sleep(0.05)
            except (subprocess.TimeoutExpired, _ProcessCancelled) as exc:
                stdout.seek(0)
                stderr.seek(0)
                if isinstance(exc, _ProcessCancelled):
                    raise
                raise subprocess.TimeoutExpired(
                    exc.cmd,
                    exc.timeout,
                    output=stdout.read(_MAX_OUTPUT_BYTES + 1),
                    stderr=stderr.read(_MAX_OUTPUT_BYTES + 1),
                ) from exc
            stdout.seek(0)
            stderr.seek(0)
            return subprocess.CompletedProcess(
                command,
                process.returncode,
                stdout=stdout.read(_MAX_OUTPUT_BYTES + 1).decode("utf-8", errors="replace"),
                stderr=stderr.read(_MAX_OUTPUT_BYTES + 1).decode("utf-8", errors="replace"),
            )
        finally:
            if os.name != "nt":
                _terminate_process_tree(process.pid)
            _release_process_containment(containment)


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        _terminate_process_tree(process.pid)
    process.wait(timeout=5)


def _contain_process_tree(process: subprocess.Popen) -> int | None:
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("read_operations", ctypes.c_ulonglong),
            ("write_operations", ctypes.c_ulonglong),
            ("other_operations", ctypes.c_ulonglong),
            ("read_bytes", ctypes.c_ulonglong),
            ("write_bytes", ctypes.c_ulonglong),
            ("other_bytes", ctypes.c_ulonglong),
        ]

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("per_process_user_time_limit", ctypes.c_longlong),
            ("per_job_user_time_limit", ctypes.c_longlong),
            ("limit_flags", wintypes.DWORD),
            ("minimum_working_set_size", ctypes.c_size_t),
            ("maximum_working_set_size", ctypes.c_size_t),
            ("active_process_limit", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority_class", wintypes.DWORD),
            ("scheduling_class", wintypes.DWORD),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("basic_limit_information", BasicLimitInformation),
            ("io_info", IoCounters),
            ("process_memory_limit", ctypes.c_size_t),
            ("job_memory_limit", ctypes.c_size_t),
            ("peak_process_memory_used", ctypes.c_size_t),
            ("peak_job_memory_used", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        process.kill()
        process.wait(timeout=5)
        raise OpenCodeGatewayError("Windows process containment is unavailable")
    information = ExtendedLimitInformation()
    information.basic_limit_information.limit_flags = 0x00002000
    if not kernel32.SetInformationJobObject(
        job,
        9,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ) or not kernel32.AssignProcessToJobObject(job, process._handle):
        kernel32.CloseHandle(job)
        process.kill()
        process.wait(timeout=5)
        raise OpenCodeGatewayError("Windows process containment could not be established")
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = (wintypes.HANDLE,)
    ntdll.NtResumeProcess.restype = ctypes.c_long
    if ntdll.NtResumeProcess(process._handle) != 0:
        kernel32.CloseHandle(job)
        process.kill()
        process.wait(timeout=5)
        raise OpenCodeGatewayError("Windows contained process could not be started")
    return int(job)


def _release_process_containment(handle: int | None) -> None:
    if handle is None:
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(handle)


def _process_identity(process_id: int) -> str | None:
    """Return an OS-backed identity that changes when a PID is reused."""
    if process_id <= 0:
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        )
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, process_id)
        if not handle:
            return None
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return None
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                return None
            created = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            value = f"{buffer.value.casefold()}\0{created}"
        finally:
            kernel32.CloseHandle(handle)
    else:
        proc = Path("/proc") / str(process_id)
        try:
            executable = (proc / "exe").resolve(strict=True)
            fields = (proc / "stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
            value = f"{executable}\0{fields[19]}"
        except (FileNotFoundError, OSError, IndexError):
            completed = subprocess.run(
                ["ps", "-o", "lstart=", "-o", "comm=", "-p", str(process_id)],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            value = completed.stdout.strip()
            if completed.returncode != 0 or not value:
                return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _process_exists(process_id: int) -> bool | None:
    if process_id <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x00100000, False, process_id)
        if not handle:
            error = ctypes.get_last_error()
            return False if error == 87 else None
        try:
            result = kernel32.WaitForSingleObject(handle, 0)
            if result == 0:
                return False
            return True if result == 258 else None
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    return True


def _terminate_process_tree(process_id: int) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(process_id), "/T", "/F"],
            capture_output=True,
            check=False,
            timeout=10,
        )
        if completed.returncode != 0 and _process_exists(process_id) is not False:
            raise OpenCodeGatewayError("OpenCode process tree termination failed")
    else:
        try:
            os.killpg(process_id, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 1
        while _process_group_exists(process_id) and time.monotonic() < deadline:
            time.sleep(0.05)
        if _process_group_exists(process_id):
            try:
                os.killpg(process_id, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return
    deadline = time.monotonic() + 5
    while _process_identity(process_id) is not None and time.monotonic() < deadline:
        time.sleep(0.05)
    if _process_identity(process_id) is not None:
        raise OpenCodeGatewayError("OpenCode process tree did not terminate")


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    return True


class OpenCodeGateway:
    """Run one V20 specialist turn through a locally installed OpenCode executable."""

    def __init__(
        self,
        *,
        repository_root: Path,
        approved_models: tuple[str, ...],
        credential_environment_keys: Mapping[str, str] | None = None,
        protected_paths: tuple[Path, ...] = (),
        control: RuntimeControl | None = None,
        executable: str = _DEFAULT_EXECUTABLE,
        runner: ProcessRunner = _run_process,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository_root = repository_root.resolve()
        self._approved_models = frozenset(approved_models)
        self._credential_environment_keys = dict(credential_environment_keys or {})
        self._protected_paths = tuple(
            path.resolve()
            for path in protected_paths
            if path.resolve().is_relative_to(self._repository_root)
        )
        self._control = control
        self._executable = executable
        self._runner = runner
        self._clock = clock

    def execute(
        self,
        request: SpecialistInput,
        *,
        prompt: str,
        model: str,
        timeout_seconds: float = 300,
        cancellation: CancellationEvent | None = None,
        execution_id: str | None = None,
        reasoning_effort: str | None = None,
        output_schema: Mapping[str, object] | None = None,
    ) -> CodexExecutionReceipt:
        if model not in self._approved_models:
            raise ModelNotApprovedError(f"model is not controller-approved: {model}")
        if "/" not in model:
            raise ModelNotApprovedError("model must use provider/model form")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        workspace = self._workspace(request.workspace)
        identifier = execution_id or f"opencode-{request.role.value}-{request.attempt}"
        started_at = self._clock()
        effective_cancellation = (
            cancellation
            if self._control is None
            else self._control.cancellation_signal(request.run_id, cancellation)
        )
        if effective_cancellation is not None and effective_cancellation.is_set():
            return self._receipt(
                request,
                identifier,
                started_at,
                model,
                ExecutionStatus.CANCELLED,
                "cancelled",
            )
        with tempfile.TemporaryDirectory(prefix="v20-opencode-") as temporary:
            config_path = Path(temporary) / "opencode.json"
            config_path.write_text(
                json.dumps(self._config(model, request), separators=(",", ":")),
                encoding="utf-8",
            )
            provider = model.split("/", maxsplit=1)[0]
            environment = self._environment(config_path, provider)
            command = [
                self._executable,
                "run",
                "--pure",
                "--format",
                "json",
                "--model",
                model,
                "--agent",
                "v20",
                "--dir",
                str(workspace),
                self._prompt(prompt, output_schema, request),
            ]
            on_start = None
            if self._control is not None:

                def on_start(process_id: int) -> None:
                    identity = _process_identity(process_id)
                    if identity is None:
                        raise OpenCodeGatewayError("OpenCode process identity is unavailable")
                    self._control.mark_active_process(
                        run_id=request.run_id,
                        execution_id=identifier,
                        runtime="opencode",
                        process_id=process_id,
                        process_identity=identity,
                        role=request.role.value,
                        attempt=request.attempt,
                    )

            clear_active = False
            try:
                completed = self._runner(
                    command,
                    workspace,
                    environment,
                    timeout_seconds,
                    effective_cancellation,
                    on_start,
                )
                clear_active = True
            except FileNotFoundError:
                clear_active = True
                return self._receipt(
                    request,
                    identifier,
                    started_at,
                    model,
                    ExecutionStatus.FAILED,
                    "opencode-not-found",
                )
            except _ProcessCancelled:
                clear_active = True
                return self._receipt(
                    request,
                    identifier,
                    started_at,
                    model,
                    ExecutionStatus.CANCELLED,
                    "cancelled",
                )
            except subprocess.TimeoutExpired as exc:
                clear_active = True
                output = self._output_bytes(exc.stdout, exc.stderr)
                if len(output) > _MAX_OUTPUT_BYTES:
                    events, thread_id, final_response = (), None, None
                else:
                    events, thread_id, final_response, _valid = self._events(exc.stdout)
                return self._receipt(
                    request,
                    identifier,
                    started_at,
                    model,
                    ExecutionStatus.TIMEOUT,
                    "timeout",
                    events=events,
                    thread_id=thread_id,
                    final_response=final_response,
                )
            finally:
                if self._control is not None and clear_active:
                    self._control.clear_active(request.run_id, identifier)

        output = self._output_bytes(completed.stdout, completed.stderr)
        if effective_cancellation is not None and effective_cancellation.is_set():
            return self._receipt(
                request,
                identifier,
                started_at,
                model,
                ExecutionStatus.CANCELLED,
                "cancelled",
            )
        if len(output) > _MAX_OUTPUT_BYTES:
            return self._receipt(
                request,
                identifier,
                started_at,
                model,
                ExecutionStatus.FAILED,
                "opencode-output-too-large",
            )
        status, error_code = self._status(completed.returncode, output)
        events, thread_id, final_response, valid = self._events(completed.stdout)
        if status is ExecutionStatus.COMPLETED and not valid:
            status, error_code = ExecutionStatus.FAILED, "invalid-opencode-output"
        return self._receipt(
            request,
            execution_id,
            started_at,
            model,
            status,
            error_code,
            events=events,
            thread_id=thread_id,
            final_response=final_response,
        )

    def _workspace(self, value: str) -> Path:
        workspace = Path(value).resolve()
        if not workspace.is_dir() or not workspace.is_relative_to(self._repository_root):
            raise WorkspaceDeniedError(f"workspace is outside the authorized repository: {value}")
        return workspace

    def _config(self, model: str, request: SpecialistInput) -> dict[str, object]:
        provider = model.split("/", maxsplit=1)[0]
        development = request.role is SpecialistRole.DEVELOPMENT
        writable = development and request.permissions.sandbox is SandboxMode.WORKSPACE_WRITE
        workspace = Path(request.workspace).resolve().relative_to(self._repository_root).as_posix()
        reserved_rules = {
            "**/.git": "deny",
            "**/.git/**": "deny",
            "**/.state": "deny",
            "**/.state/**": "deny",
            "*.env": "deny",
            "*.env.*": "deny",
            "**/*.env": "deny",
            "**/*.env.*": "deny",
        }
        if workspace == ".":
            workspace_rules = {"*": "allow", **reserved_rules}
        else:
            workspace_rules = {
                "*": "deny",
                workspace: "allow",
                f"{workspace}/**": "allow",
                **reserved_rules,
            }
        for path in self._protected_paths:
            relative = path.relative_to(self._repository_root).as_posix()
            workspace_rules[relative] = "deny"
            workspace_rules[f"{relative}/**"] = "deny"
        permission = {
            "read": workspace_rules if development else "deny",
            "edit": workspace_rules if writable else "deny",
            "bash": "deny",
            "glob": "deny",
            "grep": "deny",
            "list": "deny",
            "task": "deny",
            "skill": "deny",
            "lsp": "deny",
            "webfetch": "deny",
            "websearch": "deny",
            "todowrite": "deny",
            "question": "deny",
            "external_directory": "deny",
        }
        config: dict[str, object] = {
            "share": "disabled",
            "autoupdate": False,
            "snapshot": False,
            "formatter": False,
            "lsp": False,
            "instructions": [],
            "mcp": {},
            "enabled_providers": [provider],
            "tools": {
                "read": development,
                "glob": False,
                "grep": False,
                "list": False,
                "write": writable,
                "edit": writable,
                "apply_patch": False,
                "bash": False,
                "task": False,
                "skill": False,
                "lsp": False,
                "webfetch": False,
                "websearch": False,
            },
            "permission": permission,
            "agent": {"v20": {"mode": "primary", "permission": permission}},
        }
        if model == "moonshot/kimi-k3":
            credential_key = self._credential_environment_keys.get(provider)
            if credential_key:
                config["provider"] = {
                    provider: {
                        "npm": "@ai-sdk/openai-compatible",
                        "name": "Moonshot AI",
                        "options": {
                            "baseURL": "https://api.moonshot.ai/v1",
                            "apiKey": f"{{env:{credential_key}}}",
                        },
                        "models": {"kimi-k3": {"name": "Kimi K3"}},
                    }
                }
        return config

    def _environment(self, config_path: Path, provider: str) -> dict[str, str]:
        environment = {key: os.environ[key] for key in _ENVIRONMENT_KEYS if key in os.environ}
        userprofile = os.environ.get("USERPROFILE")
        if provider in self._credential_environment_keys:
            credential_key = self._credential_environment_keys[provider]
            credential = os.environ.get(credential_key) if credential_key else None
            if not credential:
                raise CredentialUnavailableError(
                    f"credential is unavailable for provider: {provider}"
                )
            environment[credential_key] = credential
        isolated_home = config_path.parent / "home"
        environment.update(
            {
                "OPENCODE_CONFIG": str(config_path),
                "OPENCODE_AUTO_SHARE": "false",
                "OPENCODE_DISABLE_AUTOUPDATE": "true",
                "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
                "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
                "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "true",
                "OPENCODE_DISABLE_MODELS_FETCH": "true",
                "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
                "HOME": str(isolated_home),
                "USERPROFILE": str(isolated_home),
                "XDG_CONFIG_HOME": str(config_path.parent / "xdg-config"),
            }
        )
        if userprofile:
            environment.update(
                {
                    "XDG_CACHE_HOME": str(Path(userprofile) / ".cache"),
                    "XDG_DATA_HOME": str(Path(userprofile) / ".local" / "share"),
                    "XDG_STATE_HOME": str(Path(userprofile) / ".local" / "state"),
                }
            )
        return environment

    @staticmethod
    def _prompt(
        prompt: str,
        output_schema: Mapping[str, object] | None,
        request: SpecialistInput,
    ) -> str:
        if request.role is SpecialistRole.DEVELOPMENT:
            tool_boundary = (
                "Use only read, edit, and write inside the exact granted workspace. "
                "Do not call shell, search, subagent, skill, web, or external-path tools. "
                "Return the final schema JSON directly as assistant text. Never write that "
                "response, a receipt, a report, or completion metadata into a workspace file."
            )
        else:
            tool_boundary = (
                "Do not call any tools. All evidence and dynamic state required for this turn "
                "is already present in the controller prompt."
            )
        prompt = prompt + "\n\n" + tool_boundary
        if output_schema is None:
            return prompt
        return prompt + "\n\nOutput schema:\n" + json.dumps(output_schema, sort_keys=True)

    @staticmethod
    def _events(
        stdout: str | bytes | None,
    ) -> tuple[tuple[dict[str, object], ...], str | None, str | None, bool]:
        if stdout is None:
            return (), None, None, True
        text = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else stdout
        events = []
        text_parts = []
        thread_id = None
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                return (), None, None, False
            if not isinstance(event, dict):
                return (), None, None, False
            session_id = event.get("sessionID")
            if isinstance(session_id, str):
                if thread_id is not None and session_id != thread_id:
                    return (), None, None, False
                thread_id = session_id
            part = event.get("part")
            if event.get("type") == "text" and isinstance(part, dict):
                content = part.get("text")
                if isinstance(content, str):
                    text_parts.append(content)
            events.append(event)
        final_response = OpenCodeGateway._normalize_response("".join(text_parts))
        return tuple(events), thread_id, final_response, True

    @staticmethod
    def _normalize_response(value: str) -> str | None:
        value = value.strip()
        marker = "```json\n"
        if value.count(marker) == 1 and value.endswith("\n```"):
            value = value[value.index(marker) + len(marker) : -len("\n```")].strip()
        return value or None

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
        execution_id: str | None,
        started_at: datetime,
        model: str,
        status: ExecutionStatus,
        error_code: str | None,
        *,
        events: tuple[dict[str, object], ...] = (),
        thread_id: str | None = None,
        final_response: str | None = None,
    ) -> CodexExecutionReceipt:
        return CodexExecutionReceipt(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            execution_id=execution_id or f"opencode-{request.role.value}-{request.attempt}",
            role=request.role,
            attempt=request.attempt,
            status=status,
            sandbox=request.permissions.sandbox,
            model=model,
            workspace=request.workspace,
            approval_mode="deny-all",
            authentication_type="opencode-local",
            permission_profile="opencode-host",
            started_at=started_at,
            finished_at=self._clock(),
            thread_id=thread_id,
            final_response=final_response,
            streamed_events=events,
            error_code=error_code,
        )
