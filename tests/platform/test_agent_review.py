import threading
import time
from datetime import date, datetime, timedelta, timezone

import pytest

from vesper.platform import service as service_module
from vesper.platform.agent_queue import AgentWorkQueue, WorkQueueEmpty
from vesper.platform.cadence import CadencePolicy
from vesper.platform.contracts import AgentRole, JournalEventType
from vesper.platform.journals import AgentJournal
from vesper.platform.persistence import PlatformPaths, open_persistence
from vesper.platform.review import DailyReviewService, HybridReviewGate
from vesper.platform.service import LocalPlatformService, SpecialistRuntimeUnavailable


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


@pytest.mark.parametrize("operation", ("renew", "complete", "fail"))
def test_stale_same_worker_attempt_cannot_mutate_successor_claim(tmp_path, operation):
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        queue = AgentWorkQueue(persistence.store)
        queue.enqueue("work", AgentRole.PRODUCT, "session", "objective", 10, NOW)
        stale = queue.claim("worker-1", NOW, lease_seconds=1)
        current = queue.claim("worker-1", NOW + timedelta(seconds=2), lease_seconds=60)

        with pytest.raises(WorkQueueEmpty, match="not owned"):
            if operation == "renew":
                queue.renew(
                    "work",
                    "worker-1",
                    stale.attempt,
                    NOW + timedelta(seconds=3),
                    lease_seconds=60,
                )
            else:
                getattr(queue, operation)("work", "worker-1", stale.attempt)

        [unchanged] = queue.list()
        assert unchanged == current


def test_two_persistence_connections_cannot_claim_the_same_work_item(tmp_path, monkeypatch):
    paths = PlatformPaths.below(tmp_path / "state")
    with open_persistence(paths) as first, open_persistence(paths) as second:
        first_queue = AgentWorkQueue(first.store)
        second_queue = AgentWorkQueue(second.store)
        first_queue.enqueue("work", AgentRole.PRODUCT, "session", "objective", 10, NOW)

        original_list = AgentWorkQueue.list
        selections_ready = threading.Barrier(2)

        def synchronized_list(queue):
            items = original_list(queue)
            selections_ready.wait(timeout=5)
            return items

        monkeypatch.setattr(AgentWorkQueue, "list", synchronized_list)

        def claim(queue, worker_id):
            try:
                return queue.claim(worker_id, NOW, lease_seconds=60)
            except WorkQueueEmpty:
                return None

        claims = [None, None]
        errors = []

        def bounded_claim(index, queue, worker_id):
            try:
                claims[index] = claim(queue, worker_id)
            except BaseException as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = (
            threading.Thread(
                target=bounded_claim,
                args=(0, first_queue, "worker-1"),
                daemon=True,
            ),
            threading.Thread(
                target=bounded_claim,
                args=(1, second_queue, "worker-2"),
                daemon=True,
            ),
        )
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert all(not thread.is_alive() for thread in threads)
        assert errors == []

        claimed = tuple(item for item in claims if item is not None)
        assert len(claimed) == 1


def _lease_threads():
    return tuple(
        thread
        for thread in threading.enumerate()
        if thread.name.startswith("v20-agent-work-lease:")
    )


def test_active_blocking_turn_renews_queue_ownership(tmp_path, monkeypatch):
    paths = PlatformPaths.below(tmp_path / "state")
    monkeypatch.setattr(service_module, "_AGENT_WORK_LEASE_SECONDS", 0.2)
    monkeypatch.setattr(service_module, "_AGENT_WORK_HEARTBEAT_SECONDS", 0.02, raising=False)
    monkeypatch.setattr(service_module, "_AGENT_WORK_HEARTBEAT_JOIN_SECONDS", 1.0, raising=False)
    service = LocalPlatformService(paths)
    service.enqueue_agent_work(
        AgentRole.MODEL_RESEARCHER.value,
        "session",
        "inspect synthetic evidence",
        10,
    )
    competitor_claims = []

    def finish_after_blocking_turn(*_args, **_kwargs):
        time.sleep(0.3)
        with open_persistence(paths) as persistence:
            try:
                competitor_claims.append(
                    AgentWorkQueue(persistence.store).claim(
                        "worker-2", datetime.now(timezone.utc), lease_seconds=60
                    )
                )
            except WorkQueueEmpty:
                pass
        return {"status": "completed"}

    monkeypatch.setattr(service, "run_agent", finish_after_blocking_turn)
    try:
        result = service.run_next_agent_work("worker-1", "abc123", {"artifact": {}}, "2026-08-01")
    except WorkQueueEmpty:
        result = None

    assert competitor_claims == []
    assert result is not None
    assert result["work"]["status"] == "completed"
    assert result["work"]["claimed_by"] is None
    assert result["work"]["lease_expires_at"] is None


