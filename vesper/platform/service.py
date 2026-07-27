"""Local graph-backed service used by the Typer control surface."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .composition import NativeSpecialistComposition
from .contracts import (
    ApprovalDecision,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RunStatus,
    SpecialistReceipt,
    TaskRequest,
)
from .persistence import PlatformPaths, PlatformPersistence, open_persistence
from .memory import DeterministicMemoryCandidateValidator, MemoryService
from .profiles import ProfileCatalog
from .sandbox_runtime import DockerCodexRuntime
from .validation import LocalDeterministicValidator, validate_acceptance_checks
from .worktree import inspect_worktree
from .workflow import (
    APPROVAL_REQUEST_NAMESPACE,
    WorkflowController,
    WorkflowView,
    build_workflow,
)

RUN_RUNTIME_NAMESPACE = ("system", "run-runtime")
M2_APPROVED_WORKSPACE = Path("docs/m2-controlled-exercise")


class SpecialistRuntimeUnavailable(RuntimeError):
    """No real or deterministic specialist runtime was configured."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def _repository_lease(repository_root: Path):
    lock_path = repository_root / ".git" / "v20-controller.lock"
    try:
        handle = lock_path.open("a+b")
    except OSError as exc:
        raise SpecialistRuntimeUnavailable("repository controller lease is unavailable") from exc
    locked = False
    try:
        if lock_path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SpecialistRuntimeUnavailable(
                "another controller operation owns the repository lease"
            ) from exc
        locked = True
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


class _UnavailableSpecialists:
    def execute(self, request):
        raise SpecialistRuntimeUnavailable(
            "create requires an explicitly configured specialist runtime; real Codex execution "
            "is not enabled by the offline platform CLI"
        )


class _UnavailableValidator:
    def validate(self, request, development_receipt):
        raise SpecialistRuntimeUnavailable("deterministic validator is not configured")


class _UnavailableRiskReviewer:
    def review(self, request, development_receipt, validation):
        raise SpecialistRuntimeUnavailable("Risk Review specialist is not configured")


