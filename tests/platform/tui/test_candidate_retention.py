from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

import vesper.platform.tui.candidate_retention as candidate_retention
from vesper.platform.ops.activation import (
    ActivationAuthorityError,
    ActivationCapability,
    ActivationGrant,
    OperationsActivation,
    OperationsActivationStore,
)
from vesper.platform.tui.candidate_retention import (
    CandidateArtifact,
    CandidateArtifactFile,
    CandidateRetentionAuthorityError,
    CandidateRetentionError,
    CandidateRetentionManifest,
    CandidateRetentionService,
)


NOW = datetime(2026, 8, 4, 12, tzinfo=timezone.utc)
GRANT_ID = "receipt:candidate-delete"


class ActivationReceipts:
    def __init__(self, expected: str | None = GRANT_ID) -> None:
        self.expected = expected
        self.calls: list[tuple[ActivationCapability, str]] = []

    def require(self, capability: ActivationCapability, receipt_id: str) -> None:
        self.calls.append((capability, receipt_id))
        if capability is not ActivationCapability.CANDIDATE_DELETION:
            raise ActivationAuthorityError("wrong activation capability")
        if receipt_id != self.expected:
            raise ActivationAuthorityError("activation receipt is unavailable or mismatched")


class CandidateDeletionReceipts:
    def __init__(self) -> None:
        self.binding: tuple[str, Path, str] | None = None
        self.calls: list[tuple[str, Path, str]] = []

    def bind(self, receipt_id: str, root: Path, plan_hash: str) -> None:
        self.binding = (receipt_id, root.resolve(), plan_hash)

    def require_candidate_deletion(
        self,
        receipt_id: str,
        approved_root: Path,
        plan_hash: str,
    ) -> object:
        call = (receipt_id, approved_root, plan_hash)
        self.calls.append(call)
        if self.binding != call:
            raise CandidateRetentionAuthorityError(
                "candidate deletion receipt is unavailable or mismatched"
            )
        return object()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_candidate_binary_hashing_does_not_retain_file_payload(tmp_path: Path) -> None:
    binary = tmp_path / "candidate.bin"
    binary.write_bytes(b"candidate-bytes")

    payload, status = candidate_retention._read_opened_regular(
        binary,
        expected_hash=_sha(binary),
    )

    assert payload == b""
    assert status.st_size == len(b"candidate-bytes")


def _activation_store(
    *, enabled: bool = True, receipt_id: str = GRANT_ID, expected: str | None = GRANT_ID
) -> OperationsActivationStore:
    activation = OperationsActivation(
        candidate_deletion=(
            ActivationGrant(enabled=True, receipt_id=receipt_id) if enabled else ActivationGrant()
        )
    )
    return OperationsActivationStore(activation, ActivationReceipts(expected))


def _artifact(
    root: Path,
    candidate_id: str,
    status: str,
    created_at: datetime,
    *,
    binary_names: tuple[str, ...] = ("model.bin",),
) -> CandidateArtifact:
    candidate_dir = root / candidate_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    files: list[CandidateArtifactFile] = []
    for name in binary_names:
        path = candidate_dir / name
        path.write_bytes(f"{candidate_id}:{name}".encode())
        files.append(
            CandidateArtifactFile(
                relative_path=f"{candidate_id}/{name}",
                kind="binary",
                sha256=_sha(path),
            )
        )
    for name, kind in (
        ("metrics.json", "metrics"),
        ("evidence.json", "evidence"),
        ("lineage.json", "lineage"),
        ("history.json", "history"),
    ):
        path = candidate_dir / name
        path.write_text(f"{candidate_id}:{kind}", encoding="utf-8")
        files.append(
            CandidateArtifactFile(
                relative_path=f"{candidate_id}/{name}", kind=kind, sha256=_sha(path)
            )
        )
    return CandidateArtifact(
        candidate_id=candidate_id,
        status=status,
        created_at_utc=created_at,
        files=tuple(files),
    )


