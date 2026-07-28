"""Durable cross-process run discovery and cancellation signals."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Protocol

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_ACTIVE_RUN_STATUSES = frozenset(
    {
        "running",
        "interrupted",
        "data-research",
        "model-evaluation",
        "product",
        "development",
        "validation",
        "risk-review",
    }
)


class CancellationEvent(Protocol):
    def is_set(self) -> bool: ...


class _CancellationSignal:
    def __init__(self, path: Path, external: CancellationEvent | None) -> None:
        self.path = path
        self.external = external

    def is_set(self) -> bool:
        return self.path.is_file() or (self.external is not None and self.external.is_set())


class RuntimeControl:
    """Store small atomic control records outside specialist workspaces."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def register_run(self, value: Mapping[str, object]) -> None:
        run_id = self._safe_id(str(value["run_id"]))
        self._write(run_id, "run.json", {**value, "status": "running"})

    def set_run_status(self, run_id: str, status: str) -> None:
        current = self._read(run_id, "run.json") or {"run_id": run_id}
        self._write(
            run_id,
            "run.json",
            {
                **current,
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def mark_active(
        self,
        *,
        run_id: str,
        execution_id: str,
        sandbox_name: str,
        role: str,
        attempt: int,
    ) -> None:
        self._write(
            run_id,
            "active.json",
            {
                "run_id": run_id,
                "execution_id": execution_id,
                "sandbox_name": sandbox_name,
                "role": role,
                "attempt": attempt,
                "process_id": os.getpid(),
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def mark_active_process(
        self,
        *,
        run_id: str,
        execution_id: str,
        runtime: str,
        process_id: int,
        process_identity: str,
        role: str,
        attempt: int,
    ) -> None:
        self._write(
            run_id,
            "active.json",
            {
                "run_id": run_id,
                "execution_id": execution_id,
                "runtime": runtime,
                "process_id": process_id,
                "process_identity": process_identity,
                "role": role,
                "attempt": attempt,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def clear_active(self, run_id: str, execution_id: str) -> None:
        active = self._read(run_id, "active.json")
        if active is not None and active.get("execution_id") == execution_id:
            self._path(run_id, "active.json").unlink(missing_ok=True)

    def request_cancel(self, run_id: str, reason: str) -> None:
        self._write(
            run_id,
            "cancel.json",
            {
                "run_id": run_id,
                "reason": reason,
                "requested_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def cancellation_signal(
        self,
        run_id: str,
        external: CancellationEvent | None = None,
    ) -> CancellationEvent:
        return _CancellationSignal(self._path(run_id, "cancel.json"), external)

    def active_execution(self, run_id: str) -> Mapping[str, object] | None:
        return self._read(run_id, "active.json")

    def run_record(self, run_id: str) -> Mapping[str, object] | None:
        return self._read(run_id, "run.json")

    def list_active_runs(self) -> tuple[Mapping[str, object], ...]:
        if not self.root.is_dir():
            return ()
        records = []
        for directory in sorted(self.root.iterdir(), key=lambda item: item.name):
            if not directory.is_dir() or not _SAFE_ID.fullmatch(directory.name):
                continue
            run = self._read(directory.name, "run.json")
            active = self._read(directory.name, "active.json")
            if run is not None and (
                run.get("status") in _ACTIVE_RUN_STATUSES or active is not None
            ):
                records.append({**run, "active_execution": active})
        return tuple(records)

    def _read(self, run_id: str, name: str) -> dict[str, object] | None:
        path = self._path(run_id, name)
        if not path.is_file() or path.is_symlink():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _write(self, run_id: str, name: str, value: Mapping[str, object]) -> None:
        path = self._path(run_id, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(dict(value), handle, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _path(self, run_id: str, name: str) -> Path:
        safe_run_id = self._safe_id(run_id)
        if name not in {"run.json", "active.json", "cancel.json"}:
            raise ValueError("unsupported runtime control record")
        return self.root / safe_run_id / name

    @staticmethod
    def _safe_id(value: str) -> str:
        if not _SAFE_ID.fullmatch(value) or value in {".", ".."}:
            raise ValueError("unsafe runtime control identifier")
        return value
