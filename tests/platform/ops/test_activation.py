from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from vesper.platform.ops.activation import (
    ActivationAuthorityError,
    ActivationCapability,
    ActivationGrant,
    OperationsActivation,
    OperationsActivationStore,
)


class ReceiptAuthority:
    def __init__(self, receipts: dict[ActivationCapability, str]) -> None:
        self.receipts = receipts
        self.calls: list[tuple[ActivationCapability, str]] = []

    def require(self, capability: ActivationCapability, receipt_id: str) -> None:
        self.calls.append((capability, receipt_id))
        if self.receipts.get(capability) != receipt_id:
            raise ActivationAuthorityError("activation receipt is unavailable or mismatched")


@pytest.mark.parametrize("capability", tuple(ActivationCapability))
def test_enabled_activation_requires_an_exact_authority_receipt(capability) -> None:
    with pytest.raises(ValidationError, match="activation-receipt-invariant"):
        ActivationGrant(enabled=True, receipt_id=None)
    with pytest.raises(ValidationError, match="activation-receipt-invariant"):
        ActivationGrant(enabled=False, receipt_id="receipt-1")

    activation = OperationsActivation.model_validate(
        {capability.value: {"enabled": True, "receipt_id": "receipt-1"}},
        strict=True,
    )
    authority = ReceiptAuthority({capability: "receipt-1"})
    store = OperationsActivationStore(activation, authority)

    assert store.validated_grant(capability).enabled is True
    assert authority.calls == [(capability, "receipt-1")]


def test_disabled_grants_are_the_frozen_default_and_need_no_receipt_lookup() -> None:
    authority = ReceiptAuthority({})
    activation = OperationsActivation()
    store = OperationsActivationStore(activation, authority)

    assert all(not store.validated_grant(capability).enabled for capability in ActivationCapability)
    assert authority.calls == []
    with pytest.raises((ValidationError, FrozenInstanceError, AttributeError)):
        activation.continuous_work = ActivationGrant(enabled=True, receipt_id="receipt-1")


def test_mismatched_receipt_fails_closed() -> None:
    capability = ActivationCapability.CONTINUOUS_WORK
    activation = OperationsActivation(
        continuous_work=ActivationGrant(enabled=True, receipt_id="wrong")
    )
    store = OperationsActivationStore(
        activation,
        ReceiptAuthority({capability: "expected"}),
    )

    with pytest.raises(ActivationAuthorityError, match="mismatched"):
        store.validated_grant(capability)
