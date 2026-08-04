"""Fail-closed inspection after an unclean V20 stop."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal, Protocol, Self

from pydantic import TypeAdapter, model_validator

from .views import NonEmptyStr, StrictModel, UtcDateTime


class RecoveryCheckId(StrEnum):
    JOURNAL_CHAIN = "journal-chain"
    STATE_VERSION = "state-version"
    ACTIVE_WORK = "active-work"
    MODEL_REFERENCE = "model-reference"
    PORTFOLIO_SOURCE = "portfolio-source"
    BROKER_RECONCILIATION = "broker-reconciliation"


RECOVERY_CHECK_IDS: tuple[RecoveryCheckId, ...] = tuple(RecoveryCheckId)
_UTC = TypeAdapter(UtcDateTime)


class RecoveryCheck(StrictModel):
    check_id: RecoveryCheckId
    state: Literal["passed", "matched", "failed", "unavailable"]
    reason: NonEmptyStr | None

    @model_validator(mode="after")
    def require_truthful_reason(self) -> Self:
        successful = self.state in {"passed", "matched"}
        if successful == (self.reason is not None):
            raise ValueError("failed checks require one reason; successful checks require none")
        if self.check_id is RecoveryCheckId.BROKER_RECONCILIATION:
            if self.state == "passed":
                raise ValueError("broker reconciliation must report matched, failed, or unavailable")
        elif self.state == "matched":
            raise ValueError("only broker reconciliation can report matched")
        return self


class RecoveryReport(StrictModel):
    mode: Literal["normal", "recovery"]
    stop_state: Literal["clean", "unclean", "unknown"]
    inspected_at_utc: UtcDateTime
    checks: dict[RecoveryCheckId, RecoveryCheck]
    broker_actions_enabled: Literal[False] = False
    resume_requires_confirmation: bool

    @model_validator(mode="after")
    def require_exact_checks_and_resume_gate(self) -> Self:
        if set(self.checks) != set(RECOVERY_CHECK_IDS):
            raise ValueError("recovery report must contain every exact check")
        if any(check_id is not check.check_id for check_id, check in self.checks.items()):
            raise ValueError("recovery check key and identity must match")
        all_passed = all(
            check.state in {"passed", "matched"} for check in self.checks.values()
        )
        broker_matched = (
            self.checks[RecoveryCheckId.BROKER_RECONCILIATION].state == "matched"
        )
        expected_resume = self.mode == "recovery" and all_passed and broker_matched
        if self.resume_requires_confirmation is not expected_resume:
            raise ValueError("resume confirmation state does not match recovery checks")
        if self.mode == "normal" and self.stop_state != "clean":
            raise ValueError("only a verified clean stop can report normal mode")
        return self


class RecoveryProbe(Protocol):
    def unclean_stop_detected(self) -> bool: ...

    def run_check(self, check_id: RecoveryCheckId) -> RecoveryCheck: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RecoveryService:
    """Run the complete read-only recovery checklist with no resume effect."""

    def __init__(
        self,
        probe: RecoveryProbe,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not callable(getattr(probe, "unclean_stop_detected", None)) or not callable(
            getattr(probe, "run_check", None)
        ):
            raise TypeError("recovery probe must provide stop state and exact checks")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._probe = probe
        self._clock = clock

    def inspect(self) -> RecoveryReport:
        try:
            unclean = self._probe.unclean_stop_detected()
            if type(unclean) is not bool:
                raise TypeError("stop state must be boolean")
            stop_state: Literal["clean", "unclean", "unknown"] = (
                "unclean" if unclean else "clean"
            )
        except Exception:
            stop_state = "unknown"

        checks = {check_id: self._run_check(check_id) for check_id in RECOVERY_CHECK_IDS}
        all_passed = all(
            check.state in {"passed", "matched"} for check in checks.values()
        )
        broker_matched = (
            checks[RecoveryCheckId.BROKER_RECONCILIATION].state == "matched"
        )
        mode: Literal["normal", "recovery"] = (
            "normal" if stop_state == "clean" and all_passed and broker_matched else "recovery"
        )
        inspected_at = _UTC.validate_python(self._clock(), strict=True)
        return RecoveryReport(
            mode=mode,
            stop_state=stop_state,
            inspected_at_utc=inspected_at,
            checks=checks,
            broker_actions_enabled=False,
            resume_requires_confirmation=(
                mode == "recovery" and all_passed and broker_matched
            ),
        )

    def _run_check(self, check_id: RecoveryCheckId) -> RecoveryCheck:
        try:
            result = self._probe.run_check(check_id)
            if type(result) is not RecoveryCheck:
                raise TypeError("recovery probe returned the wrong type")
            checked = RecoveryCheck.model_validate(result.model_dump(), strict=True)
            if checked.check_id is not check_id:
                raise ValueError("recovery probe returned the wrong check")
            return checked
        except Exception:
            return RecoveryCheck(
                check_id=check_id,
                state="unavailable",
                reason="Check is unavailable.",
            )
