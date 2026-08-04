"""Strict native profiles for the five bounded quant agents."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator
from yaml.events import AliasEvent, CollectionEndEvent, CollectionStartEvent

from .contracts import AgentRole, NonEmptyStr

AUTONOMOUS_AGENT_ROLES = (
    AgentRole.QUANT_RESEARCH_LEAD,
    AgentRole.MODEL_RESEARCHER,
    AgentRole.INDEPENDENT_QUANT_VALIDATOR,
    AgentRole.PORTFOLIO_RESEARCHER,
    AgentRole.EXECUTION_PERFORMANCE_ANALYST,
)


class AgentProfileIntegrityError(RuntimeError):
    pass


class AgentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal["1.0"]
    profile_id: AgentRole
    purpose: NonEmptyStr
    model: Literal["qwen:64k"]
    allowed_tools: tuple[Literal["read_file", "search_text"], ...]
    skills: tuple[NonEmptyStr, ...]
    memory_namespace: tuple[NonEmptyStr, NonEmptyStr]
    output_contract: NonEmptyStr
    protected_paths: tuple[NonEmptyStr, ...]
    prohibited_actions: tuple[NonEmptyStr, ...]
    soul: NonEmptyStr
    profile_sha256: str
    soul_sha256: str

    @field_validator("profile_sha256", "soul_sha256")
    @classmethod
    def hash_is_valid(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("profile hashes must be lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def boundaries_are_fixed(self) -> AgentProfile:
        if self.profile_id not in AUTONOMOUS_AGENT_ROLES:
            raise ValueError("profile is not an autonomous quant role")
        if self.memory_namespace != ("agents", self.profile_id.value):
            raise ValueError("agent memory namespace must be role-isolated")
        for path in (*self.skills, *self.protected_paths):
            candidate = Path(path)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError("profile paths must be safe and relative")
        if any(not skill.startswith("knowledge/skills/") for skill in self.skills):
            raise ValueError("only approved repository skills may be injected")
        return self


class AgentProfileCatalog:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def load_all(self) -> tuple[AgentProfile, ...]:
        return tuple(self.load(role) for role in AUTONOMOUS_AGENT_ROLES)

    def load_all_bounded(
        self,
        *,
        max_profile_bytes: int,
        max_soul_bytes: int,
        max_yaml_depth: int,
        max_yaml_events: int,
        max_yaml_aliases: int,
    ) -> tuple[AgentProfile, ...]:
        return tuple(
            self.load_bounded(
                role,
                max_profile_bytes=max_profile_bytes,
                max_soul_bytes=max_soul_bytes,
                max_yaml_depth=max_yaml_depth,
                max_yaml_events=max_yaml_events,
                max_yaml_aliases=max_yaml_aliases,
            )
            for role in AUTONOMOUS_AGENT_ROLES
        )

    def load_bounded(
        self,
        role: AgentRole,
        *,
        max_profile_bytes: int,
        max_soul_bytes: int,
        max_yaml_depth: int,
        max_yaml_events: int,
        max_yaml_aliases: int,
    ) -> AgentProfile:
        for label, value, allow_zero in (
            ("max_profile_bytes", max_profile_bytes, False),
            ("max_soul_bytes", max_soul_bytes, False),
            ("max_yaml_depth", max_yaml_depth, False),
            ("max_yaml_events", max_yaml_events, False),
            ("max_yaml_aliases", max_yaml_aliases, True),
        ):
            if type(value) is not int or value < (0 if allow_zero else 1):
                raise ValueError(f"{label} has an invalid bound")
        directory, profile_path, soul_path = self._paths(role)
        del directory
        try:
            profile_bytes = _read_bounded_regular(
                profile_path,
                max_profile_bytes,
                "profile",
            )
            soul_bytes = _read_bounded_regular(soul_path, max_soul_bytes, "SOUL")
            profile_text = profile_bytes.decode("utf-8")
            soul_text = soul_bytes.decode("utf-8")
            raw = _load_bounded_yaml(
                profile_text,
                max_depth=max_yaml_depth,
                max_events=max_yaml_events,
                max_aliases=max_yaml_aliases,
            )
            return self._build(role, profile_bytes, soul_bytes, soul_text, raw)
        except AgentProfileIntegrityError:
            raise
        except (
            OSError,
            UnicodeDecodeError,
            yaml.YAMLError,
            ValidationError,
            ValueError,
            TypeError,
            RecursionError,
        ) as exc:
            raise AgentProfileIntegrityError(f"profile is malformed: {role.value}") from exc

    def load(self, role: AgentRole) -> AgentProfile:
        _directory, profile_path, soul_path = self._paths(role)
        profile_bytes = profile_path.read_bytes()
        soul_bytes = soul_path.read_bytes()
        try:
            raw = yaml.safe_load(profile_bytes)
            return self._build(
                role,
                profile_bytes,
                soul_bytes,
                soul_bytes.decode("utf-8"),
                raw,
            )
        except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError, ValueError) as exc:
            raise AgentProfileIntegrityError(f"profile is malformed: {role.value}") from exc

    def _paths(self, role: AgentRole) -> tuple[Path, Path, Path]:
        if role not in AUTONOMOUS_AGENT_ROLES:
            raise AgentProfileIntegrityError(f"unsupported autonomous role: {role.value}")
        unresolved_directory = self.root / role.value
        if unresolved_directory.is_symlink():
            raise AgentProfileIntegrityError(
                f"profile directory is missing or unsafe: {role.value}"
            )
        directory = unresolved_directory.resolve()
        if directory.parent != self.root or not directory.is_dir() or directory.is_symlink():
            raise AgentProfileIntegrityError(
                f"profile directory is missing or unsafe: {role.value}"
            )
        profile_path = directory / "profile.yaml"
        soul_path = directory / "SOUL.md"
        if any(path.is_symlink() or not path.is_file() for path in (profile_path, soul_path)):
            raise AgentProfileIntegrityError(f"profile files are incomplete: {role.value}")
        return directory, profile_path, soul_path

    @staticmethod
    def _build(
        role: AgentRole,
        profile_bytes: bytes,
        soul_bytes: bytes,
        soul_text: str,
        raw: object,
    ) -> AgentProfile:
        try:
            if not isinstance(raw, dict):
                raise ValueError("profile must be a mapping")
            profile = AgentProfile.model_validate_json(
                json.dumps(
                    {
                        **raw,
                        "soul": soul_text.strip(),
                        "profile_sha256": hashlib.sha256(profile_bytes).hexdigest(),
                        "soul_sha256": hashlib.sha256(soul_bytes).hexdigest(),
                    }
                )
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise AgentProfileIntegrityError(f"profile is malformed: {role.value}") from exc
        if profile.profile_id is not role:
            raise AgentProfileIntegrityError(
                f"profile directory {role.value} declares {profile.profile_id.value}"
            )
        return profile


def _read_bounded_regular(path: Path, limit: int, label: str) -> bytes:
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or _is_reparse(before):
            raise AgentProfileIntegrityError(f"{label} file is missing or unsafe")
        if before.st_nlink != 1:
            raise AgentProfileIntegrityError(f"{label} file has multiple hard links")
        if before.st_size > limit:
            raise AgentProfileIntegrityError(f"{label} exceeds its size limit")
        signature = _stat_signature(before)
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode) or _stat_signature(opened) != signature:
                raise AgentProfileIntegrityError(f"{label} changed while it was read")
            content = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
            if _stat_signature(after) != signature or len(content) != after.st_size:
                raise AgentProfileIntegrityError(f"{label} changed while it was read")
    except AgentProfileIntegrityError:
        raise
    except OSError as exc:
        raise AgentProfileIntegrityError(f"{label} could not be read safely") from exc
    if len(content) > limit:
        raise AgentProfileIntegrityError(f"{label} exceeds its size limit")
    return content


def _load_bounded_yaml(
    text: str,
    *,
    max_depth: int,
    max_events: int,
    max_aliases: int,
) -> object:
    depth = 0
    event_count = 0
    alias_count = 0
    for event in yaml.parse(text, Loader=yaml.SafeLoader):
        event_count += 1
        if event_count > max_events:
            raise AgentProfileIntegrityError("profile YAML event limit exceeded")
        if isinstance(event, AliasEvent):
            alias_count += 1
            if alias_count > max_aliases:
                raise AgentProfileIntegrityError("profile YAML alias limit exceeded")
        if isinstance(event, CollectionStartEvent):
            depth += 1
            if depth > max_depth:
                raise AgentProfileIntegrityError("profile YAML depth limit exceeded")
        elif isinstance(event, CollectionEndEvent):
            depth -= 1
    if depth != 0:
        raise AgentProfileIntegrityError("profile YAML collection structure is invalid")
    return yaml.safe_load(text)


def _stat_signature(status: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(status.st_dev),
        int(status.st_ino),
        int(status.st_nlink),
        int(status.st_size),
        int(status.st_mtime_ns),
    )


def _is_reparse(status: os.stat_result) -> bool:
    if stat.S_ISLNK(status.st_mode):
        return True
    attributes = getattr(status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)
