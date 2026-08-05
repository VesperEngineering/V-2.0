"""Independent authority grants for optional V20 operations."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, Self

from pydantic import Field, model_validator

from vesper.platform.tui.views import NonEmptyStr, StrictModel


class ActivationAuthorityError(RuntimeError):
    """The stored grant cannot be proven by the authority receipt store."""


class ActivationCapability(StrEnum):
    RUNTIME_START = "runtime_start"
    CONTINUOUS_WORK = "continuous_work"
    DAILY_MEMORY_CURATION = "daily_memory_curation"
    CANDIDATE_TRAINING = "candidate_training"
    CANDIDATE_DELETION = "candidate_deletion"
    AUTOMATIC_MERGE = "automatic_merge"


class ActivationGrant(StrictModel):
    enabled: bool = False
    receipt_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def require_receipt_iff_enabled(self) -> Self:
        if self.enabled != (self.receipt_id is not None):
            raise ValueError("activation-receipt-invariant")
        return self


class OperationsActivation(StrictModel):
    runtime_start: ActivationGrant = Field(default_factory=ActivationGrant)
    continuous_work: ActivationGrant = Field(default_factory=ActivationGrant)
    daily_memory_curation: ActivationGrant = Field(default_factory=ActivationGrant)
    candidate_training: ActivationGrant = Field(default_factory=ActivationGrant)
    candidate_deletion: ActivationGrant = Field(default_factory=ActivationGrant)
    automatic_merge: ActivationGrant = Field(default_factory=ActivationGrant)


class AuthorityReceiptStore(Protocol):
    def require(self, capability: ActivationCapability, receipt_id: str) -> None: ...


class OperationsActivationStore:
    """Read-only activation snapshot backed by separately validated receipts."""

    def __init__(
        self,
        activation: OperationsActivation,
        authority_receipts: AuthorityReceiptStore,
    ) -> None:
        if type(activation) is not OperationsActivation:
            raise TypeError("activation must be OperationsActivation")
        self._activation = activation
        self._authority_receipts = authority_receipts

    def current(self) -> OperationsActivation:
        return self._activation

    def validated_grant(self, capability: ActivationCapability) -> ActivationGrant:
        if type(capability) is not ActivationCapability:
            raise TypeError("capability must be ActivationCapability")
        grant = getattr(self._activation, capability.value)
        if not grant.enabled:
            return grant
        if grant.receipt_id is None:  # protected again if construction rules change
            raise ActivationAuthorityError("activation receipt is missing")
        try:
            self._authority_receipts.require(capability, grant.receipt_id)
        except ActivationAuthorityError:
            raise
        except Exception as error:
            raise ActivationAuthorityError(
                "activation receipt is unavailable or mismatched"
            ) from error
        return grant
