from datetime import date, datetime, timedelta, timezone

import pytest

from vesper.platform.agent_queue import AgentWorkQueue, WorkQueueConflict
from vesper.platform.cadence import CadencePolicy
from vesper.platform.contracts import AgentRole
from vesper.platform.persistence import PlatformPaths, open_persistence
from vesper.platform.review import DailyReviewService, HybridReviewGate


NOW = datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc)


def test_queue_is_priority_fifo_deduplicated_and_persistent(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    with open_persistence(paths) as persistence:
        queue = AgentWorkQueue(persistence.store)
        queue.enqueue(
            "normal", AgentRole.MODEL_RESEARCHER, "session", "normal", "normal", 10, NOW
        )
        queue.enqueue(
            "urgent",
            AgentRole.QUANT_RESEARCH_LEAD,
            "session",
            "urgent",
            "urgent",
            90,
            NOW,
        )
        queue.enqueue(
            "normal", AgentRole.MODEL_RESEARCHER, "session", "normal", "normal", 10, NOW
        )
        claimed = queue.claim("worker-1", NOW, lease_seconds=60)
        assert claimed.work_id == "urgent"
        assert len(queue.list()) == 2
    with open_persistence(paths) as persistence:
        assert len(AgentWorkQueue(persistence.store).list()) == 2


def test_expired_queue_claim_can_be_reclaimed(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        queue = AgentWorkQueue(persistence.store)
        queue.enqueue(
            "work",
            AgentRole.MODEL_RESEARCHER,
            "session",
            "objective",
            "objective",
            10,
            NOW,
        )
        queue.claim("worker-1", NOW, lease_seconds=1)
        reclaimed = queue.claim("worker-2", NOW + timedelta(seconds=2), lease_seconds=1)
        assert reclaimed.claimed_by == "worker-2"
        assert reclaimed.attempt == 2


def test_legacy_queue_row_without_title_decodes_across_all_operations(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    with open_persistence(paths) as persistence:
        persistence.store.put(
            ("agent-work", "items"),
            "legacy-work",
            {
                "work_id": "legacy-work",
                "role": AgentRole.MODEL_RESEARCHER.value,
                "session_id": "legacy-session",
                "objective": "Legacy objective",
                "priority": 50,
                "created_at": NOW.isoformat(),
                "status": "queued",
                "attempt": 0,
                "claimed_by": None,
                "lease_expires_at": None,
            },
        )
        queue = AgentWorkQueue(persistence.store)

        loaded = queue.get("legacy-work")
        assert loaded is not None
        assert loaded.title == "Legacy objective"
        assert queue.list() == (loaded,)
        claimed = queue.claim("worker-1", NOW, lease_seconds=60)
        assert claimed.title == "Legacy objective"
        completed = queue.complete("legacy-work", "worker-1")
        assert completed.title == "Legacy objective"
        assert queue.enqueue(
            "legacy-work",
            AgentRole.MODEL_RESEARCHER,
            "legacy-session",
            "Legacy objective",
            "Legacy objective",
            50,
            NOW,
        ) == completed
        with pytest.raises(WorkQueueConflict, match="conflicting agent work"):
            queue.enqueue(
                "legacy-work",
                AgentRole.MODEL_RESEARCHER,
                "legacy-session",
                "Changed title",
                "Legacy objective",
                50,
                NOW,
            )


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
