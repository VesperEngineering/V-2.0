"""Strict native profiles for the five bounded quant agents."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

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

    def load(self, role: AgentRole) -> AgentProfile:
        if role not in AUTONOMOUS_AGENT_ROLES:
            raise AgentProfileIntegrityError(f"unsupported autonomous role: {role.value}")
        directory = (self.root / role.value).resolve()
        if directory.parent != self.root or not directory.is_dir() or directory.is_symlink():
            raise AgentProfileIntegrityError(
                f"profile directory is missing or unsafe: {role.value}"
            )
        profile_path = directory / "profile.yaml"
        soul_path = directory / "SOUL.md"
        if any(path.is_symlink() or not path.is_file() for path in (profile_path, soul_path)):
            raise AgentProfileIntegrityError(f"profile files are incomplete: {role.value}")
        profile_bytes = profile_path.read_bytes()
        soul_bytes = soul_path.read_bytes()
        try:
            raw = yaml.safe_load(profile_bytes)
            if not isinstance(raw, dict):
                raise ValueError("profile must be a mapping")
            profile = AgentProfile.model_validate_json(
                json.dumps(
                    {
                        **raw,
                        "soul": soul_bytes.decode("utf-8").strip(),
                        "profile_sha256": hashlib.sha256(profile_bytes).hexdigest(),
                        "soul_sha256": hashlib.sha256(soul_bytes).hexdigest(),
                    }
                )
            )
        except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError, ValueError) as exc:
            raise AgentProfileIntegrityError(f"profile is malformed: {role.value}") from exc
        if profile.profile_id is not role:
            raise AgentProfileIntegrityError(
                f"profile directory {role.value} declares {profile.profile_id.value}"
            )
        return profile
