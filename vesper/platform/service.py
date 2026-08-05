"""Local graph-backed service used by the Typer control surface."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from .composition import NativeSpecialistComposition
from .agent_profiles import AgentProfileCatalog, AUTONOMOUS_AGENT_ROLES
from .agent_queue import AgentWorkQueue, WorkQueueEmpty
from .agent_runner import AutonomousAgentRunner
from .agent_tools import AgentToolGateway
from .authority import ProposalRouter
from .contracts import (
    ApprovalDecision,
    AgentRole,
    JournalEventType,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RunStatus,
    SpecialistReceipt,
    SpecialistRole,
    TaskRequest,
)
from .control import RuntimeControl
from .journals import AgentJournal, JournalConflictError
from .ollama import OllamaClient, QWEN_MODEL, QwenSpecialistAdapter
from .persistence import PlatformPaths, PlatformPersistence, open_persistence
from .memory import DeterministicMemoryCandidateValidator, MemoryService
from .knowledge import ObsidianKnowledgeService
from .opencode import (
    OpenCodeGateway,
    _process_exists,
    _process_identity,
    _terminate_process_tree,
)
from .profiles import ProfileCatalog
from .qwen_runtime import QwenTurnRunner
from .review import DailyDigest, DailyReviewService, HybridReviewGate
from .research import LocalDataResearcher, LocalModelEvaluator
from .sandbox_runtime import DockerCodexRuntime
from .validation import LocalDeterministicValidator, validate_acceptance_checks
from .worktree import inspect_worktree
from .workflow import (
    APPROVAL_DECISION_NAMESPACE,
    APPROVAL_REQUEST_NAMESPACE,
    WorkflowController,
    WorkflowView,
    build_workflow,
)

_TUI_APPROVAL_BINDING_NAMESPACE = ("tui-command-approvals", "by-approval-id")

RUN_RUNTIME_NAMESPACE = ("system", "run-runtime")
M2_APPROVED_WORKSPACE = Path("docs/m2-controlled-exercise")
DOCKER_CODEX_RUNTIME = "docker-codex"
OPENCODE_RUNTIME = "opencode"
OLLAMA_QWEN_RUNTIME = "ollama-qwen"
_QWEN_INFERENCE_WAIT_SECONDS = 900
_AGENT_WORK_LEASE_SECONDS = 300
_AGENT_WORK_HEARTBEAT_SECONDS = 60
_AGENT_WORK_HEARTBEAT_JOIN_SECONDS = 35
ROOT_WORKSPACE_PROTECTED_PATHS = (
    Path(".git"),
    Path(".state"),
    Path(".env"),
    Path("AGENTS.md"),
    Path("SKILLS"),
    Path("profiles"),
    Path("vesper/platform"),
    Path("config/settings.yaml"),
    Path("models"),
    Path("knowledge"),
    Path("vesper/data/massive"),
    Path("vesper/data/model_research"),
)


class SpecialistRuntimeUnavailable(RuntimeError):
    """No real or deterministic specialist runtime was configured."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def _agent_work_lease_heartbeat(
    paths: PlatformPaths,
    work_id: str,
    worker_id: str,
    claim_attempt: int,
    clock: Callable[[], datetime],
):
    stop = threading.Event()
    failures: list[Exception] = []

    def maintain_lease() -> None:
        while not stop.wait(_AGENT_WORK_HEARTBEAT_SECONDS):
            try:
                with open_persistence(paths) as persistence:
                    AgentWorkQueue(persistence.store).renew(
                        work_id,
                        worker_id,
                        claim_attempt,
                        clock(),
                        lease_seconds=_AGENT_WORK_LEASE_SECONDS,
                    )
            except Exception as exc:
                failures.append(exc)
                return

    thread = threading.Thread(
        target=maintain_lease,
        name=f"v20-agent-work-lease:{work_id}",
        daemon=True,
    )
    thread.start()
    try:
        yield failures
    finally:
        stop.set()
        thread.join(timeout=_AGENT_WORK_HEARTBEAT_JOIN_SECONDS)
        if thread.is_alive():
            failures.append(RuntimeError("agent work lease heartbeat did not stop"))


@contextmanager
def _repository_lease(repository_root: Path, *, wait_seconds: float = 0):
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
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise SpecialistRuntimeUnavailable(
                        "another controller operation owns the repository lease"
                    ) from exc
                time.sleep(0.05)
                handle.seek(0)
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


class _UnavailableDataResearcher:
    def research(self, request):
        raise SpecialistRuntimeUnavailable("Data Research is not configured")


class _UnavailableModelEvaluator:
    def evaluate(self, request):
        raise SpecialistRuntimeUnavailable("Model Evaluation is not configured")