def _service(
    tmp_path: Path,
    artifacts: tuple[CandidateArtifact, ...],
    *,
    active_id: str | None = None,
    rollback_id: str | None = None,
    disk_free_gb: int = 100,
    root: Path | None = None,
    repository_root: Path | None = None,
) -> CandidateRetentionService:
    candidate_root = root or tmp_path / "candidate-output"
    candidate_root.mkdir(parents=True, exist_ok=True)
    repository = repository_root or tmp_path / "repository"
    repository.mkdir(parents=True, exist_ok=True)
    manifest = CandidateRetentionManifest(
        candidates=artifacts,
        active_candidate_id=active_id,
        rollback_candidate_id=rollback_id,
    )
    return CandidateRetentionService(
        candidate_root,
        manifest,
        repository_root=repository,
        disk_free_gb=lambda _root: disk_free_gb,
        minimum_disk_free_gb=10,
    )


@pytest.mark.parametrize(
    ("status", "days"),
    (("failed", 30), ("rejected", 30), ("passed", 90), ("unselected", 90)),
)
def test_retention_starts_at_exact_status_boundary(tmp_path: Path, status: str, days: int) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "candidate-1", status, NOW - timedelta(days=days))
    service = _service(tmp_path, (artifact,), root=root)

    before = service.plan(NOW - timedelta(seconds=1))
    at_boundary = service.plan(NOW)

    assert before.deletions == ()
    assert tuple(item.relative_path for item in at_boundary.deletions) == ("candidate-1/model.bin",)


