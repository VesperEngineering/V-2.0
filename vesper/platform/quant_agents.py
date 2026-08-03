"""Typed, proposal-only outputs for the five core quant agents."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import AgentProposal, AgentRole, NonEmptyStr, RunContract


class QuantAgentOutput(RunContract):
    role: AgentRole
    session_id: NonEmptyStr
    summary: NonEmptyStr
    evidence_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    confidence: Annotated[float, Field(ge=0, le=1)]
    limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    proposals: tuple[AgentProposal, ...] = ()

    @model_validator(mode="after")
    def proposal_authority_matches(self) -> QuantAgentOutput:
        for proposal in self.proposals:
            if (
                proposal.role is not self.role
                or proposal.run_id != self.run_id
                or proposal.task_id != self.task_id
                or proposal.repository_revision != self.repository_revision
                or proposal.created_at != self.created_at
            ):
                raise ValueError("agent proposal authority must match its output")
        return self


class QuantResearchLeadOutput(QuantAgentOutput):
    role: Literal[AgentRole.QUANT_RESEARCH_LEAD]
    hypotheses: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    priorities: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]


class ModelResearcherOutput(QuantAgentOutput):
    role: Literal[AgentRole.MODEL_RESEARCHER]
    findings: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]


class IndependentQuantValidatorOutput(QuantAgentOutput):
    role: Literal[AgentRole.INDEPENDENT_QUANT_VALIDATOR]
    challenges: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    verdict: Literal["supported", "not-supported", "inconclusive"]


class PortfolioResearcherOutput(QuantAgentOutput):
    role: Literal[AgentRole.PORTFOLIO_RESEARCHER]
    exposures: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    constraints: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]


class ExecutionPerformanceOutput(QuantAgentOutput):
    role: Literal[AgentRole.EXECUTION_PERFORMANCE_ANALYST]
    diagnostics: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]


OUTPUT_MODELS = {
    AgentRole.QUANT_RESEARCH_LEAD: QuantResearchLeadOutput,
    AgentRole.MODEL_RESEARCHER: ModelResearcherOutput,
    AgentRole.INDEPENDENT_QUANT_VALIDATOR: IndependentQuantValidatorOutput,
    AgentRole.PORTFOLIO_RESEARCHER: PortfolioResearcherOutput,
    AgentRole.EXECUTION_PERFORMANCE_ANALYST: ExecutionPerformanceOutput,
}