class LocalPlatformService:
    """Open local persistence per command and expose graph lifecycle operations."""

    def __init__(
        self,
        paths: PlatformPaths,
        *,
        controller_factory: Callable[[PlatformPersistence], WorkflowController] | None = None,
        profiles_root: Path | None = None,
        adapter_factory: Callable[[Path, tuple[str, ...]], object] | None = None,
        specialist_runtime: str = DOCKER_CODEX_RUNTIME,
        opencode_model: str | None = None,
        opencode_credential_environment_key: str | None = None,
        allow_repository_root_workspace: bool = False,
        knowledge_root: Path | None = None,
        research_data_root: Path | None = None,
        require_disposable_worktree: bool = True,
        require_clean_worktree: bool = True,
        required_branch_prefix: str = "m2/",
        approved_workspace_relative_paths: tuple[Path, ...] = (M2_APPROVED_WORKSPACE,),
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        cancellation_wait_seconds: float = 360,
    ) -> None:
        self.paths = paths
        self.control = RuntimeControl(paths.root / "control")
        self._controller_factory = controller_factory
        self._profiles_root = (
            Path("profiles/native").resolve() if profiles_root is None else profiles_root.resolve()
        )
        self._adapter_factory = adapter_factory
        self._validate_runtime_configuration(
            specialist_runtime,
            opencode_model,
            opencode_credential_environment_key,
        )
        self._specialist_runtime = specialist_runtime
        self._opencode_model = opencode_model
        self._opencode_credential_environment_key = opencode_credential_environment_key
        if allow_repository_root_workspace and specialist_runtime != OPENCODE_RUNTIME:
            raise SpecialistRuntimeUnavailable(
                "repository-root workspace requires the OpenCode runtime"
            )
        if allow_repository_root_workspace and not require_disposable_worktree:
            raise SpecialistRuntimeUnavailable(
                "repository-root workspace requires a standalone disposable clone"
            )
        self._allow_repository_root_workspace = allow_repository_root_workspace
        self._knowledge_root = None if knowledge_root is None else knowledge_root.resolve()
        self._research_data_root = (
            (Path(__file__).resolve().parents[2] / "vesper" / "data" / "massive")
            if research_data_root is None
            else research_data_root.resolve()
        )
        self._require_disposable_worktree = require_disposable_worktree
        self._require_clean_worktree = require_clean_worktree
        self._required_branch_prefix = required_branch_prefix
        self._approved_workspace_relative_paths = approved_workspace_relative_paths
        self._clock = clock
        self._id_factory = id_factory
        self._cancellation_wait_seconds = cancellation_wait_seconds

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
        self.control.register_run(
            {
                "run_id": task.run_id,
                "task_id": task.task_id,
                "repository_revision": repository_revision,
                "workspace": str(workspace_path),
                "repository_root": None if repository_root is None else str(repository_root),
                "created_at": task.created_at.isoformat(),
            }
        )
        try:
            with open_persistence(self.paths) as persistence:
                if repository_root is not None:
                    knowledge_root = self._knowledge_root_for_repository(repository_root)
                    knowledge = ObsidianKnowledgeService(
                        vault_root=knowledge_root,
                        store=persistence.store,
                        index=persistence.knowledge_index,
                    )
                    knowledge_sync = knowledge.sync()
                    knowledge.snapshot(task)
                    persistence.store.put(
                        RUN_RUNTIME_NAMESPACE,
                        task.run_id,
                        {
                            "repository_root": str(repository_root),
                            "workspace": str(workspace_path),
                            "repository_revision": repository_revision,
                            "profiles_root": str(self._profiles_root),
                            "profile_fingerprints": profile_fingerprints,
                            "specialist_runtime": self._specialist_runtime,
                            "specialist_model": self._opencode_model,
                            "credential_environment_key": (
                                self._opencode_credential_environment_key
                            ),
                            "allow_repository_root_workspace": (
                                self._allow_repository_root_workspace
                            ),
                            "research_data_root": str(self._research_data_root),
                            "knowledge_root": str(knowledge_root),
                            "knowledge_sync": knowledge_sync,
                        },
                    )
                view = self._controller(persistence, repository_root=repository_root).start(task)
        except Exception:
            self.control.set_run_status(task.run_id, "interrupted")
            raise
        self.control.set_run_status(task.run_id, view.state.status.value)
        return self._view_payload(view)

    def inspect_run(self, run_id: str) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            view = self._controller(persistence).inspect(run_id)
        return self._view_payload(view)

    def resume_run(self, run_id: str) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            with self._lease_for_run(persistence, run_id):
                view = self._controller_for_run(persistence, run_id).resume(run_id)
                self.control.set_run_status(run_id, view.state.status.value)
        return self._view_payload(view)

    def list_active_runs(self) -> dict[str, object]:
        active = []
        with open_persistence(self.paths) as persistence:
            for raw in self.control.list_active_runs():
                item = dict(raw)
                if item.get("active_execution") is None:
                    run_id = str(item["run_id"])
                    try:
                        view = self._controller(persistence).inspect(run_id)
                    except RuntimeError:
                        item["status"] = RunStatus.INTERRUPTED.value
                    else:
                        item["status"] = view.state.status.value
                if (
                    item.get("status")
                    in {
                        "running",
                        RunStatus.INTERRUPTED.value,
                        RunStatus.DATA_RESEARCH.value,
                        RunStatus.MODEL_EVALUATION.value,
                        RunStatus.PRODUCT.value,
                        RunStatus.DEVELOPMENT.value,
                        RunStatus.VALIDATION.value,
                        RunStatus.RISK_REVIEW.value,
                    }
                    or item.get("active_execution") is not None
                ):
                    active.append(item)
        return {"active": active}

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
        if view.state.data_research is not None:
            artifacts.extend(view.state.data_research.evidence)
        if view.state.model_evaluation is not None:
            artifacts.extend(view.state.model_evaluation.evidence)
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
                self._journal_operator_decision(persistence, decision)
                payload = self._view_payload(controller.inspect(run_id))
                self.control.set_run_status(run_id, str(payload["status"]))
        payload["resume_required"] = True
        return payload

    def record_tui_approval_decision(
        self,
        *,
        command_id: str,
        approval_id: str,
        run_id: str,
        checkpoint_id: str,
        operator_id: str,
        decision: ApprovalDecision,
        reason: str,
        decided_at: datetime,
    ) -> dict[str, object]:
        """Persist one exact TUI decision without resuming or reconciling execution."""
        with open_persistence(self.paths) as persistence:
            with self._tui_decision_lease(persistence, run_id):
                if self.control.active_execution(run_id) is not None:
                    raise SpecialistRuntimeUnavailable(
                        "TUI approval is blocked while the run has an active execution"
                    )
                controller = self._controller_for_run(persistence, run_id)
                view = controller.inspect(run_id)
                request = view.pending_approval
                if (
                    request is None
                    or view.state.status is not RunStatus.AWAITING_APPROVAL
                    or request.run_id != run_id
                    or request.checkpoint_id != checkpoint_id
                    or view.checkpoint_id != checkpoint_id
                ):
                    raise SpecialistRuntimeUnavailable(
                        "TUI approval does not match the exact pending checkpoint"
                    )
                raw = persistence.store.get(APPROVAL_DECISION_NAMESPACE, run_id)
                existing = (
                    None
                    if raw is None
                    else HumanApprovalDecision.model_validate_json(json.dumps(raw))
                )
                stable_decided_at = (
                    existing.decided_at
                    if existing is not None and existing.approval_id == approval_id
                    else decided_at
                )
                candidate = HumanApprovalDecision(
                    run_id=request.run_id,
                    task_id=request.task_id,
                    repository_revision=request.repository_revision,
                    created_at=request.created_at,
                    approval_id=approval_id,
                    request_id=request.request_id,
                    checkpoint_id=checkpoint_id,
                    operator_id=operator_id,
                    decision=decision,
                    reason=reason,
                    decided_at=stable_decided_at,
                )
                binding = {
                    "approval_id": approval_id,
                    "run_id": run_id,
                }
                existing_binding = persistence.store.get(
                    _TUI_APPROVAL_BINDING_NAMESPACE,
                    approval_id,
                )
                if existing_binding is not None and dict(existing_binding) != binding:
                    raise SpecialistRuntimeUnavailable(
                        f"conflicting TUI approval binding for command {command_id}"
                    )
                if existing is not None:
                    if existing != candidate:
                        raise SpecialistRuntimeUnavailable(
                            f"conflicting TUI approval decision for command {command_id}"
                        )
                    recorded = existing
                else:
                    recorded = controller.record_decision(run_id, candidate)
                if existing_binding is None:
                    persistence.store.put(
                        _TUI_APPROVAL_BINDING_NAMESPACE,
                        approval_id,
                        binding,
                    )
                self._journal_operator_decision(persistence, recorded)
        return {
            "command_id": command_id,
            "approval_id": recorded.approval_id,
            "run_id": recorded.run_id,
            "checkpoint_id": recorded.checkpoint_id,
            "decision": recorded.decision.value,
            "reason": recorded.reason,
            "decided_at": recorded.decided_at.isoformat(),
            "resume_required": recorded.decision is ApprovalDecision.APPROVE,
        }

    def recover_tui_approval(
        self,
        *,
        approval_id: str,
        run_id: str,
        checkpoint_id: str,
        operator_id: str,
        decision: ApprovalDecision,
        reason: str,
    ) -> str:
        """Validate deterministic approval evidence and repair its exact journal event."""
        with open_persistence(self.paths) as persistence:
            with self._tui_decision_lease(persistence, run_id):
                binding = persistence.store.get(
                    _TUI_APPROVAL_BINDING_NAMESPACE,
                    approval_id,
                )
                expected_binding = {
                    "approval_id": approval_id,
                    "run_id": run_id,
                }
                raw = persistence.store.get(APPROVAL_DECISION_NAMESPACE, run_id)
                if raw is None:
                    return "not-started" if binding is None else "unknown"
                try:
                    persisted = HumanApprovalDecision.model_validate_json(
                        json.dumps(raw)
                    )
                except (TypeError, ValueError):
                    return "failed"
                if (
                    persisted.approval_id != approval_id
                    or persisted.run_id != run_id
                    or persisted.checkpoint_id != checkpoint_id
                    or persisted.operator_id != operator_id
                    or persisted.decision is not decision
                    or persisted.reason != reason
                ):
                    return "unknown"
                if binding is not None and dict(binding) != expected_binding:
                    return "unknown"
                try:
                    if binding is None:
                        persistence.store.put(
                            _TUI_APPROVAL_BINDING_NAMESPACE,
                            approval_id,
                            expected_binding,
                        )
                    self._journal_operator_decision(persistence, persisted)
                    journal = AgentJournal(persistence.store)
                    if not journal.verify(AgentRole.RISK_REVIEW, persisted.run_id):
                        return "failed"
                except (JournalConflictError, TypeError, ValueError):
                    return "failed"
                return "completed"

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
                self._journal_operator_decision(persistence, decision)
                rejected = controller.resume(run_id)
                self.control.set_run_status(run_id, rejected.state.status.value)
        return self._view_payload(rejected)

    def cancel_run(self, run_id: str, reason: str) -> dict[str, object]:
        self.control.request_cancel(run_id, reason)
        with open_persistence(self.paths) as persistence:
            with self._lease_for_run(
                persistence,
                run_id,
                wait_seconds=self._cancellation_wait_seconds,
            ):
                view = self._controller_for_run(persistence, run_id).cancel(run_id, reason)
                self.control.set_run_status(run_id, view.state.status.value)
        return self._view_payload(view)

    def sync_knowledge(self) -> dict[str, int]:
        with open_persistence(self.paths) as persistence:
            return ObsidianKnowledgeService(
                vault_root=self._operator_knowledge_root(),
                store=persistence.store,
                index=persistence.knowledge_index,
            ).sync()

    def search_knowledge(self, query: str, role: str) -> dict[str, object]:
        try:
            specialist_role = SpecialistRole(role)
        except ValueError as exc:
            choices = ", ".join(item.value for item in SpecialistRole)
            raise SpecialistRuntimeUnavailable(
                f"unknown specialist role {role!r}; expected one of: {choices}"
            ) from exc
        with open_persistence(self.paths) as persistence:
            documents = ObsidianKnowledgeService(
                vault_root=self._operator_knowledge_root(),
                store=persistence.store,
                index=persistence.knowledge_index,
            ).search(specialist_role, query)
        return {
            "query": query,
            "role": specialist_role.value,
            "results": [item.model_dump(mode="json") for item in documents],
        }

    def knowledge_status(self) -> dict[str, int]:
        with open_persistence(self.paths) as persistence:
            return ObsidianKnowledgeService(
                vault_root=self._operator_knowledge_root(),
                store=persistence.store,
                index=persistence.knowledge_index,
            ).status()

    def agent_roster(self) -> dict[str, object]:
        autonomous = AgentProfileCatalog(self._profiles_root).load_all()
        rows = [
            {
                "role": role.value,
                "status": "existing-workflow",
                "runtime": "operator-selected",
                "route": "seven-node governed workflow",
            }
            for role in (AgentRole.PRODUCT, AgentRole.DEVELOPMENT, AgentRole.RISK_REVIEW)
        ]
        rows.extend(
            {
                "role": profile.profile_id.value,
                "status": "bounded-action-only",
                "runtime": profile.model,
                "route": "proposal router -> journal -> operator review",
            }
            for profile in autonomous
        )
        return {"count": len(rows), "agents": rows, "scheduler_active": False}

    def run_agent(
        self,
        role: str,
        session_id: str,
        objective: str,
        repository_revision: str,
        evidence: dict[str, object],
        prior_session_date: str,
    ) -> dict[str, object]:
        try:
            agent_role = AgentRole(role)
            prior_date = date.fromisoformat(prior_session_date)
        except ValueError as exc:
            raise SpecialistRuntimeUnavailable("invalid agent role or prior session date") from exc
        if agent_role not in AUTONOMOUS_AGENT_ROLES:
            raise SpecialistRuntimeUnavailable(
                "agent run supports the five bounded quant roles only"
            )
        repository_root = Path.cwd().resolve()
        created_at = self._clock()
        run_id = self._id_factory()
        task_id = self._id_factory()
        rendered_digest = self.render_agent_digest(prior_session_date)
        with open_persistence(self.paths) as persistence:
            gate = HybridReviewGate(persistence.store)
            if not gate.can_admit(prior_date, digest_sha256=str(rendered_digest["sha256"])):
                raise SpecialistRuntimeUnavailable(
                    f"daily review for {prior_date.isoformat()} is not acknowledged"
                )
            journal = AgentJournal(persistence.store)
            result = AutonomousAgentRunner(
                repository_root=repository_root,
                profiles=AgentProfileCatalog(self._profiles_root),
                qwen=QwenTurnRunner(
                    OllamaClient(),
                    AgentToolGateway(repository_root),
                    self.paths.root,
                    wait_seconds=_QWEN_INFERENCE_WAIT_SECONDS,
                ),
                journal=journal,
                router=ProposalRouter(),
            ).run(
                role=agent_role,
                session_id=session_id,
                run_id=run_id,
                task_id=task_id,
                repository_revision=repository_revision,
                created_at=created_at,
                objective=objective,
                evidence=evidence,
            )
        return {
            "run_id": run_id,
            "task_id": task_id,
            "role": agent_role.value,
            "output": result.output.model_dump(mode="json"),
            "decisions": [decision.model_dump(mode="json") for decision in result.decisions],
            "runtime": "qwen:64k",
        }

    def enqueue_agent_work(
        self, role: str, session_id: str, objective: str, priority: int
    ) -> dict[str, object]:
        try:
            agent_role = AgentRole(role)
        except ValueError as exc:
            raise SpecialistRuntimeUnavailable(f"unknown agent role: {role}") from exc
        if agent_role not in AUTONOMOUS_AGENT_ROLES:
            raise SpecialistRuntimeUnavailable("only bounded quant roles enter the Qwen queue")
        work_id = self._id_factory()
        with open_persistence(self.paths) as persistence:
            item = AgentWorkQueue(persistence.store).enqueue(
                work_id,
                agent_role,
                session_id,
                objective,
                objective,
                priority,
                self._clock(),
            )
        return item.model_dump(mode="json")

    def enqueue_tui_agent_work(
        self,
        *,
        work_id: str,
        role: AgentRole,
        session_id: str,
        title: str,
        objective: str,
        priority: int,
        created_at: datetime,
    ) -> dict[str, object]:
        if role not in AUTONOMOUS_AGENT_ROLES:
            raise SpecialistRuntimeUnavailable(
                "TUI queue requires an approved autonomous quant role"
            )
        with open_persistence(self.paths) as persistence:
            item = AgentWorkQueue(persistence.store).enqueue(
                work_id,
                role,
                session_id,
                title,
                objective,
                priority,
                created_at,
            )
        return item.model_dump(mode="json")

    def get_tui_agent_work(self, work_id: str) -> dict[str, object] | None:
        with open_persistence(self.paths) as persistence:
            item = AgentWorkQueue(persistence.store).get(work_id)
        return None if item is None else item.model_dump(mode="json")

    def list_agent_work(self) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            items = AgentWorkQueue(persistence.store).list()
        ordered = sorted(items, key=lambda item: (-item.priority, item.created_at, item.work_id))
        return {"work": [item.model_dump(mode="json") for item in ordered]}

    def run_next_agent_work(
        self,
        worker_id: str,
        repository_revision: str,
        evidence: dict[str, object],
        prior_session_date: str,
    ) -> dict[str, object]:
        with open_persistence(self.paths) as persistence:
            claimed = AgentWorkQueue(persistence.store).claim(
                worker_id, self._clock(), lease_seconds=_AGENT_WORK_LEASE_SECONDS
            )
        try:
            with _agent_work_lease_heartbeat(
                self.paths, claimed.work_id, worker_id, claimed.attempt, self._clock
            ) as renewal_failures:
                result = self.run_agent(
                    claimed.role.value,
                    claimed.session_id,
                    claimed.objective,
                    repository_revision,
                    evidence,
                    prior_session_date,
                )
        except Exception as agent_error:
            try:
                with open_persistence(self.paths) as persistence:
                    AgentWorkQueue(persistence.store).fail(
                        claimed.work_id, worker_id, claimed.attempt
                    )
            except Exception as cleanup_error:
                agent_error.add_note(f"queue fail cleanup failed: {type(cleanup_error).__name__}")
            raise
        if renewal_failures:
            with open_persistence(self.paths) as persistence:
                try:
                    AgentWorkQueue(persistence.store).fail(
                        claimed.work_id, worker_id, claimed.attempt
                    )
                except WorkQueueEmpty:
                    pass
            raise RuntimeError("agent work lease renewal failed") from renewal_failures[0]
        with open_persistence(self.paths) as persistence:
            completed = AgentWorkQueue(persistence.store).complete(
                claimed.work_id, worker_id, claimed.attempt
            )
        return {**result, "work": completed.model_dump(mode="json")}

    def render_agent_digest(self, session_date: str) -> dict[str, object]:
        target = self._session_date(session_date)
        with open_persistence(self.paths) as persistence:
            journal = AgentJournal(persistence.store)
            grouped: dict[AgentRole, list] = {}
            try:
                sessions = journal.sessions()
            except JournalConflictError as exc:
                raise SpecialistRuntimeUnavailable(
                    "agent journal session discovery failed"
                ) from exc
            for role, session_id in sessions:
                if not journal.verify(role, session_id):
                    raise SpecialistRuntimeUnavailable(
                        f"agent journal integrity failed: {role.value}/{session_id}"
                    )
                events = [
                    event
                    for event in journal.list(role, session_id)
                    if event.created_at.date() == target
                ]
                grouped.setdefault(role, []).extend(events)
            ordered = {
                role: tuple(sorted(events, key=lambda event: (event.session_id, event.sequence)))
                for role, events in grouped.items()
            }
            digest = DailyReviewService(persistence.store, self.paths.root / "daily-review").render(
                target, ordered
            )
        return {
            "session_date": target.isoformat(),
            "sha256": digest.sha256,
            "json_path": str(digest.json_path),
            "markdown_path": str(digest.markdown_path),
            "sections": [
                {"role": section.role.value, "event_count": section.event_count}
                for section in digest.sections
            ],
        }

    def acknowledge_agent_digest(self, session_date: str, operator_id: str) -> dict[str, object]:
        target = self._session_date(session_date)
        rendered = self.render_agent_digest(session_date)
        with open_persistence(self.paths) as persistence:
            review = DailyReviewService(persistence.store, self.paths.root / "daily-review")
            digest = DailyDigest(
                target,
                (),
                str(rendered["sha256"]),
                Path(str(rendered["json_path"])),
                Path(str(rendered["markdown_path"])),
            )
            review.acknowledge(digest, operator_id, self._clock())
        return {"session_date": session_date, "acknowledged": True, "operator_id": operator_id}

    def agent_gate_status(self, prior_session_date: str) -> dict[str, object]:
        target = self._session_date(prior_session_date)
        with open_persistence(self.paths) as persistence:
            admitted = HybridReviewGate(persistence.store).can_admit(target)
        return {"prior_session_date": prior_session_date, "new_proposals_admitted": admitted}

    @staticmethod
    def _session_date(value: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise SpecialistRuntimeUnavailable("session date must use YYYY-MM-DD") from exc

    @staticmethod
    def _journal_operator_decision(
        persistence: PlatformPersistence, decision: HumanApprovalDecision
    ) -> None:
        AgentJournal(persistence.store).append(
            event_id=f"{decision.run_id}:operator:{decision.approval_id}",
            role=AgentRole.RISK_REVIEW,
            session_id=decision.run_id,
            run_id=decision.run_id,
            task_id=decision.task_id,
            repository_revision=decision.repository_revision,
            created_at=decision.decided_at,
            event_type=JournalEventType.OPERATOR_DECISION,
            payload={
                "decision": decision.decision.value,
                "operator_id": decision.operator_id,
                "reason": decision.reason,
            },
        )

    def _controller(
        self,
        persistence: PlatformPersistence,
        *,
        repository_root: Path | None = None,
        specialist_runtime: str | None = None,
        opencode_model: str | None = None,
        opencode_credential_environment_key: str | None = None,
        allow_repository_root_workspace: bool | None = None,
    ) -> WorkflowController:
        if self._controller_factory is not None:
            return self._controller_factory(persistence)
        if repository_root is not None:
            runtime_name = specialist_runtime or self._specialist_runtime
            if specialist_runtime is None:
                opencode_model = self._opencode_model
                opencode_credential_environment_key = self._opencode_credential_environment_key
                allow_repository_root_workspace = self._allow_repository_root_workspace
            if allow_repository_root_workspace is None:
                allow_repository_root_workspace = False
            self._validate_runtime_configuration(
                runtime_name,
                opencode_model,
                opencode_credential_environment_key,
            )
            if not self._profiles_root.is_relative_to(repository_root):
                raise SpecialistRuntimeUnavailable(
                    "native profile catalog must be inside the approved clone"
                )
            profiles = ProfileCatalog(self._profiles_root)
            loaded = profiles.load_all()
            profile_models = tuple(sorted({profile.model.name for profile in loaded}))
            approved_models = (
                (opencode_model,)
                if runtime_name == OPENCODE_RUNTIME
                else ((QWEN_MODEL,) if runtime_name == OLLAMA_QWEN_RUNTIME else profile_models)
            )
            protected_paths = (
                *(repository_root / relative for relative in ROOT_WORKSPACE_PROTECTED_PATHS),
                self._knowledge_root_for_repository(repository_root),
                *(
                    repository_root / relative / "README.md"
                    for relative in self._approved_workspace_relative_paths
                ),
            )
            if self._adapter_factory is not None:
                adapter = self._adapter_factory(repository_root, approved_models)
            elif runtime_name == OPENCODE_RUNTIME:
                provider = opencode_model.split("/", maxsplit=1)[0]
                credential_keys = (
                    {}
                    if opencode_credential_environment_key is None
                    else {provider: opencode_credential_environment_key}
                )
                adapter = OpenCodeGateway(
                    repository_root=repository_root,
                    approved_models=approved_models,
                    credential_environment_keys=credential_keys,
                    protected_paths=protected_paths,
                    control=self.control,
                    clock=self._clock,
                )
            elif runtime_name == OLLAMA_QWEN_RUNTIME:
                adapter = QwenSpecialistAdapter(
                    repository_root,
                    self.paths.root,
                    clock=self._clock,
                    journal=AgentJournal(persistence.store),
                )
            else:
                adapter = DockerCodexRuntime(
                    repository_root=repository_root,
                    approved_models=approved_models,
                    control=self.control,
                    clock=self._clock,
                )
            composition = NativeSpecialistComposition(
                repository_root=repository_root,
                profiles=profiles,
                adapter=adapter,
                evidence=persistence.evidence,
                turn_store=persistence.store,
                agent_journal=AgentJournal(persistence.store),
                protected_paths=protected_paths,
                model_override=(
                    opencode_model
                    if runtime_name == OPENCODE_RUNTIME
                    else (QWEN_MODEL if runtime_name == OLLAMA_QWEN_RUNTIME else None)
                ),
                execution_runtime=(
                    "opencode"
                    if runtime_name == OPENCODE_RUNTIME
                    else ("ollama-qwen" if runtime_name == OLLAMA_QWEN_RUNTIME else "codex")
                ),
                authentication_type=(
                    "opencode-local"
                    if runtime_name == OPENCODE_RUNTIME
                    else ("local-ollama" if runtime_name == OLLAMA_QWEN_RUNTIME else "chatgpt")
                ),
                permission_profile=(
                    "opencode-host"
                    if runtime_name == OPENCODE_RUNTIME
                    else (
                        "controller-tools"
                        if runtime_name == OLLAMA_QWEN_RUNTIME
                        else "docker-one-shot"
                    )
                ),
                allow_repository_root_workspace=allow_repository_root_workspace,
                knowledge_context_reader=ObsidianKnowledgeService(
                    vault_root=self._knowledge_root_for_repository(repository_root),
                    store=persistence.store,
                    index=persistence.knowledge_index,
                ).context,
                clock=self._clock,
                id_factory=self._id_factory,
            )
            graph = build_workflow(
                checkpointer=persistence.checkpointer,
                store=persistence.langgraph_store,
                specialists=composition,
                data_researcher=LocalDataResearcher(
                    repository_root,
                    persistence.evidence,
                    clock=self._clock,
                    massive_data_root=self._research_data_root,
                ),
                model_evaluator=LocalModelEvaluator(
                    repository_root,
                    persistence.evidence,
                    clock=self._clock,
                ),
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
            data_researcher=_UnavailableDataResearcher(),
            model_evaluator=_UnavailableModelEvaluator(),
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
            workspace = Path(str(runtime["workspace"])).resolve()
            expected_revision = str(runtime["repository_revision"])
            profiles_root = Path(str(runtime["profiles_root"])).resolve()
            expected_profile_fingerprints = runtime["profile_fingerprints"]
            persisted_research_data_root = Path(str(runtime["research_data_root"])).resolve()
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
        if persisted_research_data_root != self._research_data_root:
            raise SpecialistRuntimeUnavailable(
                "configured research data root differs from the persisted run runtime"
            )
        persisted_knowledge_root = runtime.get("knowledge_root")
        if persisted_knowledge_root is not None and Path(
            str(persisted_knowledge_root)
        ).resolve() != (self._knowledge_root_for_repository(repository_root)):
            raise SpecialistRuntimeUnavailable(
                "configured knowledge root differs from the persisted run runtime"
            )
        allow_repository_root_workspace = bool(
            runtime.get("allow_repository_root_workspace", False)
        )
        self._validate_production_boundaries(
            repository_root,
            workspace,
            allow_repository_root_workspace=allow_repository_root_workspace,
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
        runtime_name = str(runtime.get("specialist_runtime", DOCKER_CODEX_RUNTIME))
        raw_model = runtime.get("specialist_model")
        raw_credential_key = runtime.get("credential_environment_key")
        model = None if raw_model is None else str(raw_model)
        credential_key = None if raw_credential_key is None else str(raw_credential_key)
        return self._controller(
            persistence,
            repository_root=repository_root,
            specialist_runtime=runtime_name,
            opencode_model=model,
            opencode_credential_environment_key=credential_key,
            allow_repository_root_workspace=allow_repository_root_workspace,
        )

    @contextmanager
    def _lease_for_run(
        self,
        persistence: PlatformPersistence,
        run_id: str,
        *,
        wait_seconds: float = 0,
    ):
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
        with _repository_lease(repository_root, wait_seconds=wait_seconds):
            active = self.control.active_execution(run_id)
            if active is not None:
                runtime_name = str(runtime.get("specialist_runtime", DOCKER_CODEX_RUNTIME))
                if runtime_name == OPENCODE_RUNTIME:
                    execution_id = str(active.get("execution_id", ""))
                    role = str(active.get("role", ""))
                    process_identity = str(active.get("process_identity", ""))
                    try:
                        process_id = int(active.get("process_id", 0))
                    except (TypeError, ValueError):
                        process_id = 0
                    if (
                        active.get("run_id") != run_id
                        or active.get("runtime") != OPENCODE_RUNTIME
                        or not execution_id
                        or role not in {item.value for item in SpecialistRole}
                        or process_id <= 0
                        or not process_identity
                    ):
                        raise SpecialistRuntimeUnavailable(
                            "persisted active OpenCode process identity is invalid"
                        )
                    current_identity = _process_identity(process_id)
                    if current_identity is None:
                        if _process_exists(process_id) is not False:
                            raise SpecialistRuntimeUnavailable(
                                "persisted active OpenCode process cannot be identified"
                            )
                    elif current_identity != process_identity:
                        raise SpecialistRuntimeUnavailable(
                            "persisted active OpenCode PID has been reused"
                        )
                    _terminate_process_tree(process_id)
                    self.control.clear_active(run_id, execution_id)
                elif runtime_name != DOCKER_CODEX_RUNTIME:
                    raise SpecialistRuntimeUnavailable(
                        "host runtime active execution cannot be reconciled automatically"
                    )
                else:
                    execution_id = str(active.get("execution_id", ""))
                    sandbox_name = str(active.get("sandbox_name", ""))
                    if not execution_id or not sandbox_name:
                        raise SpecialistRuntimeUnavailable(
                            "persisted active execution metadata is malformed"
                        )
                    role = str(active.get("role", ""))
                    if (
                        active.get("run_id") != run_id
                        or role not in {item.value for item in SpecialistRole}
                        or sandbox_name
                        != DockerCodexRuntime.expected_sandbox_name(role, execution_id)
                    ):
                        raise SpecialistRuntimeUnavailable(
                            "persisted active execution sandbox identity is invalid"
                        )
                    if self._adapter_factory is not None:
                        raise SpecialistRuntimeUnavailable(
                            "custom runtime must reconcile its active sandbox before resume"
                        )
                    DockerCodexRuntime(
                        repository_root=repository_root,
                        control=self.control,
                    ).reconcile_sandbox(sandbox_name)
                    self.control.clear_active(run_id, execution_id)
            yield

    @contextmanager
    def _tui_decision_lease(
        self,
        persistence: PlatformPersistence,
        run_id: str,
    ):
        """Serialize a decision without invoking active-runtime reconciliation."""
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

    @staticmethod
    def _validate_runtime_configuration(
        specialist_runtime: str,
        opencode_model: str | None,
        credential_environment_key: str | None,
    ) -> None:
        if specialist_runtime not in {
            DOCKER_CODEX_RUNTIME,
            OPENCODE_RUNTIME,
            OLLAMA_QWEN_RUNTIME,
        }:
            raise SpecialistRuntimeUnavailable(
                f"unsupported specialist runtime: {specialist_runtime}"
            )
        if specialist_runtime == OPENCODE_RUNTIME:
            if not opencode_model or "/" not in opencode_model:
                raise SpecialistRuntimeUnavailable(
                    "OpenCode runtime requires an exact provider/model"
                )
            if credential_environment_key == "":
                raise SpecialistRuntimeUnavailable(
                    "OpenCode credential environment key cannot be empty"
                )
            return
        if opencode_model is not None or credential_environment_key is not None:
            raise SpecialistRuntimeUnavailable(
                "OpenCode model and credential binding require the OpenCode runtime"
            )

    def _validate_production_boundaries(
        self,
        repository_root: Path,
        workspace: Path,
        *,
        allow_repository_root_workspace: bool | None = None,
    ) -> None:
        allow_root = (
            self._allow_repository_root_workspace
            if allow_repository_root_workspace is None
            else allow_repository_root_workspace
        )
        if workspace == repository_root and not allow_root:
            raise SpecialistRuntimeUnavailable(
                "specialist workspace must be a dedicated clone subdirectory"
            )
        approved_roots = tuple(
            (repository_root / relative).resolve()
            for relative in self._approved_workspace_relative_paths
        )
        if workspace != repository_root and (
            not approved_roots
            or not any(
                workspace == approved or workspace.is_relative_to(approved)
                for approved in approved_roots
            )
        ):
            raise SpecialistRuntimeUnavailable(
                "specialist workspace is outside the M2 controller-approved documentation boundary"
            )
        if not self._profiles_root.is_relative_to(repository_root):
            raise SpecialistRuntimeUnavailable(
                "native profile catalog must be inside the approved clone"
            )
        knowledge_root = self._knowledge_root_for_repository(repository_root)
        if not knowledge_root.is_relative_to(repository_root):
            raise SpecialistRuntimeUnavailable("knowledge root must be inside the approved clone")
        if workspace != repository_root and (
            knowledge_root.is_relative_to(workspace) or workspace.is_relative_to(knowledge_root)
        ):
            raise SpecialistRuntimeUnavailable("specialist workspace overlaps knowledge root")

        if workspace != repository_root and (
            self._profiles_root.is_relative_to(workspace)
            or workspace.is_relative_to(self._profiles_root)
        ):
            raise SpecialistRuntimeUnavailable("specialist workspace overlaps native profiles")
        if self._research_data_root.is_relative_to(
            repository_root
        ) or repository_root.is_relative_to(self._research_data_root):
            raise SpecialistRuntimeUnavailable(
                "research data root must not overlap the approved repository"
            )
        state_roots = (self.paths.root.resolve(), self.paths.evidence_root.resolve())
        if any(
            state.is_relative_to(self._research_data_root)
            or self._research_data_root.is_relative_to(state)
            for state in state_roots
        ):
            raise SpecialistRuntimeUnavailable(
                "platform state and evidence must not overlap the research data root"
            )
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

    def _knowledge_root_for_repository(self, repository_root: Path) -> Path:
        if self._knowledge_root is None:
            return (repository_root / "knowledge").resolve()
        return self._knowledge_root

    def _operator_knowledge_root(self) -> Path:
        knowledge_root = (
            Path("knowledge").resolve() if self._knowledge_root is None else self._knowledge_root
        )
        repository_root = self._repository_root(Path.cwd().resolve())
        if not knowledge_root.is_relative_to(repository_root):
            raise SpecialistRuntimeUnavailable(
                "knowledge root must be inside the current repository"
            )
        return knowledge_root

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
            "data_research": (
                None
                if view.state.data_research is None
                else view.state.data_research.model_dump(mode="json")
            ),
            "model_evaluation": (
                None
                if view.state.model_evaluation is None
                else view.state.model_evaluation.model_dump(mode="json")
            ),
            "pending_approval": (
                None
                if view.pending_approval is None
                else view.pending_approval.model_dump(mode="json")
            ),
            "terminal_reason": view.state.terminal_reason,
        }