def test_active_and_rollback_candidates_are_permanent_and_manifest_is_frozen(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate-output"
    artifacts = tuple(
        _artifact(root, candidate_id, "failed", NOW - timedelta(days=31))
        for candidate_id in ("active", "rollback", "expired")
    )
    manifest = CandidateRetentionManifest(
        candidates=artifacts,
        active_candidate_id="active",
        rollback_candidate_id="rollback",
    )
    service = CandidateRetentionService(
        root,
        manifest,
        repository_root=tmp_path / "repository",
        disk_free_gb=lambda _root: 100,
    )

    assert {item.candidate_id for item in service.plan(NOW).deletions} == {"expired"}
    with pytest.raises(ValidationError):
        manifest.active_candidate_id = "expired"  # type: ignore[misc]


def test_apply_deletes_only_planned_binaries_and_keeps_permanent_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "rejected", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is True
    assert receipt.deleted_files == ("expired/model.bin",)
    assert not (root / "expired/model.bin").exists()
    for name in ("metrics.json", "evidence.json", "lineage.json", "history.json"):
        assert (root / "expired" / name).exists()
    deletion_manifest = root / ".retention" / f"{plan.plan_hash}.json"
    persisted = json.loads(deletion_manifest.read_text(encoding="utf-8"))
    assert persisted["plan_hash"] == plan.plan_hash
    assert persisted["deletions"][0]["sha256"] == plan.deletions[0].sha256


def test_all_file_hashes_are_rechecked_before_any_delete(tmp_path: Path) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(
        root,
        "expired",
        "failed",
        NOW - timedelta(days=31),
        binary_names=("one.bin", "two.bin"),
    )
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    (root / "expired/two.bin").write_bytes(b"changed-after-plan")
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is False
    assert receipt.reason == "planned-file-changed"
    assert (root / "expired/one.bin").exists()
    assert (root / "expired/two.bin").exists()
    assert not (root / ".retention").exists()


def test_permanent_metadata_hash_is_rechecked_before_binary_delete(tmp_path: Path) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    (root / "expired/evidence.json").write_text("changed-after-plan", encoding="utf-8")
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is False
    assert receipt.reason == "planned-file-changed"
    assert (root / "expired/model.bin").exists()
    assert not (root / ".retention").exists()


def test_disabled_activation_makes_no_filesystem_mutation(tmp_path: Path) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()

    receipt = service.apply(
        plan.plan_hash,
        _activation_store(enabled=False),
        authority,
    )

    assert receipt.accepted is False
    assert receipt.reason == "activation-disabled"
    assert authority.calls == []
    assert (root / "expired/model.bin").exists()
    assert not (root / ".retention").exists()


def test_mismatched_activation_receipt_fails_before_deletion_authority(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()

    receipt = service.apply(
        plan.plan_hash,
        _activation_store(receipt_id="wrong", expected=GRANT_ID),
        authority,
    )

    assert receipt.accepted is False
    assert receipt.reason == "activation-authority-invalid"
    assert authority.calls == []
    assert (root / "expired/model.bin").exists()


@pytest.mark.parametrize("binding", ("missing", "wrong-root", "wrong-plan"))
def test_candidate_deletion_receipt_binds_exact_root_and_plan(tmp_path: Path, binding: str) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    if binding == "wrong-root":
        authority.bind(GRANT_ID, tmp_path / "other-root", plan.plan_hash)
    elif binding == "wrong-plan":
        authority.bind(GRANT_ID, root, "f" * 64)

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is False
    assert receipt.reason == "deletion-authority-invalid"
    assert (root / "expired/model.bin").exists()
    assert not (root / ".retention").exists()


def test_unknown_or_unsafe_manifest_values_fail_closed(tmp_path: Path) -> None:
    file_hash = "a" * 64
    with pytest.raises(ValidationError):
        CandidateArtifact(
            candidate_id="candidate-1",
            status="unknown",
            created_at_utc=NOW,
            files=(
                CandidateArtifactFile(
                    relative_path="candidate-1/model.bin",
                    kind="binary",
                    sha256=file_hash,
                ),
            ),
        )
    for path in ("../model.bin", "candidate-1/../../model.bin", "C:\\model.bin"):
        with pytest.raises(ValidationError):
            CandidateArtifactFile(relative_path=path, kind="binary", sha256=file_hash)


def test_candidate_root_cannot_overlap_repository_or_protected_data(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    root = repository / "vesper" / "data" / "model_research" / "candidates"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    manifest = CandidateRetentionManifest(candidates=(artifact,))

    with pytest.raises(CandidateRetentionError, match="protected root"):
        CandidateRetentionService(
            root,
            manifest,
            repository_root=repository,
            disk_free_gb=lambda _root: 100,
        )


def test_symlink_escape_is_rejected_without_reading_or_deleting_target(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate-output"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "model.bin"
    target.write_bytes(b"outside")
    link = root / "escaped"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    artifact = CandidateArtifact(
        candidate_id="candidate-1",
        status="failed",
        created_at_utc=NOW - timedelta(days=31),
        files=(
            CandidateArtifactFile(
                relative_path="escaped/model.bin",
                kind="binary",
                sha256=_sha(target),
            ),
        ),
    )
    service = _service(tmp_path, (artifact,), root=root)

    with pytest.raises(CandidateRetentionError, match="outside candidate root"):
        service.plan(NOW)
    assert target.read_bytes() == b"outside"


def test_low_disk_pauses_training_without_shortening_retention(tmp_path: Path) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "young", "failed", NOW - timedelta(days=30, seconds=-1))
    low = _service(tmp_path, (artifact,), root=root, disk_free_gb=9)
    high = _service(tmp_path, (artifact,), root=root, disk_free_gb=100)

    low_plan = low.plan(NOW)
    high_plan = high.plan(NOW)

    assert low_plan.candidate_training_paused is True
    assert high_plan.candidate_training_paused is False
    assert low_plan.deletions == high_plan.deletions == ()


def test_wrong_or_unplanned_hash_is_rejected_without_mutation(tmp_path: Path) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    service.plan(NOW)
    authority = CandidateDeletionReceipts()

    receipt = service.apply("f" * 64, _activation_store(), authority)

    assert receipt.accepted is False
    assert receipt.reason == "plan-not-found"
    assert authority.calls == []
    assert (root / "expired/model.bin").exists()

    with pytest.raises(TypeError, match="SHA-256"):
        service.apply("z" * 64, _activation_store(), authority)

    assert authority.calls == []
    assert (root / "expired/model.bin").exists()


def test_manifest_requires_active_and_rollback_ids_to_be_known_and_distinct(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "candidate-1", "passed", NOW)
    with pytest.raises(ValidationError, match="active candidate ID"):
        CandidateRetentionManifest(candidates=(artifact,), active_candidate_id="missing")
    with pytest.raises(ValidationError, match="must be distinct"):
        CandidateRetentionManifest(
            candidates=(artifact,),
            active_candidate_id="candidate-1",
            rollback_candidate_id="candidate-1",
        )


@pytest.mark.parametrize(
    "relative_path",
    (
        "candidate-1/model.bin.",
        "candidate-1/model.bin ",
        " candidate-1/model.bin",
    ),
)
def test_windows_trailing_dot_or_space_alias_is_rejected(relative_path: str) -> None:
    with pytest.raises(ValidationError, match="Windows alias"):
        CandidateArtifactFile(
            relative_path=relative_path,
            kind="binary",
            sha256="a" * 64,
        )


def test_manifest_rejects_case_insensitive_windows_path_aliases() -> None:
    first = CandidateArtifact(
        candidate_id="candidate-1",
        status="failed",
        created_at_utc=NOW,
        files=(
            CandidateArtifactFile(relative_path="Alpha/model.bin", kind="binary", sha256="a" * 64),
        ),
    )
    second = CandidateArtifact(
        candidate_id="candidate-2",
        status="failed",
        created_at_utc=NOW,
        files=(
            CandidateArtifactFile(relative_path="alpha/MODEL.bin", kind="binary", sha256="b" * 64),
        ),
    )

    with pytest.raises(ValidationError, match="Windows path aliases"):
        CandidateRetentionManifest(candidates=(first, second))


def test_constructor_revalidates_model_copy_path_bypass(tmp_path: Path) -> None:
    root = tmp_path / "candidate-output"
    root.mkdir()
    repository = tmp_path / "repository"
    repository.mkdir()
    valid_file = CandidateArtifactFile(
        relative_path="candidate-1/model.bin", kind="binary", sha256="a" * 64
    )
    bypassed_file = valid_file.model_copy(update={"relative_path": "candidate-1/model.bin. "})
    valid_artifact = CandidateArtifact(
        candidate_id="candidate-1",
        status="failed",
        created_at_utc=NOW,
        files=(valid_file,),
    )
    bypassed_artifact = valid_artifact.model_copy(update={"files": (bypassed_file,)})
    bypassed_manifest = CandidateRetentionManifest(candidates=()).model_copy(
        update={"candidates": (bypassed_artifact,)}
    )

    with pytest.raises(CandidateRetentionError, match="manifest is invalid"):
        CandidateRetentionService(
            root,
            bypassed_manifest,
            repository_root=repository,
            disk_free_gb=lambda _root: 100,
        )


def test_returned_plan_mutation_cannot_change_controller_owned_plan(tmp_path: Path) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    object.__setattr__(plan, "deletions", ())
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is True
    assert receipt.deleted_files == ("expired/model.bin",)
    assert not (root / "expired/model.bin").exists()


def test_active_and_expired_hardlink_alias_fails_before_planning(tmp_path: Path) -> None:
    root = tmp_path / "candidate-output"
    expired = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    active = _artifact(root, "active", "passed", NOW - timedelta(days=100))
    active_model = root / "active/model.bin"
    active_model.unlink()
    try:
        os.link(root / "expired/model.bin", active_model)
    except OSError as error:
        pytest.skip(f"hard-link creation unavailable: {error}")
    active_files = tuple(
        file.model_copy(update={"sha256": _sha(active_model)})
        if file.relative_path == "active/model.bin"
        else file
        for file in active.files
    )
    active = active.model_copy(update={"files": active_files})
    service = _service(
        tmp_path,
        (expired, active),
        root=root,
        active_id="active",
    )

    with pytest.raises(CandidateRetentionError, match="hard links|file identity"):
        service.plan(NOW)


def test_existing_manifest_symlink_is_rejected_without_outside_read_or_chmod(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    retention = root / ".retention"
    retention.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside-manifest")
    original_mode = outside.stat().st_mode
    try:
        os.symlink(outside, retention / f"{plan.plan_hash}.json")
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    real_read_bytes = Path.read_bytes
    real_chmod = Path.chmod

    def forbid_outside_read(path: Path):
        if path.resolve(strict=True) == outside.resolve(strict=True):
            raise AssertionError("outside manifest was read")
        return real_read_bytes(path)

    def forbid_outside_chmod(path: Path, *args, **kwargs):
        if path.resolve(strict=True) == outside.resolve(strict=True):
            raise AssertionError("outside manifest was chmodded")
        return real_chmod(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", forbid_outside_read)
    monkeypatch.setattr(Path, "chmod", forbid_outside_chmod)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is False
    assert receipt.reason == "deletion-manifest-unsafe"
    assert outside.stat().st_size == len(b"outside-manifest")
    assert outside.stat().st_mode == original_mode
    assert (root / "expired/model.bin").exists()


def test_existing_manifest_hardlink_is_rejected_without_mutation(tmp_path: Path) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    retention = root / ".retention"
    retention.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside-manifest")
    try:
        os.link(outside, retention / f"{plan.plan_hash}.json")
    except OSError as error:
        pytest.skip(f"hard-link creation unavailable: {error}")
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is False
    assert receipt.reason == "deletion-manifest-unsafe"
    assert outside.read_bytes() == b"outside-manifest"
    assert (root / "expired/model.bin").exists()


def test_existing_manifest_parent_swap_is_blocked_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    retention = root / ".retention"
    retention.mkdir()
    payload = json.dumps(
        service._plans[plan.plan_hash].model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    (retention / f"{plan.plan_hash}.json").write_bytes(payload)
    outside = tmp_path / "outside-retention"
    outside.mkdir()
    (outside / f"{plan.plan_hash}.json").write_bytes(payload)
    backup = root / ".retention-backup"
    real_read = candidate_retention._read_opened_regular
    attempted = False
    blocked = False

    def race_parent(path: Path, **kwargs):
        nonlocal attempted, blocked
        if not attempted and path.suffix == ".json":
            attempted = True
            try:
                os.rename(retention, backup)
                os.symlink(outside, retention, target_is_directory=True)
            except OSError:
                blocked = True
        return real_read(path, **kwargs)

    monkeypatch.setattr(candidate_retention, "_read_opened_regular", race_parent)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)

    service.apply(plan.plan_hash, _activation_store(), authority)

    assert attempted is True
    assert blocked is True


def test_manifest_parent_swap_is_blocked_before_exclusive_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    retention = root / ".retention"
    backup = root / ".retention-backup"
    outside = tmp_path / "outside-retention"
    outside.mkdir()
    real_create = candidate_retention._create_exclusive_manifest
    attempted = False
    blocked = False

    def race_parent(path: Path, payload: bytes):
        nonlocal attempted, blocked
        attempted = True
        try:
            os.rename(retention, backup)
            os.symlink(outside, retention, target_is_directory=True)
        except OSError:
            blocked = True
        return real_create(path, payload)

    monkeypatch.setattr(candidate_retention, "_create_exclusive_manifest", race_parent)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)

    service.apply(plan.plan_hash, _activation_store(), authority)

    assert attempted is True
    assert blocked is True


def test_second_stage_move_failure_rolls_back_every_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(
        root,
        "expired",
        "failed",
        NOW - timedelta(days=31),
        binary_names=("one.bin", "two.bin"),
    )
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)
    real_rename = candidate_retention.os.rename

    def fail_second_stage(source, destination):
        if Path(source).name == "two.bin" and ".retention" in Path(destination).parts:
            raise OSError("injected second move failure")
        return real_rename(source, destination)

    monkeypatch.setattr(candidate_retention.os, "rename", fail_second_stage)

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is False
    assert receipt.reason == "candidate-staging-failed"
    assert (root / "expired/one.bin").exists()
    assert (root / "expired/two.bin").exists()
    assert not (root / ".retention").exists()


def test_reopen_restores_prepared_staging_after_process_crash(tmp_path: Path) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)

    service._stage_plan(plan)

    prepared = root / ".retention" / f"{plan.plan_hash}.prepared.json"
    quarantined = root / ".retention/quarantine" / plan.plan_hash / "expired/model.bin"
    assert prepared.exists()
    assert not (root / "expired/model.bin").exists()
    assert quarantined.exists()

    reopened = _service(tmp_path, (artifact,), root=root)

    assert (root / "expired/model.bin").exists()
    assert not quarantined.exists()
    assert not prepared.exists()
    assert reopened.plan(NOW).plan_hash == plan.plan_hash


def test_reopen_restores_a_partially_staged_prepared_transaction(tmp_path: Path) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(
        root,
        "expired",
        "failed",
        NOW - timedelta(days=31),
        binary_names=("one.bin", "two.bin"),
    )
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    service._stage_plan(plan)
    transaction = root / ".retention/quarantine" / plan.plan_hash / "expired"
    os.rename(transaction / "two.bin", root / "expired/two.bin")

    _service(tmp_path, (artifact,), root=root)

    assert (root / "expired/one.bin").exists()
    assert (root / "expired/two.bin").exists()
    assert not (root / ".retention" / f"{plan.plan_hash}.prepared.json").exists()


def test_reopen_does_not_restore_after_committed_manifest_crash(tmp_path: Path) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    _staged, _created, prepared = service._stage_plan(plan)
    manifest_path = root / ".retention" / f"{plan.plan_hash}.json"
    manifest_payload = json.dumps(
        plan.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    assert service._commit_manifest(manifest_path, manifest_payload) is True

    reopened = _service(tmp_path, (artifact,), root=root)

    quarantined = root / ".retention/quarantine" / plan.plan_hash / "expired/model.bin"
    assert not (root / "expired/model.bin").exists()
    assert quarantined.exists()
    assert not prepared.exists()
    assert reopened.root == root.resolve()


def test_manifest_commit_failure_rolls_back_staged_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)
    real_create = candidate_retention._create_exclusive_manifest

    def fail_committed_manifest(path: Path, payload: bytes) -> bool:
        if path.name.endswith(".prepared.json"):
            return real_create(path, payload)
        raise OSError("injected commit failure")

    monkeypatch.setattr(
        candidate_retention,
        "_create_exclusive_manifest",
        fail_committed_manifest,
        raising=False,
    )

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is False
    assert receipt.reason == "deletion-manifest-unavailable"
    assert (root / "expired/model.bin").exists()
    assert not (root / ".retention").exists()


def test_manifest_fsync_failure_removes_manifest_and_rolls_back_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)
    real_create = candidate_retention._create_exclusive_manifest
    real_fsync = candidate_retention.os.fsync

    def fail_committed_manifest_fsync(path: Path, payload: bytes) -> bool:
        if path.name.endswith(".prepared.json"):
            return real_create(path, payload)
        with monkeypatch.context() as commit_patch:
            commit_patch.setattr(
                candidate_retention.os,
                "fsync",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("injected fsync failure")),
            )
            return real_create(path, payload)

    monkeypatch.setattr(
        candidate_retention, "_create_exclusive_manifest", fail_committed_manifest_fsync
    )

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is False
    assert receipt.reason == "deletion-manifest-unavailable"
    assert (root / "expired/model.bin").exists()
    assert not (root / ".retention").exists()


