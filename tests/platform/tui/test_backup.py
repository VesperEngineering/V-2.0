from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from vesper.platform.tui.backup import (
    BackupError,
    BackupRestoreError,
    BackupService,
    RestoreConfirmation,
)


class Protection:
    def __init__(self, user: str = "user-a") -> None:
        self.user = user

    def protect(self, plaintext: bytes) -> bytes:
        return self.user.encode() + b"\0" + plaintext[::-1]

    def unprotect(self, ciphertext: bytes) -> bytes:
        prefix = self.user.encode() + b"\0"
        if not ciphertext.startswith(prefix):
            raise ValueError("wrong user")
        return ciphertext[len(prefix) :][::-1]


class Runtime:
    def __init__(self, stopped: bool = True) -> None:
        self.stopped = stopped
        self.calls = 0

    def exactly_stopped(self) -> bool:
        self.calls += 1
        return self.stopped


class ReplaceSpy:
    def __init__(self, root: Path, *, fail_target_call: int | None = None) -> None:
        self.root = root.resolve()
        self.fail_target_call = fail_target_call
        self.target_calls = 0
        self.calls: list[tuple[Path, Path]] = []

    def __call__(self, source: Path, destination: Path) -> None:
        destination = Path(destination)
        self.calls.append((Path(source), destination))
        try:
            is_target = destination.resolve(strict=False).is_relative_to(self.root)
        except OSError:
            is_target = False
        if is_target:
            self.target_calls += 1
            if self.target_calls == self.fail_target_call:
                self.fail_target_call = None
                raise OSError("injected target replace failure")
        os.replace(source, destination)


def _seed(root: Path, value: str) -> None:
    (root / "state").mkdir(parents=True)
    (root / "state/config.json").write_text(value, encoding="utf-8")
    (root / "state/.env").write_text("SECRET=never", encoding="utf-8")
    (root / "state/credentials").mkdir()
    (root / "state/credentials/token.txt").write_text("never", encoding="utf-8")
    (root / "vesper/data/massive").mkdir(parents=True)
    (root / "vesper/data/massive/source.db").write_text("protected", encoding="utf-8")
    (root / "vesper/data/model_research").mkdir(parents=True)
    (root / "vesper/data/model_research/model.bin").write_text("protected", encoding="utf-8")


def _service(
    root: Path,
    tmp_path: Path,
    *,
    runtime: Runtime | None = None,
    protection: Protection | None = None,
    replace: ReplaceSpy | None = None,
    safety_destination=None,
) -> BackupService:
    return BackupService(
        root.resolve(),
        ("state", "vesper/data"),
        runtime=Runtime() if runtime is None else runtime,
        safety_destination=(
            (lambda: tmp_path / "automatic-safety.v20backup")
            if safety_destination is None
            else safety_destination
        ),
        protection=Protection() if protection is None else protection,
        atomic_replace=os.replace if replace is None else replace,
    )


def _confirmation(preview_hash: str, safety_receipt_id: str) -> RestoreConfirmation:
    return RestoreConfirmation(
        preview_hash=preview_hash,
        safety_backup_receipt_id=safety_receipt_id,
        first_confirmed=True,
        second_confirmed=True,
    )


def test_backup_excludes_secrets_caches_and_protected_data(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "old")
    (root / "state/__pycache__").mkdir()
    (root / "state/__pycache__/module.pyc").write_bytes(b"cache")
    destination = tmp_path / "state.v20backup"

    manifest = _service(root, tmp_path).create(destination)

    assert destination.is_file()
    assert not destination.read_bytes().startswith(b"PK\x03\x04")
    lowered = tuple(path.casefold() for path in manifest.paths)
    assert lowered == ("state/config.json",)
    assert all(".env" not in path and "credentials" not in path for path in lowered)
    assert all("massive" not in path and "model_research" not in path for path in lowered)
    assert all("__pycache__" not in path for path in lowered)


def test_plaintext_archive_is_deterministic_and_ciphertext_is_not_plain(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "same")
    service = _service(root, tmp_path)

    first = service.create(tmp_path / "first.v20backup")
    second = service.create(tmp_path / "second.v20backup")

    assert first.plaintext_sha256 == second.plaintext_sha256
    assert first.receipt_id == second.receipt_id
    assert (tmp_path / "first.v20backup").read_bytes() == (
        tmp_path / "second.v20backup"
    ).read_bytes()
    assert b"same" not in (tmp_path / "first.v20backup").read_bytes()


