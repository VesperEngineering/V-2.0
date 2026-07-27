from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.platform.composition import (
    NativeSpecialistComposition,
    ProfilePermissionMismatch,
    WorkspaceMutationDenied,
    _codex_output_schema,
    _make_object_schemas_strict,
)
from vesper.platform.contracts import (
    CodexExecutionReceipt,
    DevelopmentSpecialistOutput,
    ExecutionStatus,
    PermissionSet,
    ProductSpecialistOutput,
    RiskDecision,
    RiskSpecialistOutput,
    SandboxMode,
    SpecialistInput,
    SpecialistReceipt,
    SpecialistRole,
    ValidationCheck,
    ValidationResult,
)
from vesper.platform.evidence import FilesystemEvidenceStore
from vesper.platform.profiles import ProfileCatalog


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILES_ROOT = REPOSITORY_ROOT / "profiles" / "native"


def request(workspace: Path, role: SpecialistRole) -> SpecialistInput:
    sandbox = (
        SandboxMode.WORKSPACE_WRITE if role is SpecialistRole.DEVELOPMENT else SandboxMode.READ_ONLY
    )
    category = {
        SpecialistRole.PRODUCT: "product-decisions",
        SpecialistRole.DEVELOPMENT: "development-episodes",
        SpecialistRole.RISK_REVIEW: "risk-decisions",
    }[role]
    return SpecialistInput(
        run_id="run-001",
        task_id="task-001",
        repository_revision="b5263eb",
        created_at=NOW,
        role=role,
        attempt=1,
        instructions="Perform the controller-scoped task.",
        workspace=str(workspace),
        memory_namespace=("profiles", role.value, category),
        permissions=PermissionSet(
            sandbox=sandbox,
            read_paths=(str(workspace),),
            write_paths=(str(workspace),) if role is SpecialistRole.DEVELOPMENT else (),
            allowed_tools=("read", "search", "write", "test")
            if role is SpecialistRole.DEVELOPMENT
            else ("read", "search"),
        ),
    )


def codex_receipt(item: SpecialistInput, final_response: str) -> CodexExecutionReceipt:
    return CodexExecutionReceipt(
        run_id=item.run_id,
        task_id=item.task_id,
        repository_revision=item.repository_revision,
        created_at=item.created_at,
        execution_id=f"exec-{item.role.value}",
        role=item.role,
        attempt=item.attempt,
        status=ExecutionStatus.COMPLETED,
        sandbox=item.permissions.sandbox,
        model="docker-codex-default",
        workspace=item.workspace,
        approval_mode="deny-all",
        authentication_type="chatgpt",
        permission_profile="docker-one-shot",
        started_at=NOW,
        finished_at=NOW,
        thread_id=f"thread-{item.role.value}",
        final_response=final_response,
    )


class FakeCodexAdapter:
    def __init__(self, outputs, mutate=None):
        self.outputs = iter(outputs)
        self.calls = []
        self.mutate = mutate

    def execute(self, item, **kwargs):
        self.calls.append((item, kwargs))
        if self.mutate is not None:
            self.mutate(item)
        return codex_receipt(item, json.dumps(next(self.outputs)))


def assert_codex_strict_objects(value):
    if isinstance(value, dict):
        assert "default" not in value
        properties = value.get("properties")
        if isinstance(properties, dict):
            assert set(value.get("required", ())) == set(properties)
            assert value.get("additionalProperties") is False
        for child in value.values():
            assert_codex_strict_objects(child)
    elif isinstance(value, list):
        for child in value:
            assert_codex_strict_objects(child)


@pytest.mark.parametrize(
    "model",
    (ProductSpecialistOutput, DevelopmentSpecialistOutput, RiskSpecialistOutput),
)
def test_codex_output_schemas_are_recursively_strict(model):
    assert_codex_strict_objects(_codex_output_schema(model))


def test_strict_schema_conversion_preserves_fields_named_like_schema_keywords():
    schema = {
        "type": "object",
        "properties": {
            "default": {"type": "string", "default": "value"},
            "properties": {"type": "string"},
        },
    }

    _make_object_schemas_strict(schema)

    assert set(schema["properties"]) == {"default", "properties"}
    assert schema["properties"]["default"] == {"type": "string"}


def composition(tmp_path, adapter, *, protected_paths=()):
    return NativeSpecialistComposition(
        repository_root=tmp_path,
        profiles=ProfileCatalog(PROFILES_ROOT),
        adapter=adapter,
        evidence=FilesystemEvidenceStore(tmp_path / ".state" / "evidence"),
        protected_paths=protected_paths,
        clock=lambda: NOW,
        id_factory=lambda: "candidate-001",
    )


