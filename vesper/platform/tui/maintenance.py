"""Receipt-bound policy and orchestration for low-risk local code maintenance."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal, Protocol, Self

from pydantic import field_validator, model_validator

from vesper.platform.ops.activation import (
    ActivationAuthorityError,
    ActivationCapability,
    OperationsActivationStore,
)
from vesper.platform.tui.command_contracts import GitRevision
from vesper.platform.tui.git_port import (
    MaintenanceTransactionReceipt,
    MergeRequest,
    VerificationRequest,
)
from vesper.platform.tui.views import NonEmptyStr, SafeId, Sha256Hex, StrictModel


_FORBIDDEN_SEGMENTS = frozenset(
    {
        ".circleci",
        ".buildkite",
        ".cargo",
        ".github",
        ".gitlab",
        "architecture",
        "architectures",
        "broker",
        "brokers",
        "credentials",
        "credential",
        "model",
        "models",
        "order",
        "orders",
        "portfolio",
        "portfolios",
        "risk",
        "scheduler",
        "schedulers",
        "schedules",
        "secret",
        "secrets",
        "training",
    }
)
_FORBIDDEN_FILENAMES = frozenset(
    {
        "agents.md",
        "cargo.lock",
        "cargo.toml",
        "composer.json",
        "composer.lock",
        ".gitmodules",
        "package-lock.json",
        "package.json",
        "pipfile",
        "pipfile.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        "tox.ini",
        "uv.lock",
        "yarn.lock",
    }
)
_FORBIDDEN_PREFIXES = (
    ("vesper", "data", "massive"),
    ("vesper", "data", "model_research"),
)
_FORBIDDEN_SUFFIXES = (".key", ".pem", ".pfx", ".p12")
_WINDOWS_RESERVED_NAMES = frozenset(
    {"aux", "con", "nul", "prn"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)


class AutomaticMergeReceiptStore(Protocol):
    def require_automatic_merge(
        self,
        receipt_id: str,
        repository_root: Path,
        expected_base_revision: str,
        candidate_revision: str,
        diff_hash: str,
    ) -> None: ...


class MaintenanceReviewReceiptStore(Protocol):
    def require_maintenance_review(
        self,
        receipt_id: str,
        author_id: str,
        reviewer_id: str,
        repository_root: Path,
        expected_base_revision: str,
        candidate_revision: str,
        diff_hash: str,
    ) -> None: ...


MaintenanceGateName = Literal[
    "focused-tests",
    "broad-tests",
    "formatting",
    "static-analysis",
]


class MaintenanceVerificationReceiptStore(Protocol):
    def require_maintenance_verification(
        self,
        receipt_id: str,
        gate_name: MaintenanceGateName,
        repository_root: Path,
        candidate_revision: str,
        diff_hash: str,
        passed: bool,
    ) -> None: ...


class BoundCheck(StrictModel):
    passed: bool
    receipt_id: SafeId
    revision: GitRevision
    diff_hash: Sha256Hex


class BoundReview(StrictModel):
    approved: bool
    reviewer_id: SafeId
    review_receipt_id: SafeId
    revision: GitRevision
    diff_hash: Sha256Hex


class MaintenanceCandidate(StrictModel):
    repository_root: Path
    worktree_root: Path
    expected_base_revision: GitRevision
    observed_base_revision: GitRevision
    candidate_revision: GitRevision
    author_id: SafeId
    changed_paths: tuple[NonEmptyStr, ...]
    diff_hash: Sha256Hex
    review: BoundReview | None
    focused_tests: BoundCheck
    broad_tests: BoundCheck
    formatting: BoundCheck
    static_analysis: BoundCheck
    rollback_revision: GitRevision | None
    main_clean: bool
    merge_lock_available: bool

    @field_validator("changed_paths")
    @classmethod
    def require_unique_changed_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) > 256:
            raise ValueError("changed paths must contain 1 to 256 entries")
        if tuple(sorted(set(value))) != value or len({path.casefold() for path in value}) != len(
            value
        ):
            raise ValueError("changed paths must be unique and sorted")
        return value

    @model_validator(mode="after")
    def require_unique_verification_receipts(self) -> Self:
        receipt_ids = (
            self.focused_tests.receipt_id,
            self.broad_tests.receipt_id,
            self.formatting.receipt_id,
            self.static_analysis.receipt_id,
        )
        if len(set(receipt_ids)) != len(receipt_ids):
            raise ValueError("verification receipt ids must be unique")
        return self


class MaintenanceDecision(StrictModel):
    allowed: bool
    reason: NonEmptyStr
    activation_receipt_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def bind_receipt_to_allowed_decision(self) -> Self:
        if self.allowed != (self.activation_receipt_id is not None):
            raise ValueError("allowed maintenance decision must bind one receipt")
        return self

    @classmethod
    def reject(cls, reason: str) -> MaintenanceDecision:
        return cls(allowed=False, reason=reason)


class MaintenanceRunReceipt(StrictModel):
    accepted: bool
    merged: bool
    reverted: bool
    reason: NonEmptyStr
    merge_revision: GitRevision | None
    final_revision: GitRevision | None


class MaintenanceGitPort(Protocol):
    def merge_verify_revert(
        self,
        request: MergeRequest,
        post_merge_verification: VerificationRequest,
    ) -> MaintenanceTransactionReceipt: ...


class MaintenancePolicy:
    """Fail closed unless one exact low-risk diff has complete evidence."""

    def __init__(
        self,
        activation_store: OperationsActivationStore,
        authority_receipts: AutomaticMergeReceiptStore,
        review_receipts: MaintenanceReviewReceiptStore,
        verification_receipts: MaintenanceVerificationReceiptStore,
        *,
        allowed_globs: tuple[str, ...],
    ) -> None:
        if type(activation_store) is not OperationsActivationStore:
            raise TypeError("activation_store must be OperationsActivationStore")
        self._activation_store = activation_store
        self._authority_receipts = authority_receipts
        self._review_receipts = review_receipts
        self._verification_receipts = verification_receipts
        self._allowed_patterns = tuple(_compile_low_risk_glob(pattern) for pattern in allowed_globs)
        if not self._allowed_patterns:
            raise ValueError("at least one explicit low-risk glob is required")

    def evaluate(self, candidate: MaintenanceCandidate) -> MaintenanceDecision:
        if type(candidate) is not MaintenanceCandidate:
            return MaintenanceDecision.reject("invalid-maintenance-candidate")
        if not candidate.main_clean:
            return MaintenanceDecision.reject(
                "Automatic merge is disabled because main is not clean."
            )
        if candidate.observed_base_revision != candidate.expected_base_revision:
            return MaintenanceDecision.reject("base-revision-mismatch")
        if candidate.review is None:
            return MaintenanceDecision.reject("review-missing")
        if not candidate.review.approved:
            return MaintenanceDecision.reject("review-not-approved")
        if candidate.review.reviewer_id == candidate.author_id:
            return MaintenanceDecision.reject("reviewer-not-independent")
        for name, evidence in (
            ("focused-tests", candidate.focused_tests),
            ("broad-tests", candidate.broad_tests),
            ("formatting", candidate.formatting),
            ("static-analysis", candidate.static_analysis),
        ):
            if not evidence.passed:
                return MaintenanceDecision.reject(f"{name}-failed")
        for name, evidence in (
            ("review", candidate.review),
            ("focused-tests", candidate.focused_tests),
            ("broad-tests", candidate.broad_tests),
            ("formatting", candidate.formatting),
            ("static-analysis", candidate.static_analysis),
        ):
            if (
                evidence.revision != candidate.candidate_revision
                or evidence.diff_hash != candidate.diff_hash
            ):
                return MaintenanceDecision.reject(f"{name}-binding-mismatch")
        if candidate.rollback_revision is None:
            return MaintenanceDecision.reject("rollback-revision-missing")
        if candidate.rollback_revision != candidate.expected_base_revision:
            return MaintenanceDecision.reject("rollback-revision-mismatch")
        if not candidate.merge_lock_available:
            return MaintenanceDecision.reject("merge-lock-held")
        path_reason = self._path_rejection(candidate)
        if path_reason is not None:
            return MaintenanceDecision.reject(path_reason)
        try:
            self._review_receipts.require_maintenance_review(
                candidate.review.review_receipt_id,
                candidate.author_id,
                candidate.review.reviewer_id,
                candidate.repository_root.resolve(strict=True),
                candidate.expected_base_revision,
                candidate.candidate_revision,
                candidate.diff_hash,
            )
        except Exception:
            return MaintenanceDecision.reject("review-authority-invalid")
        for name, evidence in (
            ("focused-tests", candidate.focused_tests),
            ("broad-tests", candidate.broad_tests),
            ("formatting", candidate.formatting),
            ("static-analysis", candidate.static_analysis),
        ):
            try:
                self._verification_receipts.require_maintenance_verification(
                    evidence.receipt_id,
                    name,
                    candidate.repository_root.resolve(strict=True),
                    candidate.candidate_revision,
                    candidate.diff_hash,
                    evidence.passed,
                )
            except Exception:
                return MaintenanceDecision.reject(f"{name}-authority-invalid")
        try:
            grant = self._activation_store.validated_grant(ActivationCapability.AUTOMATIC_MERGE)
        except (ActivationAuthorityError, TypeError, AttributeError):
            return MaintenanceDecision.reject("automatic-merge-authority-invalid")
        if not grant.enabled:
            return MaintenanceDecision.reject("automatic-merge-disabled")
        if grant.receipt_id is None:
            return MaintenanceDecision.reject("automatic-merge-authority-invalid")
        try:
            self._authority_receipts.require_automatic_merge(
                grant.receipt_id,
                candidate.repository_root.resolve(strict=True),
                candidate.expected_base_revision,
                candidate.candidate_revision,
                candidate.diff_hash,
            )
        except Exception:
            return MaintenanceDecision.reject("automatic-merge-receipt-mismatch")
        return MaintenanceDecision(
            allowed=True,
            reason="maintenance-approved",
            activation_receipt_id=grant.receipt_id,
        )

    def _path_rejection(self, candidate: MaintenanceCandidate) -> str | None:
        try:
            worktree = candidate.worktree_root.resolve(strict=True)
        except OSError:
            return "unsafe-maintenance-path"
        if candidate.worktree_root.is_symlink() or not worktree.is_dir():
            return "unsafe-maintenance-path"
        for relative in candidate.changed_paths:
            if not _is_canonical_relative_path(relative):
                return "unsafe-maintenance-path"
            parts = tuple(part.lower() for part in PurePosixPath(relative).parts)
            if _is_forbidden(parts):
                return "forbidden-maintenance-path"
            if not any(pattern.fullmatch(relative) for pattern in self._allowed_patterns):
                return "maintenance-path-not-allowed"
            if not _path_stays_below_unsymlinked_root(candidate.worktree_root, relative):
                return "unsafe-maintenance-path"
        return None


class MaintenanceService:
    """Merge one approved candidate and revert once if the final checks fail."""

    def __init__(self, policy: MaintenancePolicy, git: MaintenanceGitPort) -> None:
        self._policy = policy
        self._git = git

    def merge(
        self,
        candidate: MaintenanceCandidate,
        *,
        post_merge_verification: VerificationRequest,
    ) -> MaintenanceRunReceipt:
        decision = self._policy.evaluate(candidate)
        if not decision.allowed:
            return MaintenanceRunReceipt(
                accepted=False,
                merged=False,
                reverted=False,
                reason=decision.reason,
                merge_revision=None,
                final_revision=None,
            )
        try:
            repository_root = candidate.repository_root.resolve(strict=True)
            verification_root = post_merge_verification.worktree.resolve(strict=False)
        except OSError:
            return MaintenanceRunReceipt(
                accepted=False,
                merged=False,
                reverted=False,
                reason="post-merge-verification-worktree-invalid",
                merge_revision=None,
                final_revision=None,
            )
        if verification_root == repository_root:
            return MaintenanceRunReceipt(
                accepted=False,
                merged=False,
                reverted=False,
                reason="post-merge-verification-must-be-isolated",
                merge_revision=None,
                final_revision=None,
            )
        transaction = self._git.merge_verify_revert(
            MergeRequest(
                repository_root=candidate.repository_root,
                expected_base_revision=candidate.expected_base_revision,
                candidate_revision=candidate.candidate_revision,
                reviewed_diff_hash=candidate.diff_hash,
                rollback_revision=candidate.rollback_revision,
                changed_paths=candidate.changed_paths,
            ),
            post_merge_verification,
        )
        merged = transaction.merge
        if merged is None or not merged.accepted or merged.revision is None:
            return MaintenanceRunReceipt(
                accepted=False,
                merged=False,
                reverted=False,
                reason=transaction.code,
                merge_revision=None if merged is None else merged.revision,
                final_revision=None if merged is None else merged.revision,
            )
        verified = transaction.verification
        reverted = transaction.revert
        if (
            transaction.accepted
            and verified is not None
            and verified.accepted
            and verified.revision == merged.revision
            and reverted is None
        ):
            return MaintenanceRunReceipt(
                accepted=True,
                merged=True,
                reverted=False,
                reason="maintenance-merged",
                merge_revision=merged.revision,
                final_revision=verified.revision,
            )
        did_revert = reverted is not None and reverted.accepted
        return MaintenanceRunReceipt(
            accepted=False,
            merged=True,
            reverted=did_revert,
            reason=transaction.code,
            merge_revision=merged.revision,
            final_revision=(
                reverted.revision
                if reverted is not None
                else (verified.revision if verified is not None else merged.revision)
            ),
        )


def _compile_low_risk_glob(pattern: str) -> re.Pattern[str]:
    pattern_parts = PurePosixPath(pattern).parts if type(pattern) is str else ()
    fixed_prefix = tuple(
        part for part in pattern_parts if not any(mark in part for mark in ("*", "?"))
    )
    first_dynamic = next(
        (
            index
            for index, part in enumerate(pattern_parts)
            if any(mark in part for mark in ("*", "?"))
        ),
        len(pattern_parts),
    )
    if (
        type(pattern) is not str
        or not pattern
        or pattern != pattern.strip()
        or "\\" in pattern
        or pattern.startswith(("/", "-"))
        or "/" not in pattern
        or ".." in PurePosixPath(pattern).parts
        or pattern in {"*", "**", "**/*"}
        or first_dynamic < 2
        or len(fixed_prefix) < 2
    ):
        raise ValueError("low-risk glob must be explicit and canonical")
    expression = ""
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                expression += ".*"
                index += 2
            else:
                expression += "[^/]*"
                index += 1
        elif character == "?":
            expression += "[^/]"
            index += 1
        else:
            expression += re.escape(character)
            index += 1
    return re.compile(expression)


def _is_canonical_relative_path(value: str) -> bool:
    windows = PureWindowsPath(value)
    posix = PurePosixPath(value)
    windows_parts = windows.parts
    return not (
        value != value.strip()
        or "\\" in value
        or windows.is_absolute()
        or posix.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or bool(windows.anchor)
        or not posix.parts
        or "." in posix.parts
        or ".." in posix.parts
        or value != posix.as_posix()
        or any(part != part.rstrip(" .") for part in windows_parts)
        or any(
            ":" in part or any(ord(character) < 32 for character in part) for part in windows_parts
        )
        or any(
            part.split(".", 1)[0].casefold() in _WINDOWS_RESERVED_NAMES for part in windows_parts
        )
    )


def _is_forbidden(parts: tuple[str, ...]) -> bool:
    if not parts:
        return True
    filename = parts[-1]
    stem = PurePosixPath(filename).stem
    if any(parts[: len(prefix)] == prefix for prefix in _FORBIDDEN_PREFIXES):
        return True
    if any(part in _FORBIDDEN_SEGMENTS for part in parts):
        return True
    if stem in _FORBIDDEN_SEGMENTS:
        return True
    if any(token in _FORBIDDEN_SEGMENTS for token in re.split(r"[_\-.]+", stem)):
        return True
    if filename in _FORBIDDEN_FILENAMES:
        return True
    if filename.startswith((".env", "requirements")):
        return True
    if filename.endswith(_FORBIDDEN_SUFFIXES):
        return True
    if filename in {
        ".gitlab-ci.yml",
        ".travis.yml",
        "appveyor.yml",
        "azure-pipelines.yml",
        "jenkinsfile",
    }:
        return True
    return False


def _path_stays_below_unsymlinked_root(root: Path, relative: str) -> bool:
    try:
        root_resolved = root.resolve(strict=True)
        current = root
        if current.is_symlink():
            return False
        for part in PurePosixPath(relative).parts:
            current = current / part
            if current.exists() or current.is_symlink():
                if current.is_symlink():
                    return False
        return current.resolve(strict=False).is_relative_to(root_resolved)
    except OSError:
        return False