def test_wrong_user_corruption_and_traversal_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "old")
    archive = tmp_path / "state.v20backup"
    _service(root, tmp_path).create(archive)

    with pytest.raises(BackupError, match="archive-unavailable"):
        _service(root, tmp_path, protection=Protection("user-b")).preview_restore(archive)

    corrupted = bytearray(archive.read_bytes())
    corrupted[-1] ^= 1
    archive.write_bytes(corrupted)
    with pytest.raises(BackupError, match="archive-unavailable"):
        _service(root, tmp_path).preview_restore(archive)

    service = _service(root, tmp_path)
    service.create(archive)
    framed = archive.read_bytes()
    plaintext = Protection().unprotect(framed[len(b"V20BK1\0") :])
    payload = json.loads(plaintext)
    payload["entries"][0]["path"] = "../outside.txt"
    forged = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    archive.write_bytes(b"V20BK1\0" + Protection().protect(forged))
    with pytest.raises(BackupError, match="archive-unavailable"):
        service.preview_restore(archive)
    assert not (tmp_path / "outside.txt").exists()


def test_archive_entry_outside_exact_allowlist_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "old")
    archive = tmp_path / "state.v20backup"
    service = _service(root, tmp_path)
    service.create(archive)
    framed = archive.read_bytes()
    plaintext = Protection().unprotect(framed[len(b"V20BK1\0") :])
    payload = json.loads(plaintext)
    payload["entries"][0]["path"] = "outside.txt"
    forged = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    archive.write_bytes(b"V20BK1\0" + Protection().protect(forged))

    with pytest.raises(BackupError, match="archive-unavailable"):
        service.preview_restore(archive)

    assert not (root / "outside.txt").exists()


def test_preview_lists_create_replace_delete_and_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "old")
    (root / "state/unchanged.txt").write_text("same", encoding="utf-8")
    (root / "state/missing-later.txt").write_text("restore", encoding="utf-8")
    service = _service(root, tmp_path)
    archive = tmp_path / "state.v20backup"
    service.create(archive)
    (root / "state/config.json").write_text("new", encoding="utf-8")
    (root / "state/missing-later.txt").unlink()
    (root / "state/extra.txt").write_text("delete", encoding="utf-8")

    preview = service.preview_restore(archive)

    actions = {change.path: change.action for change in preview.changes}
    assert actions == {
        "state/config.json": "replace",
        "state/extra.txt": "delete",
        "state/missing-later.txt": "create",
        "state/unchanged.txt": "unchanged",
    }


@pytest.mark.parametrize(
    ("stopped", "first", "second", "reason"),
    (
        (False, True, True, "runtime-not-stopped"),
        (True, False, True, "double-confirmation-required"),
        (True, True, False, "double-confirmation-required"),
    ),
)
def test_restore_prerequisites_change_no_target(
    tmp_path: Path,
    stopped: bool,
    first: bool,
    second: bool,
    reason: str,
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "old")
    runtime = Runtime(stopped)
    replace = ReplaceSpy(root)
    service = _service(root, tmp_path, runtime=runtime, replace=replace)
    archive = tmp_path / "old.v20backup"
    service.create(archive)
    (root / "state/config.json").write_text("new", encoding="utf-8")
    safety = service.create(tmp_path / "external-safety.v20backup")
    preview = service.preview_restore(archive)
    replace.target_calls = 0
    confirmation = RestoreConfirmation(
        preview_hash=preview.preview_hash,
        safety_backup_receipt_id=safety.receipt_id,
        first_confirmed=first,
        second_confirmed=second,
    )

    receipt = service.restore(archive, confirmation)

    assert receipt.accepted is False
    assert receipt.reason == reason
    assert (root / "state/config.json").read_text(encoding="utf-8") == "new"
    assert replace.target_calls == 0


def test_restore_requires_exact_preview_and_safety_backup_binding(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "old")
    service = _service(root, tmp_path)
    archive = tmp_path / "old.v20backup"
    service.create(archive)
    (root / "state/config.json").write_text("new", encoding="utf-8")
    safety = service.create(tmp_path / "external-safety.v20backup")
    preview = service.preview_restore(archive)

    wrong_preview = service.restore(
        archive,
        _confirmation("0" * 64, safety.receipt_id),
    )
    wrong_safety = service.restore(
        archive,
        _confirmation(preview.preview_hash, "backup:" + "0" * 64),
    )

    assert wrong_preview.reason == "preview-mismatch"
    assert wrong_safety.reason == "safety-backup-mismatch"
    assert (root / "state/config.json").read_text(encoding="utf-8") == "new"


