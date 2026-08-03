import json
from datetime import datetime, timezone

import pytest

from vesper.platform.agent_profiles import AgentProfileCatalog, AgentProfileIntegrityError
from vesper.platform.agent_runner import AutonomousAgentRunner
from vesper.platform.contracts import AgentRole, JournalEventType, ProposalStatus
from vesper.platform.journals import AgentJournal
from vesper.platform.persistence import PlatformPaths, open_persistence
from vesper.platform.qwen_runtime import QwenTurnResult
from vesper.platform.quant_agents import OUTPUT_MODELS
from vesper.platform.service import LocalPlatformService
from vesper.platform.review import DailyReviewService


NOW = datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc)
ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
NEW_ROLES = (
    AgentRole.QUANT_RESEARCH_LEAD,
    AgentRole.MODEL_RESEARCHER,
    AgentRole.INDEPENDENT_QUANT_VALIDATOR,
    AgentRole.PORTFOLIO_RESEARCHER,
    AgentRole.EXECUTION_PERFORMANCE_ANALYST,
)


def test_all_five_profiles_are_qwen_bounded_and_separate():
    profiles = AgentProfileCatalog(ROOT / "profiles" / "native").load_all()
    assert {profile.profile_id for profile in profiles} == set(NEW_ROLES)
    assert all(profile.model == "qwen:64k" for profile in profiles)
    assert len({profile.memory_namespace for profile in profiles}) == 5
    assert all(set(profile.allowed_tools) <= {"read_file", "search_text"} for profile in profiles)


def test_profile_catalog_rejects_role_mismatch(tmp_path):
    source = ROOT / "profiles" / "native" / AgentRole.MODEL_RESEARCHER.value
    target = tmp_path / AgentRole.MODEL_RESEARCHER.value
    __import__("shutil").copytree(source, target)
    profile = target / "profile.yaml"
    profile.write_text(
        profile.read_text().replace("v20-model-researcher", "v20-portfolio-researcher")
    )
    with pytest.raises(AgentProfileIntegrityError):
        AgentProfileCatalog(tmp_path).load(AgentRole.MODEL_RESEARCHER)


def output_document(role: AgentRole):
    base = {
        "schema_version": "1.0",
        "run_id": "run-1",
        "task_id": "task-1",
        "repository_revision": "abc123",
        "created_at": NOW.isoformat().replace("+00:00", "Z"),
        "role": role.value,
        "session_id": "session-1",
        "summary": "Bounded evidence review.",
        "evidence_ids": ["artifact-1"],
        "confidence": 0.7,
        "limitations": ["Synthetic evidence."],
        "proposals": [
            {
                "schema_version": "1.0",
                "run_id": "run-1",
                "task_id": "task-1",
                "repository_revision": "abc123",
                "created_at": NOW.isoformat().replace("+00:00", "Z"),
                "proposal_id": "proposal-1",
                "role": role.value,
                "capability": "research",
                "summary": "Run a bounded follow-up.",
                "rationale": "Evidence supports follow-up.",
                "evidence_ids": ["artifact-1"],
            }
        ],
    }
    extras = {
        AgentRole.QUANT_RESEARCH_LEAD: {
            "hypotheses": ["Signal may persist."],
            "priorities": ["Validate OOS."],
        },
        AgentRole.MODEL_RESEARCHER: {"findings": ["Metadata is internally consistent."]},
        AgentRole.INDEPENDENT_QUANT_VALIDATOR: {
            "challenges": ["Check leakage."],
            "verdict": "inconclusive",
        },
        AgentRole.PORTFOLIO_RESEARCHER: {
            "exposures": ["Sector concentration."],
            "constraints": ["No allocation change."],
        },
        AgentRole.EXECUTION_PERFORMANCE_ANALYST: {"diagnostics": ["Slippage rose."]},
    }
    return {**base, **extras[role]}


