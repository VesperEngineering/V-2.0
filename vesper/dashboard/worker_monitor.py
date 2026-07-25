"""Read-only V20 Kanban worker monitor for the Tkinter dashboard."""

import json
import queue
import re
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk


BG = "#1e1e1e"
FG = "#d4d4d4"
MUTED = "#858585"
HEADER = "#2d2d2d"
GREEN = "#4ec9b0"
GREEN_DIM = "#2f7f73"
COMPLETE_GREEN = "#6a9955"
RED = "#f44747"
AMBER = "#ce9178"
ORANGE = "#ff8c00"
BLUE = "#569cd6"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

WORKERS = (
    ("v20-product", "Product"),
    ("v20-data-engineer", "Data Engineer"),
    ("v20-quant-research", "Quant Research"),
    ("v20-ml-systems", "ML Systems"),
    ("v20-portfolio-research", "Portfolio Research"),
    ("v20-risk-review", "Risk Review"),
    ("v20-development", "Development"),
)

_STATE = {
    "running": "RUNNING",
    "ready": "READY",
    "todo": "WAITING",
    "blocked": "BLOCKED",
    "done": "COMPLETE",
}
_PRIORITY = {"running": 5, "ready": 4, "blocked": 3, "todo": 2, "done": 1}
_STATUS_MARKERS = {"BLOCKED": "B", "READY": "R", "COMPLETE": "C", "WAITING": "W"}
HEARTBEAT_FRESH_SECONDS = 90
_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret)\s*[=:]\s*)[^\s]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]+\b"),
)


