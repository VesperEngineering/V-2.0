"""Fail-closed inspection after an unclean V20 stop."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from threading import Lock
from typing import Literal, Protocol, Self

from pydantic import TypeAdapter, model_validator

from .views import NonEmptyStr, SafeId, Sha256Hex, StrictModel, UtcDateTime


class RecoveryCheckId(StrEnum):
    JOURNAL_CHAIN = "journal-chain"
    STATE_VERSION = "state-version"
    ACTIVE_WORK = "active-work"
    MODEL_REFERENCE = "model-reference"
    PORTFOLIO_SOURCE = "portfolio-source"
    BROKER_RECONCILIATION = "broker-reconciliation"


RECOVERY_CHECK_IDS: tuple[RecoveryCheckId, ...] = tuple(RecoveryCheckId)
_UTC = TypeAdapter(UtcDateTime)
_CONFIRMATION_LIFETIME = timedelta(minutes=5)


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
                raise ValueError(
                    "broker reconciliation must report matched, failed, or unavailable"
                )
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
        all_passed = all(check.state in {"passed", "matched"} for check in self.checks.values())
        broker_matched = self.checks[RecoveryCheckId.BROKER_RECONCILIATION].state == "matched"
        expected_resume = self.mode == "recovery" and all_passed and broker_matched
        if self.resume_requires_confirmation is not expected_resume:
            raise ValueError("resume confirmation state does not match recovery checks")
        if self.mode == "normal" and self.stop_state != "clean":
            raise ValueError("only a verified clean stop can report normal mode")
        return self


class RecoveryConfirmationChallenge(StrictModel):
    challenge_id: SafeId
    report_fingerprint: Sha256Hex
    issued_at_utc: UtcDateTime
    expires_at_utc: UtcDateTime


class RecoveryConfirmation(StrictModel):
    challenge_id: SafeId
    report_fingerprint: Sha256Hex
    confirmed: Literal[True]


class RecoveryAuthorizationDecision(StrictModel):
    authorized: bool
    reason: Literal[
        "authorized",
        "recovery-report-not-eligible",
        "confirmation-required",
        "confirmation-stale",
        "confirmation-report-mismatch",
    ]

    @model_validator(mode="after")
    def require_exact_authorization_state(self) -> Self:
        if self.authorized is not (self.reason == "authorized"):
            raise ValueError("recovery authorization decision is inconsistent")
        return self


class RecoveryProbe(Protocol):
    def unclean_stop_detected(self) -> bool: ...

    def run_check(self, check_id: RecoveryCheckId) -> RecoveryCheck: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _challenge_id() -> str:
    return f"recovery:{secrets.token_hex(16)}"


def _report_fingerprint(report: RecoveryReport) -> str:
    canonical = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _eligible_for_recovery_confirmation(report: RecoveryReport) -> bool:
    return (
        report.mode == "recovery"
        and report.stop_state == "unclean"
        and report.resume_requires_confirmation
        and all(check.state in {"passed", "matched"} for check in report.checks.values())
        and report.checks[RecoveryCheckId.BROKER_RECONCILIATION].state == "matched"
    )


class RecoveryAuthorizationGate:
    """Issue and consume one exact, short-lived recovery confirmation."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = _challenge_id,
    ) -> None:
        if not callable(clock) or not callable(id_factory):
            raise TypeError("recovery authorization dependencies must be callable")
        self._clock = clock
        self._id_factory = id_factory
        self._lock = Lock()
        self._pending: RecoveryConfirmationChallenge | None = None

    def begin_confirmation(
        self,
        report: RecoveryReport,
    ) -> RecoveryConfirmationChallenge | None:
        if type(report) is not RecoveryReport:
            raise TypeError("report must be a RecoveryReport")
        with self._lock:
            self._pending = None
            if not _eligible_for_recovery_confirmation(report):
                return None
            issued_at = _UTC.validate_python(self._clock(), strict=True)
            challenge = RecoveryConfirmationChallenge(
                challenge_id=self._id_factory(),
                report_fingerprint=_report_fingerprint(report),
                issued_at_utc=issued_at,
                expires_at_utc=issued_at + _CONFIRMATION_LIFETIME,
            )
            self._pending = challenge
            return challenge

    def authorize(
        self,
        report: RecoveryReport,
        confirmation: RecoveryConfirmation | None,
    ) -> RecoveryAuthorizationDecision:
        if type(report) is not RecoveryReport:
            raise TypeError("report must be a RecoveryReport")
        with self._lock:
            if not _eligible_for_recovery_confirmation(report):
                self._pending = None
                return self._decision(False, "recovery-report-not-eligible")
            if confirmation is None:
                return self._decision(False, "confirmation-required")
            if type(confirmation) is not RecoveryConfirmation:
                raise TypeError("confirmation must be a RecoveryConfirmation")
            challenge = self._pending
            if challenge is None or confirmation.challenge_id != challenge.challenge_id:
                return self._decision(False, "confirmation-stale")
            now = _UTC.validate_python(self._clock(), strict=True)
            if now < challenge.issued_at_utc or now > challenge.expires_at_utc:
                self._pending = None
                return self._decision(False, "confirmation-stale")
            current_fingerprint = _report_fingerprint(report)
            if (
                current_fingerprint != challenge.report_fingerprint
                or confirmation.report_fingerprint != challenge.report_fingerprint
            ):
                self._pending = None
                return self._decision(False, "confirmation-report-mismatch")
            self._pending = None
            return self._decision(True, "authorized")

    @staticmethod
    def _decision(
        authorized: bool,
        reason: Literal[
            "authorized",
            "recovery-report-not-eligible",
            "confirmation-required",
            "confirmation-stale",
            "confirmation-report-mismatch",
        ],
    ) -> RecoveryAuthorizationDecision:
        return RecoveryAuthorizationDecision(authorized=authorized, reason=reason)


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
            stop_state: Literal["clean", "unclean", "unknown"] = "unclean" if unclean else "clean"
        except Exception:
            stop_state = "unknown"

        checks = {check_id: self._run_check(check_id) for check_id in RECOVERY_CHECK_IDS}
        all_passed = all(check.state in {"passed", "matched"} for check in checks.values())
        broker_matched = checks[RecoveryCheckId.BROKER_RECONCILIATION].state == "matched"
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
            resume_requires_confirmation=(mode == "recovery" and all_passed and broker_matched),
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