PROHIBITED_MODEL_TEXT_CASES = (
    (AgentRole.MODEL_RESEARCHER, ("summary",), "api_key=[FAKE-REDACTED]"),
    (
        AgentRole.MODEL_RESEARCHER,
        ("limitations", 0),
        "raw_protected_market_data=[FAKE-REDACTED]",
    ),
    (
        AgentRole.QUANT_RESEARCH_LEAD,
        ("hypotheses", 0),
        "authorization: bearer [FAKE-REDACTED]",
    ),
    (AgentRole.QUANT_RESEARCH_LEAD, ("priorities", 0), "token=[FAKE-REDACTED]"),
    (AgentRole.MODEL_RESEARCHER, ("findings", 0), "secret=[FAKE-REDACTED]"),
    (AgentRole.MODEL_RESEARCHER, ("findings", 0), "password=[FAKE-REDACTED]"),
    (AgentRole.MODEL_RESEARCHER, ("findings", 0), "credential=[FAKE-REDACTED]"),
    (
        AgentRole.INDEPENDENT_QUANT_VALIDATOR,
        ("challenges", 0),
        "api-key=[FAKE-REDACTED]",
    ),
    (AgentRole.PORTFOLIO_RESEARCHER, ("exposures", 0), "token=[FAKE-REDACTED]"),
    (
        AgentRole.PORTFOLIO_RESEARCHER,
        ("constraints", 0),
        "raw-protected-market-data=[FAKE-REDACTED]",
    ),
    (
        AgentRole.EXECUTION_PERFORMANCE_ANALYST,
        ("diagnostics", 0),
        "secret=[FAKE-REDACTED]",
    ),
    (
        AgentRole.MODEL_RESEARCHER,
        ("proposals", 0, "summary"),
        "api_key=[FAKE-REDACTED]",
    ),
    (
        AgentRole.MODEL_RESEARCHER,
        ("proposals", 0, "rationale"),
        "raw_protected_market_data=[FAKE-REDACTED]",
    ),
)


@pytest.mark.parametrize(("role", "path", "sentinel"), PROHIBITED_MODEL_TEXT_CASES)
def test_runner_rejects_prohibited_model_text_without_model_derived_event(
    tmp_path, role, path, sentinel
):
    document = output_document(role)
    target = document
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = sentinel

    class Qwen:
        def run(self, *_args, **_kwargs):
            return QwenTurnResult(json.dumps(document), 100, 0)

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        journal = AgentJournal(persistence.store)
        runner = AutonomousAgentRunner(
            repository_root=ROOT,
            profiles=AgentProfileCatalog(ROOT / "profiles" / "native"),
            qwen=Qwen(),
            journal=journal,
        )
        with pytest.raises(ValueError, match="prohibited model content") as captured:
            runner.run(
                role=role,
                session_id="session-1",
                run_id="run-1",
                task_id="task-1",
                repository_revision="abc123",
                created_at=NOW,
                objective="Inspect bounded financial evidence.",
                evidence={"artifact-1": {"claim": "bounded"}},
            )
        assert sentinel not in str(captured.value)

        events = journal.list(role, "session-1")
        assert [event.event_type for event in events] == [
            JournalEventType.OBSERVATION,
            JournalEventType.VALIDATION,
        ]
        assert events[-1].payload == {
            "status": "failed",
            "error_type": "ModelContentPolicyError",
        }
        assert sentinel not in json.dumps(
            [event.model_dump(mode="json") for event in events], sort_keys=True
        )


def test_runner_checks_prohibited_text_before_schema_validation(tmp_path):
    role = AgentRole.MODEL_RESEARCHER
    sentinel = "api_key=[FAKE-REDACTED]"
    document = output_document(role)
    document["confidence"] = sentinel

    class Qwen:
        def run(self, *_args, **_kwargs):
            return QwenTurnResult(json.dumps(document), 100, 0)

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        journal = AgentJournal(persistence.store)
        runner = AutonomousAgentRunner(
            repository_root=ROOT,
            profiles=AgentProfileCatalog(ROOT / "profiles" / "native"),
            qwen=Qwen(),
            journal=journal,
        )
        with pytest.raises(ValueError) as captured:
            runner.run(
                role=role,
                session_id="session-1",
                run_id="run-1",
                task_id="task-1",
                repository_revision="abc123",
                created_at=NOW,
                objective="Inspect bounded financial evidence.",
                evidence={"artifact-1": {"claim": "bounded"}},
            )

        assert str(captured.value) == "prohibited model content"
        assert sentinel not in str(captured.value)
        events = journal.list(role, "session-1")
        assert [event.event_type for event in events] == [
            JournalEventType.OBSERVATION,
            JournalEventType.VALIDATION,
        ]
        assert events[-1].payload == {
            "status": "failed",
            "error_type": "ModelContentPolicyError",
        }
        assert sentinel not in json.dumps(
            [event.model_dump(mode="json") for event in events], sort_keys=True
        )