class LocalPlatformService:
    """Open local persistence per command and expose graph lifecycle operations."""

    def __init__(
        self,
        paths: PlatformPaths,
        *,
        controller_factory: Callable[[PlatformPersistence], WorkflowController] | None = None,
        profiles_root: Path | None = None,
        adapter_factory: Callable[[Path, tuple[str, ...]], object] | None = None,
        require_disposable_worktree: bool = True,
        require_clean_worktree: bool = True,
        required_branch_prefix: str = "m2/",
        approved_workspace_relative_paths: tuple[Path, ...] = (M2_APPROVED_WORKSPACE,),
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.paths = paths
        self._controller_factory = controller_factory
        self._profiles_root = (
            Path("profiles/native").resolve() if profiles_root is None else profiles_root.resolve()
        )
        self._adapter_factory = adapter_factory
        self._require_disposable_worktree = require_disposable_worktree
        self._require_clean_worktree = require_clean_worktree
        self._required_branch_prefix = required_branch_prefix
        self._approved_workspace_relative_paths = approved_workspace_relative_paths
        self._clock = clock
        self._id_factory = id_factory

    def create_run(
        self,
        objective: str,
        workspace: str,
        repository_revision: str,
        acceptance_checks: tuple[str, ...] | None = None,
    ) -> dict[str, object]:
        workspace_path = Path(workspace).resolve()
        checks = acceptance_checks or ("git-diff-check",)
        try:
            validate_acceptance_checks(checks)
        except ValueError as exc:
            raise SpecialistRuntimeUnavailable(str(exc)) from exc
        repository_root = (
            None if self._controller_factory is not None else self._repository_root(workspace_path)
        )
        if repository_root is not None:
            with _repository_lease(repository_root):
                return self._create_run_locked(
                    objective,
                    workspace_path,
                    repository_revision,
                    checks,
                    repository_root,
                )
        return self._create_run_locked(
            objective,
            workspace_path,
            repository_revision,
            checks,
            None,
        )

    def _create_run_locked(
        self,
        objective: str,
        workspace_path: Path,
        repository_revision: str,
        checks: tuple[str, ...],
        repository_root: Path | None,
    ) -> dict[str, object]:
        if repository_root is not None:
            self._validate_production_boundaries(repository_root, workspace_path)
            context = inspect_worktree(
                repository_root,
                require_standalone=self._require_disposable_worktree,
                require_clean=self._require_clean_worktree,
                required_branch_prefix=(
                    self._required_branch_prefix if self._require_disposable_worktree else None
                ),
            )
            if repository_revision != context.commit:
                raise SpecialistRuntimeUnavailable(
                    "repository revision must exactly match the disposable clone HEAD"
                )
            profile_fingerprints = self._profile_fingerprints()
        else:
            profile_fingerprints = None
        task = TaskRequest(
            run_id=self._id_factory(),
            task_id=self._id_factory(),
            repository_revision=repository_revision,
            created_at=self._clock(),
            objective=objective,
            repository_root=str(workspace_path),
            acceptance_checks=checks,
        )
        with open_persistence(self.paths) as persistence:
            if repository_root is not None:
                persistence.store.put(
                    RUN_RUNTIME_NAMESPACE,
                    task.run_id,
                    {
                        "repository_root": str(repository_root),
                        "workspace": str(workspace_path),
                        "repository_revision": repository_revision,
                        "profiles_root": str(self._profiles_root),
                        "profile_fingerprints": profile_fingerprints,
                    },
                )
            view = self._controller(persistence, repository_root=repository_root).start(task)
        return self._view_payload(view)

    def inspect_run(self, run_id: str) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            view = self._controller(persistence).inspect(run_id)
        return self._view_payload(view)

    def resume_run(self, run_id: str) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            with self._lease_for_run(persistence, run_id):
                view = self._controller_for_run(persistence, run_id).resume(run_id)
        return self._view_payload(view)

    def list_receipts(self, run_id: str) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            view = self._controller(persistence).inspect(run_id)
        return {
            "run_id": run_id,
            "status": view.state.status.value,
            "receipts": [receipt.model_dump(mode="json") for receipt in view.state.receipts],
        }

    def list_evidence(self, run_id: str) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            view = self._controller(persistence).inspect(run_id)
        artifacts = []
        for receipt in view.state.receipts:
            artifacts.extend(receipt.evidence)
        if view.state.validation is not None:
            for check in view.state.validation.checks:
                artifacts.extend(check.evidence)
        if view.state.risk_review is not None:
            artifacts.extend(view.state.risk_review.evidence)
        if view.pending_approval is not None:
            artifacts.extend(view.pending_approval.evidence)
        unique = {
            (artifact.relative_path, artifact.sha256): artifact.model_dump(mode="json")
            for artifact in artifacts
        }
        return {
            "run_id": run_id,
            "status": view.state.status.value,
            "evidence": list(unique.values()),
        }

    def list_pending_approvals(self) -> dict[str, object]:
        pending = []
        with open_persistence(self.paths) as persistence:
            for raw in persistence.store.search(APPROVAL_REQUEST_NAMESPACE, limit=100):
                request = HumanApprovalRequest.model_validate_json(json.dumps(raw))
                controller = self._controller(persistence)
                view = controller.inspect(request.run_id)
                if view.state.status is RunStatus.AWAITING_APPROVAL:
                    pending.append(self._view_payload(view))
        pending.sort(key=lambda item: str(item["run_id"]))
        return {"pending": pending}

    def approve_run(
        self,
        run_id: str,
        checkpoint_id: str,
        operator_id: str,
        reason: str,
    ) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            with self._lease_for_run(persistence, run_id):
                controller = self._controller_for_run(persistence, run_id)
                view = controller.inspect(run_id)
                decision = self._decision(
                    view,
                    checkpoint_id=checkpoint_id,
                    operator_id=operator_id,
                    reason=reason,
                    decision=ApprovalDecision.APPROVE,
                )
                controller.record_decision(run_id, decision)
                payload = self._view_payload(controller.inspect(run_id))
        payload["resume_required"] = True
        return payload

    def reject_run(
        self,
        run_id: str,
        checkpoint_id: str,
        operator_id: str,
        reason: str,
    ) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            with self._lease_for_run(persistence, run_id):
                controller = self._controller_for_run(persistence, run_id)
                view = controller.inspect(run_id)
                decision = self._decision(
                    view,
                    checkpoint_id=checkpoint_id,
                    operator_id=operator_id,
                    reason=reason,
                    decision=ApprovalDecision.REJECT,
                )
                controller.record_decision(run_id, decision)
                rejected = controller.resume(run_id)
        return self._view_payload(rejected)

    def cancel_run(self, run_id: str, reason: str) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            with self._lease_for_run(persistence, run_id):
                view = self._controller_for_run(persistence, run_id).cancel(run_id, reason)
        return self._view_payload(view)

    def _controller(
        self,
        persistence: PlatformPersistence,
        *,
        repository_root: Path | None = None,
    ) -> WorkflowController:
        if self._controller_factory is not None:
            return self._controller_factory(persistence)
        if repository_root is not None:
            if not self._profiles_root.is_relative_to(repository_root):
                raise SpecialistRuntimeUnavailable(
                    "native profile catalog must be inside the approved clone"
                )
            profiles = ProfileCatalog(self._profiles_root)
            loaded = profiles.load_all()
            models = tuple(sorted({profile.model.name for profile in loaded}))
            adapter = (
                self._adapter_factory(repository_root, models)
                if self._adapter_factory is not None
                else DockerCodexRuntime(
                    repository_root=repository_root,
                    approved_models=models,
                    clock=self._clock,
                )
            )
            composition = NativeSpecialistComposition(
                repository_root=repository_root,
                profiles=profiles,
                adapter=adapter,
                evidence=persistence.evidence,
                protected_paths=tuple(
                    repository_root / relative / "README.md"
                    for relative in self._approved_workspace_relative_paths
                ),
                clock=self._clock,
                id_factory=self._id_factory,
            )
            graph = build_workflow(
                checkpointer=persistence.checkpointer,
                store=persistence.langgraph_store,
                specialists=composition,
                validator=LocalDeterministicValidator(
                    repository_root=repository_root,
                    evidence=persistence.evidence,
                    clock=self._clock,
                ),
                risk_reviewer=composition,
                memory_service=MemoryService(
                    persistence.store,
                    id_factory=self._id_factory,
                    clock=self._clock,
                ),
                memory_validator=DeterministicMemoryCandidateValidator(),
                evidence_reader=persistence.evidence.read_verified,
                clock=self._clock,
            )
            return WorkflowController(
                graph=graph,
                store=persistence.store,
                evidence_reader=persistence.evidence.read_verified,
                clock=self._clock,
                id_factory=self._id_factory,
            )
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            store=persistence.langgraph_store,
            specialists=_UnavailableSpecialists(),
            validator=_UnavailableValidator(),
            risk_reviewer=_UnavailableRiskReviewer(),
            clock=self._clock,
        )
        return WorkflowController(graph=graph, store=persistence.store, clock=self._clock)

    def _controller_for_run(
        self,
        persistence: PlatformPersistence,
        run_id: str,
    ) -> WorkflowController:
        if self._controller_factory is not None:
            return self._controller_factory(persistence)
        runtime = persistence.store.get(RUN_RUNTIME_NAMESPACE, run_id)
        if runtime is None:
            return self._controller(persistence)
        try:
            repository_root = Path(str(runtime["repository_root"])).resolve()
            expected_revision = str(runtime["repository_revision"])
            profiles_root = Path(str(runtime["profiles_root"])).resolve()
            expected_profile_fingerprints = runtime["profile_fingerprints"]
        except KeyError as exc:
            raise SpecialistRuntimeUnavailable(
                "persisted run runtime metadata is malformed"
            ) from exc
        if profiles_root != self._profiles_root:
            raise SpecialistRuntimeUnavailable(
                "configured profile catalog differs from the persisted run runtime"
            )
        if expected_profile_fingerprints != self._profile_fingerprints():
            raise SpecialistRuntimeUnavailable(
                "native profile bytes differ from the persisted run runtime"
            )
        context = inspect_worktree(
            repository_root,
            require_standalone=self._require_disposable_worktree,
            require_clean=False,
            required_branch_prefix=(
                self._required_branch_prefix if self._require_disposable_worktree else None
            ),
        )
        if context.commit != expected_revision:
            raise SpecialistRuntimeUnavailable(
                "persisted run revision no longer matches the clone HEAD"
            )
        return self._controller(persistence, repository_root=repository_root)

    @contextmanager
    def _lease_for_run(self, persistence: PlatformPersistence, run_id: str):
        if self._controller_factory is not None:
            yield
            return
        runtime = persistence.store.get(RUN_RUNTIME_NAMESPACE, run_id)
        if runtime is None:
            yield
            return
        try:
            repository_root = Path(str(runtime["repository_root"])).resolve()
        except KeyError as exc:
            raise SpecialistRuntimeUnavailable(
                "persisted run runtime metadata is malformed"
            ) from exc
        with _repository_lease(repository_root):
            yield

    def _validate_production_boundaries(
        self,
        repository_root: Path,
        workspace: Path,
    ) -> None:
        if workspace == repository_root:
            raise SpecialistRuntimeUnavailable(
                "specialist workspace must be a dedicated clone subdirectory"
            )
        approved_roots = tuple(
            (repository_root / relative).resolve()
            for relative in self._approved_workspace_relative_paths
        )
        if not approved_roots or not any(
            workspace == approved or workspace.is_relative_to(approved)
            for approved in approved_roots
        ):
            raise SpecialistRuntimeUnavailable(
                "specialist workspace is outside the M2 controller-approved documentation boundary"
            )
        if not self._profiles_root.is_relative_to(repository_root):
            raise SpecialistRuntimeUnavailable(
                "native profile catalog must be inside the approved clone"
            )

        if self._profiles_root.is_relative_to(workspace) or workspace.is_relative_to(
            self._profiles_root
        ):
            raise SpecialistRuntimeUnavailable("specialist workspace overlaps native profiles")
        state_roots = (self.paths.root.resolve(), self.paths.evidence_root.resolve())
        if any(
            state.is_relative_to(repository_root) or repository_root.is_relative_to(state)
            for state in state_roots
        ):
            raise SpecialistRuntimeUnavailable(
                "platform state and evidence must not overlap the approved repository"
            )

    def _profile_fingerprints(self) -> dict[str, list[str]]:
        return {
            profile.profile_id.value: [profile.profile_sha256, profile.soul_sha256]
            for profile in ProfileCatalog(self._profiles_root).load_all()
        }

    @staticmethod
    def _repository_root(workspace: Path) -> Path:
        if not workspace.is_dir():
            raise SpecialistRuntimeUnavailable("workspace does not exist")
        completed = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
        if completed.returncode != 0:
            raise SpecialistRuntimeUnavailable("workspace is not inside a Git clone")
        root = Path(completed.stdout.strip()).resolve()
        if not workspace.is_relative_to(root):
            raise SpecialistRuntimeUnavailable("workspace escaped its Git clone")
        return root

    def _decision(
        self,
        view: WorkflowView,
        *,
        checkpoint_id: str,
        operator_id: str,
        reason: str,
        decision: ApprovalDecision,
    ) -> HumanApprovalDecision:
        request = view.pending_approval
        if request is None:
            raise RuntimeError("run has no pending approval request")
        return HumanApprovalDecision(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            approval_id=self._id_factory(),
            request_id=request.request_id,
            checkpoint_id=checkpoint_id,
            operator_id=operator_id,
            decision=decision,
            reason=reason,
            decided_at=self._clock(),
        )

    @staticmethod
    def _view_payload(view: WorkflowView) -> dict[str, object]:
        return {
            "run_id": view.state.run_id,
            "task_id": view.state.task_id,
            "status": view.state.status.value,
            "checkpoint_id": view.checkpoint_id,
            "next_nodes": list(view.next_nodes),
            "correction_count": view.state.correction_count,
            "pending_approval": (
                None
                if view.pending_approval is None
                else view.pending_approval.model_dump(mode="json")
            ),
            "terminal_reason": view.state.terminal_reason,
        }