def test_product_loads_approved_profile_and_emits_typed_receipt(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    adapter = FakeCodexAdapter(
        [
            {
                "schema_version": "1.0",
                "run_id": "run-001",
                "task_id": "task-001",
                "repository_revision": "b5263eb",
                "created_at": "2026-07-27T16:00:00Z",
                "role": "v20-product",
                "attempt": 1,
                "route": "v20-development",
                "summary": "A bounded documentation task.",
                "development_instructions": "Create only the requested documentation file.",
                "acceptance_checks": ["git-diff-check"],
                "memory": [],
            }
        ]
    )

    receipt = composition(tmp_path, adapter).execute(request(workspace, SpecialistRole.PRODUCT))

    assert receipt.status is ExecutionStatus.COMPLETED
    assert receipt.output.role is SpecialistRole.PRODUCT
    assert receipt.output.route is SpecialistRole.DEVELOPMENT
    assert receipt.evidence
    _, options = adapter.calls[0]
    assert options["model"] == "docker-codex-default"
    assert options["reasoning_effort"] == "medium"
    assert options["output_schema"]["additionalProperties"] is False
    assert_codex_strict_objects(options["output_schema"])
    assert 'memory_type="product-decision"' in options["prompt"]
    assert 'content="Product routed task to v20-development."' in options["prompt"]


@pytest.mark.parametrize(
    ("response", "error_code"),
    [
        (None, "missing-specialist-output"),
        ("not-json", "invalid-specialist-output"),
        (
            json.dumps(
                {
                    "schema_version": "1.0",
                    "run_id": "foreign-run",
                    "task_id": "task-001",
                    "repository_revision": "b5263eb",
                    "created_at": "2026-07-27T16:00:00Z",
                    "role": "v20-product",
                    "attempt": 1,
                    "route": "v20-development",
                    "summary": "Foreign authority.",
                    "development_instructions": "Do nothing.",
                    "acceptance_checks": ["git-diff-check"],
                    "memory": [],
                }
            ),
            "foreign-specialist-output",
        ),
    ],
)
def test_malformed_or_foreign_output_becomes_persistable_failed_receipt(
    tmp_path,
    response,
    error_code,
):
    workspace = tmp_path / "task"
    workspace.mkdir()

    class OutputAdapter:
        def execute(self, item, **_kwargs):
            return CodexExecutionReceipt(
                run_id=item.run_id,
                task_id=item.task_id,
                repository_revision=item.repository_revision,
                created_at=item.created_at,
                execution_id="invalid-output",
                role=item.role,
                attempt=item.attempt,
                status=ExecutionStatus.COMPLETED,
                sandbox=item.permissions.sandbox,
                model="docker-codex-default",
                workspace=item.workspace,
                approval_mode="deny-all",
                authentication_type="chatgpt",
                permission_profile="docker-one-shot",
                started_at=NOW,
                finished_at=NOW,
                final_response=response,
            )

    receipt = composition(tmp_path, OutputAdapter()).execute(
        request(workspace, SpecialistRole.PRODUCT)
    )

    assert receipt.status is ExecutionStatus.FAILED
    assert receipt.error_code == error_code
    assert receipt.output is None
    assert receipt.final_response is None
    assert len(receipt.evidence) == 1


def test_foreign_execution_receipt_becomes_a_failed_audit_record(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    item = request(workspace, SpecialistRole.PRODUCT)
    valid_output = {
        "schema_version": "1.0",
        "run_id": item.run_id,
        "task_id": item.task_id,
        "repository_revision": item.repository_revision,
        "created_at": "2026-07-27T16:00:00Z",
        "role": item.role.value,
        "attempt": item.attempt,
        "route": "v20-development",
        "summary": "Bounded.",
        "development_instructions": "Change only the workspace.",
        "acceptance_checks": ["git-diff-check"],
        "memory": [],
    }

    class ForeignAdapter:
        def execute(self, request_item, **_kwargs):
            return codex_receipt(request_item, json.dumps(valid_output)).model_copy(
                update={"run_id": "foreign-run"}
            )

    receipt = composition(tmp_path, ForeignAdapter()).execute(item)

    assert receipt.status is ExecutionStatus.FAILED
    assert receipt.error_code == "foreign-execution-receipt"
    assert receipt.output is None
    assert len(receipt.evidence) == 1


def test_composition_rejects_permissions_that_do_not_exactly_match_profile(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    item = request(workspace, SpecialistRole.PRODUCT).model_copy(
        update={
            "permissions": PermissionSet(
                sandbox=SandboxMode.READ_ONLY,
                read_paths=(str(workspace),),
                allowed_tools=("read",),
            )
        }
    )
    adapter = FakeCodexAdapter([])

    with pytest.raises(ProfilePermissionMismatch):
        composition(tmp_path, adapter).execute(item)
    assert adapter.calls == []


def test_development_cannot_mutate_outside_controller_workspace(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    protected = tmp_path / "profiles" / "v20-risk-review" / "SOUL.md"
    protected.parent.mkdir(parents=True)
    protected.write_text("independent", encoding="utf-8")

    def mutate(_item):
        protected.write_text("tampered", encoding="utf-8")

    adapter = FakeCodexAdapter(
        [
            {
                "schema_version": "1.0",
                "run_id": "run-001",
                "task_id": "task-001",
                "repository_revision": "b5263eb",
                "created_at": "2026-07-27T16:00:00Z",
                "role": "v20-development",
                "attempt": 1,
                "summary": "Done.",
                "changed_files": [],
                "verification_commands": [],
                "residual_risks": [],
                "memory": [],
            }
        ],
        mutate=mutate,
    )

    with pytest.raises(WorkspaceMutationDenied):
        composition(tmp_path, adapter).execute(request(workspace, SpecialistRole.DEVELOPMENT))
    assert protected.read_text(encoding="utf-8") == "independent"


def test_rejected_turn_rolls_back_allowed_and_unauthorized_mutations(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    protected = tmp_path / "profiles" / "policy.md"
    protected.parent.mkdir(parents=True)
    protected.write_text("protected\n", encoding="utf-8")

    def mutate(_item):
        (workspace / "RESULT.md").write_text("partial\n", encoding="utf-8")
        protected.write_text("tampered\n", encoding="utf-8")

    adapter = FakeCodexAdapter(
        [
            {
                "schema_version": "1.0",
                "run_id": "run-001",
                "task_id": "task-001",
                "repository_revision": "b5263eb",
                "created_at": "2026-07-27T16:00:00Z",
                "role": "v20-development",
                "attempt": 1,
                "summary": "Done.",
                "changed_files": [],
                "verification_commands": [],
                "residual_risks": [],
                "memory": [],
            }
        ],
        mutate=mutate,
    )

    with pytest.raises(WorkspaceMutationDenied):
        composition(tmp_path, adapter).execute(request(workspace, SpecialistRole.DEVELOPMENT))

    assert not (workspace / "RESULT.md").exists()
    assert protected.read_text(encoding="utf-8") == "protected\n"


def test_adapter_exception_rolls_back_all_turn_mutations(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    protected = tmp_path / "protected.md"
    protected.write_text("protected\n", encoding="utf-8")

    class CrashingAdapter:
        def execute(self, _item, **_kwargs):
            (workspace / "RESULT.md").write_text("partial\n", encoding="utf-8")
            protected.write_text("tampered\n", encoding="utf-8")
            raise RuntimeError("adapter crashed")

    with pytest.raises(RuntimeError, match="adapter crashed"):
        composition(tmp_path, CrashingAdapter()).execute(
            request(workspace, SpecialistRole.DEVELOPMENT)
        )

    assert not (workspace / "RESULT.md").exists()
    assert protected.read_text(encoding="utf-8") == "protected\n"


def test_ignored_file_outside_workspace_is_detected_and_restored(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    workspace = tmp_path / "task"
    workspace.mkdir()
    ignored = tmp_path / "secret.cache"
    ignored.write_text("original\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*.cache\n", encoding="utf-8")

    def mutate(_item):
        ignored.write_text("tampered\n", encoding="utf-8")

    adapter = FakeCodexAdapter(
        [
            {
                "schema_version": "1.0",
                "run_id": "run-001",
                "task_id": "task-001",
                "repository_revision": "b5263eb",
                "created_at": "2026-07-27T16:00:00Z",
                "role": "v20-development",
                "attempt": 1,
                "summary": "Done.",
                "changed_files": [],
                "verification_commands": [],
                "residual_risks": [],
                "memory": [],
            }
        ],
        mutate=mutate,
    )

    with pytest.raises(WorkspaceMutationDenied):
        composition(tmp_path, adapter).execute(request(workspace, SpecialistRole.DEVELOPMENT))

    assert ignored.read_text(encoding="utf-8") == "original\n"


def test_development_cannot_leave_an_empty_directory_outside_workspace(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    unauthorized = tmp_path / "config" / "created-by-specialist"

    def mutate(_item):
        unauthorized.mkdir(parents=True)

    adapter = FakeCodexAdapter(
        [
            {
                "schema_version": "1.0",
                "run_id": "run-001",
                "task_id": "task-001",
                "repository_revision": "b5263eb",
                "created_at": "2026-07-27T16:00:00Z",
                "role": "v20-development",
                "attempt": 1,
                "summary": "Done.",
                "changed_files": [],
                "verification_commands": [],
                "residual_risks": [],
                "memory": [],
            }
        ],
        mutate=mutate,
    )

    with pytest.raises(WorkspaceMutationDenied):
        composition(tmp_path, adapter).execute(request(workspace, SpecialistRole.DEVELOPMENT))

    assert not unauthorized.exists()


def test_development_link_replacement_cannot_redirect_controller_restoration(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    controlled = workspace / "RESULT.md"
    controlled.write_text("controller-owned\n", encoding="utf-8")
    protected = tmp_path / "profiles" / "v20-risk-review" / "policy.md"
    protected.parent.mkdir(parents=True)
    protected.write_text("risk-policy\n", encoding="utf-8")

    def mutate(_item):
        controlled.unlink()
        controlled.symlink_to(protected)
        controlled.write_text("tampered\n", encoding="utf-8")

    adapter = FakeCodexAdapter(
        [
            {
                "schema_version": "1.0",
                "run_id": "run-001",
                "task_id": "task-001",
                "repository_revision": "b5263eb",
                "created_at": "2026-07-27T16:00:00Z",
                "role": "v20-development",
                "attempt": 1,
                "summary": "Done.",
                "changed_files": [],
                "verification_commands": [],
                "residual_risks": [],
                "memory": [],
            }
        ],
        mutate=mutate,
    )

    with pytest.raises(WorkspaceMutationDenied, match="introduced a link"):
        composition(tmp_path, adapter).execute(request(workspace, SpecialistRole.DEVELOPMENT))

    assert not controlled.is_symlink()
    assert controlled.read_text(encoding="utf-8") == "controller-owned\n"
    assert protected.read_text(encoding="utf-8") == "risk-policy\n"


def test_development_cannot_mutate_controller_protected_path_inside_workspace(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    protected = workspace / "approval-policy.md"
    protected.write_text("operator approval required\n", encoding="utf-8")

    def mutate(_item):
        protected.write_text("self approval allowed\n", encoding="utf-8")

    adapter = FakeCodexAdapter(
        [
            {
                "schema_version": "1.0",
                "run_id": "run-001",
                "task_id": "task-001",
                "repository_revision": "b5263eb",
                "created_at": "2026-07-27T16:00:00Z",
                "role": "v20-development",
                "attempt": 1,
                "summary": "Done.",
                "changed_files": [],
                "verification_commands": [],
                "residual_risks": [],
                "memory": [],
            }
        ],
        mutate=mutate,
    )

    with pytest.raises(WorkspaceMutationDenied, match="protected path"):
        composition(tmp_path, adapter, protected_paths=(protected,)).execute(
            request(workspace, SpecialistRole.DEVELOPMENT)
        )
    assert protected.read_text(encoding="utf-8") == "operator approval required\n"
    assert len(adapter.calls) == 1


def test_risk_review_uses_independent_read_only_turn_and_structured_decision(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    adapter = FakeCodexAdapter(
        [
            {
                "schema_version": "1.0",
                "run_id": "run-001",
                "task_id": "task-001",
                "repository_revision": "b5263eb",
                "created_at": "2026-07-27T16:00:00Z",
                "role": "v20-risk-review",
                "attempt": 1,
                "decision": "approve",
                "rationale": "Scope and evidence are sufficient.",
                "reviewed_changed_files": ["M2-CONTROLLED-EXERCISE.md"],
                "scope_compliant": True,
                "evidence_owned": True,
                "prohibited_actions_compliant": True,
                "residual_risks": [],
                "memory": [],
            }
        ]
    )
    item = request(workspace, SpecialistRole.DEVELOPMENT)
    development = SpecialistReceipt(
        run_id=item.run_id,
        task_id=item.task_id,
        repository_revision=item.repository_revision,
        created_at=item.created_at,
        receipt_id="development-001",
        role=SpecialistRole.DEVELOPMENT,
        attempt=1,
        status=ExecutionStatus.COMPLETED,
        final_response="done",
    )
    validation = ValidationResult(
        run_id=item.run_id,
        task_id=item.task_id,
        repository_revision=item.repository_revision,
        created_at=item.created_at,
        attempt=1,
        passed=True,
        checks=(
            ValidationCheck(
                name="git-diff-check",
                passed=True,
                command="git diff --check",
                exit_code=0,
            ),
        ),
    )

    review = composition(tmp_path, adapter).review_task(
        item=item,
        development=development,
        validation=validation,
    )

    assert review.decision.decision is RiskDecision.APPROVE
    assert review.receipt.role is SpecialistRole.RISK_REVIEW
    risk_input, _ = adapter.calls[0]
    assert risk_input.permissions.sandbox is SandboxMode.READ_ONLY
    assert risk_input.permissions.allowed_tools == ("read", "search")
    assert risk_input.permissions.read_paths == (str(workspace),)
    assert risk_input.memory_namespace[1] == "v20-risk-review"


def test_risk_review_preserves_noncompleted_execution_receipt(tmp_path):
    workspace = tmp_path / "task"
    workspace.mkdir()
    item = request(workspace, SpecialistRole.DEVELOPMENT)
    development = SpecialistReceipt(
        run_id=item.run_id,
        task_id=item.task_id,
        repository_revision=item.repository_revision,
        created_at=item.created_at,
        receipt_id="development-001",
        role=SpecialistRole.DEVELOPMENT,
        attempt=1,
        status=ExecutionStatus.COMPLETED,
    )
    validation = ValidationResult(
        run_id=item.run_id,
        task_id=item.task_id,
        repository_revision=item.repository_revision,
        created_at=item.created_at,
        attempt=1,
        passed=True,
        checks=(
            ValidationCheck(
                name="check",
                command="deterministic-check",
                passed=True,
                exit_code=0,
            ),
        ),
    )

    class UsageLimitedAdapter:
        def execute(self, risk_item, **_kwargs):
            return CodexExecutionReceipt(
                run_id=risk_item.run_id,
                task_id=risk_item.task_id,
                repository_revision=risk_item.repository_revision,
                created_at=risk_item.created_at,
                execution_id="risk-usage-limited",
                role=SpecialistRole.RISK_REVIEW,
                attempt=1,
                status=ExecutionStatus.USAGE_LIMITED,
                sandbox=SandboxMode.READ_ONLY,
                model="docker-codex-default",
                workspace=risk_item.workspace,
                approval_mode="deny-all",
                authentication_type="chatgpt",
                permission_profile="docker-one-shot",
                started_at=NOW,
                finished_at=NOW,
                error_code="usage_limit",
            )

    review = composition(tmp_path, UsageLimitedAdapter()).review_task(
        item=item,
        development=development,
        validation=validation,
    )

    assert review.decision is None
    assert review.receipt.status is ExecutionStatus.USAGE_LIMITED
    assert review.receipt.error_code == "usage_limit"


def test_correction_receipt_reports_cumulative_workspace_changes(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    workspace = tmp_path / "task"
    workspace.mkdir()
    (workspace / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=V20 Test",
            "-c",
            "user.email=v20-test@example.invalid",
            "commit",
            "-q",
            "-m",
            "baseline",
        ],
        cwd=tmp_path,
        check=True,
    )
    calls = 0

    def mutate(_item):
        nonlocal calls
        calls += 1
        if calls == 1:
            (workspace / "RESULT.md").write_text("controlled\n", encoding="utf-8")

    outputs = []
    for attempt in (1, 2):
        outputs.append(
            {
                "schema_version": "1.0",
                "run_id": "run-001",
                "task_id": "task-001",
                "repository_revision": "b5263eb",
                "created_at": "2026-07-27T16:00:00Z",
                "role": "v20-development",
                "attempt": attempt,
                "summary": "Done.",
                "changed_files": [],
                "verification_commands": [],
                "residual_risks": [],
                "memory": [],
            }
        )
    adapter = FakeCodexAdapter(outputs, mutate=mutate)
    runtime = composition(tmp_path, adapter)

    first = runtime.execute(request(workspace, SpecialistRole.DEVELOPMENT))
    second_input = request(workspace, SpecialistRole.DEVELOPMENT).model_copy(update={"attempt": 2})
    second = runtime.execute(second_input)

    assert first.output.changed_files == ("RESULT.md",)
    assert second.output.changed_files == ("RESULT.md",)