def test_runner_translates_schema_validation_error_without_raw_input(tmp_path):
    role = AgentRole.MODEL_RESEARCHER
    invalid_input = "not-a-number-input"
    document = output_document(role)
    document["confidence"] = invalid_input

    class Qwen:
        def run(self, *_args, **_kwargs):
            return QwenTurnResult(json.dumps(document), 100, 0)

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        journal = AgentJournal(persistence.store)
        runner = AutonomousAgentRunner(
            repository_root=ROOT,
            profiles=AgentProfileCatalog(ROOT / "profiles" / "native"),
            qwen=Qwen(),
            journal=journal,
        )
        with pytest.raises(ValueError) as captured:
            runner.run(
                role=role,
                session_id="session-1",
                run_id="run-1",
                task_id="task-1",
                repository_revision="abc123",
                created_at=NOW,
                objective="Inspect bounded financial evidence.",
                evidence={"artifact-1": {"claim": "bounded"}},
            )

        assert str(captured.value) == "model output failed validation"
        assert captured.value.__cause__ is None
        assert invalid_input not in str(captured.value)
        events = journal.list(role, "session-1")
        assert events[-1].payload == {
            "status": "failed",
            "error_type": "ModelOutputValidationError",
        }


@pytest.mark.parametrize("role", NEW_ROLES)
def test_each_agent_output_is_typed_and_proposal_only(role):
    parsed = OUTPUT_MODELS[role].model_validate_json(json.dumps(output_document(role)))
    assert parsed.role is role
    assert parsed.proposals[0].role is role


@pytest.mark.parametrize(
    ("role", "conclusions"),
    (
        (
            AgentRole.QUANT_RESEARCH_LEAD,
            {"hypotheses": '["Signal may persist."]', "priorities": '["Validate OOS."]'},
        ),
        (AgentRole.MODEL_RESEARCHER, {"findings": '["Metadata is internally consistent."]'}),
        (
            AgentRole.INDEPENDENT_QUANT_VALIDATOR,
            {"challenges": '["Check leakage."]', "verdict": "inconclusive"},
        ),
        (
            AgentRole.PORTFOLIO_RESEARCHER,
            {"exposures": '["Sector concentration."]', "constraints": '["No allocation change."]'},
        ),
        (AgentRole.EXECUTION_PERFORMANCE_ANALYST, {"diagnostics": '["Slippage rose."]'}),
    ),
)
def test_runner_journals_validated_completed_output_for_each_role(tmp_path, role, conclusions):

    class Qwen:
        def run(self, actual_role, prompt, **kwargs):
            assert actual_role is role
            assert "producer_reasoning" not in prompt
            assert kwargs["allowed_tools"] == ("read_file", "search_text")
            return QwenTurnResult(json.dumps(output_document(role)), 100, 0)

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        journal = AgentJournal(persistence.store)
        runner = AutonomousAgentRunner(
            repository_root=ROOT,
            profiles=AgentProfileCatalog(ROOT / "profiles" / "native"),
            qwen=Qwen(),
            journal=journal,
        )
        result = runner.run(
            role=role,
            session_id="session-1",
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            objective="Inspect signal.",
            evidence={"artifact-1": {"claim": "bounded"}, "producer_reasoning": "hidden"},
        )
        assert result.decisions[0].status is ProposalStatus.ADMITTED
        events = journal.list(role, "session-1")
        assert [event.event_type for event in events] == [
            JournalEventType.OBSERVATION,
            JournalEventType.ACTION_COMPLETED,
            JournalEventType.PROPOSAL_CREATED,
            JournalEventType.ROUTING_DECISION,
        ]
        completed_output = events[1].payload
        assert completed_output == {
            "summary": "Bounded evidence review.",
            "confidence": 0.7,
            "evidence_ids": '["artifact-1"]',
            "limitations": '["Synthetic evidence."]',
            "proposal_count": 1,
            **conclusions,
        }
        assert all(
            not isinstance(value, (list, dict, tuple)) for value in completed_output.values()
        )
        digest = DailyReviewService(persistence.store, tmp_path / "review").render(
            NOW.date(), {role: events}
        )
        markdown = digest.markdown_path.read_text(encoding="utf-8")
        assert "Bounded evidence review." in markdown
        assert "action-completed" in markdown
        assert all(key in markdown for key in conclusions)
        assert "Run a bounded follow-up." in markdown
        assert role.value in markdown


