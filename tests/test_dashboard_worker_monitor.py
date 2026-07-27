import threading
import time

from vesper.dashboard.app import DashboardApp
from vesper.dashboard.worker_monitor import (
    WORKERS,
    redact_worker_output,
    state_style,
    status_marker,
    worker_rows,
)


def _snapshot():
    return {
        "workers": [],
        "activity": [],
        "selected_task_id": None,
        "output": "No emitted worker output is available.",
        "observed_at": "09:45:00",
    }


def test_worker_rows_show_one_current_state_per_known_worker():
    now = time.time()
    tasks = [
        {
            "id": "old",
            "title": "Old review",
            "assignee": "v20-quant-research",
            "status": "done",
            "created_at": now - 300,
            "started_at": now - 240,
            "completed_at": now - 180,
        },
        {
            "id": "active",
            "title": "Design next experiment",
            "assignee": "v20-quant-research",
            "status": "running",
            "created_at": now - 90,
            "started_at": now - 60,
            "heartbeat_at": now - 5,
            "completed_at": None,
        },
    ]

    rows = worker_rows(tasks, now=now)
    quant = next(row for row in rows if row["profile"] == "v20-quant-research")
    data = next(row for row in rows if row["profile"] == "v20-data-engineer")

    assert quant["state"] == "RUNNING"
    assert quant["task_id"] == "active"
    assert quant["elapsed"] == "1m"
    assert data["state"] == "IDLE"
    assert data["task_id"] is None
    assert [row["label"] for row in rows] == [
        "Product",
        "Data Engineer",
        "Quant Research",
        "ML Systems",
        "Portfolio Research",
        "Risk Review",
        "Development",
    ]


def test_redact_worker_output_removes_credentials_and_bounds_lines():
    text = "\n".join([f"line {i}" for i in range(405)])
    text += "\nAuthorization: Bearer secret-token\napi_key=abc123\nsk-live-secret"

    rendered = redact_worker_output(text, max_lines=400)

    assert "secret-token" not in rendered
    assert "abc123" not in rendered
    assert "sk-live-secret" not in rendered
    assert "[REDACTED]" in rendered
    assert "line 0" not in rendered
    assert "line 404" in rendered


def test_status_markers_abbreviate_blocked_ready_complete_and_waiting():
    assert status_marker("BLOCKED") == "B"
    assert status_marker("READY") == "R"
    assert status_marker("COMPLETE") == "C"
    assert status_marker("WAITING") == "W"


def test_running_and_complete_workflow_states_have_distinct_visual_styles():
    running_color, running_label = state_style("RUNNING")
    complete_color, complete_label = state_style("COMPLETE")

    assert running_color != complete_color
    assert running_label == "● running"
    assert complete_label == "C complete"


def test_running_task_without_a_heartbeat_is_not_shown_as_working():
    rows = worker_rows(
        [
            {
                "id": "task-1",
                "assignee": "v20-product",
                "status": "running",
                "started_at": 100,
            }
        ],
        now=200,
    )

    assert rows[0]["state"] == "RUNNING_UNVERIFIED"
    assert state_style(rows[0]["state"])[1] == "○ running · no heartbeat"


def test_dashboard_live_team_button_shows_read_only_monitor_in_main_window(monkeypatch, tk_root):
    monkeypatch.setattr(
        "vesper.dashboard.worker_monitor.load_worker_snapshot", lambda *_args: _snapshot()
    )
    app = DashboardApp(tk_root)
    assert app.live_team_btn.cget("text") == "Live Team"

    app.live_team_btn.invoke()
    tk_root.update_idletasks()

    assert app._worker_monitor is not None
    assert app._worker_monitor.window is app._live_team_frame
    assert app._live_team_frame.winfo_manager() == "pack"
    assert app._main.winfo_manager() == ""
    assert app._worker_monitor._workforce_frame.pack_info()["side"] == "left"
    assert app._worker_monitor._workflow_canvas.winfo_manager() == "pack"
    assert len(app._worker_monitor._workflow_cards) == len(WORKERS)
    app._worker_monitor._return_to_dashboard()
    assert app._worker_monitor is None
    assert app._main.winfo_manager() == "pack"


def test_worker_selection_switches_the_read_only_output_target(monkeypatch, tk_root):
    monkeypatch.setattr(
        "vesper.dashboard.worker_monitor.load_worker_snapshot", lambda *_args: _snapshot()
    )
    app = DashboardApp(tk_root)
    app.live_team_btn.invoke()
    monitor = app._worker_monitor
    monitor._in_flight = True
    snapshot = {
        "workers": [
            {
                "profile": "v20-data-engineer",
                "label": "Data Engineer",
                "state": "COMPLETE",
                "task_id": "data-task",
                "title": "Audit",
                "elapsed": "2m",
            },
            {
                "profile": "v20-quant-research",
                "label": "Quant Research",
                "state": "RUNNING",
                "task_id": "quant-task",
                "title": "Research",
                "elapsed": "1m",
            },
        ],
        "activity": [],
        "selected_task_id": "quant-task",
        "output": "quant output",
        "observed_at": "09:45:00",
    }
    monitor._render(snapshot)

    monitor._select_worker("v20-data-engineer")
    monitor._render(snapshot)

    assert monitor._selected_task_id == "data-task"
    monitor.close()


def test_close_cancels_and_joins_an_in_flight_snapshot_loader(monkeypatch, tk_root):
    started = threading.Event()

    def blocking_snapshot(_selected_task_id, cancelled):
        started.set()
        assert cancelled.wait(1)
        return _snapshot()

    monkeypatch.setattr("vesper.dashboard.worker_monitor.load_worker_snapshot", blocking_snapshot)
    app = DashboardApp(tk_root)
    app.live_team_btn.invoke()
    monitor = app._worker_monitor
    assert started.wait(1)

    monitor.close()

    assert not monitor._load_thread.is_alive()
