from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from vesper.platform.codex import CodexSdkAdapter
from vesper.platform.contracts import PermissionSet, SandboxMode, SpecialistInput, SpecialistRole


pytestmark = [
    pytest.mark.local_codex,
    pytest.mark.skipif(
        os.environ.get("V20_ENABLE_CODEX_INTEGRATION") != "1",
        reason="requires explicit operator opt-in and a locally authenticated Codex SDK",
    ),
]


def test_real_codex_sdk_boundary_is_read_only(tmp_path):
    now = datetime.now(timezone.utc)
    request = SpecialistInput(
        run_id="local-integration",
        task_id="local-integration",
        repository_revision="operator-enabled",
        created_at=now,
        role=SpecialistRole.RISK_REVIEW,
        attempt=1,
        instructions="Return a response without changing files.",
        workspace=str(tmp_path),
        memory_namespace=("profiles", "v20-risk-review", "risk-decisions"),
        permissions=PermissionSet(
            sandbox=SandboxMode.READ_ONLY,
            read_paths=(str(tmp_path),),
            allowed_tools=("read",),
        ),
    )
    model = os.environ["V20_CODEX_INTEGRATION_MODEL"]
    adapter = CodexSdkAdapter(repository_root=tmp_path, approved_models=(model,))

    receipt = adapter.execute(
        request,
        prompt="Reply with the single word ready.",
        model=model,
        timeout_seconds=60,
    )

    assert receipt.thread_id
    assert receipt.final_response