def test_runner_binds_controller_authority_into_prompt_and_response_schema(tmp_path):
    role = AgentRole.QUANT_RESEARCH_LEAD
    captured = {}

    class Qwen:
        def run(self, actual_role, prompt, **kwargs):
            captured["role"] = actual_role
            captured["prompt"] = prompt
            captured["response_format"] = kwargs["response_format"]
            return QwenTurnResult(json.dumps(output_document(role)), 100, 0)

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        AutonomousAgentRunner(
            repository_root=ROOT,
            profiles=AgentProfileCatalog(ROOT / "profiles" / "native"),
            qwen=Qwen(),
            journal=AgentJournal(persistence.store),
        ).run(
            role=role,
            session_id="session-1",
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            objective="Inspect signal.",
            evidence={"artifact-1": {"claim": "bounded"}},
        )

    expected = {
        "role": role.value,
        "session_id": "session-1",
        "run_id": "run-1",
        "task_id": "task-1",
        "repository_revision": "abc123",
        "created_at": NOW.isoformat(),
    }
    assert captured["role"] is role
    assert all(value in captured["prompt"] for value in expected.values())
    properties = captured["response_format"]["properties"]
    assert {key: properties[key]["const"] for key in expected} == expected
    proposal_properties = captured["response_format"]["properties"]["proposals"]["items"][
        "properties"
    ]
    proposal_expected = {key: expected[key] for key in expected if key != "session_id"}
    assert {
        key: proposal_properties[key]["const"] for key in proposal_expected
    } == proposal_expected