def test_prepared_journal_fsync_failure_never_moves_candidate_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)
    monkeypatch.setattr(
        candidate_retention.os,
        "fsync",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("injected fsync failure")),
    )

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is False
    assert receipt.reason == "candidate-staging-failed"
    assert (root / "expired/model.bin").exists()
    assert not (root / ".retention").exists()


def test_post_fsync_manifest_uncertainty_is_accepted_and_left_quarantined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)
    real_verify = candidate_retention._verify_created_manifest_path

    def fail_committed_manifest_verification(path: Path, *args) -> None:
        if path.name.endswith(".prepared.json"):
            real_verify(path, *args)
            return
        raise OSError("injected lstat failure")

    monkeypatch.setattr(
        candidate_retention,
        "_verify_created_manifest_path",
        fail_committed_manifest_verification,
        raising=False,
    )

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is True
    assert receipt.reason == "candidate-retention-commit-indeterminate"
    assert receipt.deleted_files == ()
    assert receipt.quarantined_files == ("expired/model.bin",)
    assert receipt.unverified_files == ()
    assert not (root / "expired/model.bin").exists()
    assert (root / ".retention/quarantine" / plan.plan_hash / "expired/model.bin").exists()


def test_post_fsync_manifest_fstat_failure_cannot_roll_back_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)
    real_create = candidate_retention._create_exclusive_manifest
    real_fsync = candidate_retention.os.fsync
    real_fstat = candidate_retention.os.fstat

    def fail_committed_manifest_post_fsync_fstat(path: Path, payload: bytes) -> bool:
        if path.name.endswith(".prepared.json"):
            return real_create(path, payload)
        fsync_finished = False

        def track_fsync(descriptor: int) -> None:
            nonlocal fsync_finished
            real_fsync(descriptor)
            fsync_finished = True

        def fail_first_post_fsync_fstat(descriptor: int):
            nonlocal fsync_finished
            if fsync_finished:
                fsync_finished = False
                raise OSError("injected post-fsync fstat failure")
            return real_fstat(descriptor)

        with monkeypatch.context() as commit_patch:
            commit_patch.setattr(candidate_retention.os, "fsync", track_fsync)
            commit_patch.setattr(candidate_retention.os, "fstat", fail_first_post_fsync_fstat)
            return real_create(path, payload)

    monkeypatch.setattr(
        candidate_retention,
        "_create_exclusive_manifest",
        fail_committed_manifest_post_fsync_fstat,
    )

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is True
    assert receipt.reason == "candidate-retention-commit-indeterminate"
    assert receipt.deleted_files == ()
    assert receipt.quarantined_files == ("expired/model.bin",)
    assert not (root / "expired/model.bin").exists()


