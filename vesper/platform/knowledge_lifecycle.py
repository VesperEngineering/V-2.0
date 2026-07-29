"""Safe consolidation of agent observations into reviewable knowledge candidates."""

from __future__ import annotations

import os
import re
import stat
import tempfile
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .contracts import KnowledgeObservation, KnowledgeRetention, KnowledgeTier
from .knowledge import (
    KnowledgeCorpus,
    KnowledgeStorePort,
    KnowledgeSyncError,
    load_knowledge_corpus,
)


OBSERVATION_NAMESPACE = ("knowledge", "adaptive", "observations")
_CANDIDATE_THRESHOLD = 3
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
            if not changed:
                return _result("candidate-unchanged", observation.concept_key, count)

        self._write_candidate(candidate, state)
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

    def _write_candidate(self, candidate: Path, state: Mapping[str, object]) -> None:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        self._candidate_path(candidate.stem)
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
        content = f"---\n{yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)}---\n{state['summary']}\n"
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