@pytest.mark.parametrize("role", NEW_ROLES)
def test_runner_response_schema_is_compact_and_bounded_for_ollama(role):
    authority = {
        "role": role.value,
        "session_id": "session-1",
        "run_id": "run-1",
        "task_id": "task-1",
        "repository_revision": "abc123",
        "created_at": NOW.isoformat(),
    }
    schema = AutonomousAgentRunner._response_format(
        role,
        authority,
        evidence_ids=("evidence-1", "evidence-2"),
    )
    forbidden_keywords = {
        "$defs",
        "$ref",
        "default",
        "format",
        "pattern",
        "title",
    }

    def assert_compact(value):
        if isinstance(value, dict):
            assert forbidden_keywords.isdisjoint(value)
            if value.get("type") == "string" and "const" not in value and "enum" not in value:
                assert value["maxLength"] == 256
            if value.get("type") == "array":
                assert value["maxItems"] <= 3
                if "minItems" in value:
                    assert value["minItems"] <= value["maxItems"]
            for nested in value.values():
                assert_compact(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_compact(nested)

    assert_compact(schema)
    properties = schema["properties"]
    assert "proposals" not in schema["required"]
    assert properties["proposals"].get("minItems", 0) == 0
    assert properties["evidence_ids"]["items"]["enum"] == ["evidence-1", "evidence-2"]
    proposal = properties["proposals"]["items"]
    assert "evidence_ids" in proposal["required"]
    assert proposal["properties"]["evidence_ids"]["minItems"] == 1
    assert proposal["properties"]["evidence_ids"]["items"]["enum"] == [
        "evidence-1",
        "evidence-2",
    ]
    assert properties["proposals"]["maxItems"] <= 2


def test_ollama_generation_budgets_do_not_narrow_pydantic_output_contract():
    document = output_document(AgentRole.QUANT_RESEARCH_LEAD)
    document["summary"] = "s" * 512
    document["limitations"] = [f"limitation-{index}" for index in range(4)]
    document["hypotheses"] = [f"hypothesis-{index}" for index in range(4)]
    document["priorities"] = [f"priority-{index}" for index in range(4)]
    document["proposals"] = [
        {**document["proposals"][0], "proposal_id": f"proposal-{index}"} for index in range(3)
    ]

    parsed = OUTPUT_MODELS[AgentRole.QUANT_RESEARCH_LEAD].model_validate_json(json.dumps(document))

    assert len(parsed.limitations) == 4
    assert len(parsed.summary) == 512
    assert len(parsed.hypotheses) == 4
    assert len(parsed.priorities) == 4
    assert len(parsed.proposals) == 3


def test_runner_rejects_unbound_output_evidence_without_action_completed(tmp_path):
    role = AgentRole.MODEL_RESEARCHER
    document = output_document(role)
    document["evidence_ids"] = ["not-supplied"]

    class Qwen:
        def run(self, *_args, **_kwargs):
            return QwenTurnResult(json.dumps(document), 100, 0)

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        journal = AgentJournal(persistence.store)
        runner = AutonomousAgentRunner(
            repository_root=ROOT,
            profiles=AgentProfileCatalog(ROOT / "profiles" / "native"),
            qwen=Qwen(),
            journal=journal,
        )
        with pytest.raises(ValueError, match="not supplied"):
            runner.run(
                role=role,
                session_id="session-1",
                run_id="run-1",
                task_id="task-1",
                repository_revision="abc123",
                created_at=NOW,
                objective="Inspect model.",
                evidence={"artifact-1": {"claim": "bounded"}},
            )
        assert [event.event_type for event in journal.list(role, "session-1")] == [
            JournalEventType.OBSERVATION,
            JournalEventType.VALIDATION,
        ]


def test_runner_rejects_authority_mismatch_without_action_completed(tmp_path):
    role = AgentRole.MODEL_RESEARCHER
    document = output_document(role)
    wrong_timestamp = (
        datetime(2026, 8, 2, 20, 1, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    )
    document["created_at"] = wrong_timestamp
    document["proposals"][0]["created_at"] = wrong_timestamp

    class Qwen:
        def run(self, *_args, **_kwargs):
            return QwenTurnResult(json.dumps(document), 100, 0)

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        journal = AgentJournal(persistence.store)
        runner = AutonomousAgentRunner(
            repository_root=ROOT,
            profiles=AgentProfileCatalog(ROOT / "profiles" / "native"),
            qwen=Qwen(),
            journal=journal,
        )
        with pytest.raises(ValueError, match="authority"):
            runner.run(
                role=role,
                session_id="session-1",
                run_id="run-1",
                task_id="task-1",
                repository_revision="abc123",
                created_at=NOW,
                objective="Inspect model.",
                evidence={"artifact-1": {"claim": "bounded"}},
            )
        assert [event.event_type for event in journal.list(role, "session-1")] == [
            JournalEventType.OBSERVATION,
            JournalEventType.VALIDATION,
        ]


def test_runner_rejects_malformed_json_without_action_completed(tmp_path):
    role = AgentRole.MODEL_RESEARCHER
    malformed = "not-json-input"

    class Qwen:
        def run(self, *_args, **_kwargs):
            return QwenTurnResult(malformed, 100, 0)

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        journal = AgentJournal(persistence.store)
        runner = AutonomousAgentRunner(
            repository_root=ROOT,
            profiles=AgentProfileCatalog(ROOT / "profiles" / "native"),
            qwen=Qwen(),
            journal=journal,
        )
        with pytest.raises(ValueError) as captured:
            runner.run(
                role=role,
                session_id="session-1",
                run_id="run-1",
                task_id="task-1",
                repository_revision="abc123",
                created_at=NOW,
                objective="Inspect model.",
                evidence={"artifact-1": {"claim": "bounded"}},
            )
        assert str(captured.value) == "model output is not valid JSON"
        assert captured.value.__cause__ is None
        assert malformed not in str(captured.value)
        assert [event.event_type for event in journal.list(role, "session-1")] == [
            JournalEventType.OBSERVATION,
            JournalEventType.VALIDATION,
        ]
        assert journal.list(role, "session-1")[-1].payload == {
            "status": "failed",
            "error_type": "ModelOutputParseError",
        }


def test_runner_rejects_unbound_proposal_evidence_without_action_completed(tmp_path):
    role = AgentRole.MODEL_RESEARCHER
    document = output_document(role)
    document["proposals"][0]["evidence_ids"] = ["not-supplied"]

    class Qwen:
        def run(self, *_args, **_kwargs):
            return QwenTurnResult(json.dumps(document), 100, 0)

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        journal = AgentJournal(persistence.store)
        runner = AutonomousAgentRunner(
            repository_root=ROOT,
            profiles=AgentProfileCatalog(ROOT / "profiles" / "native"),
            qwen=Qwen(),
            journal=journal,
        )
        with pytest.raises(ValueError, match="proposal cites evidence"):
            runner.run(
                role=role,
                session_id="session-1",
                run_id="run-1",
                task_id="task-1",
                repository_revision="abc123",
                created_at=NOW,
                objective="Inspect model.",
                evidence={"artifact-1": {"claim": "bounded"}},
            )
        assert [event.event_type for event in journal.list(role, "session-1")] == [
            JournalEventType.OBSERVATION,
            JournalEventType.VALIDATION,
        ]


def test_service_reports_eight_roles_and_manual_review_gate(tmp_path):
    service = LocalPlatformService(
        PlatformPaths.below(tmp_path / "state"),
        profiles_root=ROOT / "profiles" / "native",
        clock=lambda: NOW,
    )
    roster = service.agent_roster()
    assert roster["count"] == 8
    assert roster["scheduler_active"] is False
    assert service.agent_gate_status("2026-08-01")["new_proposals_admitted"] is False
    digest = service.render_agent_digest("2026-08-01")
    assert len(digest["sections"]) == 8
    service.acknowledge_agent_digest("2026-08-01", "operator")
    assert service.agent_gate_status("2026-08-01")["new_proposals_admitted"] is True
