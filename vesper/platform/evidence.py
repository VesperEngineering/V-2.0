"""Immutable, hash-verified filesystem evidence storage."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from .contracts import EvidenceArtifactRef, RunManifest

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_SUFFIX = re.compile(r"^\.[A-Za-z0-9]+$")


class EvidenceError(RuntimeError):
    """Base error for evidence integrity failures."""


class DuplicateEvidenceError(EvidenceError):
    """An immutable evidence identifier already has different content."""


class CorruptEvidenceError(EvidenceError):
    """Stored evidence no longer matches its authoritative hash or schema."""


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _require_safe_segment(value: str, label: str) -> str:
    if not _SAFE_SEGMENT.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"unsafe {label}: {value!r}")
    return value


class FilesystemEvidenceStore:
    """Write immutable artifacts below an explicitly supplied local root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()

    def put_bytes(
        self,
        *,
        run_id: str,
        task_id: str,
        repository_revision: str,
        created_at,
        artifact_id: str,
        body: bytes,
        media_type: str,
        suffix: str = ".bin",
    ) -> EvidenceArtifactRef:
        _require_safe_segment(run_id, "run ID")
        _require_safe_segment(artifact_id, "artifact ID")
        if not _SAFE_SUFFIX.fullmatch(suffix):
            raise ValueError(f"unsafe artifact suffix: {suffix!r}")
        relative = PurePosixPath("runs", run_id, f"{artifact_id}{suffix}")
        digest = _sha256(body)

        with self._write_lock:
            path = self._path_for(relative.as_posix())
            self._create_immutable(path, body, digest)

        return EvidenceArtifactRef(
            run_id=run_id,
            task_id=task_id,
            repository_revision=repository_revision,
            created_at=created_at,
            artifact_id=artifact_id,
            relative_path=relative.as_posix(),
            sha256=digest,
            size_bytes=len(body),
            media_type=media_type,
        )

    def read_verified(self, ref: EvidenceArtifactRef) -> bytes:
        path = self._path_for(ref.relative_path)
        if path.is_symlink() or not path.is_file():
            raise CorruptEvidenceError(f"artifact is missing or unsafe: {ref.artifact_id}")
        body = path.read_bytes()
        if len(body) != ref.size_bytes or _sha256(body) != ref.sha256:
            raise CorruptEvidenceError(f"artifact hash mismatch: {ref.artifact_id}")
        return body

    def write_manifest(self, manifest: RunManifest) -> EvidenceArtifactRef:
        _require_safe_segment(manifest.run_id, "run ID")
        body = manifest.model_dump_json(indent=2).encode("utf-8") + b"\n"
        relative = PurePosixPath("runs", manifest.run_id, "manifest.json")
        digest = _sha256(body)

        with self._write_lock:
            path = self._path_for(relative.as_posix())
            hash_path = path.with_suffix(".json.sha256")
            self._create_immutable(path, body, digest)
            self._create_immutable(
                hash_path, f"{digest}\n".encode("ascii"), _sha256(f"{digest}\n".encode("ascii"))
            )

        return EvidenceArtifactRef(
            run_id=manifest.run_id,
            task_id=manifest.task_id,
            repository_revision=manifest.repository_revision,
            created_at=manifest.created_at,
            artifact_id="manifest",
            relative_path=relative.as_posix(),
            sha256=digest,
            size_bytes=len(body),
            media_type="application/json",
        )

    def read_manifest(self, run_id: str) -> RunManifest:
        _require_safe_segment(run_id, "run ID")
        path = self._path_for(PurePosixPath("runs", run_id, "manifest.json").as_posix())
        hash_path = path.with_suffix(".json.sha256")
        if (
            path.is_symlink()
            or hash_path.is_symlink()
            or not path.is_file()
            or not hash_path.is_file()
        ):
            raise CorruptEvidenceError(f"manifest is missing or unsafe: {run_id}")
        body = path.read_bytes()
        expected = hash_path.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or _sha256(body) != expected:
            raise CorruptEvidenceError(f"manifest hash mismatch: {run_id}")
        try:
            manifest = RunManifest.model_validate_json(body)
        except (ValidationError, ValueError) as exc:
            raise CorruptEvidenceError(f"manifest schema is invalid: {run_id}") from exc
        if manifest.run_id != run_id:
            raise CorruptEvidenceError(f"manifest run ID mismatch: {run_id}")
        return manifest

    def _path_for(self, relative_path: str) -> Path:
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise ValueError(f"artifact path must be repository-relative: {relative_path!r}")
        path = self.root.joinpath(*pure.parts)
        resolved_parent = path.parent.resolve()
        if not resolved_parent.is_relative_to(self.root):
            raise ValueError(f"artifact path escapes evidence root: {relative_path!r}")
        return path

    @staticmethod
    def _create_immutable(path: Path, body: bytes, digest: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.is_symlink() or not path.is_file() or _sha256(path.read_bytes()) != digest:
                raise DuplicateEvidenceError(
                    f"artifact already exists with different content: {path.name}"
                )
            return

        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.is_symlink() or not path.is_file() or _sha256(path.read_bytes()) != digest:
                    raise DuplicateEvidenceError(
                        f"artifact already exists with different content: {path.name}"
                    )
        finally:
            temporary.unlink(missing_ok=True)
