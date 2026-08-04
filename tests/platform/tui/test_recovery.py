from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from vesper.platform.tui.gateway import Gateway
from vesper.platform.tui.recovery import (
    RECOVERY_CHECK_IDS,
    RecoveryCheck,
    RecoveryCheckId,
    RecoveryService,
)


NOW = datetime(2026, 8, 4, 16, 0, tzinfo=timezone.utc)


class _Probe:
    def __init__(
        self,
        *,
        unclean: bool = True,
        states: dict[RecoveryCheckId, str] | None = None,
        stop_failure: bool = False,
    ) -> None:
        self.unclean = unclean
        self.states = states or {}
        self.stop_failure = stop_failure
        self.calls: list[RecoveryCheckId] = []

    def unclean_stop_detected(self) -> bool:
        if self.stop_failure:
            raise RuntimeError("private stop-state failure")
        return self.unclean

    def run_check(self, check_id: RecoveryCheckId) -> RecoveryCheck:
        self.calls.append(check_id)
        state = self.states.get(
            check_id,
            "matched" if check_id is RecoveryCheckId.BROKER_RECONCILIATION else "passed",
        )
        return RecoveryCheck(
            check_id=check_id,
            state=state,
            reason=None if state in {"passed", "matched"} else "Check did not pass.",
        )


def test_unclean_stop_blocks_broker_actions_until_reconciled() -> None:
    probe = _Probe()
    service = RecoveryService(probe, clock=lambda: NOW)

    report = service.inspect()

    assert report.mode == "recovery"
    assert report.broker_actions_enabled is False
    assert set(report.checks) == set(RECOVERY_CHECK_IDS)
    assert report.checks[RecoveryCheckId.BROKER_RECONCILIATION].state == "matched"
    assert report.resume_requires_confirmation is True
    assert probe.calls == list(RECOVERY_CHECK_IDS)


def test_any_failed_check_keeps_resume_unavailable() -> None:
    service = RecoveryService(
        _Probe(states={RecoveryCheckId.MODEL_REFERENCE: "failed"}),
        clock=lambda: NOW,
    )

    report = service.inspect()

    assert report.mode == "recovery"
    assert report.resume_requires_confirmation is False
    assert report.checks[RecoveryCheckId.MODEL_REFERENCE].reason == "Check did not pass."


def test_invalid_or_failed_probe_result_becomes_generic_unavailable() -> None:
    class BadProbe(_Probe):
        def run_check(self, check_id: RecoveryCheckId) -> RecoveryCheck:
            if check_id is RecoveryCheckId.ACTIVE_WORK:
                raise RuntimeError("private active-work details")
            if check_id is RecoveryCheckId.STATE_VERSION:
                return RecoveryCheck(
                    check_id=RecoveryCheckId.JOURNAL_CHAIN,
                    state="passed",
                    reason=None,
                )
            return super().run_check(check_id)

    report = RecoveryService(BadProbe(), clock=lambda: NOW).inspect()

    assert report.checks[RecoveryCheckId.ACTIVE_WORK].state == "unavailable"
    assert report.checks[RecoveryCheckId.STATE_VERSION].state == "unavailable"
    assert "private" not in report.model_dump_json()
    assert report.resume_requires_confirmation is False


def test_unknown_stop_state_fails_into_recovery_without_leaking_error() -> None:
    report = RecoveryService(_Probe(stop_failure=True), clock=lambda: NOW).inspect()

    assert report.stop_state == "unknown"
    assert report.mode == "recovery"
    assert report.broker_actions_enabled is False
    assert "private" not in report.model_dump_json()


def test_clean_stop_reports_normal_but_never_enables_broker() -> None:
    report = RecoveryService(_Probe(unclean=False), clock=lambda: NOW).inspect()

    assert report.mode == "normal"
    assert report.stop_state == "clean"
    assert report.broker_actions_enabled is False
    assert report.resume_requires_confirmation is False


def test_clean_stop_with_failed_integrity_check_still_enters_recovery() -> None:
    report = RecoveryService(
        _Probe(unclean=False, states={RecoveryCheckId.JOURNAL_CHAIN: "failed"}),
        clock=lambda: NOW,
    ).inspect()

    assert report.stop_state == "clean"
    assert report.mode == "recovery"
    assert report.resume_requires_confirmation is False


def test_gateway_exposes_read_only_recovery_report(tmp_path: Path) -> None:
    service = RecoveryService(_Probe(), clock=lambda: NOW)
    gateway = Gateway(tmp_path, recovery_service=service, logon_sid_provider=lambda: "S-1-5-21")

    first = gateway.recovery_report()
    second = gateway.recovery_report()

    assert first.mode == second.mode == "recovery"
    assert first.broker_actions_enabled is second.broker_actions_enabled is False
