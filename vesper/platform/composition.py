"""Controller-owned composition of the three approved local Codex specialists."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ValidationError

from .contracts import (
    CodexExecutionReceipt,
    DevelopmentSpecialistOutput,
    EvidenceArtifactRef,
    ExecutionStatus,
    MemoryCandidate,
    MemoryProposal,
    MemoryType,
    PermissionSet,
    ProductSpecialistOutput,
    RiskReviewDecision,
    RiskReviewExecution,
    RiskSpecialistOutput,
    SandboxMode,
    SpecialistInput,
    SpecialistOutput,
    SpecialistReceipt,
    SpecialistRole,
    TaskRequest,
    ValidationResult,
)
from .evidence import FilesystemEvidenceStore
from .profiles import LoadedProfile, ProfileCatalog


class CompositionError(RuntimeError):
    """Base class for specialist composition policy failures."""


class ProfilePermissionMismatch(CompositionError):
    """Controller input exceeds or differs from the loaded profile."""


class SpecialistOutputError(CompositionError):
    """Codex output is missing, malformed, or has foreign authority fields."""


class WorkspaceMutationDenied(CompositionError):
    """A specialist mutated files outside its controller-granted boundary."""


class SpecialistTurnAdapter(Protocol):
    def execute(
        self,
        request: SpecialistInput,
        *,
        prompt: str,
        model: str,
        timeout_seconds: float,
        reasoning_effort: str | None,
        output_schema: Mapping[str, object] | None,
    ) -> CodexExecutionReceipt: ...


@dataclass(frozen=True, slots=True)
class _FileState:
    kind: str
    body: bytes | None = None
    link_target: str | None = None


_ROLE_OUTPUTS = {
    SpecialistRole.PRODUCT: ProductSpecialistOutput,
    SpecialistRole.DEVELOPMENT: DevelopmentSpecialistOutput,
    SpecialistRole.RISK_REVIEW: RiskSpecialistOutput,
}

_ROLE_MEMORY = {
    SpecialistRole.PRODUCT: frozenset({MemoryType.PRODUCT_DECISION}),
    SpecialistRole.DEVELOPMENT: frozenset(
        {MemoryType.DEVELOPMENT_EPISODE, MemoryType.FAILED_ATTEMPT}
    ),
    SpecialistRole.RISK_REVIEW: frozenset({MemoryType.RISK_DECISION}),
}

_MEMORY_CATEGORY = {
    SpecialistRole.PRODUCT: "product-decisions",
    SpecialistRole.DEVELOPMENT: "development-episodes",
    SpecialistRole.RISK_REVIEW: "risk-decisions",
}

_SNAPSHOT_EXCLUDES = frozenset({".git", ".state"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _codex_output_schema(model: type[BaseModel]) -> dict[str, object]:
    """Return the strict JSON schema required by Codex structured output."""
    schema = model.model_json_schema()
    _make_object_schemas_strict(schema)
    return schema


def _make_object_schemas_strict(value: object) -> None:
    if isinstance(value, dict):
        value.pop("default", None)
        properties = value.get("properties")
        if isinstance(properties, dict):
            value["required"] = list(properties)
            value["additionalProperties"] = False
        for key, child in tuple(value.items()):
            if key in {"properties", "$defs", "patternProperties", "dependentSchemas"}:
                if isinstance(child, dict):
                    for child_schema in child.values():
                        _make_object_schemas_strict(child_schema)
                continue
            _make_object_schemas_strict(child)
    elif isinstance(value, list):
        for child in value:
            _make_object_schemas_strict(child)


class NativeSpecialistComposition:
    """Load approved profiles, invoke Codex, and emit controller-verifiable receipts."""

    def __init__(
        self,
        *,
        repository_root: Path,
        profiles: ProfileCatalog,
        adapter: SpecialistTurnAdapter,
        evidence: FilesystemEvidenceStore,
        protected_paths: tuple[Path, ...] = (),
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.profiles = profiles
        self.adapter = adapter
        self.evidence = evidence
        implicit_protected = (profiles.root, Path(__file__).resolve().parent)
        self.protected_paths = tuple(
            path.resolve()
            for path in (*implicit_protected, *protected_paths)
            if path.resolve().is_relative_to(self.repository_root)
        )
        self.clock = clock
        self.id_factory = id_factory

    def execute(self, request: SpecialistInput) -> SpecialistReceipt:
        """Execute Product or Development through its exact approved profile."""
        if request.role is SpecialistRole.RISK_REVIEW:
            raise CompositionError("Risk Review requires review_task with validation evidence")
        profile = self.profiles.load(request.role)
        workspace = self._validate_request(profile, request)
        before = self._snapshot_repository()
        try:
            execution = self.adapter.execute(
                request,
                prompt=self._specialist_prompt(profile, request),
                model=profile.model.name,
                timeout_seconds=profile.timeout.seconds,
                reasoning_effort=profile.model.reasoning_effort,
                output_schema=_codex_output_schema(_ROLE_OUTPUTS[request.role]),
            )
        except Exception:
            self._rollback_turn(before)
            raise
        changed = self._enforce_mutation_boundary(
            request=request,
            workspace=workspace,
            before=before,
        )
        return self._build_receipt(
            request,
            execution,
            changed_files=changed,
            expected_model=profile.model.name,
        )

    def review(
        self,
        request: TaskRequest,
        development_receipt: SpecialistReceipt,
        validation: ValidationResult,
    ) -> RiskReviewExecution:
        item = SpecialistInput(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            role=SpecialistRole.RISK_REVIEW,
            attempt=development_receipt.attempt,
            instructions=self._risk_instructions(request, development_receipt, validation),
            workspace=request.repository_root,
            memory_namespace=(
                "profiles",
                SpecialistRole.RISK_REVIEW.value,
                "risk-decisions",
            ),
            permissions=PermissionSet(
                sandbox=SandboxMode.READ_ONLY,
                read_paths=(request.repository_root,),
                allowed_tools=("read", "search"),
            ),
        )
        return self.review_task(
            item=item,
            development=development_receipt,
            validation=validation,
        )

    def review_task(
        self,
        *,
        item: SpecialistInput,
        development: SpecialistReceipt,
        validation: ValidationResult,
    ) -> RiskReviewExecution:
        """Run independent Risk Review with only controller-supplied evidence."""
        if item.role is not SpecialistRole.RISK_REVIEW:
            item = item.model_copy(
                update={
                    "role": SpecialistRole.RISK_REVIEW,
                    "permissions": PermissionSet(
                        sandbox=SandboxMode.READ_ONLY,
                        read_paths=(item.workspace,),
                        allowed_tools=("read", "search"),
                    ),
                    "memory_namespace": (
                        "profiles",
                        SpecialistRole.RISK_REVIEW.value,
                        "risk-decisions",
                    ),
                    "instructions": self._risk_instructions_from_records(
                        development,
                        validation,
                    ),
                }
            )
        profile = self.profiles.load(SpecialistRole.RISK_REVIEW)
        workspace = self._validate_request(profile, item)
        before = self._snapshot_repository()
        try:
            execution = self.adapter.execute(
                item,
                prompt=self._specialist_prompt(profile, item),
                model=profile.model.name,
                timeout_seconds=profile.timeout.seconds,
                reasoning_effort=profile.model.reasoning_effort,
                output_schema=_codex_output_schema(RiskSpecialistOutput),
            )
        except Exception:
            self._rollback_turn(before)
            raise
        self._enforce_mutation_boundary(request=item, workspace=workspace, before=before)
        receipt = self._build_receipt(
            item,
            execution,
            changed_files=(),
            expected_model=profile.model.name,
        )
        if receipt.status is not ExecutionStatus.COMPLETED:
            return RiskReviewExecution(receipt=receipt)
        if not isinstance(receipt.output, RiskSpecialistOutput):
            raise SpecialistOutputError("Risk Review did not produce a completed typed output")
        output = receipt.output
        if isinstance(development.output, DevelopmentSpecialistOutput) and set(
            output.reviewed_changed_files
        ) != set(development.output.changed_files):
            return RiskReviewExecution(
                receipt=self._invalid_output_receipt(
                    item,
                    execution,
                    receipt.evidence,
                    error_code="risk-changed-files-mismatch",
                )
            )
        decision = RiskReviewDecision(
            run_id=output.run_id,
            task_id=output.task_id,
            repository_revision=output.repository_revision,
            created_at=output.created_at,
            attempt=output.attempt,
            decision=output.decision,
            rationale=output.rationale,
            evidence=receipt.evidence,
            reviewed_changed_files=output.reviewed_changed_files,
            scope_compliant=output.scope_compliant,
            evidence_owned=output.evidence_owned,
            prohibited_actions_compliant=output.prohibited_actions_compliant,
            residual_risks=output.residual_risks,
        )
        return RiskReviewExecution(receipt=receipt, decision=decision)

    def _build_receipt(
        self,
        request: SpecialistInput,
        execution: CodexExecutionReceipt,
        *,
        changed_files: tuple[str, ...],
        expected_model: str,
    ) -> SpecialistReceipt:
        execution_identifier = hashlib.sha256(execution.execution_id.encode("utf-8")).hexdigest()[
            :24
        ]
        execution_ref = self.evidence.put_bytes(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=self.clock(),
            artifact_id=f"codex-{request.role.value}-{request.attempt}-{execution_identifier}",
            body=execution.model_dump_json(indent=2).encode("utf-8") + b"\n",
            media_type="application/json",
            suffix=".json",
        )
        if not self._execution_matches_request(request, execution, expected_model):
            return self._invalid_output_receipt(
                request,
                execution,
                (execution_ref,),
                error_code="foreign-execution-receipt",
            )
        if execution.status is not ExecutionStatus.COMPLETED:
            return SpecialistReceipt(
                run_id=request.run_id,
                task_id=request.task_id,
                repository_revision=request.repository_revision,
                created_at=request.created_at,
                receipt_id=f"receipt-{execution.execution_id}",
                role=request.role,
                attempt=request.attempt,
                status=execution.status,
                thread_id=execution.thread_id,
                final_response=execution.final_response,
                evidence=(execution_ref,),
                error_code=execution.error_code,
            )
        if not execution.final_response:
            return self._invalid_output_receipt(
                request,
                execution,
                (execution_ref,),
                error_code="missing-specialist-output",
            )
        output_type = _ROLE_OUTPUTS[request.role]
        try:
            output = output_type.model_validate_json(execution.final_response)
        except (ValidationError, ValueError):
            return self._invalid_output_receipt(
                request,
                execution,
                (execution_ref,),
                error_code="invalid-specialist-output",
            )
        if (
            output.run_id != request.run_id
            or output.task_id != request.task_id
            or output.repository_revision != request.repository_revision
            or output.role is not request.role
            or output.attempt != request.attempt
        ):
            return self._invalid_output_receipt(
                request,
                execution,
                (execution_ref,),
                error_code="foreign-specialist-output",
            )
        if request.role is SpecialistRole.DEVELOPMENT:
            output = output.model_copy(update={"changed_files": changed_files})
        output_ref = self.evidence.put_bytes(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=self.clock(),
            artifact_id=f"output-{request.role.value}-{request.attempt}-{execution_identifier}",
            body=output.model_dump_json(indent=2).encode("utf-8") + b"\n",
            media_type="application/json",
            suffix=".json",
        )
        try:
            candidates = self._memory_candidates(request, output.memory, output_ref)
        except SpecialistOutputError:
            return self._invalid_output_receipt(
                request,
                execution,
                (execution_ref, output_ref),
                error_code="unauthorized-memory-proposal",
            )
        return SpecialistReceipt(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            receipt_id=f"receipt-{execution.execution_id}",
            role=request.role,
            attempt=request.attempt,
            status=execution.status,
            thread_id=execution.thread_id,
            final_response=output.model_dump_json(),
            output=output,
            evidence=(execution_ref, output_ref),
            memory_candidates=candidates,
            error_code=execution.error_code,
        )

    @staticmethod
    def _execution_matches_request(
        request: SpecialistInput,
        execution: CodexExecutionReceipt,
        expected_model: str,
    ) -> bool:
        try:
            execution_workspace = (
                None if execution.workspace is None else Path(execution.workspace).resolve()
            )
            requested_workspace = Path(request.workspace).resolve()
        except OSError:
            return False
        return (
            execution.run_id == request.run_id
            and execution.task_id == request.task_id
            and execution.repository_revision == request.repository_revision
            and execution.created_at == request.created_at
            and execution.role is request.role
            and execution.attempt == request.attempt
            and execution.sandbox is request.permissions.sandbox
            and execution.model == expected_model
            and execution_workspace == requested_workspace
            and execution.approval_mode == "deny-all"
            and execution.authentication_type == "chatgpt"
            and execution.permission_profile == "docker-one-shot"
        )

    @staticmethod
    def _invalid_output_receipt(
        request: SpecialistInput,
        execution: CodexExecutionReceipt,
        evidence: tuple[EvidenceArtifactRef, ...],
        *,
        error_code: str,
    ) -> SpecialistReceipt:
        return SpecialistReceipt(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            receipt_id=f"receipt-{execution.execution_id}",
            role=request.role,
            attempt=request.attempt,
            status=ExecutionStatus.FAILED,
            thread_id=execution.thread_id,
            evidence=evidence,
            error_code=error_code,
        )

    def _memory_candidates(
        self,
        request: SpecialistInput,
        proposals: tuple[MemoryProposal, ...],
        source_artifact,
    ) -> tuple[MemoryCandidate, ...]:
        candidates = []
        for proposal in proposals:
            if proposal.memory_type not in _ROLE_MEMORY[request.role]:
                raise SpecialistOutputError(
                    f"{request.role.value} proposed an unauthorized memory type"
                )
            candidates.append(
                MemoryCandidate(
                    run_id=request.run_id,
                    task_id=request.task_id,
                    repository_revision=request.repository_revision,
                    created_at=self.clock(),
                    candidate_id=self.id_factory(),
                    namespace=request.memory_namespace,
                    memory_type=proposal.memory_type,
                    content=proposal.content,
                    source_artifact=source_artifact,
                    confidence=proposal.confidence,
                    contradicts=proposal.contradicts,
                    expiration_policy=proposal.expiration_policy,
                )
            )
        return tuple(candidates)

    def _validate_request(self, profile: LoadedProfile, request: SpecialistInput) -> Path:
        if profile.profile_id is not request.role:
            raise ProfilePermissionMismatch("profile role does not match specialist input")
        requested_workspace = Path(os.path.abspath(request.workspace))
        try:
            requested_workspace.relative_to(self.repository_root)
        except ValueError as exc:
            raise ProfilePermissionMismatch("workspace is outside the approved repository") from exc
        if self._first_link_component(requested_workspace) is not None:
            raise ProfilePermissionMismatch("workspace path crosses a symbolic link or junction")
        workspace = requested_workspace.resolve()
        if not workspace.is_dir() or not workspace.is_relative_to(self.repository_root):
            raise ProfilePermissionMismatch("workspace is outside the approved repository")
        if workspace == self.repository_root:
            raise ProfilePermissionMismatch("workspace must be a dedicated repository subdirectory")
        if any(
            workspace == protected or workspace.is_relative_to(protected)
            for protected in self.protected_paths
        ):
            raise ProfilePermissionMismatch(
                "workspace overlaps controller-protected profiles or platform policy"
            )
        if self._workspace_link(workspace) is not None:
            raise ProfilePermissionMismatch(
                "workspace contains a symbolic link or junction and is not an isolated boundary"
            )
        expected_namespace = (
            *profile.memory_namespace,
            _MEMORY_CATEGORY[request.role],
        )
        if request.memory_namespace != expected_namespace:
            raise ProfilePermissionMismatch("memory namespace differs from the profile boundary")
        if request.permissions.sandbox is not profile.permissions.sandbox:
            raise ProfilePermissionMismatch("sandbox differs from the profile boundary")
        if request.permissions.allowed_tools != profile.permissions.allowed_tools:
            raise ProfilePermissionMismatch("tool allowlist differs from the profile boundary")
        expected_read = (workspace,)
        actual_read = tuple(Path(item).resolve() for item in request.permissions.read_paths)
        expected_write = (workspace,) if request.role is SpecialistRole.DEVELOPMENT else ()
        actual_write = tuple(Path(item).resolve() for item in request.permissions.write_paths)
        if actual_read != expected_read or actual_write != expected_write:
            raise ProfilePermissionMismatch("filesystem paths differ from the controller boundary")
        return workspace

    def _enforce_mutation_boundary(
        self,
        *,
        request: SpecialistInput,
        workspace: Path,
        before: Mapping[str, _FileState],
    ) -> tuple[str, ...]:
        after = self._snapshot_repository()
        changed = tuple(
            sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
        )
        link_changes = {
            relative
            for relative in changed
            if any(
                state is not None and state.kind == "link"
                for state in (before.get(relative), after.get(relative))
            )
        }
        permitted = request.role is SpecialistRole.DEVELOPMENT
        unauthorized = [
            relative
            for relative in changed
            if not permitted
            or not (self.repository_root / relative).resolve().is_relative_to(workspace)
            or self._is_protected(self.repository_root / relative)
        ]
        if link_changes:
            unauthorized = list(changed)
        if unauthorized:
            self._restore_snapshot(before, after, list(changed))
            raise WorkspaceMutationDenied(
                "specialist changed files outside its boundary, introduced a link, "
                "or changed a protected path: " + ", ".join(unauthorized)
            )
        cumulative = self._cumulative_workspace_changes(workspace)
        if cumulative is not None:
            return cumulative
        return tuple(
            (self.repository_root / relative).resolve().relative_to(workspace).as_posix()
            for relative in changed
            if (
                (after.get(relative) is not None and after[relative].kind == "file")
                or (before.get(relative) is not None and before[relative].kind == "file")
            )
        )

    def _rollback_turn(self, before: Mapping[str, _FileState]) -> None:
        after = self._snapshot_repository()
        changed = [path for path in set(before) | set(after) if before.get(path) != after.get(path)]
        if changed:
            self._restore_snapshot(before, after, changed)

    def _is_protected(self, path: Path) -> bool:
        resolved = path.resolve()
        return any(
            resolved == protected or resolved.is_relative_to(protected)
            for protected in self.protected_paths
        )

    def _cumulative_workspace_changes(self, workspace: Path) -> tuple[str, ...] | None:
        relative_workspace = workspace.relative_to(self.repository_root).as_posix()
        changed = subprocess.run(
            [
                "git",
                "-C",
                str(self.repository_root),
                "diff",
                "--name-only",
                "-z",
                "HEAD",
                "--",
                relative_workspace,
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
        untracked = subprocess.run(
            [
                "git",
                "-C",
                str(self.repository_root),
                "ls-files",
                "--others",
                "-z",
                "--",
                relative_workspace,
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
        if changed.returncode != 0 or untracked.returncode != 0:
            return None
        paths = {
            raw.decode("utf-8")
            for raw in (*changed.stdout.split(b"\0"), *untracked.stdout.split(b"\0"))
            if raw
        }
        return tuple(
            sorted(
                self.repository_root.joinpath(*Path(relative).parts)
                .resolve()
                .relative_to(workspace)
                .as_posix()
                for relative in paths
            )
        )

    def _snapshot_repository(self) -> dict[str, _FileState]:
        paths = self._git_paths()
        if paths is None:
            paths = tuple(
                path
                for path in self.repository_root.rglob("*")
                if path.is_file()
                and not any(
                    part in _SNAPSHOT_EXCLUDES
                    for part in path.relative_to(self.repository_root).parts
                )
            )
        result = {}
        for root, directories, _files in os.walk(self.repository_root, followlinks=False):
            current = Path(root)
            retained = []
            for name in directories:
                candidate = current / name
                relative = candidate.relative_to(self.repository_root)
                if any(part in _SNAPSHOT_EXCLUDES for part in relative.parts):
                    continue
                if self._is_link_like(candidate):
                    result[relative.as_posix()] = _FileState(
                        kind="link",
                        link_target=self._read_link_target(candidate),
                    )
                    continue
                result[relative.as_posix()] = _FileState(kind="directory")
                retained.append(name)
            directories[:] = retained
        for path in paths:
            link = self._first_link_component(path)
            if link is not None:
                relative = link.relative_to(self.repository_root).as_posix()
                result[relative] = _FileState(
                    kind="link",
                    link_target=self._read_link_target(link),
                )
                continue
            if not path.is_file():
                continue
            relative = path.relative_to(self.repository_root).as_posix()
            result[relative] = _FileState(kind="file", body=path.read_bytes())
        return result

    @staticmethod
    def _is_link_like(path: Path) -> bool:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return False
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        attributes = getattr(metadata, "st_file_attributes", 0)
        return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)

    def _first_link_component(self, path: Path) -> Path | None:
        try:
            relative = path.relative_to(self.repository_root)
        except ValueError:
            return None
        current = self.repository_root
        for part in relative.parts:
            current = current / part
            if self._is_link_like(current):
                return current
        return None

    def _workspace_link(self, workspace: Path) -> Path | None:
        for root, directories, files in os.walk(workspace, followlinks=False):
            current = Path(root)
            for name in (*directories, *files):
                candidate = current / name
                if self._is_link_like(candidate):
                    return candidate
        return None

    @staticmethod
    def _read_link_target(path: Path) -> str:
        try:
            return os.readlink(path)
        except OSError:
            return "<reparse-point>"

    def _git_paths(self) -> tuple[Path, ...] | None:
        top_level = subprocess.run(
            ["git", "-C", str(self.repository_root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
        if (
            top_level.returncode != 0
            or Path(top_level.stdout.strip()).resolve() != self.repository_root
        ):
            return None
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(self.repository_root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
        ignored = subprocess.run(
            [
                "git",
                "-C",
                str(self.repository_root),
                "ls-files",
                "--others",
                "--ignored",
                "--exclude-standard",
                "-z",
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0 or ignored.returncode != 0:
            return None
        return tuple(
            path
            for raw in (*completed.stdout.split(b"\0"), *ignored.stdout.split(b"\0"))
            if raw
            for path in (self.repository_root.joinpath(*Path(raw.decode("utf-8")).parts),)
            if not any(
                part in _SNAPSHOT_EXCLUDES for part in path.relative_to(self.repository_root).parts
            )
        )

    def _restore_snapshot(
        self,
        before: Mapping[str, _FileState],
        after: Mapping[str, _FileState],
        paths: list[str],
    ) -> None:
        ordered = sorted(set(paths), key=lambda value: len(Path(value).parts), reverse=True)
        for relative in ordered:
            path = self.repository_root.joinpath(*Path(relative).parts)
            if self._is_link_like(path) or path.is_file():
                path.unlink()
            elif path.exists() and path.is_dir():
                previous = before.get(relative)
                if previous is None or previous.kind != "directory":
                    try:
                        path.rmdir()
                    except OSError as exc:
                        raise WorkspaceMutationDenied(
                            f"cannot safely remove a nonempty unauthorized directory: {relative}"
                        ) from exc
        for relative in sorted(set(paths), key=lambda value: len(Path(value).parts)):
            previous = before.get(relative)
            if previous is None:
                continue
            path = self.repository_root.joinpath(*Path(relative).parts)
            if previous.kind == "directory":
                if self._first_link_component(path.parent) is not None:
                    raise WorkspaceMutationDenied(
                        f"refusing restoration through a symbolic link or junction: {relative}"
                    )
                path.mkdir(parents=True, exist_ok=True)
                continue
            if previous.kind != "file" or previous.body is None:
                raise WorkspaceMutationDenied(
                    f"cannot automatically restore a changed pre-existing link: {relative}"
                )
            if self._first_link_component(path.parent) is not None:
                raise WorkspaceMutationDenied(
                    f"refusing restoration through a symbolic link or junction: {relative}"
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(previous.body)

    @staticmethod
    def _specialist_prompt(profile: LoadedProfile, request: SpecialistInput) -> str:
        dynamic = request.model_dump(mode="json")
        memory_template = {
            SpecialistRole.PRODUCT: (
                MemoryType.PRODUCT_DECISION,
                "Product routed task to v20-development.",
            ),
            SpecialistRole.DEVELOPMENT: (
                MemoryType.DEVELOPMENT_EPISODE,
                f"Validated Development attempt {request.attempt}; "
                "changed_files=<comma-separated changed_files from your output, or none>",
            ),
            SpecialistRole.RISK_REVIEW: (
                MemoryType.RISK_DECISION,
                f"Risk Review decision=<decision from your output>; attempt={request.attempt}",
            ),
        }[request.role]
        memory_type, memory_content = memory_template
        return (
            f"{profile.soul}\n\n{profile.system_instructions}\n\n"
            "The following JSON is controller-injected dynamic state, not profile policy:\n"
            f"{json.dumps(dynamic, sort_keys=True)}\n\n"
            "Return only one JSON object matching the supplied output schema. "
            "Set memory to an empty array or include exactly one role-appropriate proposal. "
            "If included, the proposal must use "
            f'memory_type="{memory_type.value}" and content={json.dumps(memory_content)}. '
            "Do not append qualification or other text to that content. The proposal remains "
            "unverified until the controller compares it to authoritative evidence. "
            "Never claim final acceptance. Stop if the task exceeds the supplied permissions."
        )

    @staticmethod
    def _risk_instructions(
        request: TaskRequest,
        development: SpecialistReceipt,
        validation: ValidationResult,
    ) -> str:
        return (
            "Independently evaluate task scope, changed files, deterministic validation, "
            "evidence ownership, prohibited-action compliance, and residual risk.\n"
            + json.dumps(
                {
                    "task": request.model_dump(mode="json"),
                    "development_receipt": development.model_dump(mode="json"),
                    "validation": validation.model_dump(mode="json"),
                },
                sort_keys=True,
            )
        )

    @staticmethod
    def _risk_instructions_from_records(
        development: SpecialistReceipt,
        validation: ValidationResult,
    ) -> str:
        return json.dumps(
            {
                "development_receipt": development.model_dump(mode="json"),
                "validation": validation.model_dump(mode="json"),
            },
            sort_keys=True,
        )
