from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from vesper.platform.contracts import ResumableRunMetadata, RunManifest, RunStatus
from vesper.platform.evidence import (
    CorruptEvidenceError,
    DuplicateEvidenceError,
    FilesystemEvidenceStore,
)


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)
COMMON = {
    "run_id": "run-001",
    "task_id": "task-001",
    "repository_revision": "9f9df7f",
    "created_at": NOW,
}


def test_evidence_write_is_repository_relative_and_hash_verified(tmp_path):
    store = FilesystemEvidenceStore(tmp_path / "evidence")

    ref = store.put_bytes(
        **COMMON,
        artifact_id="validation-001",
        body=b'{"passed":true}',
        media_type="application/json",
        suffix=".json",
    )

    assert ref.relative_path == "runs/run-001/validation-001.json"
    assert ref.size_bytes == 15
    assert len(ref.sha256) == 64
    assert store.read_verified(ref) == b'{"passed":true}'
    assert not ref.relative_path.startswith(("/", "\\"))


def test_duplicate_write_is_idempotent_only_for_identical_content(tmp_path):
    store = FilesystemEvidenceStore(tmp_path / "evidence")
    first = store.put_bytes(
        **COMMON,
        artifact_id="receipt-001",
        body=b"same",
        media_type="text/plain",
    )
    second = store.put_bytes(
        **COMMON,
        artifact_id="receipt-001",
        body=b"same",
        media_type="text/plain",
    )
    assert second == first

    with pytest.raises(DuplicateEvidenceError):
        store.put_bytes(
            **COMMON,
            artifact_id="receipt-001",
            body=b"different",
            media_type="text/plain",
        )


def test_corrupted_artifact_is_rejected(tmp_path):
    store = FilesystemEvidenceStore(tmp_path / "evidence")
    ref = store.put_bytes(
        **COMMON,
        artifact_id="result",
        body=b"authoritative",
        media_type="text/plain",
    )
    (store.root / ref.relative_path).write_bytes(b"tampered")

    with pytest.raises(CorruptEvidenceError):
        store.read_verified(ref)


@pytest.mark.parametrize("artifact_id", ("../escape", "a/b", "a\\b", ".", ""))
def test_unsafe_artifact_ids_are_rejected(tmp_path, artifact_id):
    store = FilesystemEvidenceStore(tmp_path / "evidence")
    with pytest.raises(ValueError):
        store.put_bytes(
            **COMMON,
            artifact_id=artifact_id,
            body=b"unsafe",
            media_type="text/plain",
        )


def test_manifest_and_resume_metadata_survive_reopen(tmp_path):
    root = tmp_path / "evidence"
    store = FilesystemEvidenceStore(root)
    ref = store.put_bytes(
        **COMMON,
        artifact_id="receipt",
        body=b"receipt body",
        media_type="text/plain",
    )
    resume = ResumableRunMetadata(
        **COMMON,
        checkpoint_id="checkpoint-001",
        thread_id="thread-001",
        status=RunStatus.INTERRUPTED,
        updated_at=NOW,
    )
    manifest = RunManifest(
        **COMMON,
        status=RunStatus.INTERRUPTED,
        artifacts=(ref,),
        resume=resume,
    )

    manifest_ref = store.write_manifest(manifest)
    reopened = FilesystemEvidenceStore(root)

    assert reopened.read_manifest("run-001") == manifest
    assert reopened.read_verified(manifest_ref)


def test_manifest_tampering_is_rejected(tmp_path):
    store = FilesystemEvidenceStore(tmp_path / "evidence")
    manifest = RunManifest(**COMMON, status=RunStatus.CREATED)
    manifest_ref = store.write_manifest(manifest)
    path = store.root / manifest_ref.relative_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "accepted"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CorruptEvidenceError):
        store.read_manifest("run-001")


def test_concurrent_identical_writes_produce_one_valid_artifact(tmp_path):
    store = FilesystemEvidenceStore(tmp_path / "evidence")

    def write_once(_):
        return store.put_bytes(
            **COMMON,
            artifact_id="concurrent",
            body=b"identical",
            media_type="application/octet-stream",
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        refs = tuple(executor.map(write_once, range(12)))

    assert len(set(refs)) == 1
    assert store.read_verified(refs[0]) == b"identical"
