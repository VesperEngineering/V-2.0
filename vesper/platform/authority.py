"""Deterministic controller authority for agent proposals."""

from __future__ import annotations

from .contracts import (
    AgentProposal,
    AgentRole,
    AuthorityClass,
    ProposalCapability,
    ProposalRoutingDecision,
    ProposalStatus,
)

_SAFE = {
    ProposalCapability.RESEARCH,
    ProposalCapability.DOCUMENTATION,
    ProposalCapability.TEST,
    ProposalCapability.CODE_CHANGE,
}
_PROTECTED = {
    ProposalCapability.MODEL_TRAINING,
    ProposalCapability.MODEL_PROMOTION,
    ProposalCapability.RISK_CHANGE,
    ProposalCapability.TRADING_ACTION,
    ProposalCapability.SCHEDULER_CHANGE,
    ProposalCapability.PROVIDER_CHANGE,
    ProposalCapability.PROTECTED_DATA_WRITE,
    ProposalCapability.DESTRUCTIVE_ACTION,
}


class ProposalRouter:
    """Classify proposals; routing is not execution or approval."""

    def route(self, proposal: AgentProposal) -> ProposalRoutingDecision:
        if not proposal.evidence_ids:
            return self._decision(
                proposal,
                AuthorityClass.DENIED,
                ProposalStatus.DENIED,
                "Evidence is required before a proposal can be routed.",
            )
        if proposal.capability in {
            ProposalCapability.CODE_CHANGE,
            ProposalCapability.DOCUMENTATION,
            ProposalCapability.TEST,
        }:
            return self._decision(
                proposal,
                AuthorityClass.SAFE,
                ProposalStatus.ADMITTED,
                "Proposal is routed to Development; the author receives no write authority.",
                routed_to=AgentRole.DEVELOPMENT,
            )
        if proposal.capability in _SAFE:
            return self._decision(
                proposal,
                AuthorityClass.SAFE,
                ProposalStatus.ADMITTED,
                "Capability is controller-allowlisted and evidence-backed.",
                routed_to=AgentRole.QUANT_RESEARCH_LEAD,
            )
        if proposal.capability in _PROTECTED:
            return self._decision(
                proposal,
                AuthorityClass.PROTECTED,
                ProposalStatus.APPROVAL_REQUIRED,
                "Capability crosses an explicit operator approval boundary.",
            )
        return self._decision(
            proposal,
            AuthorityClass.DENIED,
            ProposalStatus.DENIED,
            "Capability is not controller-allowlisted.",
        )

    @staticmethod
    def _decision(
        proposal: AgentProposal,
        authority: AuthorityClass,
        status: ProposalStatus,
        reason: str,
        routed_to: AgentRole | None = None,
    ) -> ProposalRoutingDecision:
        return ProposalRoutingDecision(
            run_id=proposal.run_id,
            task_id=proposal.task_id,
            repository_revision=proposal.repository_revision,
            created_at=proposal.created_at,
            proposal_id=proposal.proposal_id,
            role=proposal.role,
            authority=authority,
            status=status,
            operator_approval_required=status is ProposalStatus.APPROVAL_REQUIRED,
            routed_to=routed_to,
            reasons=(reason,),
        )
