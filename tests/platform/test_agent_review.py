from datetime import date, datetime, timedelta, timezone

import pytest

from vesper.platform.agent_queue import AgentWorkQueue
from vesper.platform.cadence import CadencePolicy
from vesper.platform.contracts import AgentRole
from vesper.platform.persistence import PlatformPaths, open_persistence
from vesper.platform.review import DailyReviewService, HybridReviewGate
from vesper.platform.service import LocalPlatformService


NOW = datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc)


def test_queue_is_priority_fifo_deduplicated_and_persistent(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    with open_persistence(paths) as persistence:
        queue = AgentWorkQueue(persistence.store)
        queue.enqueue("normal", AgentRole.MODEL_RESEARCHER, "session", "normal", 10, NOW)
        queue.enqueue("urgent", AgentRole.QUANT_RESEARCH_LEAD, "session", "urgent", 90, NOW)
        queue.enqueue("normal", AgentRole.MODEL_RESEARCHER, "session", "changed", 10, NOW)
        claimed = queue.claim("worker-1", NOW, lease_seconds=60)
        assert claimed.work_id == "urgent"
        assert len(queue.list()) == 2
    with open_persistence(paths) as persistence:
        assert len(AgentWorkQueue(persistence.store).list()) == 2


def test_expired_queue_claim_can_be_reclaimed(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        queue = AgentWorkQueue(persistence.store)
        queue.enqueue("work", AgentRole.PRODUCT, "session", "objective", 10, NOW)
        queue.claim("worker-1", NOW, lease_seconds=1)
        reclaimed = queue.claim("worker-2", NOW + timedelta(seconds=2), lease_seconds=1)
        assert reclaimed.claimed_by == "worker-2"
        assert reclaimed.attempt == 2


def test_service_marks_claimed_work_failed_when_agent_run_raises(tmp_path, monkeypatch):
    paths = PlatformPaths.below(tmp_path / "state")
    service = LocalPlatformService(paths, clock=lambda: NOW)
    enqueued = service.enqueue_agent_work(
        AgentRole.MODEL_RESEARCHER.value,
        "session",
        "inspect synthetic evidence",
        10,
    )

    def fail_run(*_args, **_kwargs):
        raise RuntimeError("invalid model output")

    monkeypatch.setattr(service, "run_agent", fail_run)
    with pytest.raises(RuntimeError, match="invalid model output"):
        service.run_next_agent_work("worker-1", "abc123", {"artifact": {}}, "2026-08-01")

    with open_persistence(paths) as persistence:
        [failed] = AgentWorkQueue(persistence.store).list()
    assert failed.work_id == enqueued["work_id"]
    assert failed.status == "failed"
    assert failed.claimed_by is None
    assert failed.lease_expires_at is None


def test_cadence_is_decision_only_and_digest_is_close_plus_fifteen():
    close = datetime(2026, 8, 3, 20, 0, tzinfo=timezone.utc)

    class Calendar:
        def session_close(self, session_date):
            return close if session_date == date(2026, 8, 3) else None

    policy = CadencePolicy(Calendar())
    assert policy.digest_due(date(2026, 8, 3), close + timedelta(minutes=14)) is False
    assert policy.digest_due(date(2026, 8, 3), close + timedelta(minutes=15)) is True
    assert policy.digest_due(date(2026, 8, 2), close) is False
    assert policy.should_enqueue("market-data-arrived") is True
    assert policy.should_enqueue("timer-tick") is False


def test_daily_digest_has_all_roles_and_gate_requires_acknowledgement(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    with open_persistence(paths) as persistence:
        review = DailyReviewService(persistence.store, paths.root / "daily-review")
        digest = review.render(date(2026, 8, 1), {})
        assert len(digest.sections) == 8
        assert digest.json_path.is_file()
        assert digest.markdown_path.is_file()
        gate = HybridReviewGate(persistence.store)
        gate.bootstrap(date(2026, 8, 1), "operator", NOW)
        assert gate.can_admit(date(2026, 8, 1)) is False
        review.acknowledge(digest, "operator", NOW)
        assert gate.can_admit(date(2026, 8, 1)) is True
        assert gate.can_admit(date(2026, 8, 1), digest_sha256="0" * 64) is False
        assert gate.can_admit(date(2026, 8, 1), digest_sha256=digest.sha256) is True
