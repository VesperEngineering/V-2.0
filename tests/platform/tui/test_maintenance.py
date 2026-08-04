from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from vesper.platform.ops.activation import (
    ActivationAuthorityError,
    ActivationCapability,
    ActivationGrant,
    OperationsActivation,
    OperationsActivationStore,
)
from vesper.platform.tui.git_port import (
    GitReceipt,
    MaintenanceTransactionReceipt,
    VerificationRequest,
)
from vesper.platform.tui.maintenance import (
    BoundCheck,
    BoundReview,
    MaintenanceCandidate,
    MaintenancePolicy,
    MaintenanceService,
)


BASE_REVISION = "a" * 40
CANDIDATE_REVISION = "b" * 40
DIFF_HASH = "c" * 64
MERGE_REVISION = "d" * 40
RECEIPT_ID = "receipt:automatic-merge"
REVIEW_RECEIPT_ID = "receipt:maintenance-review"
AUTHOR_ID = "v20-author"
REVIEWER_ID = "v20-reviewer"
CHECK_RECEIPT_IDS = {
    "focused-tests": "receipt:focused-tests",
    "broad-tests": "receipt:broad-tests",
    "formatting": "receipt:formatting",
    "static-analysis": "receipt:static-analysis",
}
LOW_RISK_GLOBS = ("vesper/platform/tui/*.py", "tests/platform/tui/*.py")


class ActivationReceipts:
    def __init__(self, expected: str = RECEIPT_ID) -> None:
        self.expected = expected

    def require(self, capability: ActivationCapability, receipt_id: str) -> None:
        if capability is not ActivationCapability.AUTOMATIC_MERGE:
            raise ActivationAuthorityError("wrong capability")
        if receipt_id != self.expected:
            raise ActivationAuthorityError("receipt mismatch")


class MergeReceipts:
    def __init__(self, expected: tuple[object, ...] | None = None) -> None:
        self.expected = expected
        self.calls: list[tuple[object, ...]] = []

    def require_automatic_merge(
        self,
        receipt_id: str,
        repository_root: Path,
        expected_base_revision: str,
        candidate_revision: str,
        diff_hash: str,
    ) -> None:
        call = (
            receipt_id,
            repository_root.resolve(),
            expected_base_revision,
            candidate_revision,
            diff_hash,
        )
        self.calls.append(call)
        if self.expected is not None and call != self.expected:
            raise ActivationAuthorityError("merge receipt mismatch")


class ReviewReceipts:
    def __init__(self, expected: tuple[object, ...] | None = None) -> None:
        self.expected = expected
        self.calls: list[tuple[object, ...]] = []

    def require_maintenance_review(
        self,
        receipt_id: str,
        author_id: str,
        reviewer_id: str,
        repository_root: Path,
        expected_base_revision: str,
        candidate_revision: str,
        diff_hash: str,
    ) -> None:
        call = (
            receipt_id,
            author_id,
            reviewer_id,
            repository_root.resolve(),
            expected_base_revision,
            candidate_revision,
            diff_hash,
        )
        self.calls.append(call)
        if self.expected is not None and call != self.expected:
            raise ActivationAuthorityError("review receipt mismatch")


class VerificationReceipts:
    def __init__(self, expected: dict[str, tuple[object, ...]] | None = None) -> None:
        self.expected = expected
        self.calls: list[tuple[object, ...]] = []

    def require_maintenance_verification(
        self,
        receipt_id: str,
        gate_name: str,
        repository_root: Path,
        candidate_revision: str,
        diff_hash: str,
        passed: bool,
    ) -> None:
        call = (
            receipt_id,
            gate_name,
            repository_root.resolve(),
            candidate_revision,
            diff_hash,
            passed,
        )
        self.calls.append(call)
        if self.expected is not None and self.expected.get(receipt_id) != call:
            raise ActivationAuthorityError("verification receipt mismatch")


def _activation_store(
    *, enabled: bool = True, receipt_id: str = RECEIPT_ID, expected: str = RECEIPT_ID
) -> OperationsActivationStore:
    grant = ActivationGrant(enabled=True, receipt_id=receipt_id) if enabled else ActivationGrant()
    return OperationsActivationStore(
        OperationsActivation(automatic_merge=grant),
        ActivationReceipts(expected),
    )


