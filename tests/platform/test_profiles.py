from __future__ import annotations

from pathlib import Path

import pytest

from vesper.platform.contracts import SandboxMode, SpecialistRole
from vesper.platform.profiles import NATIVE_PROFILE_IDS, ProfileCatalog, ProfileIntegrityError


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILES_ROOT = REPOSITORY_ROOT / "profiles" / "native"


def test_native_catalog_loads_only_the_three_expected_profiles():
    catalog = ProfileCatalog(PROFILES_ROOT)

    profiles = catalog.load_all()

    assert tuple(profile.profile_id for profile in profiles) == NATIVE_PROFILE_IDS
    assert all(len(profile.profile_sha256) == 64 for profile in profiles)
    assert all(len(profile.soul_sha256) == 64 for profile in profiles)


@pytest.mark.parametrize(
    ("profile_id", "sandbox", "namespace"),
    [
        (SpecialistRole.PRODUCT, SandboxMode.READ_ONLY, ("profiles", "v20-product")),
        (
            SpecialistRole.DEVELOPMENT,
            SandboxMode.WORKSPACE_WRITE,
            ("profiles", "v20-development"),
        ),
        (SpecialistRole.RISK_REVIEW, SandboxMode.READ_ONLY, ("profiles", "v20-risk-review")),
    ],
)
def test_profiles_define_permissions_contracts_and_retry_policy(profile_id, sandbox, namespace):
    profile = ProfileCatalog(PROFILES_ROOT).load(profile_id)

    assert profile.permissions.sandbox is sandbox
    assert profile.memory_namespace == namespace
    assert profile.input_contract == "SpecialistInput@1.0"
    assert profile.output_contract == "SpecialistReceipt@1.0"
    assert profile.retry.max_correction_attempts == 3
    assert profile.retry.infrastructure_failures_consume_correction is False
    assert profile.system_instructions.strip()
    assert profile.prohibited_actions
    assert "SOUL.md" in profile.protected_paths
    assert "profile.yaml" in profile.protected_paths


def test_profiles_contain_no_dynamic_repository_state():
    forbidden = ("repository_revision:", "run_id:", "task_id:", "current_branch:")
    for path in PROFILES_ROOT.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8").lower()
            assert all(term not in text for term in forbidden), path


def test_catalog_never_discovers_historical_profile_tree():
    profiles = ProfileCatalog(PROFILES_ROOT).load_all()
    loaded_paths = {profile.source_directory for profile in profiles}

    assert all(path.parent == PROFILES_ROOT.resolve() for path in loaded_paths)
    assert not any("vesper-factory" in str(path) for path in loaded_paths)


def test_profile_directory_and_declared_id_must_match(tmp_path):
    profile_dir = tmp_path / "v20-product"
    profile_dir.mkdir()
    (profile_dir / "SOUL.md").write_text("Stable role identity.\n", encoding="utf-8")
    (profile_dir / "profile.yaml").write_text(
        "schema_version: '1.0'\nprofile_id: v20-development\n",
        encoding="utf-8",
    )

    with pytest.raises(ProfileIntegrityError):
        ProfileCatalog(tmp_path).load(SpecialistRole.PRODUCT)
