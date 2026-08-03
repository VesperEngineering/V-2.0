from datetime import datetime, timezone

import pytest

from vesper.platform.authority import ProposalRouter
from vesper.platform.contracts import (
    AgentProposal,
    AgentRole,
    AuthorityClass,
    ProposalCapability,
    ProposalStatus,
)


NOW = datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc)


def proposal(capability: ProposalCapability, *, evidence=("artifact-1",)) -> AgentProposal:
    return AgentProposal(
        run_id="run-1",
        task_id="task-1",
        repository_revision="abc123",
        created_at=NOW,
        proposal_id="proposal-1",
        role=AgentRole.QUANT_RESEARCH_LEAD,
        capability=capability,
        summary="Investigate a bounded hypothesis.",
        rationale="Evidence indicates this is worth testing.",
        evidence_ids=evidence,
    )


def test_eight_role_roster_is_explicit():
    assert len(AgentRole) == 8
    assert AgentRole.EXECUTION_PERFORMANCE_ANALYST.value == "v20-execution-performance-analyst"


def test_router_admits_safe_evidence_backed_proposal():
    routed = ProposalRouter().route(proposal(ProposalCapability.RESEARCH))
    assert routed.authority is AuthorityClass.SAFE
    assert routed.status is ProposalStatus.ADMITTED
    assert routed.operator_approval_required is False


@pytest.mark.parametrize(
    "capability",
    [
        ProposalCapability.MODEL_TRAINING,
        ProposalCapability.MODEL_PROMOTION,
        ProposalCapability.RISK_CHANGE,
        ProposalCapability.TRADING_ACTION,
        ProposalCapability.SCHEDULER_CHANGE,
        ProposalCapability.PROTECTED_DATA_WRITE,
    ],
)
def test_router_requires_operator_approval_for_protected_capabilities(capability):
    routed = ProposalRouter().route(proposal(capability))
    assert routed.authority is AuthorityClass.PROTECTED
    assert routed.status is ProposalStatus.APPROVAL_REQUIRED
    assert routed.operator_approval_required is True


def test_router_denies_missing_evidence():
    routed = ProposalRouter().route(proposal(ProposalCapability.CODE_CHANGE, evidence=()))
    assert routed.authority is AuthorityClass.DENIED
    assert routed.status is ProposalStatus.DENIED


def test_non_development_code_proposal_routes_to_development_without_write_authority():
    routed = ProposalRouter().route(proposal(ProposalCapability.CODE_CHANGE))
    assert routed.status is ProposalStatus.ADMITTED
    assert routed.routed_to is AgentRole.DEVELOPMENT
    assert "no write authority" in routed.reasons[0]