def _bound_check(
    gate_name: str = "focused-tests",
    *,
    passed: bool = True,
    diff_hash: str = DIFF_HASH,
) -> BoundCheck:
    return BoundCheck(
        passed=passed,
        receipt_id=CHECK_RECEIPT_IDS[gate_name],
        revision=CANDIDATE_REVISION,
        diff_hash=diff_hash,
    )


def _candidate(tmp_path: Path, **changes: object) -> MaintenanceCandidate:
    repository = tmp_path / "repo"
    worktree = tmp_path / "candidate"
    repository.mkdir(exist_ok=True)
    target = worktree / "vesper" / "platform" / "tui" / "safe_fix.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    values: dict[str, object] = {
        "repository_root": repository,
        "worktree_root": worktree,
        "expected_base_revision": BASE_REVISION,
        "observed_base_revision": BASE_REVISION,
        "candidate_revision": CANDIDATE_REVISION,
        "author_id": AUTHOR_ID,
        "changed_paths": ("vesper/platform/tui/safe_fix.py",),
        "diff_hash": DIFF_HASH,
        "review": BoundReview(
            approved=True,
            reviewer_id=REVIEWER_ID,
            review_receipt_id=REVIEW_RECEIPT_ID,
            revision=CANDIDATE_REVISION,
            diff_hash=DIFF_HASH,
        ),
        "focused_tests": _bound_check("focused-tests"),
        "broad_tests": _bound_check("broad-tests"),
        "formatting": _bound_check("formatting"),
        "static_analysis": _bound_check("static-analysis"),
        "rollback_revision": BASE_REVISION,
        "main_clean": True,
        "merge_lock_available": True,
    }
    values.update(changes)
    return MaintenanceCandidate(**values)


def _policy(
    tmp_path: Path,
    *,
    activation_store: OperationsActivationStore | None = None,
    merge_receipts: MergeReceipts | None = None,
    review_receipts: ReviewReceipts | None = None,
    verification_receipts: VerificationReceipts | None = None,
) -> tuple[MaintenancePolicy, MaintenanceCandidate, MergeReceipts]:
    candidate = _candidate(tmp_path)
    receipts = merge_receipts or MergeReceipts(
        (
            RECEIPT_ID,
            candidate.repository_root.resolve(),
            BASE_REVISION,
            CANDIDATE_REVISION,
            DIFF_HASH,
        )
    )
    policy = MaintenancePolicy(
        activation_store or _activation_store(),
        receipts,
        review_receipts
        or ReviewReceipts(
            (
                REVIEW_RECEIPT_ID,
                AUTHOR_ID,
                REVIEWER_ID,
                candidate.repository_root.resolve(),
                BASE_REVISION,
                CANDIDATE_REVISION,
                DIFF_HASH,
            )
        ),
        verification_receipts or _verification_receipts(candidate),
        allowed_globs=LOW_RISK_GLOBS,
    )
    return policy, candidate, receipts


def _verification_receipts(candidate: MaintenanceCandidate) -> VerificationReceipts:
    repository = candidate.repository_root.resolve()
    return VerificationReceipts(
        {
            receipt_id: (
                receipt_id,
                gate_name,
                repository,
                CANDIDATE_REVISION,
                DIFF_HASH,
                True,
            )
            for gate_name, receipt_id in CHECK_RECEIPT_IDS.items()
        }
    )


def test_bound_check_requires_trusted_receipt_id() -> None:
    with pytest.raises(ValidationError, match="receipt_id"):
        BoundCheck(
            passed=True,
            revision=CANDIDATE_REVISION,
            diff_hash=DIFF_HASH,
        )