def test_restore_exactly_replaces_allowlisted_state_and_preserves_exclusions(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "old")
    service = _service(root, tmp_path)
    archive = tmp_path / "old.v20backup"
    service.create(archive)
    (root / "state/config.json").write_text("new", encoding="utf-8")
    (root / "state/extra.txt").write_text("extra", encoding="utf-8")
    (root / "state/.env").write_text("SECRET=current", encoding="utf-8")
    (root / "vesper/data/massive/source.db").write_text("current", encoding="utf-8")
    safety = service.create(tmp_path / "external-safety.v20backup")
    preview = service.preview_restore(archive)

    receipt = service.restore(archive, _confirmation(preview.preview_hash, safety.receipt_id))

    assert receipt.accepted is True
    assert receipt.reason == "restore-completed"
    assert (root / "state/config.json").read_text(encoding="utf-8") == "old"
    assert not (root / "state/extra.txt").exists()
    assert (root / "state/.env").read_text(encoding="utf-8") == "SECRET=current"
    assert (root / "vesper/data/massive/source.db").read_text(encoding="utf-8") == "current"
    assert (tmp_path / "automatic-safety.v20backup").is_file()
    assert receipt.safety_backup_receipt_id == safety.receipt_id


def test_restore_does_not_rewrite_unchanged_files(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "old")
    (root / "state/unchanged.txt").write_text("same", encoding="utf-8")
    replace = ReplaceSpy(root)
    service = _service(root, tmp_path, replace=replace)
    archive = tmp_path / "old.v20backup"
    service.create(archive)
    (root / "state/config.json").write_text("new", encoding="utf-8")
    safety = service.create(tmp_path / "external-safety.v20backup")
    preview = service.preview_restore(archive)
    replace.target_calls = 0

    receipt = service.restore(archive, _confirmation(preview.preview_hash, safety.receipt_id))

    assert receipt.accepted is True
    assert receipt.restored_paths == ("state/config.json",)
    assert replace.target_calls == 1


def test_restore_uses_one_safety_destination_for_write_and_staging(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "old")
    calls: list[int] = []

    def safety_destination() -> Path:
        calls.append(len(calls))
        return tmp_path / f"automatic-safety-{len(calls)}.v20backup"

    service = _service(root, tmp_path, safety_destination=safety_destination)
    archive = tmp_path / "old.v20backup"
    service.create(archive)
    (root / "state/config.json").write_text("new", encoding="utf-8")
    safety = service.create(tmp_path / "external-safety.v20backup")
    preview = service.preview_restore(archive)

    receipt = service.restore(archive, _confirmation(preview.preview_hash, safety.receipt_id))

    assert receipt.accepted is True
    assert calls == [0]


def test_post_replace_failure_rolls_every_target_back_from_safety_backup(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "old-one")
    (root / "state/two.txt").write_text("old-two", encoding="utf-8")
    replace = ReplaceSpy(root)
    service = _service(root, tmp_path, replace=replace)
    archive = tmp_path / "old.v20backup"
    service.create(archive)
    (root / "state/config.json").write_text("new-one", encoding="utf-8")
    (root / "state/two.txt").write_text("new-two", encoding="utf-8")
    safety = service.create(tmp_path / "external-safety.v20backup")
    preview = service.preview_restore(archive)
    replace.target_calls = 0
    replace.fail_target_call = 2

    with pytest.raises(BackupRestoreError, match="restore-failed-rolled-back"):
        service.restore(archive, _confirmation(preview.preview_hash, safety.receipt_id))

    assert (root / "state/config.json").read_text(encoding="utf-8") == "new-one"
    assert (root / "state/two.txt").read_text(encoding="utf-8") == "new-two"


def test_changed_target_after_preview_is_rejected_before_replacement(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "old")
    replace = ReplaceSpy(root)
    service = _service(root, tmp_path, replace=replace)
    archive = tmp_path / "old.v20backup"
    service.create(archive)
    (root / "state/config.json").write_text("new", encoding="utf-8")
    preview = service.preview_restore(archive)
    (root / "state/config.json").write_text("changed-after-preview", encoding="utf-8")
    safety = service.create(tmp_path / "external-safety.v20backup")
    replace.target_calls = 0

    receipt = service.restore(archive, _confirmation(preview.preview_hash, safety.receipt_id))

    assert receipt.accepted is False
    assert receipt.reason == "preview-mismatch"
    assert replace.target_calls == 0
    assert (root / "state/config.json").read_text(encoding="utf-8") == "changed-after-preview"


def test_symlinked_source_is_rejected_without_reading_target(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "old")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = root / "state/link.txt"
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    with pytest.raises(BackupError, match="unsafe-source-path"):
        _service(root, tmp_path).create(tmp_path / "state.v20backup")

    assert outside.read_text(encoding="utf-8") == "outside"


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_current_user_dpapi_archive_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _seed(root, "old")
    service = BackupService(
        root.resolve(),
        ("state",),
        runtime=Runtime(),
        safety_destination=lambda: tmp_path / "safety.v20backup",
    )
    archive = tmp_path / "state.v20backup"

    service.create(archive)
    preview = service.preview_restore(archive)

    assert preview.archive_sha256
    assert b"old" not in archive.read_bytes()