def test_queue_renew_requires_current_unexpired_owner(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        queue = AgentWorkQueue(persistence.store)
        queue.enqueue("work", AgentRole.PRODUCT, "session", "objective", 10, NOW)
        claimed = queue.claim("worker-1", NOW, lease_seconds=60)

        assert hasattr(queue, "renew"), "queue renewal is missing"
        with pytest.raises(WorkQueueEmpty, match="not owned"):
            queue.renew(
                "work",
                "worker-2",
                claimed.attempt,
                NOW + timedelta(seconds=1),
                lease_seconds=60,
            )

        renewed = queue.renew(
            "work",
            "worker-1",
            claimed.attempt,
            NOW + timedelta(seconds=1),
            lease_seconds=60,
        )
        assert renewed.claimed_by == "worker-1"
        assert renewed.lease_expires_at == NOW + timedelta(seconds=61)

        successor = queue.claim("worker-2", NOW + timedelta(seconds=62), lease_seconds=60)
        with pytest.raises(WorkQueueEmpty, match="not owned"):
            queue.renew(
                "work",
                "worker-1",
                successor.attempt,
                NOW + timedelta(seconds=63),
                lease_seconds=60,
            )


@pytest.mark.parametrize(
    ("agent_fails", "terminal_operation"), ((False, "complete"), (True, "fail"))
)
def test_heartbeat_stops_before_terminal_transition_without_thread_leak(
    tmp_path, monkeypatch, agent_fails, terminal_operation
):
    paths = PlatformPaths.below(tmp_path / "state")
    monkeypatch.setattr(service_module, "_AGENT_WORK_LEASE_SECONDS", 0.2)
    monkeypatch.setattr(service_module, "_AGENT_WORK_HEARTBEAT_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(service_module, "_AGENT_WORK_HEARTBEAT_JOIN_SECONDS", 1.0, raising=False)
    service = LocalPlatformService(paths)
    service.enqueue_agent_work(
        AgentRole.MODEL_RESEARCHER.value,
        "session",
        "inspect synthetic evidence",
        10,
    )

    renew_calls = []
    original_renew = getattr(AgentWorkQueue, "renew", None)

    def track_renew(queue, *args, **kwargs):
        renew_calls.append(threading.current_thread().name)
        if original_renew is None:
            raise AssertionError("queue renewal is missing")
        return original_renew(queue, *args, **kwargs)

    monkeypatch.setattr(AgentWorkQueue, "renew", track_renew, raising=False)
    original_terminal = getattr(AgentWorkQueue, terminal_operation)
    terminal_threads = []

    def track_terminal(queue, *args, **kwargs):
        terminal_threads.append(_lease_threads())
        return original_terminal(queue, *args, **kwargs)

    monkeypatch.setattr(AgentWorkQueue, terminal_operation, track_terminal)

    def bounded_agent_run(*_args, **_kwargs):
        deadline = time.monotonic() + 0.3
        while not renew_calls and time.monotonic() < deadline:
            time.sleep(0.005)
        if agent_fails:
            raise RuntimeError("agent failed")
        return {"status": "completed"}

    monkeypatch.setattr(service, "run_agent", bounded_agent_run)
    if agent_fails:
        with pytest.raises(RuntimeError, match="agent failed"):
            service.run_next_agent_work("worker-1", "abc123", {"artifact": {}}, "2026-08-01")
    else:
        service.run_next_agent_work("worker-1", "abc123", {"artifact": {}}, "2026-08-01")

    assert renew_calls
    assert terminal_threads == [()]
    renewal_count = len(renew_calls)
    time.sleep(0.04)
    assert len(renew_calls) == renewal_count
    assert _lease_threads() == ()


def test_renewal_failure_fails_closed_before_completion(tmp_path, monkeypatch):
    paths = PlatformPaths.below(tmp_path / "state")
    monkeypatch.setattr(service_module, "_AGENT_WORK_LEASE_SECONDS", 0.2)
    monkeypatch.setattr(service_module, "_AGENT_WORK_HEARTBEAT_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(service_module, "_AGENT_WORK_HEARTBEAT_JOIN_SECONDS", 1.0, raising=False)
    service = LocalPlatformService(paths)
    service.enqueue_agent_work(
        AgentRole.MODEL_RESEARCHER.value,
        "session",
        "inspect synthetic evidence",
        10,
    )
    completed = []
    original_complete = AgentWorkQueue.complete

    def reject_renewal(*_args, **_kwargs):
        raise WorkQueueEmpty("simulated renewal failure")

    def track_complete(queue, *args, **kwargs):
        completed.append(True)
        return original_complete(queue, *args, **kwargs)

    monkeypatch.setattr(AgentWorkQueue, "renew", reject_renewal, raising=False)
    monkeypatch.setattr(AgentWorkQueue, "complete", track_complete)
    monkeypatch.setattr(service, "run_agent", lambda *_args, **_kwargs: time.sleep(0.05) or {})

    with pytest.raises(RuntimeError, match="lease renewal failed"):
        service.run_next_agent_work("worker-1", "abc123", {"artifact": {}}, "2026-08-01")

    assert completed == []
    with open_persistence(paths) as persistence:
        [failed] = AgentWorkQueue(persistence.store).list()
    assert failed.status == "failed"
    assert failed.claimed_by is None
    assert failed.lease_expires_at is None
    assert _lease_threads() == ()


def test_agent_error_is_preserved_after_lease_passes_to_successor(tmp_path, monkeypatch):
    paths = PlatformPaths.below(tmp_path / "state")
    monkeypatch.setattr(service_module, "_AGENT_WORK_LEASE_SECONDS", 0.05)
    monkeypatch.setattr(service_module, "_AGENT_WORK_HEARTBEAT_SECONDS", 0.2)
    monkeypatch.setattr(service_module, "_AGENT_WORK_HEARTBEAT_JOIN_SECONDS", 1.0)
    service = LocalPlatformService(paths)
    service.enqueue_agent_work(
        AgentRole.MODEL_RESEARCHER.value,
        "session",
        "inspect synthetic evidence",
        10,
    )

    def fail_after_successor_claims(*_args, **_kwargs):
        time.sleep(0.08)
        with open_persistence(paths) as persistence:
            AgentWorkQueue(persistence.store).claim(
                "worker-2", datetime.now(timezone.utc), lease_seconds=60
            )
        raise RuntimeError("agent failed after lease loss")

    monkeypatch.setattr(service, "run_agent", fail_after_successor_claims)
    with pytest.raises(RuntimeError, match="agent failed after lease loss"):
        service.run_next_agent_work("worker-1", "abc123", {"artifact": {}}, "2026-08-01")

    with open_persistence(paths) as persistence:
        [successor] = AgentWorkQueue(persistence.store).list()
    assert successor.status == "claimed"
    assert successor.claimed_by == "worker-2"
    assert successor.lease_expires_at is not None
    assert _lease_threads() == ()


@pytest.mark.parametrize(
    ("operation", "expected_status"), (("complete", "completed"), ("fail", "failed"))
)
def test_queue_finish_requires_current_owner_and_clears_lease(tmp_path, operation, expected_status):
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        queue = AgentWorkQueue(persistence.store)
        queue.enqueue("work", AgentRole.PRODUCT, "session", "objective", 10, NOW)
        claimed = queue.claim("worker-1", NOW, lease_seconds=60)

        with pytest.raises(WorkQueueEmpty, match="not owned"):
            getattr(queue, operation)("work", "worker-2", claimed.attempt)

        finished = getattr(queue, operation)("work", "worker-1", claimed.attempt)
        assert finished.status == expected_status
        assert finished.claimed_by is None
        assert finished.lease_expires_at is None


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


def test_digest_rejects_sibling_journal_registry_namespace(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    with open_persistence(paths) as persistence:
        persistence.store.put(
            ("agent-journals", "sessions", "injected"),
            "v20-product:injected",
            {"role": AgentRole.PRODUCT.value, "session_id": "injected"},
        )

    with pytest.raises(SpecialistRuntimeUnavailable, match="session discovery"):
        LocalPlatformService(paths).render_agent_digest("2026-08-02")


def test_digest_does_not_hide_events_when_session_registry_is_missing(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    role = AgentRole.MODEL_RESEARCHER
    session_id = "session-hidden"
    with open_persistence(paths) as persistence:
        AgentJournal(persistence.store).append(
            event_id="event-1",
            role=role,
            session_id=session_id,
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            event_type=JournalEventType.OBSERVATION,
            payload={"worker": 1},
        )
        persistence.store.delete(
            ("agent-journals", "sessions"),
            f"{role.value}:{session_id}",
        )

    with pytest.raises(SpecialistRuntimeUnavailable, match="journal integrity failed"):
        LocalPlatformService(paths).render_agent_digest("2026-08-02")
