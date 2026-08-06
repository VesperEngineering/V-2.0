"""Vesper 2.0 Operator Dashboard — Tkinter Monitor View.

Dark, flat, functional. Polls engine_state.json every 2s.
Includes live training log panel.
Run: python -m vesper.dashboard.app
"""

import json
import logging
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk

from vesper.dashboard.backtest_evidence import load_backtest_evidence
from vesper.dashboard.model_runs import best_oos_so_far, model_run_rows, promotion_oos_ic

logger = logging.getLogger("vesper.dashboard")

# ── Palette ──────────────────────────────────────────────────
BG = "#1e1e1e"
FG = "#d4d4d4"
SELECT = "#264f78"
ALT_ROW = "#252526"
BTN_BG = "#333333"
HEADER = "#2d2d2d"
GREEN = "#4ec9b0"
RED = "#f44747"
AMBER = "#ce9178"
ORANGE = "#ff8c00"

STATE_FILE = Path("data/engine_state.json")
TRAIN_SCRIPT = Path("scripts/train_model.py")
MODEL_ITERATION_STATE = Path("reports/model_iteration_state.json")
BACKTEST_AUDIT = Path("reports/backtest_accounting_audit.json")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _fmt_currency(v):
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "—"


def _fmt_pct(v):
    return f"{v:+.2f}%" if isinstance(v, (int, float)) else "—"


class DashboardApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("VESPER 2.0")
        self.root.geometry("1400x1000")
        self.root.minsize(1000, 700)
        self.root.configure(bg=BG)

        self._train_queue: queue.Queue[str] = queue.Queue()
        self._train_thread: threading.Thread | None = None
        self._backtest_queue: queue.Queue[str] = queue.Queue()
        self._backtest_thread: threading.Thread | None = None
        self._test_queue: queue.Queue[str] = queue.Queue()
        self._test_thread: threading.Thread | None = None
        self._model_window: tk.Frame | None = None
        self._model_runs_frame: tk.Frame | None = None
        self._backtest_evidence_window: tk.Toplevel | None = None

        self._apply_theme()
        self._build_ui()
        self._poll()
        self._drain_queues()

    # ── Theme ──────────────────────────────────────────────────

    def _apply_theme(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=FG, fieldbackground=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TFrame", background=BG)
        style.configure("TLabelframe", background=BG, foreground=FG)
        style.configure("TButton", background=BTN_BG, foreground=FG, borderwidth=1)
        style.map("TButton", background=[("active", SELECT)])
        style.configure("Treeview", background=BG, foreground=FG, fieldbackground=BG)
        style.map("Treeview", background=[("selected", SELECT)])
        style.configure("Treeview.Heading", background=HEADER, foreground=FG, relief="flat")

    # ── Layout ─────────────────────────────────────────────────

    def _build_ui(self):
        # App bar
        appbar = tk.Frame(self.root, bg=BG, height=40)
        appbar.pack(fill="x", padx=8, pady=(4, 0))
        appbar.pack_propagate(False)

        tk.Label(appbar, text="VESPER 2.0", font=("Segoe UI", 14, "bold"),
                 bg=BG, fg=ORANGE).pack(side="left")

        self.status_lbl = tk.Label(appbar, text="INITIALIZING", font=("Segoe UI", 10),
                                   bg=BG, fg=AMBER)
        self.status_lbl.pack(side="left", padx=(20, 0))

        self.train_btn = tk.Button(
            appbar, text="Train Model", font=("Segoe UI", 9),
            bg=BTN_BG, fg=FG, activebackground=SELECT,
            relief="flat", cursor="hand2", command=self._launch_training
        )
        self.train_btn.pack(side="left", padx=(20, 0))

        self.backtest_btn = tk.Button(
            appbar, text="Run Backtest", font=("Segoe UI", 9),
            bg=BTN_BG, fg=FG, activebackground=SELECT,
            relief="flat", cursor="hand2", command=self._launch_backtest
        )
        self.backtest_btn.pack(side="left", padx=(8, 0))

        self.model_runs_btn = tk.Button(
            appbar, text="Model Runs", font=("Segoe UI", 9),
            bg=BTN_BG, fg=FG, activebackground=SELECT,
            relief="flat", cursor="hand2", command=self._open_model_runs
        )
        self.model_runs_btn.pack(side="left", padx=(8, 0))

        self.backtest_evidence_btn = tk.Button(
            appbar, text="Backtest Evidence", font=("Segoe UI", 9),
            bg=BTN_BG, fg=FG, activebackground=SELECT,
            relief="flat", cursor="hand2", command=self._open_backtest_evidence
        )
        self.backtest_evidence_btn.pack(side="left", padx=(8, 0))

        self.refresh_lbl = tk.Label(appbar, text="—", font=("Segoe UI", 9),
                                    bg=BG, fg=FG)
        self.refresh_lbl.pack(side="right")

        # Main grid
        self._main = tk.Frame(self.root, bg=BG)
        self._main.pack(fill="both", expand=True, padx=8, pady=8)
        self._main.columnconfigure(0, weight=1)
        self._main.columnconfigure(1, weight=1)
        self._main.rowconfigure(1, weight=1)

        # Row 0: Account + Risk
        self.account_card = self._card(self._main, "Account", 0, 0)
        self.risk_card = self._card(self._main, "Risk", 0, 1)

        # Row 1: Positions (span 2 cols)
        pos_frame = tk.LabelFrame(self._main, text="Portfolio", bg=BG, fg=FG,
                                  font=("Segoe UI", 10, "bold"), bd=1)
        pos_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=4, pady=4)
        self.pos_tree = self._tree(pos_frame,
                                   ("Symbol", "Qty", "Entry", "Price", "Value", "P&L", "P&L%"),
                                   width=(80, 80, 100, 100, 120, 120, 80))
        self.pos_tree.pack(fill="both", expand=True, padx=4, pady=4)

        # Row 2: Signals + Orders
        sig_frame = tk.LabelFrame(self._main, text="Recent Signals", bg=BG, fg=FG,
                                  font=("Segoe UI", 10, "bold"), bd=1)
        sig_frame.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        self.sig_tree = self._tree(sig_frame,
                                   ("Time", "Action", "Symbol", "Strength", "Reason"),
                                   width=(120, 60, 80, 60, 300))
        self.sig_tree.pack(fill="both", expand=True, padx=4, pady=4)

        ord_frame = tk.LabelFrame(self._main, text="Recent Orders", bg=BG, fg=FG,
                                  font=("Segoe UI", 10, "bold"), bd=1)
        ord_frame.grid(row=2, column=1, sticky="nsew", padx=4, pady=4)
        self.ord_tree = self._tree(ord_frame,
                                   ("Time", "Symbol", "Side", "Qty", "Price", "Status"),
                                   width=(120, 80, 60, 60, 100, 80))
        self.ord_tree.pack(fill="both", expand=True, padx=4, pady=4)

        # Row 3: Training Log (span 2 cols)
        log_frame = tk.LabelFrame(self._main, text="Training Log", bg=BG, fg=FG,
                                  font=("Segoe UI", 10, "bold"), bd=1)
        log_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=4, pady=4)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.train_log = tk.Text(log_frame, wrap="word", font=("Cascadia Mono", 9),
                                 bg=BG, fg=FG, relief="flat", state="disabled",
                                 highlightthickness=0, padx=4, pady=4)
        self.train_log.grid(row=0, column=0, sticky="nsew")

        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.train_log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.train_log.configure(yscrollcommand=log_scroll.set)

        # Account metrics
        self.acct_grid = self._metric_grid(self.account_card,
                                           ["Equity", "Cash", "Buying Power", "Daily P&L"])

        # Risk metrics
        self.risk_grid = self._metric_grid(self.risk_card,
                                           ["Circuit Breaker", "Exposure", "Drawdown", "Peak Equity"])

    def _card(self, parent, title, row, col):
        frame = tk.LabelFrame(parent, text=title, bg=BG, fg=FG,
                              font=("Segoe UI", 10, "bold"), bd=1)
        frame.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
        return frame

    def _tree(self, parent, cols, width):
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=6)
        for c, w in zip(cols, width):
            tree.heading(c, text=c)
            tree.column(c, width=w, anchor="w")
        tree.tag_configure("green", foreground=GREEN)
        tree.tag_configure("red", foreground=RED)
        tree.tag_configure("amber", foreground=AMBER)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        return tree

    def _metric_grid(self, parent, labels):
        grid = {}
        for i, lbl in enumerate(labels):
            tk.Label(parent, text=lbl + ":", font=("Segoe UI", 10),
                     bg=BG, fg=FG, anchor="w").grid(row=i, column=0, sticky="w", padx=8, pady=4)
            val = tk.Label(parent, text="—", font=("Segoe UI", 10, "bold"),
                           bg=BG, fg=FG, anchor="w")
            val.grid(row=i, column=1, sticky="w", padx=8, pady=4)
            grid[lbl] = val
        return grid

    # ── Training ───────────────────────────────────────────────

    def _launch_training(self):
        if self._train_thread is not None and self._train_thread.is_alive():
            self._log_line("Training already running. Please wait.")
            return

        if not TRAIN_SCRIPT.exists():
            self._log_line(f"ERROR: Training script not found: {TRAIN_SCRIPT}")
            return

        self._log_line("=" * 50)
        self._log_line(f"Launching training: {TRAIN_SCRIPT}")
        self.train_btn.config(state="disabled", text="Training...")

        self._train_thread = threading.Thread(
            target=self._read_training_output, daemon=True
        )
        self._train_thread.start()

    def _read_training_output(self):
        try:
            proc = subprocess.Popen(
                [sys.executable, str(TRAIN_SCRIPT)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            if proc.stdout is None:
                self._train_queue.put("ERROR: Could not open training stdout\n")
                return

            for line in proc.stdout:
                self._train_queue.put(line)

            proc.wait()
            self._train_queue.put(f"\nTraining finished (exit code {proc.returncode})\n")
        except Exception as e:
            self._train_queue.put(f"\nTraining error: {e}\n")
        finally:
            self._train_queue.put("__TRAIN_DONE__")

    def _launch_backtest(self):
        if self._backtest_thread is not None and self._backtest_thread.is_alive():
            self._log_line("Backtest already running. Please wait.")
            return

        backtest_script = Path("scripts/run_backtest.py")
        if not backtest_script.exists():
            self._log_line(f"ERROR: Backtest script not found: {backtest_script}")
            return

        self._log_line("=" * 50)
        self._log_line(f"Launching backtest: {backtest_script}")
        self.backtest_btn.config(state="disabled", text="Backtesting...")

        self._backtest_thread = threading.Thread(
            target=self._read_backtest_output, daemon=True
        )
        self._backtest_thread.start()

    def _read_backtest_output(self):
        try:
            proc = subprocess.Popen(
                [sys.executable, "scripts/run_backtest.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            if proc.stdout is None:
                self._backtest_queue.put("ERROR: Could not open backtest stdout\n")
                return

            for line in proc.stdout:
                self._backtest_queue.put(line)

            proc.wait()
            self._backtest_queue.put(f"\nBacktest finished (exit code {proc.returncode})\n")
        except Exception as e:
            self._backtest_queue.put(f"\nBacktest error: {e}\n")
        finally:
            self._backtest_queue.put("__BACKTEST_DONE__")

    def _drain_queues(self):
        # Drain training queue
        while True:
            try:
                line = self._train_queue.get_nowait()
                if line == "__TRAIN_DONE__":
                    self.train_btn.config(state="normal", text="Train Model")
                else:
                    self._log_line(line.rstrip())
            except queue.Empty:
                break

        # Drain backtest queue
        while True:
            try:
                line = self._backtest_queue.get_nowait()
                if line == "__BACKTEST_DONE__":
                    self.backtest_btn.config(state="normal", text="Run Backtest")
                else:
                    self._log_line(line.rstrip())
            except queue.Empty:
                break

        # Drain test queue
        while True:
            try:
                line = self._test_queue.get_nowait()
                if line == "__TEST_DONE__":
                    if self._model_window and self._model_window.winfo_exists():
                        self.test_btn.config(state="normal", text="Run Tests")
                else:
                    self._append_test_output(line)
            except queue.Empty:
                break

        self.root.after(200, self._drain_queues)

    def _open_model_runs(self):
        if self._model_window:
            return
        self._main.pack_forget()

        window = tk.Frame(self.root, bg=BG)
        window.pack(fill="both", expand=True, padx=8, pady=8)
        self._model_runs_frame = window
        self._model_window = window

        header = tk.Frame(window, bg=BG)
        header.pack(fill="x", padx=8, pady=(8, 2))
        tk.Label(header, text="Model Iteration Evidence", font=("Segoe UI", 13, "bold"),
                 bg=BG, fg=ORANGE).pack(side="left")
        tk.Button(header, text="← Dashboard", font=("Segoe UI", 9),
                  bg=BTN_BG, fg=FG, activebackground=SELECT,
                  relief="flat", cursor="hand2", command=self._close_model_runs).pack(side="right")
        self.test_btn = tk.Button(header, text="Run Tests", font=("Segoe UI", 9),
                                  bg=BTN_BG, fg=FG, activebackground=SELECT,
                                  relief="flat", cursor="hand2", command=self._launch_test_suite)
        self.test_btn.pack(side="right", padx=(0, 8))

        plot_frame = tk.LabelFrame(window, text="OOS IC by Run — blue best-so-far; dots are individual candidates",
                                   bg=BG, fg=FG, font=("Segoe UI", 10, "bold"), bd=1)
        plot_frame.pack(fill="x", padx=8, pady=4)
        self.model_plot = tk.Canvas(plot_frame, height=220, bg=BG, highlightthickness=0)
        self.model_plot.pack(fill="both", expand=True, padx=6, pady=6)
        self.model_plot.bind("<Configure>", lambda _event: self._refresh_model_runs())

        table_frame = tk.LabelFrame(window, text="Run Metrics", bg=BG, fg=FG,
                                    font=("Segoe UI", 10, "bold"), bd=1)
        table_frame.pack(fill="both", expand=True, padx=8, pady=4)
        self.model_tree = self._tree(table_frame, ("Run", "Status", "OOS IC", "Rank IC", "Spread"),
                                      width=(60, 100, 120, 120, 120))
        self.model_tree.pack(fill="both", expand=True, padx=4, pady=4)

        terminal_frame = tk.LabelFrame(window, text="Test Terminal", bg=BG, fg=FG,
                                       font=("Segoe UI", 10, "bold"), bd=1)
        terminal_frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.test_terminal = tk.Text(terminal_frame, height=10, wrap="word", font=("Cascadia Mono", 9),
                                     bg=BG, fg=FG, relief="flat", state="disabled", highlightthickness=0)
        self.test_terminal.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        scrollbar = ttk.Scrollbar(terminal_frame, orient="vertical", command=self.test_terminal.yview)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=4)
        self.test_terminal.configure(yscrollcommand=scrollbar.set)
        self._refresh_model_runs()

    def _close_model_runs(self):
        if self._model_window:
            self._model_window.destroy()
        self._model_window = None
        self._model_runs_frame = None
        self._main.pack(fill="both", expand=True, padx=8, pady=8)

    def _open_backtest_evidence(self):
        if self._backtest_evidence_window and self._backtest_evidence_window.winfo_exists():
            self._backtest_evidence_window.lift()
            return

        window = tk.Toplevel(self.root)
        window.title("VESPER 2.0 — Latest Backtest Evidence")
        window.geometry("760x420")
        window.minsize(640, 340)
        window.configure(bg=BG)
        window.protocol("WM_DELETE_WINDOW", self._close_backtest_evidence)
        self._backtest_evidence_window = window

        tk.Label(window, text="Latest Backtest Evidence", font=("Segoe UI", 13, "bold"),
                 bg=BG, fg=ORANGE).pack(anchor="w", padx=12, pady=(12, 4))
        self.backtest_evidence_text = tk.Text(window, wrap="word", font=("Cascadia Mono", 10),
                                              bg=BG, fg=FG, relief="flat", state="disabled",
                                              highlightthickness=0, padx=12, pady=8)
        self.backtest_evidence_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._refresh_backtest_evidence()

    def _close_backtest_evidence(self):
        if self._backtest_evidence_window:
            self._backtest_evidence_window.destroy()
        self._backtest_evidence_window = None

    def _refresh_backtest_evidence(self):
        if not self._backtest_evidence_window or not self._backtest_evidence_window.winfo_exists():
            return
        evidence = load_backtest_evidence(BACKTEST_AUDIT)
        if evidence["status"] == "EVIDENCE UNAVAILABLE":
            text = "EVIDENCE UNAVAILABLE\n\nSource: reports/backtest_accounting_audit.json"
        else:
            text = (
                f"Status: {evidence['status']}\n"
                f"Window: {evidence['window']}\n"
                f"Final return: {evidence['return']:+.2%}\n"
                f"Paper fills: {evidence['fills']}\n"
                f"Stale snapshot approvals: {evidence['stale_snapshot_approvals']}\n\n"
                f"Method: {evidence['method']}\n\n"
                "Scope: backtest evidence only; not promotion or execution readiness.\n"
                "Source: reports/backtest_accounting_audit.json"
            )
        self.backtest_evidence_text.configure(state="normal")
        self.backtest_evidence_text.delete("1.0", "end")
        self.backtest_evidence_text.insert("1.0", text)
        self.backtest_evidence_text.configure(state="disabled")

    def _read_model_runs(self) -> dict:
        if not MODEL_ITERATION_STATE.exists():
            return {}
        try:
            return json.loads(MODEL_ITERATION_STATE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read model runs: %s", exc)
            return {}

    def _refresh_model_runs(self):
        if not self._model_window or not self._model_window.winfo_exists():
            return
        state = self._read_model_runs()
        rows = model_run_rows(state)
        self.model_tree.delete(*self.model_tree.get_children())
        for row in rows:
            status = row["status"]
            tag = "green" if status in ("BASELINE", "ACCEPTED") else "red"
            self.model_tree.insert("", "end", values=(
                row["run"], status,
                "—" if row["oos_ic"] is None else f"{row['oos_ic']:.6f}",
                "—" if row["rank_ic"] is None else f"{row['rank_ic']:.6f}",
                "—" if row["spread"] is None else f"{row['spread']:.6f}",
            ), tags=(tag,))
        self._draw_model_plot(rows, promotion_oos_ic(state))

    def _draw_model_plot(self, rows: list[dict], promotion_gate: float | None):
        self.model_plot.delete("all")
        values = [row["oos_ic"] for row in rows if row["oos_ic"] is not None]
        if promotion_gate is not None:
            values.append(promotion_gate)
        if not values:
            self.model_plot.create_text(20, 20, text="No model-run evidence found", anchor="nw", fill=AMBER)
            return
        width = max(self.model_plot.winfo_width(), 500)
        height = max(self.model_plot.winfo_height(), 220)
        left, right, top, bottom = 50, 20, 20, 30
        lo, hi = min(values), max(values)
        margin = max((hi - lo) * 0.2, 0.001)
        lo, hi = lo - margin, hi + margin
        max_run = max(row["run"] for row in rows)
        x = lambda run: left + (width - left - right) * run / max(max_run, 1)
        y = lambda value: top + (hi - value) * (height - top - bottom) / (hi - lo)
        baseline = rows[0]["oos_ic"]
        self.model_plot.create_line(left, y(baseline), width - right, y(baseline), fill=AMBER, dash=(4, 3))
        self.model_plot.create_text(left, y(baseline) - 8, text=f"baseline {baseline:.4f}", anchor="w", fill=AMBER)
        if promotion_gate is not None:
            self.model_plot.create_line(left, y(promotion_gate), width - right, y(promotion_gate), fill=GREEN, dash=(2, 2))
            self.model_plot.create_text(left, y(promotion_gate) - 8, text=f"promotion gate {promotion_gate:.4f}", anchor="w", fill=GREEN)
        leaders = best_oos_so_far(rows)
        points = []
        for i, leader in enumerate(leaders):
            if leader is None:
                continue
            px = x(rows[i]["run"])
            if points:
                points.extend((px, points[-1], px, y(leader)))
            else:
                points.extend((px, y(leader)))
        if len(points) >= 4:
            best_leader = next(value for value in reversed(leaders) if value is not None)
            self.model_plot.create_line(*points, fill="#569cd6", width=3)
            self.model_plot.create_text(width - right, y(best_leader) - 8, text="best observed", anchor="e", fill="#569cd6")
        for row in rows:
            if row["oos_ic"] is None:
                continue
            color = GREEN if row["status"] in ("BASELINE", "ACCEPTED") else RED
            px, py = x(row["run"]), y(row["oos_ic"])
            self.model_plot.create_oval(px - 4, py - 4, px + 4, py + 4, fill=color, outline="")
            self.model_plot.create_text(px, height - 14, text=str(row["run"]), fill=FG)

    def _launch_test_suite(self):
        if self._test_thread is not None and self._test_thread.is_alive():
            return
        self.test_btn.config(state="disabled", text="Tests Running...")
        self._append_test_output("$ python -m pytest tests -q")
        self._test_thread = threading.Thread(target=self._read_test_output, daemon=True)
        self._test_thread.start()

    def _read_test_output(self):
        try:
            proc = subprocess.Popen([sys.executable, "-m", "pytest", "tests", "-q"], cwd=PROJECT_ROOT,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            if proc.stdout:
                for line in proc.stdout:
                    self._test_queue.put(line)
            proc.wait()
            self._test_queue.put(f"Tests finished (exit code {proc.returncode})\n")
        except OSError as exc:
            self._test_queue.put(f"Test launch error: {exc}\n")
        finally:
            self._test_queue.put("__TEST_DONE__")

    def _append_test_output(self, text: str):
        if not self._model_window or not self._model_window.winfo_exists():
            return
        self.test_terminal.configure(state="normal")
        self.test_terminal.insert("end", text.rstrip() + "\n")
        self.test_terminal.see("end")
        self.test_terminal.configure(state="disabled")

    def _log_line(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.train_log.configure(state="normal")
        self.train_log.insert("end", f"[{ts}] {text}\n")
        self.train_log.see("end")
        self.train_log.configure(state="disabled")

    # ── Data ───────────────────────────────────────────────────

    def _read_state(self) -> dict:
        if not STATE_FILE.exists():
            return {}
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception as e:
            logger.warning("Failed to read state: %s", e)
            return {}

    # ── Render ─────────────────────────────────────────────────

    def _update(self, state: dict):
        ts = state.get("ts", "—")
        self.refresh_lbl.config(text=f"Last update: {ts}")

        # Status
        breaker = state.get("breaker_tripped", False)
        if breaker:
            self.status_lbl.config(text="CIRCUIT BREAKER", fg=RED)
        else:
            self.status_lbl.config(text="ACTIVE", fg=GREEN)

        # Account
        positions = state.get("positions", {})
        equity = state.get("starting_equity", 0) + state.get("daily_pnl", 0)
        self.acct_grid["Equity"].config(text=_fmt_currency(equity))
        self.acct_grid["Cash"].config(text="—")
        self.acct_grid["Buying Power"].config(text="—")
        pnl = state.get("daily_pnl", 0)
        self.acct_grid["Daily P&L"].config(text=_fmt_currency(pnl),
                                           fg=GREEN if pnl >= 0 else RED)

        # Risk
        self.risk_grid["Circuit Breaker"].config(
            text="TRIPPED" if breaker else "OK",
            fg=RED if breaker else GREEN)
        self.risk_grid["Exposure"].config(text="—")
        self.risk_grid["Drawdown"].config(text="—")
        self.risk_grid["Peak Equity"].config(text=_fmt_currency(state.get("peak_equity", 0)))

        # Positions
        for item in self.pos_tree.get_children():
            self.pos_tree.delete(item)
        for sym, p in positions.items():
            qty = p.get("qty", 0)
            entry = p.get("entry", 0)
            price = p.get("price", 0)
            mv = abs(qty) * price
            pnl = (price - entry) * qty
            pnl_pct = (pnl / (entry * abs(qty)) * 100) if entry and qty else 0
            tag = "green" if pnl >= 0 else "red"
            self.pos_tree.insert("", "end", values=(
                sym, qty, _fmt_currency(entry), _fmt_currency(price),
                _fmt_currency(mv), _fmt_currency(pnl), _fmt_pct(pnl_pct)),
                tags=(tag,))

        # Signals & Orders
        for item in self.sig_tree.get_children():
            self.sig_tree.delete(item)
        for item in self.ord_tree.get_children():
            self.ord_tree.delete(item)

    # ── Polling ────────────────────────────────────────────────

    def _poll(self):
        state = self._read_state()
        self._update(state)
        self._refresh_model_runs()
        self._refresh_backtest_evidence()
        self.root.after(2000, self._poll)

    def close(self):
        if self._model_window and self._model_window.winfo_exists():
            self._model_window.destroy()
        self.root.destroy()


def main():
    logging.basicConfig(level=logging.INFO)
    root = tk.Tk()
    app = DashboardApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
