"""Pure, read-only routing for TUI message drafts."""

from __future__ import annotations

from typing import Protocol

from vesper.platform.contracts import AgentRole

from .command_contracts import LongText, ScreenName
from .views import (
    CapabilityState,
    CapabilityView,
    ConfidenceFloat,
    NonEmptyStr,
    SafeId,
    StrictModel,
)


SEND_DISABLED_REASON = "No controller-owned agent message port is configured."


class EntityRef(StrictModel):
    entity_type: SafeId
    entity_id: SafeId


class AgentRouteView(StrictModel):
    agent: AgentRole
    reason: NonEmptyStr
    confidence: ConfidenceFloat
    send_capability: CapabilityView


class MessageRoutingPort(Protocol):
    def route(
        self,
        text: str,
        screen: ScreenName,
        selected_entity: EntityRef | None,
    ) -> AgentRouteView: ...


class _RouteInput(StrictModel):
    text: LongText
    screen: ScreenName
    selected_entity: EntityRef | None


_SCREEN_ROUTES: dict[ScreenName, tuple[AgentRole, str]] = {
    "impact": (AgentRole.PRODUCT, "Impact context routes to Product."),
    "portfolio": (
        AgentRole.PORTFOLIO_RESEARCHER,
        "Portfolio context routes to Portfolio Research.",
    ),
    "orders": (
        AgentRole.PRODUCT,
        "Orders context routes to Product unless an audited correction is selected.",
    ),
    "agents": (AgentRole.PRODUCT, "Agent coordination routes to Product."),
    "models-regime": (
        AgentRole.MODEL_RESEARCHER,
        "Model and regime context routes to Model Research.",
    ),
    "timeline": (AgentRole.PRODUCT, "Timeline context routes to Product."),
    "risk-approvals": (
        AgentRole.RISK_REVIEW,
        "Risk and approval context routes to Risk Review.",
    ),
    "data-evidence": (
        AgentRole.QUANT_RESEARCH_LEAD,
        "Data and evidence context routes to Quant Research.",
    ),
    "memory": (AgentRole.PRODUCT, "Memory context routes to Product."),
    "system": (AgentRole.DEVELOPMENT, "System context routes to Development."),
}
_TECHNICAL_ENTITY_TYPES = frozenset({"code", "repository", "service"})
_SEND_CAPABILITY = CapabilityView(
    capability_id="agent.send-message",
    state=CapabilityState.DISABLED,
    reason=SEND_DISABLED_REASON,
)


class StaticMessageRoutingPort:
    """Route from reviewed screen/entity context without sending anything."""

    def route(
        self,
        text: str,
        screen: ScreenName,
        selected_entity: EntityRef | None,
    ) -> AgentRouteView:
        if selected_entity is not None and type(selected_entity) is not EntityRef:
            raise TypeError("selected_entity must be EntityRef or None")
        request = _RouteInput(
            text=text,
            screen=screen,
            selected_entity=selected_entity,
        )
        entity_type = (
            None if request.selected_entity is None else request.selected_entity.entity_type
        )
        if entity_type in _TECHNICAL_ENTITY_TYPES:
            agent = AgentRole.DEVELOPMENT
            reason = "Selected technical context routes to Development."
        elif request.screen == "orders" and entity_type == "audited-order-correction":
            agent = AgentRole.EXECUTION_PERFORMANCE_ANALYST
            reason = "Audited order correction routes to Execution Performance."
        else:
            agent, reason = _SCREEN_ROUTES[request.screen]
        return AgentRouteView(
            agent=agent,
            reason=reason,
            confidence=1.0,
            send_capability=_SEND_CAPABILITY,
        )
