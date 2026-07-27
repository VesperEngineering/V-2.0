"""Strict loader for the three native specialist profiles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .contracts import NonEmptyStr, PermissionSet, SpecialistRole

NATIVE_PROFILE_IDS = (
    SpecialistRole.PRODUCT,
    SpecialistRole.DEVELOPMENT,
    SpecialistRole.RISK_REVIEW,
)


class ProfileIntegrityError(RuntimeError):
    """A profile is missing, mismatched, or malformed."""


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_correction_attempts: int = Field(ge=1, le=3)
    infrastructure_failures_consume_correction: bool


class ProfileDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: str = Field(pattern=r"^1\.0$")
    profile_id: SpecialistRole
    system_instructions: NonEmptyStr
    permissions: PermissionSet
    memory_namespace: tuple[NonEmptyStr, ...]
    input_contract: NonEmptyStr
    output_contract: NonEmptyStr
    retry: RetryPolicy
    protected_paths: tuple[NonEmptyStr, ...]
    prohibited_actions: tuple[NonEmptyStr, ...]


class LoadedProfile(ProfileDefinition):
    source_directory: Path
    soul: NonEmptyStr
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    soul_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProfileCatalog:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def load_all(self) -> tuple[LoadedProfile, ...]:
        return tuple(self.load(profile_id) for profile_id in NATIVE_PROFILE_IDS)

    def load(self, profile_id: SpecialistRole) -> LoadedProfile:
        if profile_id not in NATIVE_PROFILE_IDS:
            raise ProfileIntegrityError(f"unsupported native profile: {profile_id}")
        candidate_directory = self.root / profile_id.value
        directory = candidate_directory.resolve()
        if (
            candidate_directory.is_symlink()
            or directory.parent != self.root
            or not directory.is_dir()
        ):
            raise ProfileIntegrityError(
                f"profile directory is missing or unsafe: {profile_id.value}"
            )

        profile_path = directory / "profile.yaml"
        soul_path = directory / "SOUL.md"
        if not profile_path.is_file() or not soul_path.is_file():
            raise ProfileIntegrityError(f"profile files are incomplete: {profile_id.value}")
        profile_bytes = profile_path.read_bytes()
        soul_bytes = soul_path.read_bytes()
        try:
            raw = yaml.safe_load(profile_bytes)
            definition = ProfileDefinition.model_validate_json(json.dumps(raw))
        except (yaml.YAMLError, TypeError, ValidationError, ValueError) as exc:
            raise ProfileIntegrityError(f"profile is malformed: {profile_id.value}") from exc
        if definition.profile_id is not profile_id:
            raise ProfileIntegrityError(
                f"profile directory {profile_id.value} declares {definition.profile_id.value}"
            )
        try:
            soul = soul_bytes.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise ProfileIntegrityError(f"SOUL.md is not UTF-8: {profile_id.value}") from exc
        if not soul:
            raise ProfileIntegrityError(f"SOUL.md is empty: {profile_id.value}")
        return LoadedProfile(
            **definition.model_dump(),
            source_directory=directory,
            soul=soul,
            profile_sha256=hashlib.sha256(profile_bytes).hexdigest(),
            soul_sha256=hashlib.sha256(soul_bytes).hexdigest(),
        )
