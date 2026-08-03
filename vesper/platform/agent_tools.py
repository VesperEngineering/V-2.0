"""Controller-owned, role-scoped tools for local agents."""

from __future__ import annotations

import hashlib
import os
import subprocess
import uuid
from pathlib import Path
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field

from .contracts import AgentRole, NonEmptyStr

_PROTECTED = (
    Path(".git"),
    Path(".env"),
    Path("AGENTS.md"),
    Path("profiles"),
    Path("vesper/data/massive"),
    Path("vesper/data/model_research"),
    Path("config/settings.yaml"),
    Path("models"),
)


class ToolPermissionError(RuntimeError):
    pass


class AgentToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    name: NonEmptyStr
    arguments: dict[str, str | int | None] = Field(default_factory=dict)


class AgentToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    name: NonEmptyStr
    output: str
    truncated: bool = False


class AgentToolGateway:
    def __init__(self, repository_root: Path, *, max_bytes: int = 64_000) -> None:
        self.root = repository_root.resolve()
        self.max_bytes = max_bytes

    def execute(self, role: AgentRole, request: AgentToolRequest) -> AgentToolResult:
        if request.name == "read_file":
            path = self._safe_path(self._argument(request, "path"), write=False)
            content = path.read_bytes()
            truncated = len(content) > self.max_bytes
            return AgentToolResult(
                name=request.name,
                output=content[: self.max_bytes].decode("utf-8", errors="replace"),
                truncated=truncated,
            )
        if request.name == "search_text":
            needle = self._argument(request, "query")
            matches: list[str] = []
            for path in sorted(self.root.rglob("*")):
                if len(matches) >= 100 or not path.is_file() or path.is_symlink():
                    continue
                try:
                    relative = path.relative_to(self.root)
                    if self._is_protected(relative) or path.stat().st_size > self.max_bytes:
                        continue
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for line_number, line in enumerate(text.splitlines(), start=1):
                    if needle.casefold() in line.casefold():
                        matches.append(f"{relative.as_posix()}:{line_number}:{line[:300]}")
                        if len(matches) >= 100:
                            break
            return AgentToolResult(name=request.name, output="\n".join(matches))
        if request.name == "write_file":
            self._require_development(role)
            path = self._safe_path(self._argument(request, "path"), write=True)
            content = self._argument(request, "content").encode("utf-8")
            expected = request.arguments.get("expected_sha256")
            if path.exists():
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                if expected != actual:
                    raise ToolPermissionError("write expected_sha256 does not match")
            elif expected not in (None, ""):
                raise ToolPermissionError("new file cannot declare an existing hash")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_bytes(content)
                os.replace(temporary, path)
            finally:
                if temporary.exists():
                    temporary.unlink()
            return AgentToolResult(name=request.name, output=hashlib.sha256(content).hexdigest())
        if request.name == "git_diff_check":
            self._require_development(role)
            completed = subprocess.run(
                ["git", "diff", "--check"],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            return AgentToolResult(
                name=request.name,
                output=(completed.stdout + completed.stderr).strip()
                or f"exit={completed.returncode}",
            )
        raise ToolPermissionError(f"unknown agent tool: {request.name}")

    @staticmethod
    def _argument(request: AgentToolRequest, name: str) -> str:
        value = request.arguments.get(name)
        if not isinstance(value, str) or not value:
            raise ToolPermissionError(f"tool argument {name} is required")
        return value

    @staticmethod
    def _require_development(role: AgentRole) -> None:
        if role is not AgentRole.DEVELOPMENT:
            raise ToolPermissionError("tool is Development-only")

    def _safe_path(self, raw: str, *, write: bool) -> Path:
        relative = Path(raw)
        if relative.is_absolute() or ".." in relative.parts:
            raise ToolPermissionError("path must be safe and repository-relative")
        candidate = self.root / relative
        scoped_parents = []
        for parent in candidate.parents:
            if parent == self.root:
                break
            scoped_parents.append(parent)
        if candidate.is_symlink() or any(parent.is_symlink() for parent in scoped_parents):
            raise ToolPermissionError("symlink paths are denied")
        resolved = candidate.resolve(strict=False)
        if resolved != self.root and self.root not in resolved.parents:
            raise ToolPermissionError("path escapes repository")
        if write and self._is_protected(relative):
            raise ToolPermissionError("protected path writes are denied")
        if not write and (not resolved.is_file() or self._is_protected(relative)):
            raise ToolPermissionError("file is missing or protected")
        return resolved

    @staticmethod
    def _is_protected(relative: Path) -> bool:
        normalized = Path(*relative.parts)
        if any(normalized == item or item in normalized.parents for item in _PROTECTED):
            return True
        sensitive_suffixes = {".pem", ".key", ".p12", ".pfx"}
        for part in normalized.parts:
            name = part.casefold()
            if (
                name.startswith(".env")
                or Path(name).suffix in sensitive_suffixes
                or any(marker in name for marker in ("credential", "secret", "api_token"))
            ):
                return True
        return False