def test_unexpected_precommit_failure_rolls_back_before_propagating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)
    real_create = candidate_retention._create_exclusive_manifest

    def fail_committed_manifest_unexpectedly(path: Path, payload: bytes) -> bool:
        if path.name.endswith(".prepared.json"):
            return real_create(path, payload)
        raise RuntimeError("unexpected")

    monkeypatch.setattr(
        candidate_retention,
        "_create_exclusive_manifest",
        fail_committed_manifest_unexpectedly,
    )

    with pytest.raises(RuntimeError, match="unexpected"):
        service.apply(plan.plan_hash, _activation_store(), authority)

    assert (root / "expired/model.bin").exists()
    assert not (root / ".retention").exists()


def test_chmod_failure_cannot_turn_committed_retention_into_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)
    monkeypatch.setattr(
        Path,
        "chmod",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("injected chmod failure")),
    )

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is True
    assert not (root / "expired/model.bin").exists()


def test_post_commit_second_cleanup_failure_returns_truthful_accepted_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(
        root,
        "expired",
        "failed",
        NOW - timedelta(days=31),
        binary_names=("one.bin", "two.bin"),
    )
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)
    real_delete = Path.unlink
    calls = 0

    def fail_second_cleanup(path: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second cleanup failure")
        real_delete(path)

    monkeypatch.setattr(candidate_retention, "_physical_delete", fail_second_cleanup, raising=False)

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is True
    assert receipt.reason == "candidate-binaries-quarantined"
    assert receipt.deleted_files == ("expired/one.bin",)
    assert receipt.quarantined_files == ("expired/two.bin",)
    assert not (root / "expired/one.bin").exists()
    assert not (root / "expired/two.bin").exists()
    assert (root / ".retention" / "quarantine" / plan.plan_hash / "expired/two.bin").exists()


def test_cleanup_that_deletes_then_raises_is_reported_as_physically_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)

    def delete_then_raise(path: Path) -> None:
        path.unlink()
        raise OSError("injected late cleanup error")

    monkeypatch.setattr(candidate_retention, "_physical_delete", delete_then_raise)

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is True
    assert receipt.reason == "candidate-binaries-deleted"
    assert receipt.deleted_files == ("expired/model.bin",)
    assert receipt.quarantined_files == ()


