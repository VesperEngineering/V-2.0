"""Read configured native-agent facts without opening runtime persistence."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from vesper.platform.agent_profiles import (
    AUTONOMOUS_AGENT_ROLES,
    AgentProfileCatalog,
    AgentProfileIntegrityError,
)
from vesper.platform.tui.ports import (
    AgentFacts,
    ConfiguredAgentFact,
    OrderFacts,
    PortfolioFacts,
    SourceSample,
    UnavailablePort,
)
from vesper.platform.tui.views import Freshness


_ACTIVE_WORK_UNAVAILABLE = "No bounded read-only active-work source is configured."
_CLOCK_UNAVAILABLE = "Native projection clock did not return UTC."
_PROFILE_ROOT_UNAVAILABLE = "Configured native profile root is unavailable or unsafe."
_PROFILE_CONTENT_UNAVAILABLE = "Configured native agent profiles are unavailable or invalid."
_MAX_PROFILE_BYTES = 64 * 1024
_MAX_SOUL_BYTES = 64 * 1024
_MAX_YAML_DEPTH = 16
_MAX_YAML_EVENTS = 512
_MAX_YAML_ALIASES = 0
_MODULE_REPOSITORY_ROOT = Path(__file__).parents[4]
_PROTECTED_SEQUENCES = (
    ("vesper", "data", "massive"),
    ("vesper", "data", "model_research"),
)


class _UnsafeProfileRoot(RuntimeError):
    pass


class NativePlatformProjection:
    """Project only the five configured Qwen profiles.

    Runtime work, persistence, approvals, journals, evidence, and controller state
    intentionally stay outside this adapter.
    """

    def __init__(
        self,
        repository_root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository_root = Path(os.path.abspath(repository_root))
        self._profile_root = self._repository_root / "profiles" / "native"
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.portfolio_port: UnavailablePort[PortfolioFacts] = UnavailablePort(
            "No typed reconciled portfolio source is configured.",
            source="native platform",
        )
        self.order_port: UnavailablePort[OrderFacts] = UnavailablePort(
            "No controller-owned typed order source is configured.",
            source="native platform",
        )

    def read(self) -> SourceSample[AgentFacts]:
        try:
            observed_at = self._utc_now()
        except Exception:
            return self._unavailable(_CLOCK_UNAVAILABLE)
        try:
            profile_root = self._validated_profile_root()
        except _UnsafeProfileRoot:
            return self._unavailable(_PROFILE_ROOT_UNAVAILABLE)
        try:
            catalog = AgentProfileCatalog(profile_root)
            if _normalized_path(catalog.root) != _normalized_path(profile_root):
                return self._unavailable(_PROFILE_ROOT_UNAVAILABLE)
            profiles = catalog.load_all_bounded(
                max_profile_bytes=_MAX_PROFILE_BYTES,
                max_soul_bytes=_MAX_SOUL_BYTES,
                max_yaml_depth=_MAX_YAML_DEPTH,
                max_yaml_events=_MAX_YAML_EVENTS,
                max_yaml_aliases=_MAX_YAML_ALIASES,
            )
            roster = tuple(
                ConfiguredAgentFact(
                    agent_id=profile.profile_id.value,
                    purpose=profile.purpose,
                    model=profile.model,
                    skills=profile.skills,
                )
                for profile in profiles
            )
            facts = AgentFacts(
                configured_roster=roster,
                active_work=None,
                active_work_error=_ACTIVE_WORK_UNAVAILABLE,
            )
            return SourceSample[AgentFacts](
                value=facts,
                freshness=Freshness.FRESH,
                observed_at_utc=observed_at,
                source="native agent profile catalog",
                error=None,
            )
        except (
            AgentProfileIntegrityError,
            OSError,
            RuntimeError,
            ValidationError,
            ValueError,
        ):
            return self._unavailable(_PROFILE_CONTENT_UNAVAILABLE)

    def _utc_now(self) -> datetime:
        observed_at = self._clock()
        if (
            not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("clock did not return UTC")
        return observed_at

    def _validated_profile_root(self) -> Path:
        expected_root = Path(os.path.abspath(_MODULE_REPOSITORY_ROOT))
        if _normalized_path(self._repository_root) != _normalized_path(expected_root):
            raise _UnsafeProfileRoot("repository root differs from the loaded V20 module")
        if _has_protected_sequence(self._repository_root) or _has_protected_sequence(
            self._profile_root
        ):
            raise _UnsafeProfileRoot("profile root targets protected data")

        expected_paths: list[tuple[Path, bool]] = [
            (self._repository_root, True),
            (self._repository_root / "profiles", True),
            (self._profile_root, True),
        ]
        for role in AUTONOMOUS_AGENT_ROLES:
            role_root = self._profile_root / role.value
            expected_paths.extend(
                (
                    (role_root, True),
                    (role_root / "profile.yaml", False),
                    (role_root / "SOUL.md", False),
                )
            )
        try:
            for path, is_directory in expected_paths:
                status = path.lstat()
                expected_type = (
                    stat.S_ISDIR(status.st_mode)
                    if is_directory
                    else stat.S_ISREG(status.st_mode)
                )
                if (
                    _is_reparse(status)
                    or not expected_type
                    or (not is_directory and status.st_nlink != 1)
                ):
                    raise _UnsafeProfileRoot("profile path is missing or unsafe")

            repository_root = self._repository_root.resolve(strict=True)
            expected_canonical_root = expected_root.resolve(strict=True)
            profile_root = self._profile_root.resolve(strict=True)
            if _normalized_path(repository_root) != _normalized_path(
                expected_canonical_root
            ):
                raise _UnsafeProfileRoot("repository root canonical path changed")
            profile_root.relative_to(repository_root)
            if _has_protected_sequence(repository_root) or _has_protected_sequence(
                profile_root
            ):
                raise _UnsafeProfileRoot("profile root resolves into protected data")
            for path, _is_directory in expected_paths[3:]:
                canonical = path.resolve(strict=True)
                canonical.relative_to(repository_root)
                if _has_protected_sequence(canonical):
                    raise _UnsafeProfileRoot("profile path resolves into protected data")
        except _UnsafeProfileRoot:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise _UnsafeProfileRoot("profile root cannot be verified") from exc
        return profile_root

    @staticmethod
    def _unavailable(reason: str) -> SourceSample[AgentFacts]:
        return SourceSample[AgentFacts](
            value=None,
            freshness=Freshness.UNAVAILABLE,
            observed_at_utc=None,
            source="native agent profile catalog",
            error=reason,
        )


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _has_protected_sequence(path: Path) -> bool:
    parts = tuple(part.casefold() for part in path.parts)
    return any(
        parts[index : index + len(sequence)] == sequence
        for sequence in _PROTECTED_SEQUENCES
        for index in range(len(parts))
    )


def _is_reparse(status: os.stat_result) -> bool:
    if stat.S_ISLNK(status.st_mode):
        return True
    attributes = getattr(status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)
