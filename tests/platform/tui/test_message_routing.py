from __future__ import annotations

import pytest
from pydantic import ValidationError

from vesper.platform.contracts import AgentRole
from vesper.platform.tui.views import CapabilityState


DISABLED_SEND_REASON = "No controller-owned agent message port is configured."


def _routing_types():
    from vesper.platform.tui.message_routing import EntityRef, StaticMessageRoutingPort

    return EntityRef, StaticMessageRoutingPort


@pytest.mark.parametrize(
    ("screen", "expected_agent"),
    (
        ("portfolio", AgentRole.PORTFOLIO_RESEARCHER),
        ("models-regime", AgentRole.MODEL_RESEARCHER),
        ("risk-approvals", AgentRole.RISK_REVIEW),
        ("data-evidence", AgentRole.QUANT_RESEARCH_LEAD),
        ("system", AgentRole.DEVELOPMENT),
        ("impact", AgentRole.PRODUCT),
        ("agents", AgentRole.PRODUCT),
        ("timeline", AgentRole.PRODUCT),
        ("memory", AgentRole.PRODUCT),
        ("orders", AgentRole.PRODUCT),
    ),
)
def test_screen_routes_are_exact_and_sending_remains_disabled(
    screen: str,
    expected_agent: AgentRole,
) -> None:
    _, router_type = _routing_types()

    route = router_type().route("Review this context.", screen, None)

    assert route.agent is expected_agent
    assert route.reason.strip() == route.reason
    assert route.reason
    assert route.confidence == 1.0
    assert route.send_capability.capability_id == "agent.send-message"
    assert route.send_capability.state is CapabilityState.DISABLED
    assert route.send_capability.reason == DISABLED_SEND_REASON


def test_only_exact_audited_order_correction_routes_to_execution_analyst() -> None:
    entity_type, router_type = _routing_types()
    router = router_type()

    audited = router.route(
        "Correct the reviewed attribution.",
        "orders",
        entity_type(
            entity_type="audited-order-correction",
            entity_id="correction:1",
        ),
    )
    ordinary = router.route(
        "Correct this order.",
        "orders",
        entity_type(entity_type="order-row", entity_id="order:1"),
    )
    near_match = router.route(
        "Correct this order.",
        "orders",
        entity_type(
            entity_type="audited-order-corrections",
            entity_id="correction:2",
        ),
    )

    assert audited.agent is AgentRole.EXECUTION_PERFORMANCE_ANALYST
    assert ordinary.agent is AgentRole.PRODUCT
    assert near_match.agent is AgentRole.PRODUCT


@pytest.mark.parametrize("entity_kind", ("code", "repository", "service"))
def test_exact_technical_entity_routes_development_on_any_screen(entity_kind: str) -> None:
    entity_type, router_type = _routing_types()

    route = router_type().route(
        "Review the selected item.",
        "portfolio",
        entity_type(entity_type=entity_kind, entity_id="item:1"),
    )

    assert route.agent is AgentRole.DEVELOPMENT


def test_text_never_changes_the_screen_route_or_substitutes_a_role() -> None:
    entity_type, router_type = _routing_types()
    router = router_type()

    code_words = router.route(
        "Please fix the code, repository, and service.",
        "portfolio",
        None,
    )
    unaudited_words = router.route(
        "This is an audited order correction.",
        "orders",
        entity_type(entity_type="order-row", entity_id="order:1"),
    )
    wrong_case = router.route(
        "Review this.",
        "portfolio",
        entity_type(entity_type="Code", entity_id="item:2"),
    )

    assert code_words.agent is AgentRole.PORTFOLIO_RESEARCHER
    assert unaudited_words.agent is AgentRole.PRODUCT
    assert wrong_case.agent is AgentRole.PORTFOLIO_RESEARCHER


@pytest.mark.parametrize(
    ("text", "screen"),
    (
        ("", "portfolio"),
        ("Review this.", "unknown"),
        (1, "portfolio"),
    ),
)
def test_route_rejects_invalid_text_and_screen(text: object, screen: object) -> None:
    _, router_type = _routing_types()

    with pytest.raises(ValidationError):
        router_type().route(text, screen, None)


def test_route_requires_the_strict_selected_entity_model() -> None:
    _, router_type = _routing_types()

    with pytest.raises(TypeError, match="selected_entity must be EntityRef or None"):
        router_type().route(
            "Review this.",
            "orders",
            {"entity_type": "audited-order-correction", "entity_id": "correction:1"},
        )


def test_entity_type_must_be_an_exact_safe_identifier() -> None:
    entity_type, _ = _routing_types()

    with pytest.raises(ValidationError):
        entity_type(entity_type=" code ", entity_id="item:1")
