"""Controller runner for the five proposal-only quant agents."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from pydantic import ValidationError

from .agent_profiles import AgentProfileCatalog
from .authority import ProposalRouter
from .contracts import AgentRole, JournalEventType, ProposalRoutingDecision
from .journals import AgentJournal
from .quant_agents import OUTPUT_MODELS, QuantAgentOutput
from .qwen_runtime import QwenTurnResult


# Ollama grammar-generation budgets only; the Pydantic output contracts stay unchanged.
_OLLAMA_GENERATION_MAX_TEXT_CHARS = 256
_OLLAMA_GENERATION_MAX_LIST_ITEMS = 3
_OLLAMA_GENERATION_MAX_PROPOSALS = 2
_PROHIBITED_MODEL_TEXT_PATTERNS = (
    re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+\S+"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password|credential)\s*[=:]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]+\b"),
    re.compile(r"(?i)\braw[\s_-]+protected(?:[\s_-]+market)?[\s_-]+data\s*[=:]\s*\S+"),
    re.compile(r"(?i)\b(?:raw[\s_-]+prompt|(?:hidden|producer)[\s_-]+reasoning)\s*[=:]"),
)


class ModelContentPolicyError(ValueError):
    """Typed model output contains content prohibited from persistence."""


class ModelOutputParseError(ValueError):
    """Model output is not valid JSON."""


class ModelOutputValidationError(ValueError):
    """Parsed model output does not satisfy its typed contract."""


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    output: QuantAgentOutput
    decisions: tuple[ProposalRoutingDecision, ...]
    turn: QwenTurnResult


class AutonomousAgentRunner:
    def __init__(
        self,
        *,
        repository_root: Path,
        profiles: AgentProfileCatalog,
        qwen,
        journal: AgentJournal,
        router: ProposalRouter | None = None,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.profiles = profiles
        self.qwen = qwen
        self.journal = journal
        self.router = router or ProposalRouter()

    def run(
        self,
        *,
        role: AgentRole,
        session_id: str,
        run_id: str,
        task_id: str,
        repository_revision: str,
        created_at: datetime,
        objective: str,
        evidence: Mapping[str, object],
    ) -> AgentRunResult:
        profile = self.profiles.load(role)
        bounded_evidence = self._without_producer_reasoning(evidence)
        authority = {
            "role": role.value,
            "session_id": session_id,
            "run_id": run_id,
            "task_id": task_id,
            "repository_revision": repository_revision,
            "created_at": created_at.isoformat(),
        }
        response_format = self._response_format(
            role, authority, evidence_ids=tuple(bounded_evidence)
        )
        prompt = self._prompt(profile, objective, bounded_evidence, authority, response_format)
        self.journal.append(
            event_id=f"{run_id}:{role.value}:observation",
            role=role,
            session_id=session_id,
            run_id=run_id,
            task_id=task_id,
            repository_revision=repository_revision,
            created_at=created_at,
            event_type=JournalEventType.OBSERVATION,
            payload={"objective": objective, "evidence_count": len(bounded_evidence)},
        )
        tool_index = 0

        def audit_tool(payload: dict[str, str | int]) -> None:
            nonlocal tool_index
            tool_index += 1
            self.journal.append(
                event_id=f"{run_id}:{role.value}:tool:{tool_index}",
                role=role,
                session_id=session_id,
                run_id=run_id,
                task_id=task_id,
                repository_revision=repository_revision,
                created_at=created_at,
                event_type=JournalEventType.TOOL_RESULT,
                payload=payload,
            )

        def record_validation_failure(error_type: str) -> None:
            self.journal.append(
                event_id=f"{run_id}:{role.value}:validation-failed",
                role=role,
                session_id=session_id,
                run_id=run_id,
                task_id=task_id,
                repository_revision=repository_revision,
                created_at=created_at,
                event_type=JournalEventType.VALIDATION,
                payload={"status": "failed", "error_type": error_type},
            )

        try:
            turn = self.qwen.run(
                role,
                prompt,
                allowed_tools=profile.allowed_tools,
                response_format=response_format,
                audit=audit_tool,
            )
            try:
                parsed_output = json.loads(turn.content)
            except json.JSONDecodeError:
                raise ModelOutputParseError("model output is not valid JSON") from None
            self._validate_model_text(parsed_output)
            try:
                output = OUTPUT_MODELS[role].model_validate_json(turn.content)
            except ValidationError:
                raise ModelOutputValidationError("model output failed validation") from None
        except Exception as exc:
            record_validation_failure(type(exc).__name__)
            raise
        if (
            output.session_id != session_id
            or output.run_id != run_id
            or output.task_id != task_id
            or output.repository_revision != repository_revision
            or output.created_at != created_at
        ):
            record_validation_failure("AuthorityMismatch")
            raise ValueError("agent output authority does not match the controller request")
        available_evidence = set(bounded_evidence)
        if not set(output.evidence_ids).issubset(available_evidence):
            record_validation_failure("UnboundEvidence")
            raise ValueError("agent output cites evidence not supplied by the controller")
        if any(
            not set(proposal.evidence_ids).issubset(available_evidence)
            for proposal in output.proposals
        ):
            record_validation_failure("UnboundProposalEvidence")
            raise ValueError("agent proposal cites evidence not supplied by the controller")
        self.journal.append(
            event_id=f"{run_id}:{role.value}:action-completed",
            role=role,
            session_id=session_id,
            run_id=run_id,
            task_id=task_id,
            repository_revision=repository_revision,
            created_at=created_at,
            event_type=JournalEventType.ACTION_COMPLETED,
            payload=self._completed_output_payload(output),
        )
        decisions: list[ProposalRoutingDecision] = []
        for index, proposal in enumerate(output.proposals, start=1):
            self.journal.append(
                event_id=f"{run_id}:{role.value}:proposal:{index}",
                role=role,
                session_id=session_id,
                run_id=run_id,
                task_id=task_id,
                repository_revision=repository_revision,
                created_at=created_at,
                event_type=JournalEventType.PROPOSAL_CREATED,
                payload={
                    "proposal_id": proposal.proposal_id,
                    "capability": proposal.capability.value,
                    "summary": proposal.summary,
                    "rationale": proposal.rationale,
                    "evidence_ids": ",".join(proposal.evidence_ids),
                },
            )
            decision = self.router.route(proposal)
            decisions.append(decision)
            self.journal.append(
                event_id=f"{run_id}:{role.value}:routing:{index}",
                role=role,
                session_id=session_id,
                run_id=run_id,
                task_id=task_id,
                repository_revision=repository_revision,
                created_at=created_at,
                event_type=JournalEventType.ROUTING_DECISION,
                payload={
                    "proposal_id": proposal.proposal_id,
                    "status": decision.status.value,
                    "routed_to": (None if decision.routed_to is None else decision.routed_to.value),
                },
            )
        return AgentRunResult(output, tuple(decisions), turn)

    @staticmethod
    def _completed_output_payload(output: QuantAgentOutput) -> dict[str, str | float | int]:
        payload: dict[str, str | float | int] = {
            "summary": output.summary,
            "confidence": output.confidence,
            "evidence_ids": json.dumps(output.evidence_ids, separators=(",", ":")),
            "limitations": json.dumps(output.limitations, separators=(",", ":")),
            "proposal_count": len(output.proposals),
        }
        for field in (
            "hypotheses",
            "priorities",
            "findings",
            "challenges",
            "verdict",
            "exposures",
            "constraints",
            "diagnostics",
        ):
            value = getattr(output, field, None)
            if value is not None:
                payload[field] = (
                    value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
                )
        return payload

    def _prompt(
        self,
        profile,
        objective: str,
        evidence: Mapping[str, object],
        authority: Mapping[str, str],
        response_format: Mapping[str, object],
    ) -> str:
        skill_text: list[str] = []
        for relative in profile.skills:
            path = (self.repository_root / relative).resolve()
            if self.repository_root not in path.parents or path.is_symlink() or not path.is_file():
                raise ValueError(f"profile skill is missing or unsafe: {relative}")
            skill_text.append(path.read_text(encoding="utf-8")[:32_000])
        return "\n\n".join(
            (
                profile.soul,
                f"Role: {profile.profile_id.value}",
                f"Objective: {objective}",
                "Controller-owned fields; copy these values exactly:\n"
                + json.dumps(authority, sort_keys=True),
                "Approved skills:\n" + "\n---\n".join(skill_text),
                "Evidence:\n" + json.dumps(evidence, sort_keys=True),
                f"Return only JSON matching {profile.output_contract}:\n"
                + json.dumps(response_format, sort_keys=True),
            )
        )

    @staticmethod
    def _response_format(
        role: AgentRole,
        authority: Mapping[str, str],
        *,
        evidence_ids: Sequence[str] = (),
    ) -> dict[str, object]:
        schema = deepcopy(OUTPUT_MODELS[role].model_json_schema())
        definitions = schema.pop("$defs", {})

        def inline_refs(value) -> None:
            if isinstance(value, dict):
                reference = value.get("$ref")
                if isinstance(reference, str) and reference.startswith("#/$defs/"):
                    name = reference.removeprefix("#/$defs/")
                    definition = definitions.get(name)
                    if not isinstance(definition, dict):
                        raise ValueError(f"unknown output schema reference: {reference}")
                    overrides = {key: item for key, item in value.items() if key != "$ref"}
                    value.clear()
                    value.update(deepcopy(definition))
                    value.update(overrides)
                for nested in tuple(value.values()):
                    inline_refs(nested)
            elif isinstance(value, list):
                for nested in value:
                    inline_refs(nested)

        inline_refs(schema)

        def bind(value) -> None:
            if isinstance(value, dict):
                properties = value.get("properties")
                if isinstance(properties, dict):
                    for field, expected in authority.items():
                        definition = properties.get(field)
                        if isinstance(definition, dict):
                            definition["const"] = expected
                for nested in value.values():
                    bind(nested)
            elif isinstance(value, list):
                for nested in value:
                    bind(nested)

        bind(schema)

        allowed_evidence_ids = list(dict.fromkeys(evidence_ids))

        def compact(value, field_name: str | None = None) -> None:
            if isinstance(value, dict):
                for keyword in ("default", "format", "pattern", "title"):
                    value.pop(keyword, None)
                if "const" in value:
                    value.pop("enum", None)
                if value.get("type") == "string" and "const" not in value and "enum" not in value:
                    value["maxLength"] = min(
                        int(value.get("maxLength", _OLLAMA_GENERATION_MAX_TEXT_CHARS)),
                        _OLLAMA_GENERATION_MAX_TEXT_CHARS,
                    )
                if value.get("type") == "array":
                    limit = (
                        _OLLAMA_GENERATION_MAX_PROPOSALS
                        if field_name == "proposals"
                        else _OLLAMA_GENERATION_MAX_LIST_ITEMS
                    )
                    value["maxItems"] = min(int(value.get("maxItems", limit)), limit)
                    if field_name == "evidence_ids" and allowed_evidence_ids:
                        value["minItems"] = max(int(value.get("minItems", 0)), 1)
                        items = value.get("items")
                        if isinstance(items, dict):
                            items["enum"] = allowed_evidence_ids
                properties = value.get("properties")
                if isinstance(properties, dict):
                    for name, nested in properties.items():
                        compact(nested, name)
                    evidence_definition = properties.get("evidence_ids")
                    if (
                        allowed_evidence_ids
                        and isinstance(evidence_definition, dict)
                        and evidence_definition.get("type") == "array"
                    ):
                        required = value.setdefault("required", [])
                        if "evidence_ids" not in required:
                            required.append("evidence_ids")
                for key, nested in tuple(value.items()):
                    if key != "properties":
                        compact(nested)
            elif isinstance(value, list):
                for nested in value:
                    compact(nested)

        compact(schema)
        return schema

    @classmethod
    def _validate_model_text(cls, value) -> None:
        if isinstance(value, str):
            if any(pattern.search(value) for pattern in _PROHIBITED_MODEL_TEXT_PATTERNS):
                raise ModelContentPolicyError("prohibited model content")
            return
        if isinstance(value, Mapping):
            for item in value.values():
                cls._validate_model_text(item)
            return
        if isinstance(value, Sequence):
            for item in value:
                cls._validate_model_text(item)

    @classmethod
    def _without_producer_reasoning(cls, value):
        if isinstance(value, Mapping):
            return {
                key: cls._without_producer_reasoning(item)
                for key, item in value.items()
                if key != "producer_reasoning"
            }
        if isinstance(value, list):
            return [cls._without_producer_reasoning(item) for item in value]
        return value