def test_clean_reviewed_low_risk_candidate_is_allowed(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    review_receipts = ReviewReceipts(
        (
            REVIEW_RECEIPT_ID,
            AUTHOR_ID,
            REVIEWER_ID,
            candidate.repository_root.resolve(),
            BASE_REVISION,
            CANDIDATE_REVISION,
            DIFF_HASH,
        )
    )
    verification_receipts = _verification_receipts(candidate)
    policy, candidate, receipts = _policy(
        tmp_path,
        review_receipts=review_receipts,
        verification_receipts=verification_receipts,
    )

    decision = policy.evaluate(candidate)

    assert decision.allowed is True
    assert decision.reason == "maintenance-approved"
    assert receipts.calls == [receipts.expected]
    assert review_receipts.calls == [review_receipts.expected]
    assert verification_receipts.calls == list(verification_receipts.expected.values())


def test_author_cannot_approve_own_maintenance_candidate(tmp_path: Path) -> None:
    policy, candidate, merge_receipts = _policy(tmp_path)
    assert candidate.review is not None
    self_review = candidate.review.model_copy(update={"reviewer_id": candidate.author_id})

    decision = policy.evaluate(candidate.model_copy(update={"review": self_review}))

    assert decision.allowed is False
    assert decision.reason == "reviewer-not-independent"
    assert merge_receipts.calls == []


def test_approved_flag_without_exact_trusted_review_receipt_never_authorizes(
    tmp_path: Path,
) -> None:
    review_receipts = ReviewReceipts(("wrong-binding",))
    policy, candidate, merge_receipts = _policy(
        tmp_path,
        review_receipts=review_receipts,
    )
    assert candidate.review is not None and candidate.review.approved is True

    decision = policy.evaluate(candidate)

    assert decision.allowed is False
    assert decision.reason == "review-authority-invalid"
    assert len(review_receipts.calls) == 1
    assert merge_receipts.calls == []


def test_spoofed_author_cannot_hide_self_review_from_trusted_receipt(
    tmp_path: Path,
) -> None:
    candidate = _candidate(tmp_path)
    self_review_receipt = ReviewReceipts(
        (
            REVIEW_RECEIPT_ID,
            AUTHOR_ID,
            AUTHOR_ID,
            candidate.repository_root.resolve(),
            BASE_REVISION,
            CANDIDATE_REVISION,
            DIFF_HASH,
        )
    )
    policy, candidate, merge_receipts = _policy(
        tmp_path,
        review_receipts=self_review_receipt,
    )
    assert candidate.review is not None
    spoofed = candidate.model_copy(
        update={
            "author_id": "v20-forged-author",
            "review": candidate.review.model_copy(update={"reviewer_id": AUTHOR_ID}),
        }
    )

    decision = policy.evaluate(spoofed)

    assert decision.allowed is False
    assert decision.reason == "review-authority-invalid"
    assert merge_receipts.calls == []


def test_passed_booleans_without_exact_trusted_check_receipts_never_authorize(
    tmp_path: Path,
) -> None:
    verification_receipts = VerificationReceipts({})
    policy, candidate, merge_receipts = _policy(
        tmp_path,
        verification_receipts=verification_receipts,
    )
    assert all(
        check.passed
        for check in (
            candidate.focused_tests,
            candidate.broad_tests,
            candidate.formatting,
            candidate.static_analysis,
        )
    )

    decision = policy.evaluate(candidate)

    assert decision.allowed is False
    assert decision.reason == "focused-tests-authority-invalid"
    assert len(verification_receipts.calls) == 1
    assert merge_receipts.calls == []


def test_one_verification_receipt_cannot_be_reused_for_multiple_gates(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    reused = candidate.broad_tests.model_copy(
        update={"receipt_id": candidate.focused_tests.receipt_id}
    )

    with pytest.raises(ValidationError, match="verification receipt ids must be unique"):
        MaintenanceCandidate(**candidate.model_dump(exclude={"broad_tests"}), broad_tests=reused)


def test_dirty_main_has_exact_operator_reason(tmp_path: Path) -> None:
    policy, candidate, _ = _policy(tmp_path)

    decision = policy.evaluate(candidate.model_copy(update={"main_clean": False}))

    assert decision.allowed is False
    assert decision.reason == "Automatic merge is disabled because main is not clean."


@pytest.mark.parametrize(
    ("change", "value", "reason"),
    (
        ("observed_base_revision", "e" * 40, "base-revision-mismatch"),
        ("review", None, "review-missing"),
        (
            "review",
            BoundReview(
                approved=False,
                reviewer_id=REVIEWER_ID,
                review_receipt_id=REVIEW_RECEIPT_ID,
                revision=CANDIDATE_REVISION,
                diff_hash=DIFF_HASH,
            ),
            "review-not-approved",
        ),
        ("focused_tests", _bound_check("focused-tests", passed=False), "focused-tests-failed"),
        ("broad_tests", _bound_check("broad-tests", passed=False), "broad-tests-failed"),
        ("formatting", _bound_check("formatting", passed=False), "formatting-failed"),
        (
            "static_analysis",
            _bound_check("static-analysis", passed=False),
            "static-analysis-failed",
        ),
        ("rollback_revision", None, "rollback-revision-missing"),
        ("rollback_revision", "e" * 40, "rollback-revision-mismatch"),
        ("merge_lock_available", False, "merge-lock-held"),
    ),
)
def test_required_merge_gate_rejects_candidate(
    tmp_path: Path,
    change: str,
    value: object,
    reason: str,
) -> None:
    policy, candidate, receipts = _policy(tmp_path)

    decision = policy.evaluate(candidate.model_copy(update={change: value}))

    assert decision.allowed is False
    assert decision.reason == reason
    assert receipts.calls == []


@pytest.mark.parametrize(
    "field",
    ("review", "focused_tests", "broad_tests", "formatting", "static_analysis"),
)
def test_review_and_checks_are_bound_to_exact_revision_and_diff(tmp_path: Path, field: str) -> None:
    policy, candidate, receipts = _policy(tmp_path)
    evidence = getattr(candidate, field)
    assert evidence is not None

    changed = evidence.model_copy(update={"diff_hash": "f" * 64})
    decision = policy.evaluate(candidate.model_copy(update={field: changed}))

    assert decision.allowed is False
    assert decision.reason == f"{field.replace('_', '-')}-binding-mismatch"
    assert receipts.calls == []


@pytest.mark.parametrize(
    "relative",
    (
        "vesper/execution/broker.py",
        "vesper/platform/tui/broker_adapter.py",
        "vesper/platform/tui/portfolio_view.py",
        "vesper/platform/tui/risk_limits.py",
        "vesper/platform/tui/model_promotion.py",
        "vesper/orders/router.py",
        "vesper/portfolio/weights.py",
        "vesper/risk/limits.py",
        "vesper/models/promote.py",
        "vesper/training/policy.py",
        "vesper/scheduler/jobs.py",
        "config/credentials.json",
        ".env",
        ".gitmodules",
        "vesper/data/massive/prices.sqlite3",
        "vesper/data/model_research/candidate.bin",
        "AGENTS.md",
        "pyproject.toml",
        "uv.lock",
        ".cargo/config.toml",
        ".github/workflows/ci.yml",
        "docs/architecture/runtime.md",
    ),
)
def test_forbidden_authority_scope_is_rejected(tmp_path: Path, relative: str) -> None:
    policy, candidate, receipts = _policy(tmp_path)
    target = candidate.worktree_root.joinpath(*relative.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("unsafe\n", encoding="utf-8")

    decision = policy.evaluate(candidate.model_copy(update={"changed_paths": (relative,)}))

    assert decision.allowed is False
    assert decision.reason == "forbidden-maintenance-path"
    assert receipts.calls == []


def test_path_outside_configured_low_risk_globs_is_rejected(tmp_path: Path) -> None:
    policy, candidate, receipts = _policy(tmp_path)
    target = candidate.worktree_root / "docs" / "readme.md"
    target.parent.mkdir(parents=True)
    target.write_text("not configured\n", encoding="utf-8")

    decision = policy.evaluate(candidate.model_copy(update={"changed_paths": ("docs/readme.md",)}))

    assert decision.allowed is False
    assert decision.reason == "maintenance-path-not-allowed"
    assert receipts.calls == []


@pytest.mark.parametrize(
    "relative",
    (
        "vesper/platform/tui/safe.py:stream",
        "vesper/platform/tui/CON.py",
    ),
)
def test_windows_alias_path_is_rejected_as_unsafe(tmp_path: Path, relative: str) -> None:
    policy, candidate, receipts = _policy(tmp_path)

    decision = policy.evaluate(candidate.model_copy(update={"changed_paths": (relative,)}))

    assert decision.allowed is False
    assert decision.reason == "unsafe-maintenance-path"
    assert receipts.calls == []


def test_case_insensitive_duplicate_paths_are_rejected(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    values = candidate.model_dump()
    values["changed_paths"] = (
        "vesper/platform/tui/SAFE_FIX.py",
        "vesper/platform/tui/safe_fix.py",
    )

    with pytest.raises(ValidationError, match="unique"):
        MaintenanceCandidate.model_validate(values)


def test_broad_glob_is_rejected_at_policy_construction(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    receipts = MergeReceipts()

    with pytest.raises(ValueError, match="explicit"):
        MaintenancePolicy(
            _activation_store(),
            receipts,
            ReviewReceipts(),
            VerificationReceipts(),
            allowed_globs=("vesper/**",),
        )

    assert candidate.worktree_root.is_dir()
    assert receipts.calls == []


@pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="symlinks unavailable")
def test_symlinked_candidate_path_is_rejected(tmp_path: Path) -> None:
    policy, candidate, receipts = _policy(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("unsafe\n", encoding="utf-8")
    link = candidate.worktree_root / "vesper" / "platform" / "tui" / "link.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    decision = policy.evaluate(
        candidate.model_copy(update={"changed_paths": ("vesper/platform/tui/link.py",)})
    )

    assert decision.allowed is False
    assert decision.reason == "unsafe-maintenance-path"
    assert receipts.calls == []


def test_disabled_or_unverifiable_automatic_merge_grant_has_no_authority_call(
    tmp_path: Path,
) -> None:
    disabled_policy, candidate, disabled_receipts = _policy(
        tmp_path,
        activation_store=_activation_store(enabled=False),
    )
    disabled = disabled_policy.evaluate(candidate)

    assert disabled.allowed is False
    assert disabled.reason == "automatic-merge-disabled"
    assert disabled_receipts.calls == []

    mismatch_policy, mismatch_candidate, mismatch_receipts = _policy(
        tmp_path,
        activation_store=_activation_store(receipt_id="receipt:wrong"),
    )
    mismatch = mismatch_policy.evaluate(mismatch_candidate)

    assert mismatch.allowed is False
    assert mismatch.reason == "automatic-merge-authority-invalid"
    assert mismatch_receipts.calls == []


def test_merge_receipt_must_bind_exact_repository_revisions_and_diff(tmp_path: Path) -> None:
    receipts = MergeReceipts(("wrong",))
    policy, candidate, _ = _policy(tmp_path, merge_receipts=receipts)

    decision = policy.evaluate(candidate)

    assert decision.allowed is False
    assert decision.reason == "automatic-merge-receipt-mismatch"
    assert len(receipts.calls) == 1


class GitSpy:
    def __init__(
        self,
        *,
        post_merge_passes: bool,
        verification_revision: str = MERGE_REVISION,
    ) -> None:
        self.post_merge_passes = post_merge_passes
        self.verification_revision = verification_revision
        self.merge_calls = 0
        self.verify_calls = 0
        self.revert_calls: list[str] = []
        self.push_calls = 0

    def merge_no_ff(self, request: object) -> GitReceipt:
        self.merge_calls += 1
        return GitReceipt(
            operation="merge-no-ff",
            accepted=True,
            code="merge-completed",
            revision=MERGE_REVISION,
            diff_hash=DIFF_HASH,
        )

    def verify(self, request: VerificationRequest) -> GitReceipt:
        self.verify_calls += 1
        return GitReceipt(
            operation="verify",
            accepted=self.post_merge_passes,
            code=("verification-passed" if self.post_merge_passes else "verification-failed"),
            revision=self.verification_revision,
            diff_hash=None,
        )

    def revert(self, commit: str) -> GitReceipt:
        self.revert_calls.append(commit)
        return GitReceipt(
            operation="revert",
            accepted=True,
            code="revert-completed",
            revision="e" * 40,
            diff_hash=None,
        )

    def push(self, *_args: object, **_kwargs: object) -> GitReceipt:
        self.push_calls += 1
        raise AssertionError("automatic maintenance must never push")

    def merge_verify_revert(
        self,
        request: object,
        verification: VerificationRequest,
    ) -> MaintenanceTransactionReceipt:
        merged = self.merge_no_ff(request)
        verified = self.verify(verification)
        if verified.accepted and verified.revision == merged.revision:
            return MaintenanceTransactionReceipt(
                accepted=True,
                code="maintenance-merged",
                merge=merged,
                verification=verified,
                revert=None,
            )
        reverted = self.revert(merged.revision or MERGE_REVISION)
        code = (
            "post-merge-verification-revision-mismatch-reverted"
            if verified.accepted
            else "post-merge-verification-failed-reverted"
        )
        return MaintenanceTransactionReceipt(
            accepted=False,
            code=code,
            merge=merged,
            verification=verified,
            revert=reverted,
        )


def test_post_merge_failed_check_creates_exactly_one_revert(tmp_path: Path) -> None:
    policy, candidate, _ = _policy(tmp_path)
    git = GitSpy(post_merge_passes=False)
    service = MaintenanceService(policy, git)
    verification = VerificationRequest(
        worktree=tmp_path / "post-merge-verification",
        commands=(),
    )

    receipt = service.merge(candidate, post_merge_verification=verification)

    assert receipt.merged is True
    assert receipt.reverted is True
    assert receipt.reason == "post-merge-verification-failed-reverted"
    assert git.merge_calls == 1
    assert git.verify_calls == 1
    assert git.revert_calls == [MERGE_REVISION]
    assert git.push_calls == 0


def test_successful_automatic_merge_never_invokes_push(tmp_path: Path) -> None:
    policy, candidate, _ = _policy(tmp_path)
    git = GitSpy(post_merge_passes=True)
    service = MaintenanceService(policy, git)

    receipt = service.merge(
        candidate,
        post_merge_verification=VerificationRequest(
            worktree=tmp_path / "post-merge-verification",
            commands=(),
        ),
    )

    assert receipt.merged is True
    assert receipt.reverted is False
    assert receipt.reason == "maintenance-merged"
    assert git.revert_calls == []
    assert git.push_calls == 0


def test_post_merge_verification_must_not_target_main_worktree(tmp_path: Path) -> None:
    policy, candidate, _ = _policy(tmp_path)
    git = GitSpy(post_merge_passes=True)

    receipt = MaintenanceService(policy, git).merge(
        candidate,
        post_merge_verification=VerificationRequest(
            worktree=candidate.repository_root,
            commands=(),
        ),
    )

    assert receipt.accepted is False
    assert receipt.merged is False
    assert receipt.reason == "post-merge-verification-must-be-isolated"
    assert git.merge_calls == 0
    assert git.verify_calls == 0
    assert git.revert_calls == []


def test_post_merge_verification_revision_must_equal_merge_revision(
    tmp_path: Path,
) -> None:
    policy, candidate, _ = _policy(tmp_path)
    git = GitSpy(post_merge_passes=True, verification_revision="f" * 40)

    receipt = MaintenanceService(policy, git).merge(
        candidate,
        post_merge_verification=VerificationRequest(
            worktree=tmp_path / "post-merge-verification",
            commands=(),
        ),
    )

    assert receipt.accepted is False
    assert receipt.merged is True
    assert receipt.reverted is True
    assert receipt.reason == "post-merge-verification-revision-mismatch-reverted"
    assert git.revert_calls == [MERGE_REVISION]


def test_rejected_policy_causes_zero_git_mutations(tmp_path: Path) -> None:
    policy, candidate, _ = _policy(
        tmp_path,
        activation_store=_activation_store(enabled=False),
    )
    git = GitSpy(post_merge_passes=True)

    receipt = MaintenanceService(policy, git).merge(
        candidate,
        post_merge_verification=VerificationRequest(
            worktree=candidate.repository_root,
            commands=(),
        ),
    )

    assert receipt.merged is False
    assert receipt.reason == "automatic-merge-disabled"
    assert git.merge_calls == 0
    assert git.verify_calls == 0
    assert git.revert_calls == []
    assert git.push_calls == 0
