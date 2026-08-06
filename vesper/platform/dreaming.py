"""Automatic V20 memory consolidation from redacted cold transcripts."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .contracts import (
    DreamAppliedChange,
    DreamGateProposal,
    DreamGateReport,
    DreamMode,
    DreamProposalType,
)
from .knowledge import load_approved_documents
from .ollama import OllamaClient, QWEN_MODEL
from .session_recorder import is_cold_transcript


class DreamGateError(RuntimeError):
    """Dream input or model output failed the proposal-only boundary."""


MAX_DREAM_SESSION_CHARS = 240_000


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DreamGate:
    """Read sessions and active memory, then write one immutable cold report."""

    def __init__(
        self,
        vault_root: Path,
        *,
        client: object | None = None,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.vault_root = vault_root.resolve()
        self._client = client or OllamaClient()
        self._clock = clock
        self._id_factory = id_factory

    def run(self, *, dry_run: bool = False) -> DreamGateReport:
        if not self.vault_root.is_dir():
            raise DreamGateError(f"knowledge vault does not exist: {self.vault_root}")
        sessions = self._session_sources()
        active = load_approved_documents(self.vault_root)
        prompt = self._prompt(sessions, active)
        if dry_run:
            payload = {"proposals": []}
        else:
            response = self._client.chat(
                [{"role": "user", "content": prompt}],
                response_format=self._response_schema(),
            )
            payload = self._parse_response(response.content)
        proposals = tuple(self._proposal(item) for item in payload.get("proposals", ()))
        dream_id = self._id_factory()
        applied, apply_limitations = ((), ()) if dry_run else self._apply_proposals(
            dream_id, proposals, tuple(item[0] for item in sessions)
        )
        applied_ids = {item.proposal_id for item in applied}
        final_proposals = tuple(
            item.model_copy(update={"status": "applied"}) if item.proposal_id in applied_ids else item
            for item in proposals
        )
        report = DreamGateReport(
            dream_id=dream_id,
            created_at=self._clock(),
            mode=(DreamMode.CROSS_SESSION if sessions else DreamMode.MEMORY_AUDIT_ONLY),
            model=QWEN_MODEL,
            source_session_ids=tuple(item[0] for item in sessions),
            source_hashes=tuple(item[1] for item in sessions),
            active_memory_sha256=self._active_hash(active),
            proposals=final_proposals,
            applied_changes=applied,
            limitations=(
                ("Dry run: model inference was not called.",) if dry_run else ()
            )
            + apply_limitations
            + ("Automatic learning does not grant controller or real-world authority.",),
        )
        self._write_report(report)
        return report

    def _session_sources(self) -> tuple[tuple[str, str, str], ...]:
        root = self.vault_root / "sessions"
        if not root.is_dir():
            return ()
        sources = []
        for path in sorted(root.rglob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            relative = path.relative_to(self.vault_root).as_posix()
            source = path.read_bytes()
            content = source.decode("utf-8")
            if not is_cold_transcript(content):
                continue
            sources.append((relative, hashlib.sha256(source).hexdigest(), content))
        return tuple(sources)

    @staticmethod
    def _active_hash(documents) -> str:
        digest = hashlib.sha256()
        for document in documents:
            digest.update(document.source_path.encode("utf-8"))
            digest.update(document.source_sha256.encode("ascii"))
        return digest.hexdigest()

    @staticmethod
    def _response_schema() -> Mapping[str, object]:
        return {
            "type": "object",
            "properties": {
                "proposals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "proposal_id": {"type": "string"},
                            "proposal_type": {
                                "type": "string",
                                "enum": [item.value for item in DreamProposalType],
                            },
                            "target": {"type": "string"},
                            "summary": {"type": "string"},
                            "evidence": {"type": "string"},
                            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        },
                        "required": [
                            "proposal_id",
                            "proposal_type",
                            "target",
                            "summary",
                            "evidence",
                            "confidence",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["proposals"],
            "additionalProperties": False,
        }

    @staticmethod
    def _parse_response(content: str) -> Mapping[str, object]:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise DreamGateError("Dream Gate model output was not valid JSON") from exc
        if not isinstance(payload, Mapping) or not isinstance(payload.get("proposals"), list):
            raise DreamGateError("Dream Gate output must contain a proposals list")
        return payload

    @staticmethod
    def _proposal(raw: object) -> DreamGateProposal:
        if not isinstance(raw, Mapping):
            raise DreamGateError("Dream Gate proposal must be an object")
        target = raw.get("target")
        if isinstance(target, str):
            target = target.strip()
            for suffix in (" (Draft)", " (draft)", " (Active)", " (active)"):
                if target.endswith(suffix):
                    target = target[: -len(suffix)].rstrip()
        if isinstance(target, str) and target.startswith(("memory/", "skills/")):
            target = f"knowledge/{target}"
        if (
            not isinstance(target, str)
            or not target.startswith(
                ("knowledge/memory/", "knowledge/skills/", "knowledge/inbox/")
            )
            or ".." in Path(target).parts
        ):
            raise DreamGateError(
                f"Dream Gate proposal target must be active knowledge: {target!r}"
            )
        try:
            return DreamGateProposal.model_validate_json(
                json.dumps(
                    {
                        **dict(raw),
                        "target": target,
                        "auto_apply": True,
                        "status": "pending",
                    }
                )
            )
        except Exception as exc:
            raise DreamGateError(f"Dream Gate proposal is invalid: {exc}") from exc

    def _prompt(self, sessions, active) -> str:
        session_text = self._bounded_session_text(sessions)
        active_text = "\n\n".join(
            f"ACTIVE {document.source_path} sha256={document.source_sha256}\n"
            f"{document.content}"
            for document in active
        ) or "No active memory documents available."
        return (
            "You are V20 Dream Gate. Analyze only the supplied redacted cold session event transcripts "
            "and approved active knowledge. Return proposals for durable facts, decisions, "
            "preferences, procedures, duplicates, or deprecations. Do not return secrets, "
            "temporary task state, unsupported authority, or raw transcript text. "
            "Apply stable memory and procedure learnings automatically to the V20 knowledge vault. "
            "Do not return secrets, temporary task state, unsupported authority, or raw transcript "
            "text.\n\nCOLD SESSION TRANSCRIPTS:\n"
            f"{session_text}\n\nACTIVE KNOWLEDGE:\n{active_text}"
        )

    @staticmethod
    def _bounded_session_text(sessions) -> str:
        if not sessions:
            return "No cold session transcripts available. Audit active memory only."
        parts = []
        used = 0
        for path, source_hash, content in sessions:
            separator_length = 2 if parts else 0
            available = MAX_DREAM_SESSION_CHARS - used - separator_length
            if available <= 0:
                break
            header = f"SOURCE {path} sha256={source_hash}\n"
            if len(header) >= available:
                parts.append(header[:available])
                break
            remaining = available - len(header)
            if len(content) > remaining:
                marker = "\n[SOURCE BODY TRUNCATED FOR DREAM CONTEXT]"
                body = (content[: max(0, remaining - len(marker))] + marker)[:remaining]
                parts.append(header + body)
                break
            else:
                body = content
            chunk = header + body
            parts.append(chunk)
            used += separator_length + len(chunk)
        return "\n\n".join(parts)

    def _write_report(self, report: DreamGateReport) -> None:
        path = self.vault_root / "dreams" / "reports" / f"{report.dream_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)

    def _apply_proposals(
        self,
        dream_id: str,
        proposals: tuple[DreamGateProposal, ...],
        source_session_ids: tuple[str, ...],
    ) -> tuple[tuple[DreamAppliedChange, ...], tuple[str, ...]]:
        applied: list[DreamAppliedChange] = []
        limitations: list[str] = []
        for proposal in proposals:
            if proposal.proposal_type is DreamProposalType.NO_CHANGE:
                continue
            target = Path(proposal.target)
            if target.parts[:2] not in (("knowledge", "memory"), ("knowledge", "skills")):
                limitations.append(f"Skipped unsupported dream target: {proposal.target}")
                continue
            relative = Path(*target.parts[1:])
            destination = self.vault_root / relative
            existed = destination.exists()
            destination.parent.mkdir(parents=True, exist_ok=True)
            kind = "skill" if target.parts[1] == "skills" else "memory"
            scope = "v20-development" if kind == "skill" else "shared"
            status = "archived" if proposal.proposal_type in {
                DreamProposalType.DEPRECATION,
                DreamProposalType.DUPLICATE,
            } else "approved"
            title = proposal.summary.strip().rstrip(".")[:160] or proposal.proposal_id
            note = (
                "---\n"
                f"vesper_id: dream-{proposal.proposal_id}\n"
                f"vesper_kind: {kind}\n"
                f"vesper_status: {status}\n"
                f"vesper_scope: {scope}\n"
                f"title: {json.dumps(title)}\n"
                f"dream_id: {dream_id}\n"
                "---\n\n"
                f"# {title}\n\n"
                f"{proposal.summary.strip()}\n\n"
                f"Evidence: {proposal.evidence.strip()}\n\n"
                f"Source sessions: {', '.join(source_session_ids) or 'memory audit'}\n"
            )
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            temporary.write_text(note, encoding="utf-8")
            temporary.replace(destination)
            action = "updated" if existed else "created"
            applied.append(
                DreamAppliedChange(
                    proposal_id=proposal.proposal_id,
                    target=target.as_posix(),
                    action=action,
                    sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                )
            )
        return tuple(applied), tuple(limitations)
