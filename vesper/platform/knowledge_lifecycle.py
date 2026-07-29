"""Safe consolidation of agent observations into reviewable knowledge candidates."""

from __future__ import annotations

import os
import re
import stat
import tempfile
from collections.abc import Callable, Mapping
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import yaml

from .contracts import (
    KnowledgeContext,
    KnowledgeDocument,
    KnowledgeObservation,
    KnowledgeRetention,
    KnowledgeTier,
    SpecialistReceipt,
    TaskRequest,
)
from .knowledge import (
    KnowledgeCorpus,
    KnowledgeStorePort,
    KnowledgeSyncError,
    load_knowledge_corpus,
)


OBSERVATION_NAMESPACE = ("knowledge", "adaptive", "observations")
USAGE_NAMESPACE = ("knowledge", "adaptive", "usage")
ACCEPTED_RUN_NAMESPACE = ("knowledge", "adaptive", "accepted-runs")
_CANDIDATE_THRESHOLD = 3
_MAX_ACTIVE_LINES = 3_000
_CONCEPT_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:api[_-]?key|password|secret|token|credential)\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


class KnowledgeLifecycleError(RuntimeError):
    """An observation cannot safely be materialized as a knowledge candidate."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeLifecycleService:
    def __init__(
        self,
        *,
        vault_root: Path,
        store: KnowledgeStorePort,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._vault_root = vault_root if vault_root.is_absolute() else Path.cwd() / vault_root
        self._store = store
        self._clock = clock

    def observe(self, observation: KnowledgeObservation) -> dict[str, object]:
        self._validate_observation(observation)
        self._validated_inbox()
        state, changed = self._merge_observation(observation)
        if changed:
            self._store.put(OBSERVATION_NAMESPACE, observation.concept_key, state)
        return self._materialize_candidate(observation, state, changed=changed)

    def record_selections(self, contexts: tuple[KnowledgeContext, ...]) -> None:
        """Persist selected knowledge references without treating selection as success."""
        for context in contexts:
            selection_ref = f"{context.run_id}:{context.role.value}"
            for document in context.documents:
                state = self._usage_state(document.knowledge_id)
                selection_refs = set(state["selection_refs"])
                if selection_ref in selection_refs:
                    continue
                selection_refs.add(selection_ref)
                state["selection_refs"] = sorted(selection_refs)
                self._store.put(USAGE_NAMESPACE, document.knowledge_id, state)

    def usage(self, knowledge_id: str) -> dict[str, object]:
        """Return persisted selection and accepted-run usage for one document."""
        state = self._usage_state(knowledge_id)
        return {
            "knowledge_id": knowledge_id,
            "selection_count": len(state["selection_refs"]),
            "successful_run_count": len(state["successful_refs"]),
            "last_successful_use": state["last_successful_use"],
        }

    def accept_run(
        self,
        task: TaskRequest,
        receipts: tuple[SpecialistReceipt, ...],
    ) -> dict[str, object]:
        """Credit selected knowledge and materialize accepted-run observations once."""
        accepted = self._store.get(ACCEPTED_RUN_NAMESPACE, task.run_id)
        if accepted is not None:
            return dict(accepted)

        observed_at = self._clock()
        observation_results = []
        for receipt in sorted(receipts, key=lambda item: (item.role.value, item.attempt)):
            if receipt.output is None:
                continue
            for proposal in receipt.output.knowledge_observations:
                observation_results.append(
                    self.observe(
                        KnowledgeObservation(
                            concept_key=proposal.concept_key,
                            title=proposal.title,
                            kind=proposal.kind,
                            scope=proposal.scope,
                            summary=proposal.summary,
                            explicit=proposal.explicit,
                            source_ref=f"{task.run_id}:{receipt.role.value}:{receipt.attempt}",
                            observed_at=observed_at,
                        )
                    )
                )

        selected_ref_prefix = f"{task.run_id}:"
        knowledge_ids = []
        for stored in self._store.search(USAGE_NAMESPACE, limit=10_000):
            knowledge_id, state = _stored_usage(stored)
            selected_refs = {
                reference
                for reference in state["selection_refs"]
                if reference.startswith(selected_ref_prefix)
            }
            if not selected_refs:
                continue
            successful_refs = set(state["successful_refs"])
            if not selected_refs.issubset(successful_refs):
                successful_refs.update(selected_refs)
                state["successful_refs"] = sorted(successful_refs)
                state["last_successful_use"] = _format_timestamp(observed_at)
                self._store.put(USAGE_NAMESPACE, knowledge_id, state)
            knowledge_ids.append(knowledge_id)

        result = {
            "accepted_at": _format_timestamp(observed_at),
            "knowledge_ids": sorted(knowledge_ids),
            "observations": observation_results,
        }
        self._store.put(ACCEPTED_RUN_NAMESPACE, task.run_id, result)
        return result

    def compaction_plan(self, target_lines: int = _MAX_ACTIVE_LINES) -> dict[str, object]:
        """Produce a deterministic review proposal without moving any knowledge files."""
        if isinstance(target_lines, bool) or not 0 <= target_lines <= _MAX_ACTIVE_LINES:
            raise KnowledgeLifecycleError("target lines must be between 0 and 3000")
        corpus = self._load_corpus()
        active = () if corpus is None else corpus.active
        active_lines = 0 if corpus is None else corpus.active_lines
        candidates = [
            document for document in active if document.retention is KnowledgeRetention.ADAPTIVE
        ]
        candidates.sort(key=self._compaction_rank)

        projected_active_lines = active_lines
        entries = []
        for document in candidates:
            if projected_active_lines <= target_lines:
                break
            usage = self.usage(document.knowledge_id)
            entries.append(self._proposal_entry(document, usage))
            projected_active_lines -= document.source_line_count

        proposal = {
            "target_lines": target_lines,
            "active_lines": active_lines,
            "projected_active_lines": projected_active_lines,
            "entries": entries,
        }
        return {"proposal_id": _proposal_hash(proposal), **proposal}

    def reactivation_plan(self) -> dict[str, object]:
        """Produce a deterministic review proposal for frequently used archived notes."""
        corpus = self._load_corpus()
        active_lines = 0 if corpus is None else corpus.active_lines
        archived = () if corpus is None else corpus.archived
        eligible = []
        for document in archived:
            usage = self.usage(document.knowledge_id)
            if usage["successful_run_count"] >= 3:
                eligible.append((document, usage))
        eligible.sort(
            key=lambda item: (
                -int(item[1]["successful_run_count"]),
                _reactivation_timestamp(item[1]["last_successful_use"]),
                item[0].knowledge_id,
            )
        )

        entries = []
        for document, usage in eligible:
            fits = active_lines + document.source_line_count <= _MAX_ACTIVE_LINES
            entry = {
                **self._proposal_entry(document, usage),
                "fits_without_displacement": fits,
            }
            if not fits:
                entry["compaction_plan"] = self.compaction_plan(
                    target_lines=max(0, _MAX_ACTIVE_LINES - document.source_line_count)
                )
            entries.append(entry)
        proposal = {"active_lines": active_lines, "entries": entries}
        return {"proposal_id": _proposal_hash(proposal), **proposal}

    def _usage_state(self, knowledge_id: str) -> dict[str, object]:
        stored = self._store.get(USAGE_NAMESPACE, knowledge_id)
        if stored is None:
            return {
                "knowledge_id": knowledge_id,
                "selection_refs": [],
                "successful_refs": [],
                "last_successful_use": None,
            }
        stored_id, state = _stored_usage(stored)
        if stored_id != knowledge_id:
            raise KnowledgeLifecycleError("stored usage state is invalid")
        return state

    def _compaction_rank(self, document: KnowledgeDocument) -> tuple[object, ...]:
        usage = self.usage(document.knowledge_id)
        return (
            not document.supersedes,
            not _is_overdue(document.review_after, self._clock().date()),
            not document.contested,
            int(usage["successful_run_count"]),
            _last_use_rank(usage["last_successful_use"]),
            -document.source_line_count,
            document.knowledge_id,
        )

    def _proposal_entry(
        self,
        document: KnowledgeDocument,
        usage: Mapping[str, object],
    ) -> dict[str, object]:
        return {
            "knowledge_id": document.knowledge_id,
            "source_path": document.source_path,
            "source_sha256": document.source_sha256,
            "lines_released": document.source_line_count,
            "selection_count": usage["selection_count"],
            "successful_run_count": usage["successful_run_count"],
            "last_successful_use": usage["last_successful_use"],
            "reasons": _compaction_reasons(document, self._clock().date()),
        }

    def _validate_observation(self, observation: KnowledgeObservation) -> None:
        for value in observation.model_dump(mode="json").values():
            if not isinstance(value, str):
                continue
            if any(ord(character) < 32 or ord(character) == 127 for character in value):
                raise KnowledgeLifecycleError("prohibited content in observation")
            if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
                raise KnowledgeLifecycleError("prohibited content in observation")
        if not _CONCEPT_KEY_PATTERN.fullmatch(observation.concept_key):
            raise KnowledgeLifecycleError("concept key is invalid")

    def _merge_observation(
        self,
        observation: KnowledgeObservation,
    ) -> tuple[dict[str, object], bool]:
        existing = self._store.get(OBSERVATION_NAMESPACE, observation.concept_key)
        existing_state = {} if existing is None else dict(existing)
        source_refs = existing_state.get("source_refs", ())
        if not isinstance(source_refs, (list, tuple)) or not all(
            isinstance(source_ref, str) for source_ref in source_refs
        ):
            raise KnowledgeLifecycleError("stored observation state is invalid")

        is_new_source = observation.source_ref not in source_refs
        first_observed_at = _earliest_timestamp(
            existing_state.get("first_observed_at"),
            observation.observed_at,
            include=is_new_source,
        )
        last_observed_at = _latest_timestamp(
            existing_state.get("last_observed_at"),
            observation.observed_at,
            include=is_new_source,
        )
        state: dict[str, object] = {
            "source_refs": sorted({*source_refs, observation.source_ref}),
            "first_observed_at": first_observed_at,
            "last_observed_at": last_observed_at,
            "title": observation.title,
            "kind": observation.kind.value,
            "scope": observation.scope.value,
            "summary": observation.summary,
            "explicit": bool(existing_state.get("explicit", False) or observation.explicit),
        }
        return state, state != existing_state

    def _materialize_candidate(
        self,
        observation: KnowledgeObservation,
        state: Mapping[str, object],
        *,
        changed: bool,
    ) -> dict[str, object]:
        count = len(_source_refs(state))
        corpus = self._load_corpus()
        if corpus is not None:
            if any(
                item.knowledge_id == observation.concept_key and item.tier is KnowledgeTier.ACTIVE
                for item in corpus.documents
            ):
                return _result("already-active", observation.concept_key, count)
            if any(
                item.knowledge_id == observation.concept_key and item.tier is KnowledgeTier.ARCHIVE
                for item in corpus.documents
            ):
                return _result("archived-observed", observation.concept_key, count)

        candidate = self._candidate_path(observation.concept_key)
        existing_candidates = self._inventory_inbox_candidates()
        existing = existing_candidates.get(observation.concept_key)
        if existing is not None and existing != candidate:
            raise KnowledgeLifecycleError("candidate path collision")
        if candidate.exists() and existing != candidate:
            raise KnowledgeLifecycleError("candidate path collision")

        if existing is None and not bool(state["explicit"]) and count < _CANDIDATE_THRESHOLD:
            return _result("recorded", observation.concept_key, count)

        if existing is not None:
            metadata = _candidate_metadata(existing)
            if metadata.get("vesper_status") != "candidate":
                raise KnowledgeLifecycleError("candidate path collision")
            content = self._render_candidate(candidate, state)
            if not changed and candidate.read_bytes() == content.encode("utf-8"):
                return _result("candidate-unchanged", observation.concept_key, count)
        else:
            content = self._render_candidate(candidate, state)

        self._write_candidate(candidate, content)
        status = "candidate-updated" if existing is not None else "candidate-created"
        return _result(status, observation.concept_key, count)

    def _load_corpus(self) -> KnowledgeCorpus | None:
        if not self._vault_root.exists():
            return None
        try:
            return load_knowledge_corpus(self._vault_root)
        except KnowledgeSyncError as exc:
            raise KnowledgeLifecycleError(str(exc)) from exc

    def _inventory_inbox_candidates(self) -> dict[str, Path]:
        inbox = self._validated_inbox()
        if not inbox.exists():
            return {}

        candidates: dict[str, Path] = {}
        for path in sorted(inbox.rglob("*.md")):
            if path.name.casefold() == "readme.md":
                continue
            metadata = _candidate_metadata(path)
            knowledge_id = metadata.get("vesper_id")
            if not isinstance(knowledge_id, str) or not knowledge_id:
                continue
            if knowledge_id in candidates:
                raise KnowledgeLifecycleError("duplicate inbox candidate id")
            candidates[knowledge_id] = path
        return candidates

    def _validated_inbox(self) -> Path:
        if _first_link_component(self._vault_root) is not None:
            raise KnowledgeLifecycleError("linked knowledge path is not allowed")
        if self._vault_root.exists() and not self._vault_root.is_dir():
            raise KnowledgeLifecycleError("knowledge vault must be a directory")

        inbox = self._vault_root / "inbox"
        if _first_link_component(inbox) is not None:
            raise KnowledgeLifecycleError("linked knowledge path is not allowed")
        if inbox.exists() and not inbox.is_dir():
            raise KnowledgeLifecycleError("inbox must be a directory")

        vault = self._vault_root.resolve()
        if not inbox.resolve().is_relative_to(vault):
            raise KnowledgeLifecycleError("inbox escapes knowledge vault")
        return inbox

    def _candidate_path(self, concept_key: str) -> Path:
        inbox = self._validated_inbox()
        candidate = inbox / f"{concept_key}.md"
        if _is_link_like(candidate) or not candidate.resolve().is_relative_to(inbox.resolve()):
            raise KnowledgeLifecycleError("candidate escapes knowledge inbox")
        return candidate

    def _render_candidate(self, candidate: Path, state: Mapping[str, object]) -> str:
        metadata = {
            "vesper_id": candidate.stem,
            "vesper_kind": state["kind"],
            "vesper_status": "candidate",
            "vesper_retention": KnowledgeRetention.ADAPTIVE.value,
            "vesper_scope": state["scope"],
            "title": state["title"],
            "tags": ["agent-observed"],
            "vesper_observation_count": len(_source_refs(state)),
            "vesper_first_observed_at": state["first_observed_at"],
            "vesper_last_observed_at": state["last_observed_at"],
            "vesper_confidence": _confidence(state),
            "vesper_source_refs": _source_refs(state),
        }
        return f"---\n{yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)}---\n{state['summary']}\n"

    def _write_candidate(self, candidate: Path, content: str) -> None:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        self._candidate_path(candidate.stem)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=candidate.parent,
                prefix=f".{candidate.stem}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(candidate)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _earliest_timestamp(existing: object, observed_at: datetime, *, include: bool) -> str:
    if existing is None:
        return _format_timestamp(observed_at)
    current = _parse_timestamp(existing)
    return _format_timestamp(min(current, observed_at) if include else current)


def _latest_timestamp(existing: object, observed_at: datetime, *, include: bool) -> str:
    if existing is None:
        return _format_timestamp(observed_at)
    current = _parse_timestamp(existing)
    return _format_timestamp(max(current, observed_at) if include else current)


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise KnowledgeLifecycleError("stored observation state is invalid")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KnowledgeLifecycleError("stored observation state is invalid") from exc
    if timestamp.utcoffset() is None or timestamp.utcoffset().total_seconds() != 0:
        raise KnowledgeLifecycleError("stored observation state is invalid")
    return timestamp.astimezone(timezone.utc)


def _source_refs(state: Mapping[str, object]) -> list[str]:
    source_refs = state["source_refs"]
    if not isinstance(source_refs, list) or not all(
        isinstance(source_ref, str) for source_ref in source_refs
    ):
        raise KnowledgeLifecycleError("stored observation state is invalid")
    return source_refs


def _confidence(state: Mapping[str, object]) -> str:
    return "high" if bool(state["explicit"]) or len(_source_refs(state)) >= 5 else "medium"


def _candidate_metadata(path: Path) -> Mapping[str, object]:
    if _is_link_like(path):
        raise KnowledgeLifecycleError("linked inbox candidates are not allowed")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise KnowledgeLifecycleError("candidate path cannot be read") from exc
    if not lines or lines[0] != "---":
        raise KnowledgeLifecycleError("candidate path collision")
    try:
        boundary = lines.index("---", 1)
        metadata = yaml.safe_load("\n".join(lines[1:boundary]))
    except (ValueError, yaml.YAMLError) as exc:
        raise KnowledgeLifecycleError("candidate path collision") from exc
    if not isinstance(metadata, Mapping):
        raise KnowledgeLifecycleError("candidate path collision")
    return metadata


def _result(status: str, concept_key: str, observation_count: int) -> dict[str, object]:
    return {
        "status": status,
        "concept_key": concept_key,
        "observation_count": observation_count,
    }


def _stored_usage(stored: Mapping[str, object]) -> tuple[str, dict[str, object]]:
    knowledge_id = stored.get("knowledge_id")
    selection_refs = stored.get("selection_refs")
    successful_refs = stored.get("successful_refs")
    last_successful_use = stored.get("last_successful_use")
    if (
        not isinstance(knowledge_id, str)
        or not isinstance(selection_refs, list)
        or not isinstance(successful_refs, list)
        or not all(isinstance(reference, str) for reference in selection_refs)
        or not all(isinstance(reference, str) for reference in successful_refs)
        or (last_successful_use is not None and not isinstance(last_successful_use, str))
    ):
        raise KnowledgeLifecycleError("stored usage state is invalid")
    return knowledge_id, {
        "knowledge_id": knowledge_id,
        "selection_refs": sorted(set(selection_refs)),
        "successful_refs": sorted(set(successful_refs)),
        "last_successful_use": last_successful_use,
    }


def _is_overdue(review_after: date | None, today: date) -> bool:
    return review_after is not None and review_after < today


def _last_use_rank(value: object) -> tuple[int, datetime]:
    if value is None:
        return (0, datetime.min.replace(tzinfo=timezone.utc))
    if not isinstance(value, str):
        raise KnowledgeLifecycleError("stored usage state is invalid")
    return (1, _parse_timestamp(value))


def _reactivation_timestamp(value: object) -> tuple[int, float]:
    rank = _last_use_rank(value)
    return (-rank[0], -rank[1].timestamp())


def _compaction_reasons(document: KnowledgeDocument, today: date) -> list[str]:
    if document.supersedes:
        return ["superseded"]
    if _is_overdue(document.review_after, today):
        return ["review-overdue"]
    if document.contested:
        return ["contested"]
    return ["low-success-use"]


def _proposal_hash(proposal: Mapping[str, object]) -> str:
    canonical = json.dumps(proposal, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & reparse_flag
    )


def _first_link_component(path: Path) -> Path | None:
    current = Path(path.anchor)
    parts = path.parts[1:] if path.anchor else path.parts
    for part in parts:
        current = current / part
        if _is_link_like(current):
            return current
    return None