def _elapsed(seconds):
    seconds = max(int(seconds), 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def status_marker(state):
    return _STATUS_MARKERS.get(state, state)


def state_style(state):
    return {
        "RUNNING": (GREEN, "● running"),
        "READY": (BLUE, "R ready"),
        "WAITING": (ORANGE, "W waiting"),
        "BLOCKED": (RED, "B blocked"),
        "COMPLETE": (COMPLETE_GREEN, "C complete"),
        "RUNNING_UNVERIFIED": (MUTED, "○ running · no heartbeat"),
        "RUNNING_STALE": (RED, "! running · stale heartbeat"),
    }.get(state, (MUTED, "○ idle"))


def worker_rows(tasks, now):
    """Return one truthful current row for each known V20 worker."""
    rows = []
    for profile, label in WORKERS:
        candidates = [task for task in tasks if task.get("assignee") == profile]
        if not candidates:
            rows.append({
                "profile": profile, "label": label, "state": "IDLE",
                "task_id": None, "title": "No assigned task", "elapsed": "—",
            })
            continue
        task = max(
            candidates,
            key=lambda item: (
                _PRIORITY.get(item.get("status"), 0),
                item.get("started_at") or item.get("created_at") or 0,
            ),
        )
        status = task.get("status", "")
        started = task.get("started_at")
        finished = task.get("completed_at")
        elapsed = "—"
        if started:
            elapsed = _elapsed((finished or now) - started)
        state = _STATE.get(status, status.upper() or "IDLE")
        if state == "RUNNING":
            heartbeat = task.get("heartbeat_at")
            if not heartbeat:
                state = "RUNNING_UNVERIFIED"
            elif now - float(heartbeat) > HEARTBEAT_FRESH_SECONDS:
                state = "RUNNING_STALE"
        rows.append({
            "profile": profile,
            "label": label,
            "state": state,
            "task_id": task.get("id"),
            "title": task.get("title") or "Untitled task",
            "elapsed": elapsed,
        })
    return rows


def redact_worker_output(text, max_lines=400):
    """Redact common credential shapes and retain a bounded output tail."""
    rendered = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            rendered = pattern.sub(r"\1[REDACTED]", rendered)
        else:
            rendered = pattern.sub("[REDACTED]", rendered)
    lines = rendered.splitlines()
    if len(lines) > max_lines:
        lines = [f"… {len(lines) - max_lines} earlier lines omitted …", *lines[-max_lines:]]
    return "\n".join(lines)


def _run_kanban(*args, cancelled=None):
    process = subprocess.Popen(
        ["hermes", "kanban", "--board", "v20", *args],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=CREATE_NO_WINDOW,
    )
    deadline = time.monotonic() + 12
    while True:
        try:
            stdout, stderr = process.communicate(timeout=0.1)
            break
        except subprocess.TimeoutExpired:
            if (cancelled is not None and cancelled.is_set()) or time.monotonic() >= deadline:
                process.terminate()
                stdout, stderr = process.communicate()
                if cancelled is not None and cancelled.is_set():
                    raise RuntimeError("Kanban read cancelled")
                raise RuntimeError("Kanban read timed out")
    if process.returncode:
        raise RuntimeError(stderr.strip() or stdout.strip() or "Kanban read failed")
    return stdout


def load_worker_snapshot(selected_task_id=None, cancelled=None):
    """Read the V20 board and one selected emitted worker log."""
    tasks = json.loads(_run_kanban("list", "--json", cancelled=cancelled))
    rows = worker_rows(tasks, time.time())
    task_ids = {task.get("id") for task in tasks}
    if selected_task_id not in task_ids:
        active = next((row for row in rows if row["state"] == "RUNNING"), None)
        selected_task_id = (active or next((row for row in rows if row["task_id"]), {})).get("task_id")
    output = "No emitted worker output is available."
    if selected_task_id:
        output = redact_worker_output(_run_kanban("log", selected_task_id, cancelled=cancelled))
    activity = sorted(
        tasks,
        key=lambda task: task.get("completed_at") or task.get("started_at") or task.get("created_at") or 0,
        reverse=True,
    )[:30]
    return {
        "workers": rows,
        "activity": activity,
        "selected_task_id": selected_task_id,
        "output": output,
        "observed_at": time.strftime("%H:%M:%S"),
    }


class WorkerMonitorWindow:
    """Read-only V20 worker view embedded in the dashboard."""

    def __init__(self, parent, on_close):
        self.window = parent
        self._on_close = on_close

        self._closing = False
        self._in_flight = False
        self._load_cancel = threading.Event()
        self._load_thread = None
        self._selected_task_id = None
        self._result_queue = queue.Queue()
        self._poll_after = None
        self._drain_after = None
        self._pulse_after = None
        self._last_output = None
        self._selected_profile = None
        self._task_ids = {}
        self._build()
        self._request_refresh()
        self._drain_results()
        self._pulse()

    def _build(self):
        header = tk.Frame(self.window, bg=BG, height=54)
        header.pack(fill="x", padx=10, pady=(8, 2))
        header.pack_propagate(False)
        tk.Label(header, text="V20 LIVE TEAM", bg=BG, fg=ORANGE,
                 font=("Segoe UI", 14, "bold")).pack(side="left")
        tk.Label(header, text="READ ONLY · Kanban task status + heartbeat freshness",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(14, 0))
        tk.Button(header, text="← Dashboard", font=("Segoe UI", 9), bg=HEADER, fg=FG,
                  activebackground=HEADER, relief="flat", cursor="hand2",
                  command=self._return_to_dashboard).pack(side="right", padx=(8, 0))
        self._spinner = tk.Label(header, text="", bg=BG, fg=ORANGE,
                                 font=("Cascadia Mono", 12, "bold"))
        self._spinner.pack(side="right")
        self._sync = tk.Label(header, text="Waiting for first snapshot", bg=BG, fg=MUTED,
                              font=("Segoe UI", 9))
        self._sync.pack(side="right", padx=(0, 10))

        body = tk.Frame(self.window, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        self._workforce_frame = tk.LabelFrame(body, text="Workflow — fixed seven-stage pipeline",
                                              bg=BG, fg=FG, font=("Segoe UI", 10, "bold"), bd=1,
                                              width=500)
        self._workforce_frame.pack(side="left", fill="y", padx=(0, 6))
        self._workforce_frame.pack_propagate(False)
        self._workflow_canvas = tk.Canvas(self._workforce_frame, bg=BG, highlightthickness=0,
                                          width=490, height=570)
        self._workflow_canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self._workflow_cards = {}
        for index, (profile, label) in enumerate(WORKERS):
            y = 8 + index * 80
            tags = (profile,)
            if index:
                self._workflow_canvas.create_line(245, y - 8, 245, y - 2, fill=MUTED,
                                                  width=2, arrow="last")
            self._workflow_cards[profile] = {
                "rect": self._workflow_canvas.create_rectangle(
                    8, y, 482, y + 70, fill=HEADER, outline=MUTED, tags=tags),
                "label": self._workflow_canvas.create_text(
                    20, y + 15, text=label, anchor="w", fill=FG,
                    font=("Segoe UI", 10, "bold"), tags=tags),
                "task": self._workflow_canvas.create_text(
                    20, y + 36, text="No assigned task", anchor="w", fill=MUTED,
                    font=("Segoe UI", 9), tags=tags),
                "state": self._workflow_canvas.create_text(
                    470, y + 15, text="○ idle", anchor="e", fill=MUTED,
                    font=("Cascadia Mono", 9, "bold"), tags=tags),
                "age": self._workflow_canvas.create_text(
                    470, y + 36, text="—", anchor="e", fill=MUTED,
                    font=("Cascadia Mono", 9), tags=tags),
            }
            self._workflow_canvas.tag_bind(profile, "<Button-1>",
                                           lambda _event, profile=profile: self._select_worker(profile))

        evidence = tk.Frame(body, bg=BG)
        evidence.pack(side="left", fill="both", expand=True)
        split = ttk.PanedWindow(evidence, orient="vertical")
        split.pack(fill="both", expand=True)

        activity_frame = tk.LabelFrame(split, text="Recent handoffs and task states",
                                       bg=BG, fg=FG, font=("Segoe UI", 10, "bold"), bd=1)
        output_frame = tk.LabelFrame(split, text="Selected worker output",
                                     bg=BG, fg=FG, font=("Segoe UI", 10, "bold"), bd=1)
        split.add(output_frame, weight=3)
        split.add(activity_frame, weight=2)

        self._activity = ttk.Treeview(
            activity_frame,
            columns=("state", "worker", "task"),
            show="headings", height=14,
        )
        for column, text, width in (
            ("state", "State", 90), ("worker", "Worker", 135), ("task", "Task", 330),
        ):
            self._activity.heading(column, text=text)
            self._activity.column(column, width=width, anchor="w")
        activity_scroll = ttk.Scrollbar(activity_frame, orient="vertical", command=self._activity.yview)
        self._activity.configure(yscrollcommand=activity_scroll.set)
        activity_scroll.pack(side="right", fill="y", pady=4, padx=(0, 4))
        self._activity.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)

        self._selected_label = tk.Label(output_frame, text="No task selected", bg=BG, fg=ORANGE,
                                        font=("Cascadia Mono", 9), anchor="w")
        self._selected_label.pack(fill="x", padx=6, pady=(5, 0))
        self._output = tk.Text(output_frame, wrap="word", bg=BG, fg=FG,
                               insertbackground=FG, font=("Cascadia Mono", 9),
                               relief="flat", state="disabled", padx=6, pady=6)
        output_scroll = ttk.Scrollbar(output_frame, orient="vertical", command=self._output.yview)
        self._output.configure(yscrollcommand=output_scroll.set)
        output_scroll.pack(side="right", fill="y", pady=4, padx=(0, 4))
        self._output.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)

    def _request_refresh(self):
        if self._closing:
            return
        if not self._in_flight:
            self._start_load(self._selected_task_id)
        self._poll_after = self.window.after(2000, self._request_refresh)

    def _start_load(self, selected):
        self._in_flight = True
        self._load_cancel.clear()
        self._load_thread = threading.Thread(target=self._load, args=(selected,), daemon=True)
        self._load_thread.start()

    def _load(self, selected):
        try:
            self._result_queue.put(("snapshot", load_worker_snapshot(selected, self._load_cancel)))
        except Exception as exc:
            self._result_queue.put(("error", str(exc)))

    def _drain_results(self):
        if self._closing:
            return
        while True:
            try:
                kind, payload = self._result_queue.get_nowait()
            except queue.Empty:
                break
            self._in_flight = False
            if kind == "snapshot":
                self._render(payload)
            else:
                self._sync.config(text=f"STALE — {payload}", fg=RED)
        self._drain_after = self.window.after(150, self._drain_results)

    def _render(self, snapshot):
        task_by_profile = {}
        for row in snapshot["workers"]:
            state = row["state"]
            color, marker = state_style(state)
            card = self._workflow_cards[row["profile"]]
            title = row["title"]
            if len(title) > 52:
                title = f"{title[:49]}..."
            self._workflow_canvas.itemconfigure(card["rect"], outline=color)
            self._workflow_canvas.itemconfigure(card["task"], text=title, fill=FG if row["task_id"] else MUTED)
            self._workflow_canvas.itemconfigure(card["state"], text=marker, fill=color)
            self._workflow_canvas.itemconfigure(card["age"], text=row["elapsed"], fill=color)
            task_by_profile[row["profile"]] = row["task_id"]
        self._task_ids = task_by_profile
        if self._selected_profile not in task_by_profile:
            self._selected_profile = next((
                profile for profile, task_id in task_by_profile.items()
                if task_id == snapshot["selected_task_id"]
            ), None)
        selected_task_id = task_by_profile.get(self._selected_profile, snapshot["selected_task_id"])
        self._selected_task_id = selected_task_id
        for profile, card in self._workflow_cards.items():
            self._workflow_canvas.itemconfigure(card["rect"], width=3 if profile == self._selected_profile else 1)

        self._activity.delete(*self._activity.get_children())
        labels = dict(WORKERS)
        for task in snapshot["activity"]:
            state = _STATE.get(task.get("status"), (task.get("status") or "").upper())
            self._activity.insert("", "end", values=(
                status_marker(state), labels.get(task.get("assignee"), task.get("assignee") or "—"),
                task.get("title") or "Untitled task",
            ))

        self._selected_label.config(text=self._selected_task_id or "No task selected")
        if selected_task_id != snapshot["selected_task_id"] and selected_task_id and not self._in_flight:
            self._start_load(selected_task_id)
        elif snapshot["output"] != self._last_output:
            at_bottom = self._output.yview()[1] >= 0.99
            position = self._output.yview()[0]
            self._output.configure(state="normal")
            self._output.delete("1.0", "end")
            self._output.insert("1.0", snapshot["output"])
            self._output.configure(state="disabled")
            if at_bottom:
                self._output.see("end")
            else:
                self._output.yview_moveto(position)
            self._last_output = snapshot["output"]
        self._sync.config(text=f"Observed {snapshot['observed_at']}", fg=MUTED)

    def _select_worker(self, profile):
        task_id = self._task_ids.get(profile)
        self._selected_profile = profile
        if task_id != self._selected_task_id:
            self._selected_task_id = task_id
            self._last_output = None
            if not self._in_flight:
                self._start_load(self._selected_task_id)

    def _pulse(self):
        if self._closing:
            return
        self._spinner.config(text="◐" if self._in_flight else "")
        self._pulse_after = self.window.after(500, self._pulse)

    def close(self):
        if self._closing:
            return
        self._closing = True
        self._load_cancel.set()
        if self._load_thread is not None and self._load_thread.is_alive():
            self._load_thread.join(timeout=2)
        for callback in (self._poll_after, self._drain_after, self._pulse_after):
            if callback is not None:
                try:
                    self.window.after_cancel(callback)
                except tk.TclError:
                    pass
        self.window.destroy()

    def _return_to_dashboard(self):
        self.close()
        self._on_close()