def test_cleanup_replacement_is_reported_unverified_not_quarantined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)

    def replace_then_raise(path: Path) -> None:
        path.unlink()
        path.write_bytes(b"unverified replacement")
        raise OSError("injected replacement")

    monkeypatch.setattr(candidate_retention, "_physical_delete", replace_then_raise)

    receipt = service.apply(plan.plan_hash, _activation_store(), authority)

    assert receipt.accepted is True
    assert receipt.reason == "candidate-binaries-unverified"
    assert receipt.deleted_files == ()
    assert receipt.quarantined_files == ()
    assert receipt.unverified_files == ("expired/model.bin",)


def test_exact_existing_manifest_replay_is_safe_and_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "candidate-output"
    artifact = _artifact(root, "expired", "failed", NOW - timedelta(days=31))
    service = _service(tmp_path, (artifact,), root=root)
    plan = service.plan(NOW)
    authority = CandidateDeletionReceipts()
    authority.bind(GRANT_ID, root, plan.plan_hash)
    first = service.apply(plan.plan_hash, _activation_store(), authority)
    manifest_path = root / ".retention" / f"{plan.plan_hash}.json"
    before = manifest_path.read_bytes()

    replay = service.apply(plan.plan_hash, _activation_store(), authority)

    assert first.accepted is replay.accepted is True
    assert replay.reason == "candidate-retention-already-committed"
    assert manifest_path.read_bytes() == before
