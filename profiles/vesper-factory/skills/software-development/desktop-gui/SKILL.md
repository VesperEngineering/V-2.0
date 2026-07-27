---
name: desktop-gui
description: "Build native desktop GUIs with the toolkit matched to the workload: Tkinter/ttk for dashboards and PySide6/Qt for rich document apps, PDF output, and Windows packaging."
trigger:
  - User asks for a "dashboard", "GUI", "desktop app", "tool", or "visualisation"
  - User asks for a native document reader/editor, Markdown preview, PDF export, or packaged Windows app
  - User says "i want it boring", "not flashy", "no web dashboard", "native windows"
  - Building a monitoring panel for a quant pipeline or cron schedule
---
# desktop-gui

Build functional native desktop GUIs with the toolkit chosen by capability.
Use Tkinter + ttk for compact dashboards, monitoring controls, timers, charts, and log panes; use PySide6/Qt for rich documents, Markdown rendering, native PDF export, and application-grade packaging.
Prioritise clarity and function, then add restrained visual identity when the user wants polish.

For modern Tkinter visual research, use the official CustomTkinter site (<https://customtkinter.tomschimansky.com/>) as a **pattern catalog**: its themes, appearance/scaling guidance, and widgets (buttons, frames, segmented controls, progress bars, scrollable frames/scrollbars, tabs, text boxes, switches, sliders, fonts, and images) map cleanly to native Tk/ttk roles. Treat it as inspiration rather than a migration mandate: preserve the existing project's toolkit and translate only a component's visual hierarchy, interaction, and truth contract.

## When to use

- User asks for a "dashboard", "GUI", "desktop app"
- User says "i want it boring", "not flashy", "no web dashboard"
- Building a monitoring/controls panel for a quant pipeline or cron schedule

## Choose the toolkit by capability

Default to Tkinter + ttk for compact dashboards, monitoring panels, tables, controls, logs, and simple charts. Do **not** force Tkinter onto document-centric applications when that would mean rebuilding standard document behavior.

Use PySide6/Qt when the app needs rich-text or Markdown rendering, source/preview panes, native PDF printing, robust drag-and-drop, document actions, recent files, or persistent window state. Qt's `QTextDocument`, `QTextBrowser`, `QPrinter`, `QAction`, and `QSettings` provide these directly and keep the implementation smaller and more reliable than a custom Tkinter renderer. See `references/pyside6-markdown-editor.md` for the proven architecture and verification matrix.

For a public Windows release, do not stop at a successful source build. Produce a branded portable directory, launch-test the packaged EXE, validate the ZIP and checksum, publish both assets, then download them back from GitHub and verify the public checksum. See `references/windows-release-publishing.md` for the complete release checklist and GitHub Actions version-alias pitfall.

## Dark theme

Use `ttk.Style` with `theme_use("clam")`. Set background `#1e1e1e`, foreground `#d4d4d4`, selection `#264f78`.

**Critical**: ttk widgets use **string** values for `relief`/`anchor`/`justify` (e.g. `"sunken"`, `"w"`), NOT tkinter constants (`tk.SUNKEN`, `tk.W`). Mixing them causes `TclError: expected integer but got "UI"`. `Menu` widgets do **not** support `selectbackground` — only `bg` and `fg` work.

## Canvas bar chart (no clipping)

Always use `winfo_width()`/`winfo_height()` for actual dimensions (returns \\`1\\` if unmapped — provide fallback). Calculate padding:
- `pad_l, pad_r = 24px` — first/last ticker labels
- `pad_t = 22px` — value text above tallest bar
- `pad_b = 24px` — ticker labels below bars

Draw width = `max(cw - pad_l - pad_r, 100)`, draw height = `max(ch - pad_t - pad_b, 40)`.
Bar width = `max((draw_w - gap * (n + 1)) // n, 24)`.
First bar x0 = `pad_l + gap`, last bar ends at `pad_l + gap + n*(bw+gap)`. This guarantees no clipping at either edge.

Floor minimum drawing area to avoid divide-by-zero on narrow canvases.

## Real-time timer / countdown

Use `master.after(ms, callback)`.

### Format showing seconds (HH:MM:SS)

Always show seconds — the user will notice a static countdown that doesn't tick:

```python
def _fmt(td: timedelta) -> str:
    s = int(td.total_seconds())
    neg = "-" if s < 0 else ""
    s = abs(s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{neg}{h:02d}:{m:02d}:{s:02d}"
```

### Fast tick + slow refresh (split pattern)

**Never put file I/O inside the live countdown tick.** File reads (globbing for latest scores, baskets, news files, reading timestamps) are orders of magnitude slower than arithmetic, and a single slow glob causes a visible UI hitch once per tick.

Split into two independent after-loops:

```python
def _tick(self):
    """1-second tick — live countdown + progress bar. No file I/O."""
    now = datetime.now(timezone.utc)
    events = [(self._next_run(j["hour"], j["minute"]), j["name"]) for j in SCHEDULE]
    nxt_dt, nm = min(events, key=lambda x: x[0])
    self._countdown_var.set(f"→ {nm} in {_fmt(nxt_dt - now)}")
    # progress bar across 24h window
    elapsed = (now - (nxt_dt - timedelta(days=1))).total_seconds()
    total = (nxt_dt - (nxt_dt - timedelta(days=1))).total_seconds() or 1
    pct = min(max(int(elapsed / total * 100), 0), 100)
    self._progress["value"] = pct
    self._pct_var.set(f"{pct}%")
    self.master.after(1000, self._tick)

def _refresh_schedule(self):
    """30-second tick — file reads, status dot. Runs independently."""
    for job in SCHEDULE:
        p = self._last_file_for(job["name"])
        ts = _mtime(p)
        self._sched_labels[job["name"]]["next"].set(...)
        self._sched_labels[job["name"]]["last"].set(...)
    self.master.after(30_000, self._refresh_schedule)
```

Call both in `__init__`:

```python
self._tick()
self._refresh_schedule()
```

## Multiple cron job countdowns (per-job rows)

When the user has 5+ cron jobs, show each one as an individual row with its own progress bar:

```
┌─ Cron Schedule — 8 jobs ───────────────────────────────────────────┐
│ ● Factor Scores      2:00   10:31:44  ████████████████████░░░░  85%│
│ ● Factor Basket      2:30   11:01:44  ████████████████████░░░   87%│
│ ● Alpaca Rebalance  14:30   23:01:44  ████████░░░░░░░░░░░░░░░░  41%│
│ ● Portfolio Snap     20:00   04:31:44  ██████░░░░░░░░░░░░░░░░░░  30%│
└───────────────────────────────────────────────────────────────────┘
```

Build rows lazily on the first `_tick` call. Each row stores its widgets in a tuple for fast updates (no file I/O in the 1s tick loop):

```python
SCHEDULE = [
    {"name":"Factor Scores",    "hour":2,  "minute":0,  "days":"daily"},
    {"name":"Factor Basket",    "hour":2,  "minute":30, "days":"daily"},
    {"name":"Alpaca Rebalance", "hour":14, "minute":30, "days":"mon-fri"},
    {"name":"Portfolio Snap",   "hour":20, "minute":0,  "days":"mon-fri"},
]

def _tick(self):
    n = datetime.now(timezone.utc)
    if not self._sjobs:
        for j in SCHEDULE:
            row = ttk.Frame(self._sf); row.pack(fill=tk.X, pady=0)
            dot = tk.Canvas(row, width=10, height=10, highlightthickness=0, bg=BG)
            dot.pack(side=tk.LEFT, padx=(3,0))
            d = dot.create_oval(1,1,9,9, fill=RED, outline="")
            nl = StringVar(value=j["name"])
            nx_l = StringVar(value="—"); cd_l = StringVar(value="—")
            pr = ttk.Progressbar(row, mode="determinate")
            last_l = StringVar(value="—")
            # ... pack all widgets ...
            self._sjobs.append((j["name"], j, dot, d, nl, nx_l, cd_l, pr, last_l))
    # Update each row (arithmetic only — no file I/O)
    for nm, j, dot, d, nl, nx_l, cd_l, pr, last_l in self._sjobs:
        dow = n.weekday(); days = j.get("days", "daily")
        if days == "mon" and dow != 0: active = False
        elif days == "mon-fri" and dow >= 5: active = False
        else: active = True
        nx = n.replace(hour=j["hour"], minute=j["minute"], second=0, microsecond=0)
        if nx <= n or not active: nx += timedelta(days=1)
            # Fast-forward past invalid days
            while True:
                d2 = j.get("days", "daily"); dow2 = nx.weekday()
                if d2 == "mon" and dow2 == 0: break
                if d2 == "mon-fri" and dow2 < 5: break
                if d2 == "daily": break
                nx += timedelta(days=1)
        nx_l.set(nx.strftime("%H:%M"))
        cd_l.set(_fmt(nx - n))
        prev = nx - timedelta(days=1)
        tot = (nx - prev).total_seconds()
        el = (n - prev).total_seconds()
        pr["value"] = min(max(el / tot * 100, 0), 100) if tot else 0
        # Status dot (do file I/O in a 30s separate loop, or inline here)
        dot.itemconfig(d, fill=GREEN if active else "#555")
    self.m.after(1000, self._tick)
```

Key design decisions:
- `"days"` key supports: `"daily"`, `"mon"`, `"mon-fri"` — auto-skips on weekends
- Status dots: green (active), grey (weekend skip)
- No file I/O in the 1s tick — status reads go in a separate 30s loop

**Don't cram all schedule info into one row of long strings.** That clips, feels cramped, and makes the next-run time hard to spot.

Use a three-layer layout inside the LabelFrame:

```
┌─ Schedule ────────────────────────────────────────┐
│ [🟢] → Factor Scores in 1h 23m 17s               │  ← bold green countdown
│ █████████████████████████████████░░░░░  87%       │  ← full-width progress + %
│ Factor Scores    │ Factor Basket      │ News       │  ← 3 equal columns
│  next 02:00 UTC  │  next 02:30 UTC    │  next ...  │
│  last 05:42 UTC  │  last 00:41 UTC    │  last —    │  ← dimmed
└───────────────────────────────────────────────────┘
```

Implementation:

```python
# Row 0: big countdown
row0 = ttk.Frame(cron_frame); row0.pack(fill=tk.X, padx=8, pady=(4,0))
self.dot = tk.Canvas(row0, width=14, height=14, highlightthickness=0, bg=BG)
self.dot.pack(side=tk.LEFT, padx=(0,6))
self.dot.create_oval(1,1,13,13, fill=RED, outline="")
self._countdown_var = StringVar(value="—")
ttk.Label(row0, textvariable=self._countdown_var,
          font=("Segoe UI", 13, "bold"), foreground=GREEN).pack(side=tk.LEFT)

# Row 1: full-width progress bar
row1 = ttk.Frame(cron_frame); row1.pack(fill=tk.X, padx=8, pady=(2,3))
self._progress = ttk.Progressbar(row1, mode="determinate")
self._progress.pack(fill=tk.X, side=tk.LEFT, expand=True)
self._pct_var = StringVar(value="")
ttk.Label(row1, textvariable=self._pct_var, font=("Segoe UI", 8),
          width=5, anchor="e").pack(side=tk.LEFT, padx=(6,0))

# Row 2: 3-column schedule cards
info = ttk.Frame(cron_frame); info.pack(fill=tk.X, padx=8, pady=(0,4))
for i, job in enumerate(SCHEDULE):
    col = ttk.Frame(info)
    col.grid(row=0, column=i, padx=6, sticky="nsew")
    info.columnconfigure(i, weight=1, uniform="cron_col")
    ttk.Label(col, text=job["name"], font=("Segoe UI", 9, "bold")).pack(anchor="w")
    self._sched_labels[job["name"]] = {
        "next": StringVar(value="next —"),
        "last": StringVar(value="last —"),
    }
    ttk.Label(col, textvariable=self._sched_labels[job["name"]]["next"],
              font=("Segoe UI", 8)).pack(anchor="w")
    ttk.Label(col, textvariable=self._sched_labels[job["name"]]["last"],
              font=("Segoe UI", 8), foreground="#888").pack(anchor="w")
    if i < len(SCHEDULE) - 1:
        ttk.Separator(info, orient=tk.VERTICAL).grid(row=0, column=i, rowspan=3,
                                                     sticky="ns", padx=2)
```

## Notebook tabs (dark theme)

When using `ttk.Notebook` with a dark background, default tab styling is invisible. Add this to `_apply_dark()`:

```python
s.configure("TNotebook", background=BG)
s.configure("TNotebook.Tab", background=HEADER, foreground=FG, padding=[12, 4], font=("Segoe UI", 10))
s.map("TNotebook.Tab", background=[("selected", SELECT), ("active", "#3a3a3a")],
      foreground=[("selected", FG), ("active", FG)])
```

Without this, tab labels blend into the background and become unreadable.

## Auto-refresh

Increment a counter inside the timer callback. Every 300 ticks (5 minutes at 1s), call `self.refresh()` to pick up new data from cron.

```python
self._auto_refresh_count += 1
if self._auto_refresh_count >= 300:
    self._auto_refresh_count = 0
    self.refresh()
```

## Loading all ranked tickers

When loading scores from JSON, prefer the `"scored"` key (all entries) over `"top_10"`:
```python
all_items = data.get("scored") or data.get("top_10", [])
```
This shows every ticker that was scored, not just the top slice.

## File modification time helpers

```python
def _mtime(path: Path | None) -> str | None:
    """Return full timestamp: '2026-07-06 06:45 UTC'."""
    if not path or not path.exists(): return None
    ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return ts.strftime("%Y-%m-%d %H:%M UTC")

def _mtime_date(path: Path | None) -> str | None:
    """Return date portion only: '20260706' (exact match for feed filter)."""
    if not path or not path.exists(): return None
    ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return ts.strftime("%Y%m%d")
```

Use `_mtime()` for display, `_mtime_date()` for equality comparison in the data feed. The substring check `today in ts` is fragile because `"20260706"` is not a substring of `"2026-07-06 06:45 UTC"`.

## Subprocess management

`cwd` must be the project root, not the script directory. For scripts in `scripts/`, use `Path(__file__).resolve().parent.parent`.

### Cancellable refresh workers and UI-test isolation

For a polling dashboard that launches a subprocess, retaining only an `in_flight` boolean is insufficient: an already-started daemon thread can survive a closed window while blocked in `subprocess.run()`.

- Store the refresh thread and a `threading.Event` cancellation token.
- Pass the token into the subprocess wrapper; use `Popen` with a bounded `communicate(timeout=...)` polling loop. On cancellation or timeout, terminate the child, collect it, and return a controlled error.
- In `close()`, first mark closing and set the event, then join the tracked worker for a short bound before destroying widgets. Continue canceling `after()` callbacks and ignore late queue results.
- Widget tests must inject or monkeypatch the snapshot loader. Do not let a visual test accidentally call a real CLI, network service, or background job. Add one regression that starts a blocking fake loader, closes the monitor, and asserts that cancellation was observed and the worker is no longer alive.

Auto-refresh on success inside the `_run` helper. Log stdout last 3 lines and stderr last 5 lines on failure.

Disable all toolbar buttons while subprocess runs to prevent double-clicks. Track buttons in `self._buttons` and call `_set_buttons(False)` before, `_set_buttons(True)` after (including in finally/except paths).

## Center-aligning numeric Treeview columns

Numeric columns (score, weight, rank, etc.) should be center-aligned. Ticker columns stay left-aligned:

```python
for c in ("score", "entropy", "hurst", "rvol", "sent", "insider"):
    self.st.column(c, width=70, anchor="center")
self.st.column("ticker", width=65)  # left-aligned by default
```

Apply to ALL trees consistently: scores, basket, performance, history.

## Tkinter memory management (widget-rebuild leak)

Avoid the classic Tkinter memory leak: **destroying and recreating widgets on a refresh loop**. 

This **leaks memory**:
```python
# BAD: destroys and recreates all widgets every refresh
def _refresh_panel(self):
    for w in self.frame.winfo_children():
        w.destroy()
    for item in data:
        card = tk.LabelFrame(self.frame, ...)
        card.pack()
        for row in item.rows:
            lbl = tk.Label(card, ...)
            lbl.pack()
```

Tkinter's internal memory pool does not fully release old widget trees after `destroy()`, so RSS grows steadily. A 100% growth over 150 refresh cycles is easy to hit.

### Fix: Use Treeview for tabular/row data

Treeviews reuse internal cells instead of creating widget trees, so there is no accumulation:

```python
def _build_tab(self, nb):
    f = ttk.Frame(nb)
    cols = ("flag", "pid", "exe", "name", "started")
    tv = ttk.Treeview(f, columns=cols, show="headings", height=12)
    for c, w in (("flag",80), ("pid",60), ...):
        tv.heading(c, text=c.title())
        tv.column(c, width=w, anchor="w")
    tv.pack(fill=tk.BOTH, expand=True)
    self._tv = tv
    # Action button below treeview instead of per-row buttons

def _refresh_panel(self):
    tv = self._tv
    tv.delete(*tv.get_children())       # clears data, no widget leak
    for item in data:
        tv.insert("", tk.END, values=(...), tags=(...))
```

This is the same pattern used in Leaks, Services, and Monitor tabs — consistent and memory-safe. If the tab needs per-row action buttons, put a single "Kill Selected" / "Stop Service" button below the Treeview and act on the selected row.

Use `treeview.selection()` + `treeview.item(sel[0], "values")` to get the selected row's PID or service name, then call the action from the button's command.

### When to keep LabelFrames

If the data is a small, fixed set of cards (e.g. 3-5 schedule rows), a few LabelFrames are fine — the widget count is bounded and doesn't grow with refresh cycles. The leak only appears when the number of recreated widgets scales *proportionally to the data size* on every refresh.

## Self-PID skip for monitoring dashboards

When building a live process monitor/dashboard that uses `psutil` (or similar) to enumerate and track processes, **always skip your own PID**:

```python
import os
self_pid = os.getpid()
for proc in psutil.process_iter():
    if proc.pid == self_pid:
        continue
    # ... detect leaks, memory, etc.
```

Otherwise the tool finds **itself** growing (Python's allocator doesn't return pages to the OS, Tkinter widget trees, scanning history), flags it as a leak, and the user sees +100% growth false positives.

## Treeview selection preservation (live refresh dashboards)

When a dashboard polls data on a timer and calls `tv.delete(*tv.get_children())`
to refresh a Treeview, the user's selection is silently dropped. If the user
clicked a row to act on it (e.g. "Kill Selected", "Stop Service"), the
deselection means the button has nothing to act on.

**Always preserve selection across refresh cycles** by saving the key value
of the selected row before `tv.delete()` and restoring it after repopulating:

```python
def _preserve_selection(self, tv, key_col=0):
    sel = tv.selection()
    if sel:
        vals = tv.item(sel[0], "values")
        if len(vals) > key_col:
            return vals[key_col]
    return None

def _restore_selection(self, tv, key, key_col=0):
    if key is None:
        return
    for child in tv.get_children(""):
        vals = tv.item(child, "values")
        if len(vals) > key_col and vals[key_col] == key:
            tv.selection_set(child)
            tv.focus(child)
            tv.see(child)
            return
```

Usage pattern in each refresh method:

```python
def _refresh_some_tab(self):
    tv = self._some_tv
    sel_key = self._preserve_selection(tv, key_col=1)  # e.g. PID column
    tv.delete(*tv.get_children())
    for item in data:
        tv.insert("", tk.END, values=(...))
    self._restore_selection(tv, sel_key, key_col=1)
```

The key column varies by tab:
- **Leaks / Dupes / Monitor**: PID (column 1 or 0)
- **Services**: service name (column 0)

When using `win32gui.Shell_NotifyIcon` for system tray icons:

- `NIM_ADD`, `NIM_DELETE`, `NIF_ICON`, `NIF_MESSAGE`, `NIF_TIP` live on the **`win32gui`** module, NOT `win32con`.
- `win32con.WM_LBUTTONDBLCLK`, `WM_RBUTTONUP`, and `GWL_WNDPROC` are correct on `win32con`.
- NOTIFYICONDATA signature: `(hwnd, id, flags, callback_msg, hicon, tooltip)` — a plain tuple passed to `Shell_NotifyIcon`.

```python
import win32gui, win32con, win32api

WM_TRAY = win32api.RegisterWindowMessage("memwatch_tray_<unique>")
nid = (hwnd, 0,
       win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
       WM_TRAY, hicon, "tooltip")
win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
# ... later ...
win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
```

The callback window proc receives the `WM_TRAY` message; `lParam` carries the mouse event (`WM_LBUTTONDBLCLK` to restore, `WM_RBUTTONUP` for context menu).

## WMI service enumeration

For enumerating Windows services with PID, state, and start type, use `win32com` WMI (more reliable across pywin32 builds than `win32service.QueryServiceConfig`):

```python
import win32com.client
wmi = win32com.client.GetObject("winmgmts:")
for s in wmi.ExecQuery(
    "SELECT Name, DisplayName, State, ProcessId, StartMode, PathName "
    "FROM Win32_Service"
):
    pid = int(s.ProcessId) if s.ProcessId else None
    start = {"Auto": 2, "Manual": 3, "Disabled": 4}.get(s.StartMode, -1)
```

`win32service.QueryServiceConfig` returns a 9-tuple (not a dict) in some pywin32 builds, with start type at index 1. `SC_STATUS_PROCESS_INFO` may not exist in some builds, making per-service PID unavailable via that path.

## Portfolio bar with Alpaca data

Add an Alpaca portfolio bar between the schedule and the notebook tabs. Show equity, cash, position count, and buying power from the latest receipt JSON:

```python
pf = ttk.LabelFrame(master, text="Portfolio")
pf.pack(fill=tk.X, padx=5)
r = ttk.Frame(pf); r.pack(fill=tk.X, padx=5, pady=2)
ttk.Label(r, textvariable=self._equity, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=10)
ttk.Label(r, textvariable=self._positions, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=10)
ttk.Label(r, text="Alpaca Paper", font=("Segoe UI", 8), foreground="#888").pack(side=tk.RIGHT, padx=10)
```

Load from `_last_receipt()` (glob for `alpaca_receipt_*.json`):

```python
def _load_ap(self):
    rp = _last_receipt()
    if not rp: self.aeq.set("Alpaca: —"); return
    d = json.loads(rp.read_text(encoding="utf-8"))
    self.aeq.set(f"Alpaca: ${d.get('account_equity',0):,.2f}")
    self.apos.set(f"{len(d.get('target_tickers',[]))} positions")
```

## Adding a new column to an existing Treeview

1. Add the column name to the `columns` tuple in `ttk.Treeview(...)` constructor
2. Add `self.tree.heading("newcol", text="NewCol")`
3. Update the `column(width=..., anchor=...)` loop to include the new column
4. Add the value to every `insert(...)` values tuple — missing any one column shifts all subsequent data
5. Update the `_load_scores` (or equivalent) insert tuple to include the new value

## Alpaca button in toolbar

Add a "4. Alpaca" button that runs `scripts/alpaca_rebalance.py`:

```python
def _btn(text, cmd):
    b = ttk.Button(toolbar, text=text, command=cmd)
    b.pack(side=tk.LEFT, padx=2)
    self._buttons.append(b)

_btn("4. Alpaca", self.rebalance_alpaca)
```

## Alpaca notional rounding

Alpaca's REST API requires notional values to have at most 2 decimal places. `round(val, 2)` all notional amounts before submitting market orders. Skip adjustments under $1.00 to avoid noise.

## Data consistency

When user can load historical data (date-jump), all actions must operate on the **loaded** data, not the latest-on-disk:
- Maintain `self._score_data` and `self._score_map`
- In `rerank`, use `self._score_data["date"]` not `_last_scores().stem`
- After re-rank, reload scores from the same file

## Layout

- `ttk.PanedWindow` for resizable panes
- `ttk.LabelFrame` for sections with titles
- `ttk.Notebook` for tabs (Portfolio, Performance, History)
- Progress bar: `fill=tk.X, expand=True` not fixed `length`
- Alternating treeview rows via `tag_configure("odd", ...)`
- Export current tab as TSV to clipboard
- Tip bar showing keyboard shortcuts at bottom of toggle row

## Keyboard shortcuts

Bind on `self.master` so they work from any panel:
- `Ctrl+R` / `Ctrl+R` → refresh
- `Ctrl+1/2/3` → scores / rerank / basket
- `Ctrl+A` → select-all in log

## Close handler

Bind `WM_DELETE_WINDOW` via `master.protocol()` to save state before closing. Always call `master.destroy()` at the end.

## Log rotation

Cap the file log at 1 MB. On each write, check size and rotate to `.log.1`. Simple atomic rename.

## Experiment evidence windows

When an existing dashboard has train/backtest controls and the operator needs to inspect iterative model research, add one dedicated `Toplevel` evidence window rather than overloading the primary activity log. Drive it from a durable research-state JSON and render only documented evidence:

- baseline as run 0 and an amber horizontal reference line;
- accepted/rejected trials as green/red dots with a metrics `Treeview`;
- a **blue best-observed-so-far stair-step line** over chronological runs, distinct from the active model;
- a separate promotion-gate line when the manifest records one; a dot above baseline is not an accepted model unless it clears every declared gate;
- a pending trial as `RUNNING` with missing metrics rendered as `—`, never invented;
- a separate `Text` terminal for test output, not interleaved with training/backtest logs.

Raw dots alone can make marginally improved but rejected experiments look like obvious missed deployment choices. Label the leader line `best observed`, preserve explicit verdicts and all gate-relevant metrics in the table, and make the reason a leader was not selected inspectable without reading raw logs.

Read state only when the evidence window is open. Run tests in a worker thread with `cwd` set to the project root, pass stdout/stderr through a dedicated `queue.Queue`, and append it only from the Tk thread via the existing `after()` drain. Disable the test button while active and restore it on a completion sentinel. Verify with a headless Tk probe that opens the evidence window, populates real rows, launches the test action, and observes its real exit-code line.

## Log pane

`tk.Text` with Ctrl+A / right-click "Select All", Copy button, Clear Log button. Timestamps, `wrap=WORD`, Consolas 9, dark background.

## Flash-close fallback: native Windows research consoles

A direct `.lnk` to `wsl.exe` can give a WSL/curses app no durable interactive terminal host; the window may flash and exit without a useful traceback. Reproduce the exact shortcut path and capture its child lifetime/error output before changing the renderer. If the app is a compact monitoring/control surface, prefer a native Windows **Tkinter + ttk** console:

1. Keep authoritative state in WSL, but retrieve a bounded JSON snapshot through an allowlisted WSL exporter invoked asynchronously from the Tk app. Do not assume `\\wsl$` or `\\wsl.localhost` paths are accessible from the Windows process.
2. Launch the Desktop `.lnk` with the exact `pythonw.exe` beside the resolved `python.exe`, with quoted entrypoint arguments and the project working directory. This removes helper-console flash.
3. Run state reads and any explicit WSL action request on background threads; update widgets only from the Tk main thread.
4. Verify the real `.lnk`, not just imports: inspect its target/arguments, launch it, assert a fresh titled native window appears and responds, then close only the verification process.
5. When illustrating a model before metrics exist, label the diagram explanatory and highlight stages only from durable run state. Never imply model growth, completion, or inference evidence that has not been recorded.

This does not replace a proven full-screen terminal operator surface. It is a robust fallback for small Windows desktop research consoles that must stay open from a clickable launcher.

## Terminal/TUI desktop launchers and live dashboards

For a terminal UI launched from a Windows desktop shortcut, treat the shortcut, entrypoint, controller, and renderer as one contract.

1. **Use the repository-owned installer as the shortcut source of truth.** Do not replace a branded `.lnk` with an ad-hoc batch launcher after a crash. The installer must set the terminal executable, working directory, module invocation, title, and icon together.
2. **Preserve controller/render contracts.** If a layout calls a controller property or method (for example `zoom_level` / `set_zoom`), implement both sides in the same change. Regression-test the render callback using `create_pipe_input()` and `DummyOutput`; this catches missing controller attributes without requiring a real console.
3. **Diagnose flash-close failures from the exact exception.** A brief `FAILED: AttributeError` is a source crash, not proof that the shortcut needs a new shell. Build a tight repro with a fake prompt-toolkit input/output, fix the missing contract, then retest before touching launch mechanics.
4. **Verify shortcuts independently.** Inspect target, arguments, working directory, and icon; launch it once and confirm the terminal process starts. If the visible UI still fails, preserve/capture the traceback before another launcher change.
5. **Version user-visible desktop/TUI changes.** Maintain one module-level semantic release value (for example `VOT_VERSION = "0.0.1"`) and render a human-facing label such as `VOT v0.0.1` in both the native window title and the always-visible status/app bar. Do not make a raw Git SHA the primary operator-facing version; it is developer provenance, not a lookup-friendly release identity. Add a regression test that rejects a non-semver value and fails if either title or status-app-bar wiring is removed. Bump the release value for every coherent behavioral/UI change so the operator has a rollback reference.
6. **Show operational meaning, not decorative motion.** Autonomous dashboards must expose current/last worker action, timestamps or age, active/blocked lane, and recent activity—not just clocks, prices, and status dots.
7. **Honor exact desktop geometry at the native-window layer.** `wt.exe --size columns,rows` means terminal cells, while `--maximized` defeats size requirements entirely. For an exact requested outer pixel rectangle, launch a uniquely titled Windows Terminal window, locate the newly created visible HWND with `EnumWindows`, and set it with `SetWindowPos`. Have the branded `.lnk` invoke `pythonw.exe` plus that launcher to avoid a helper-console flash; explicitly retain `IconLocation`.
8. **Verify the actual desktop path.** Inspect shortcut target/arguments/working directory/icon, launch the `.lnk`, then assert `GetWindowRect` for the titled visible window. A running WindowsTerminal process or a passing source-level command is not proof of the requested opening geometry.
9. **PowerShell installer structure is strict.** `param(...)` must remain the first executable construct; comments may precede it, assignments may not.
10. **Treat scrolling fragments as a screen-painting failure first.** In Windows Terminal pseudoconsole sessions, do not force `PROMPT_TOOLKIT_OUTPUT=ansi` or run `mode con` from inside the TUI; those can turn full-screen redraws into scrollback fragments. Let Windows Terminal own dimensions and Prompt Toolkit select its native output backend. Keep exact pixel sizing in the uniquely titled launcher window layer, not in the dashboard process.
11. **Verify the real desktop path end to end.** Run the targeted controller/layout/shortcut tests with a repository-local `--basetemp` when the default Windows pytest temp root has access-control problems, then launch the actual `.lnk`, confirm the titled HWND remains visible at the expected dimensions, and close only that test window. A source-level pass is not sufficient for a desktop rendering fix.

See `references/windows-terminal-fixed-size-launcher.md` for the repeatable fixed-pixel launcher and verification contract. See `references/windows-terminal-redraws.md` for the scrolling-fragment diagnosis and verification recipe. See `references/vesper-tui-live-activity.md` for structured worker events, fixed-width activity rendering, semantic Prompt Toolkit colors, redacted runtime logs, and verification probes. See `references/tkinter-node-connector-progress.md` for a Canvas-based node-and-connector training-progression diagram with status-driven coloring and an inference-path companion.

## Hermes Kanban worker monitors (read-only operator window)

For a simple native worker monitor, use **Tkinter + ttk** and drive it only from the Hermes Kanban CLI's read-only surfaces. This keeps the monitor accurate without giving a visibility tool authority to change tasks.

### Data contract

1. Fetch the task inventory with `hermes kanban --board <board> list --json`.
2. Render task `status`, `assignee`, `title`, and task ID in a `Treeview`; default-select a `running` task.
3. Treat the task card `body` as **INPUT** and render it separately from output.
4. For an investigative/operator monitor, fetch the full emitted worker flow with `hermes kanban --board <board> log <task_id>` (no `--tail`) and label it **OUTPUT — full worker log**. Use `--tail` only when the user explicitly asks for bounded output.
5. Poll asynchronously (for example, every 2 seconds) with a background thread and return data through a queue to the Tk main thread. Never call subprocesses directly from Tk callbacks.
6. Preserve visual continuity: cache logs by task ID, keep the last successful board summary and complete worker log visible while a refresh runs, and render only if fetched content changed. Do not replace populated panes with transient `Refreshing…`/`Loading…` messages. Preserve the reader's scroll position; follow new output only when they are already at the bottom.
7. Make the tool read-only: call only `list --json` and `log`; do not wire dispatch, claim, block/unblock, archive, complete, or shell-command controls into a visibility view.
8. State the boundary in the UI: worker logs show intentionally emitted task activity and receipts, **not hidden model reasoning**; displayed text is not itself approval or execution evidence.

### Verification

- Add `--smoke-test`: perform the same live list and selected-task log requests as the GUI, print task/log counts, and exit.
- Test Tk availability with a create/withdraw/destroy probe, but also run a real window launch under a bounded external timeout. A withdrawn-root probe does not execute all UI-building paths and can miss NameErrors in widget construction.
- For a long-lived monitor, start it with a tracked background-process mechanism and verify it remains running after launch.

### Embedded live-team view for an existing V20 dashboard

When an existing V20 Tkinter dashboard already has action/evidence buttons and the operator asks for a read-only view of the autonomous Kanban team, add one **Live Team** button that opens a dedicated `Toplevel` (or an established in-app view toggle) rather than crowding the portfolio/training surface.

**Explicit same-window request takes precedence:** if the operator says the Live Team view must stay in the main dashboard window, use the established in-app view toggle. Keep the app bar mounted, `pack_forget()` the normal dashboard body, pack a dedicated Live Team `Frame` in its place, and add a visible `← Dashboard` control that restores the original body. Do not create a `Toplevel` for that path. Stop polling and animation callbacks before destroying the embedded frame; regression-test both entering the view and returning to the dashboard.

### Fixed workforce visibility and mutually exclusive embedded views

If the operator cannot see the workforce without scrolling, do **not** stack the roster above the evidence panes. Use a fixed, non-scrolling left roster rail sized for the known worker count. Each row must expose worker, truthful state, current/latest bounded task, and age; keep selected-worker output and recent activity in a resizable evidence area to the right. Test that the roster is side-mounted and has enough rows for every configured worker.

**Roster truth and compact status vocabulary:** derive the display roster from the authoritative configured worker/profile list, not from a stale hard-coded subset. If the configured V20 profiles and the dashboard roster disagree, resolve the discrepancy with the coordinator before changing the view; do not silently omit roles. Use the roster count for the fixed Treeview height. Preserve distinct raw states: `ready` must render as `READY`, not be collapsed into waiting. When the operator asks for compact status glyphs, render `B` for BLOCKED (red), `R` for READY (blue), `C` for COMPLETE (green), and `W` for WAITING (orange). Keep an actively executing RUNNING state visually distinct (for example, a pulsing green row/dot) rather than mislabeling it as completed. Test the raw-state-to-display-marker mapping independently of Tk, then test the Treeview wiring separately.

### Static workflow charts

When the operator asks to see the team as a workflow rather than a roster, replace the roster table with a fixed-position pipeline chart. Source the stage order and role labels from the project-owned worker contract, then render one durable card per role in that order with arrows between stages. The card geometry must not depend on task count or output volume.

Each card must show its role, bounded current task, age, and a truthful Kanban-derived state. Treat task status and process liveness as separate claims: render `● running` / `working` only when a `running` task also has a fresh authoritative heartbeat (define and test a bounded freshness threshold). A `running` task without a heartbeat must render an explicit muted `running · no heartbeat`; one with an expired heartbeat must render a distinct stale warning. An empty emitted log neither proves nor disproves liveness. Keep `COMPLETE` visually distinct from active running (label plus a different green shade), keep unassigned roles visibly `idle`, and retain click-through to the selected worker's emitted output when a task exists. Keep the chart read-only: refresh card values from the board snapshot, but never add mutation controls.

**Selection and truth contract:** Canvas card clicks must persist across asynchronous refreshes. Store the selected role/task independently of the arriving snapshot; if a stale snapshot carries the prior selected task, do not overwrite the new selection, and request the newly selected task’s log once the current fetch completes. Give the selected card a visible outline for immediate click feedback. Distinguish `RUNNING` from `COMPLETE` with both labels and different green shades (`● running` vs `C complete`); task status is a Kanban projection, not process liveness. If the board lacks a usable heartbeat/freshness timestamp, say so explicitly in the monitor header rather than implying that `running` proves a worker process is alive.

For V20, the canonical seven-stage order is Product → Data → Quant → ML Systems → Portfolio → Risk → Development. Test the pure role/order projection separately, then assert the Tk workflow canvas/card count matches the configured roster.

When a dashboard has several full-surface embedded views (for example, Live Team and Model Runs), they must be mutually exclusive: close/destroy the active embedded frame and restore the base body before opening the next one. Never pack two full-body views into the same parent; that makes key panels disappear or forces avoidable scrolling. Add regression coverage for enter → return and for switching views.

The first slice should show:

- one truthful current row per approved worker: status, bounded task, elapsed age, heartbeat/freshness, blocker, prior handoff, and latest receipt;
- a selected-worker output pane sourced from intentionally emitted Kanban logs/receipts, explicitly labeled as worker output rather than hidden model reasoning;
- a separate bounded recent-handoffs/activity timeline, because event history is not current concurrency;
- read-only behavior only: no claim, dispatch, approve, reject, complete, archive, comment, or shell controls;
- polling in a background thread with immutable queue results, last-good preservation, stable selection/scroll, and change-only rendering;
- restrained semantic animation only: a slow running pulse, refresh spinner while an actual fetch is in flight, and brief evidence/handoff highlight. Never simulate typing, terminal activity, or progress that the sources did not emit.

Do **not** launch one terminal or process per worker for display. A worker-terminal visual is a projection of the existing task/run/log evidence; spawning display terminals can duplicate work and creates false process ownership. Keep the implementation lean: prefer one monitor/view-model module plus focused tests and a small button/window hook in the existing app. Reuse the existing palette, fonts, and lifecycle.

For the V20-specific source contract, state vocabulary, animation contract, and acceptance matrix, read `references/v20-live-team-read-only-view.md`.

### Reference-driven Command Split layouts

When the user supplies a visual HTML/mockup reference and identifies a direction such as Command Split, treat that as the acceptance target—not as inspiration for an unrelated redesign. First map the reference to operational semantics: a worker/task rail on the left, a selected-worker focus header, and a large evidence/output surface on the right. Preserve the authoritative input/output lineage while changing presentation. If a tab has no authoritative source (for example Diff or Events), render an explicit unavailable state rather than inventing content.

For a standalone Desktop `.py` monitor, back up the file before editing. Preserve the read-only Kanban contract: task list from the JSON list surface, task card as input/brief, complete worker log as output, asynchronous subprocesses, cached last-good content during refresh, and no mutation controls. Keep polling units explicit (`2` seconds becomes `after(2 * 1000, ...)`), and route `WM_DELETE_WINDOW` through a close method that marks closing, cancels tracked `after()` callbacks, and destroys the root.

Use `references/worker-monitor-command-split.md` for the reusable implementation and verification recipe.

When adding provider-account usage, keep it visually subordinate and semantically separate from worker evidence. Use a compact app-bar summary plus an expanded command-palette block; fetch asynchronously on a slower cadence than local task polling; preserve last-good values; render missing data as unavailable; and never merge OpenAI quota, OpenRouter dollars, Hermes token history, or application-local receipts into one unlabeled number. Use `references/worker-monitor-provider-usage.md` for source selection, formatting semantics, refresh architecture, and live visual verification.

For this user's dense Vesper monitors, legibility outranks mockup-level microtype: do not ship 5–7 pt operational text merely to preserve density. Use an 8 pt floor, scale related roles together, enlarge fixed popups when wrapping increases, and recapture both the actual shortcut-launched window and app-local popup. Never send global hotkeys unless foreground ownership is proven. Use `references/dense-monitor-typography.md` for the scale, AST contract probe, safe Tk popup capture, and clipping checklist.

When the operator needs adjustable text, use shared `tkinter.font.Font` objects rather than rewriting widget tuples. Persist a bounded `Aa NNN%` scale, resize fixed-height bands and existing worker rows with the fonts, and test worst-case provider/app-bar strings at maximum scale before visual acceptance. Use `references/dynamic-tk-typography.md` for the managed-font architecture, TDD slices, Windows test lifecycle, and real-shortcut verification.

For deterministic Windows icon recolors, update the palette contract before the builder, regenerate every ICO size, validate small-size antialiasing semantically, refresh the `.lnk` plus Shell cache without restarting Explorer, and prove the result on the actual shortcut-launched HWND. Use `references/windows-icon-palette-refresh.md` for the complete workflow and cache-refresh recipe.

When cleaning a Windows Desktop so it contains launchers only, treat source folders, shortcuts, nested repositories, and registered services as one relocation contract. Inventory dirty state and shortcut metadata first; use a parent-repo-local ignored tool container; verify cross-volume copies and source remnants rather than trusting robocopy codes; migrate locked Windows-service binaries with UAC, rollback, logs, and a receipt; then prove every shortcut and service path. Use `references/windows-desktop-tool-relocation.md` for the complete workflow.

## Rebuilding a Prompt Toolkit terminal app as a Tkinter desktop app

When the user wants a terminal/TUI app rebuilt as a native Tkinter desktop
app (e.g. VOT rebuilt to mirror VWM), treat it as a **fresh build**, not
incremental tweaks to the terminal renderer. Signals: "it needs to mirror
the design", "not just different tweaks", "the tinker [Tkinter] loader,
not in the terminal".

**Do NOT incrementally tweak the Prompt Toolkit renderer** (recoloring,
adding `▌` tokens, restructuring headers one TDD cycle at a time) when the
user wants a full Tkinter rebuild. That wastes cycles on the wrong layer.
Recognize the "mirror the design" signal early and start fresh.

### Architecture: Command Split (from VWM)

Mirror the VWM's proven structure — see the `vwm-design-contract` skill
for the full contract:

1. **Appbar** (64px): orange rail accent (full-height 3px bar on left edge,
   NOT a `▌` glyph next to text — the user explicitly preferred the bar
   over the glyph) + VESPER / OPERATOR CONTROL brand + state brackets
   ([PAPER] [AUTHORITY] [EVIDENCE]) + counters + sync status
2. **Body**: rail (350px, left) + focus (right, expands)
3. **Rail**: heading + scrollable card list (Canvas + Frame) + queue box
4. **Focus**: focus_head (116px) with title/meta + metrics grid (2×2) +
   termbar (40px) with tabs + terminal body (Text widget with dim/mid/bright
   tags)

### File Structure (modular, not monolithic)

Split into focused modules — each under 8K tokens for safe `write_file`
calls (the `write_file` tool times out on large content):

- `app/vot_tk_palette.py` — color constants (exact VWM palette)
- `app/vot_tk_fonts.py` — FontManager with text scaling (Ctrl++/-/0)
- `app/vot_tk_appbar.py` — the 64px command strip
- `app/vot_tk_rail.py` — the 350px left panel (cards + queue box)
- `app/vot_tk_focus.py` — the right panel (head + metrics + tabs + terminal)
- `app/vot_tk.py` — main app (ties it together, data polling, threading)

### Data Flow (mirrors VWM)

- Background thread fetches snapshot → puts on `queue.Queue` → main thread
  drains via `root.after(150, self._drain_queue)`
- Poll every 5 seconds (VWM uses 2s for Kanban, VOT uses 5s for heavier
  snapshot loading)
- `pythonw.exe` for launch (no console window)
- **Critical**: patch `_default_runner` with `CREATE_NO_WINDOW` at startup
  or console windows flash every poll cycle — see
  `references/tkinter-no-window-flashing.md`

### Orange Rail Preference

The user prefers the orange rail as a **full-height 3px accent bar** on the
left edge of the appbar, NOT as a `▌` Unicode glyph next to the brand text.
When both were present, the user asked to remove the glyph and keep only
the bar.

### VOT desktop shortcut identity and build provenance

Treat the Desktop `.lnk`, the Python module it imports, and the dashboard data root as separate facts. Inspect the actual `.lnk` before changing code: record its `TargetPath`, `Arguments`, `WorkingDirectory`, and `IconLocation` through `WScript.Shell.CreateShortcut`. The shortcut working directory determines which checkout supplies `-m app.vot_tk`; a `--root` argument/default may intentionally point at a different canonical data root. Do not call a shortcut stale merely because its code checkout and data root differ.

Make the release identity visible in the Tk surface. Define one module-level semantic version (for example `VOT_VERSION = "0.0.1"`) and render `VOT v0.0.1` in both the native window title and appbar sync/status string. This label is mandatory, release-oriented, and lookup-friendly; do not expose a raw Git SHA as the primary operator-facing version. Test the semver format and both title/appbar display hooks. A Git revision may be retained only as optional developer diagnostics, resolved once at startup from the module repository—not from the data root.

### Vesper Snapshot Loading

The VOT Tkinter app reuses the existing Vesper service layer
(`load_dashboard_snapshot`), which requires four tracker arguments:
`codex_tracker`, `workspace_tracker`, `git_tracker`, `event_source` — plus
optional `provider_telemetry`. Construct these fresh on each poll:

```python
from app.services.operator_terminal_status import load_dashboard_snapshot
from app.services.operator_codex_activity import CodexActivityTracker
from app.services.operator_workspace_activity import (
    WorkspaceEventTracker, WindowsDirectoryEventSource, GitActivityTracker
)
from app.services.operator_provider_telemetry import build_provider_telemetry_supervisor

codex_tracker = CodexActivityTracker(root)
workspace_tracker = WorkspaceEventTracker(root, started_at=observed)
git_tracker = GitActivityTracker(root)
event_source = WindowsDirectoryEventSource(root)
provider_supervisor = build_provider_telemetry_supervisor(root)

snap = load_dashboard_snapshot(
    root,
    codex_tracker=codex_tracker,
    workspace_tracker=workspace_tracker,
    git_tracker=git_tracker,
    event_source=event_source,
    provider_telemetry=provider_supervisor.snapshot(),
)
```

Note: `GitActivityTracker` lives in `operator_workspace_activity`, NOT
`operator_git_activity` — a common import-name mistake.

### Refresh-in-progress indicator

For a live read-only VOT, show a small stateful indicator rather than a permanently animated decoration. Use a dedicated `StringVar` in the appbar, rendered in the established orange accent, with restrained quarter-wheel frames (`◐ ◓ ◑ ◒`). Start it immediately before the background snapshot thread, advance it through one `root.after` callback, and clear it after either a snapshot or error reaches the main-thread queue. Preserve the semantic version in connecting/error status text. Cancel an existing spinner callback before restarting it (manual refreshes otherwise create duplicate loops), and cancel it again during `close()`.

Keep the spinner separate from the sync text so it can carry semantic orange without recoloring provenance/freshness information. Add a small pure frame/wrap test; the actual appbar wiring should remain compilation-tested.

### VOT maintenance: lint, dead code, and lightweight fixtures

Audit the VOT production modules and VOT tests as separate scopes: a clean `app/vot*.py` lint result does not prove the test surface is clean. Run targeted Ruff over both, use a repository-local `--basetemp` for pytest on Windows, and distinguish inherited baseline debt from violations introduced by new tests. Do not add broad production-code defensive `hasattr` checks merely to satisfy lightweight tests that construct `VotTkApp` with `object.__new__`; update those fixtures with each new lifecycle field (`StringVar`, callback ID, and state flag) so they model the real class contract.

Before deleting a suspected VOT dead symbol, search all callers and inspect `git blame`. Safe removals include constants, private helpers, and callback parameters with no readers; module-level palette exports are CAREFUL because external consumers may exist. If a test asserts a widget class, first verify that the live implementation actually uses that widget—do not retain a false assertion for a wheel-only Canvas surface.

## Pitfalls

- **Lost session work**: `patch` and `write_file` edits to GUI files only exist in the working tree. If the conversation shifts to a different topic, gets compacted, or a handoff occurs, uncommitted patches vanish with no trace. **Commit after every coherent set of changes** (`git add <file> && git commit -m "descriptive message"`) even for intermediate steps — a commit per logical chunk is fine. Do not rely on "I'll commit later" when there's an unbounded number of turns ahead or a pending topic switch.
- ttk widgets use **string** values for relief/anchor/justify, not tkinter constants
- **Font specification**: Always use a **tuple** for fonts with spaces in the name: `("Segoe UI", 10)` not `"Segoe UI 10"`. The string form causes `TclError: expected integer but got "UI"` because Tk parses the space as a field separator and tries to parse `UI` as an integer.
- **`pad=` is not a valid tkinter option**: `tk.LabelFrame` and most tkinter widgets do NOT accept a bare `pad=` keyword. Use `padx=` and `pady=` separately. Passing `pad=6` causes `_tkinter.TclError: unknown option "-pad"`.
- `tk.Menu` does **not** support `selectbackground` — only `bg` and `fg`
- `Canvas.winfo_width()` returns `1` if unmapped — always provide a fallback
- Subprocess `cwd` must be project root, not script's directory
- `rerank` must use loaded date from `_score_data`, not `_last_scores()`
- Adding a column to Treeview requires updating heading def, column widths, AND every `insert()` value tuple — missing any one causes a silent data shift
- `Ctrl+A` on log must be bound on **both** the log widget and `self.master` to work from any panel
- Schedule text clips at right edge if using default font size 10 and wide padding — use Segoe UI 8 and column weights
- Patch tool (`patch`) can introduce indentation errors when replacing multi-line code blocks — prefer `write_file` for large GUI file replacements
- **Patch tool backslash double-escaping**: when `patch`'s `new_string` contains `\n` literals inside f-strings or string literals (common when breaking long lines for ruff E501), the tool can write `\\n` (two backslashes + n) to disk instead of `\n` (newline). Always verify with `cat -A` after patching string literals — `$` marks a healthy EOL, `\\n` marks a doubled escape. Re-patch or fall back to `write_file`/`sed` if doubled. See `references/patch-tool-backslash-escaping.md` for detection, fix, and prevention patterns.
- **Bulk GUI edits**: When making multiple changes to a compact dashboard file, use Python inline string replacement (`text = text.replace(old, new)`) or `sed` instead of the `patch` tool. The `patch` tool fails on compact one-liner code because it cannot reliably match multi-line `old_string` patterns against the compact format. The Python approach applies all changes in memory at once, then writes the result: `with open(...) as f: text = f.read(); text = text.replace(...); with open(...) as f: f.write(text)`
- **`.env` key loading**: use `python-dotenv` to load `.env`, store API keys for broker connections (Alpaca, FMP, etc.). round() notional amounts to 2 decimal places for Alpaca's order API
- **Worktrees don't inherit `.env`**: a git worktree (`D:/vesper-wt-*`) is a separate working directory and does NOT inherit `.env` from the main repo. When a Tkinter app runs from a worktree and reads `ROOT / ".env"`, it resolves to the worktree — and the file doesn't exist there. Copy `.env` from the main repo: `cp D:/vesper/.env D:/vesper-wt-X/.env` (`.env` is gitignored, so copying is safe). See `vwm-design-contract` skill for the full pitfall.
- **Polling tramples user state**: when a Tkinter app polls for data on a timer, the refresh cycle silently overwrites scroll position and card selection. Use `force_scroll=False` on background refresh and preserve `selected_key` across cycles. Pattern: (1) add `force_scroll` param to the output setter — when False, capture `yview()[0]` before update and `yview_moveto` after; (2) in the refresh callback, check if a card is selected — if so, find it in the new data and keep showing it; only fall back to the default when nothing is selected or the key disappeared. See `vwm-design-contract` skill's build patterns reference #3 for the exact code.
- **Actionable tabs for approval workflows**: when a monitoring dashboard also needs approval/deny actions (e.g. Kanban task management), add a dedicated actionable tab — not text dumped into a detail/read-only tab. The user said: "I dont see a seperate channel or tab for kanban. So I dont know how or where I would talk to or approve/deny work being done there." Pattern: separate tab with task list + task selection (entry bar or click) + action shortcuts (A=approve, R=reject, U=unblock) + immediate refresh after action.
- **Buttons over keyboard shortcuts**: when building operator panels that need approve/reject/unblock/comment actions, the user explicitly preferred real clickable `tk.Button` widgets over A/R/U key bindings. Quote: *"we can have buttons instead of commands"*. Key bindings are fine as a secondary input method, but the primary action surface should be visible buttons — not hidden keyboard shortcuts that the user has to discover.
- **No native popup dialogs for integrated dashboards**: when an operator dashboard needs confirmation (approve/reject/unblock), do NOT use `messagebox.askyesno` or `simpledialog.askstring` — these pop up as separate windows outside the dashboard. The user said: "It also has a separate panel that pops up for approval unlike hermes kanban that utilizes a richer panel inside the dashboard." Pattern: render confirmation prompts **inline** in the terminal output area (`⚠ APPROVE this task? [Y] Yes [N] No [ESC] Cancel`), use keyboard shortcuts (Y/N/Escape) for confirmation, and use the entry bar for input (e.g. rejection reason). This mirrors how Hermes Kanban itself works — everything inline, no external windows. Note: the dedicated Kanban panel (`vot_kanban.py`) uses **action buttons** (APPROVE/REJECT/UNBLOCK) rather than inline confirmation prompts — buttons are the preferred surface when the panel is specifically built for Kanban management.
- **Dedicated window for complex panels**: when a sub-feature (Kanban management, worker monitoring) needs its own full UI surface (workforce bar, clickable cards, worker logs, action buttons, comment box), build it as a **separate Tkinter window** (`app/vot_kanban.py`), not as a tab crammed into the main dashboard's terminal text output. The user said: *"we can have a whole new window that specializes in kanban with everything we want"*. The separate window can run alongside the main VOT — both open simultaneously. See `vwm-design-contract` skill's "Dedicated Kanban panel" section for the full architecture.
- **Scrollbar on scrollable card lists**: when a Canvas-based card list (left panel) may accumulate more cards than fit in the viewport, add a proper `tk.Scrollbar` paired with the Canvas via `yscrollcommand`/`command`. Use the shared dark palette for every scrollbar instance: `bg=CHARCOAL`, `troughcolor=CHARCOAL`, flat relief, and a non-white active background. Apply it consistently to the main rail, embedded views, and dedicated companion windows; mouse-wheel scrolling alone is insufficient.
- **View toggle for integrated sub-panels**: when a sub-feature (Kanban, worker monitor) needs its own full UI surface but the user wants it **inside the main dashboard** (not a separate window), use a view toggle pattern: build the sub-panel as a `tk.Frame`, and toggle between the main body and the sub-panel with `pack_forget()`/`pack()`. Both views share the same appbar. The user said: *"I want you to incorporate that whole thing inside VOT. Using the available template we already have for the VOT dashboard, it would mirror the top section."* Pattern: `if self._view_mode == "evidence": self.body.pack_forget(); self._kanban_view.pack(fill=BOTH, expand=True)` / `else: self._kanban_view.pack_forget(); self.body.pack(fill=BOTH, expand=True)`. All sub-panel data methods should be prefixed (e.g. `_kv_`) to distinguish from the main view's methods.
- **Never navigate widget tree via `.master.master`**: when binding mouse wheel events on cards inside a Canvas-based scrollable list, do NOT try to reach the Canvas via `card_frame.master.master.yview_scroll()`. The widget hierarchy depth varies between contexts, causing `AttributeError: 'Frame' object has no attribute 'yview_scroll'`. Bind on the Canvas directly instead.

## TSV export pattern

```python
def _export_tsv(self):
    tab = self.notebook.select()
    idx = self.notebook.index(tab)
    trees = [self.scores_tree, self.perf_tree, self.hist_tree]
    if idx < len(trees):
        t = trees[idx]
        lines = ["\t".join(t.heading(c, "text") for c in t["columns"])]
        for row in t.get_children():
            lines.append("\t".join(str(v) for v in t.item(row)["values"]))
        self.master.clipboard_clear()
        self.master.clipboard_append("\n".join(lines))
```

## Monitor View layout (1920×1080)

For full-HD displays, structure the main content as a two-column split with a bottom strip:

```
┌───────────────────────────────┬──────────────────────────────┐
│ Factor Scores (20 rows)       │ Alpaca Portfolio             │
│ Ticker Score Ent  Hurst Vol   │  Equity, Cash, Positions     │
│ ...                           │  ┌─Equity Curve─────────────┐│
│                               │  │  ▁▄▇▆▅▄▃                ││
│ ┌─Bar Chart (110px)─────────┐ │  └──────────────────────────┘│
│ │ ██ AAPL ██ AVGO ██ NVDA  │ │  Today's Data               │
│ └───────────────────────────┘ │  Time  Source      Result    │
└───────────────────────────────┴──────────────────────────────┘
┌─ Nova Basket ───┬─ Factor Basket ──┬─ Log (compact) ────────┐
│ # Ticker Weight │ # Ticker  Score  │ Select All Copy Clear  │
└─────────────────┴──────────────────┴────────────────────────┘
```

Implementation:

```python
# Main area: PanedWindow with left (scores) weight=2, right (portfolio) weight=1
main_pw = ttk.PanedWindow(master, orient=tk.HORIZONTAL)
main_pw.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

left_f = ttk.Frame(main_pw); main_pw.add(left_f, weight=2)
right_f = ttk.Frame(main_pw); main_pw.add(right_f, weight=1)

# Bottom strip: 3 panels side by side in a Frame
bottom_f = ttk.Frame(master)
bottom_f.pack(fill=tk.X, padx=5, pady=(0, 5))
# Use side=tk.LEFT, fill=tk.X, expand=True for each
nova_f = ttk.LabelFrame(bottom_f, text="Nova Basket")
nova_f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
fac_f = ttk.LabelFrame(bottom_f, text="Factor Basket")
fac_f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
log_f = ttk.LabelFrame(bottom_f, text="Log")
log_f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
```

- `weight=2` for scores (wider), `weight=1` for portfolio (narrower)
- Bottom strip uses `side=tk.LEFT` with `expand=True` for equal-width panels
- `height=20` for scores tree, `height=4` for basket trees
- Equity curve canvas `height=120`, bar chart canvas `height=110`

## Today's Data ingestion feed

A timeline view showing what data was ingested today, sorted by most recent:

```python
feed_f = ttk.LabelFrame(right_f, text="Today's Data")
feed_f.pack(fill=tk.BOTH, expand=True)

self.feed_tree = ttk.Treeview(feed_f, columns=("time", "source", "detail"), show="headings", height=8)
self.feed_tree.heading("time", text="Time")
self.feed_tree.heading("source", text="Source")
self.feed_tree.heading("detail", text="Result")
self.feed_tree.column("time", width=60, anchor="center")
self.feed_tree.column("source", width=130)
self.feed_tree.column("detail", width=180)
```

Build entries by checking data files on disk. Only show entries from today:

```python
def _load_feed(self):
        for r in self.feed_tree.get_children():
            self.feed_tree.delete(r)
        today = date.today().strftime("%Y%m%d")
        entries: list[tuple[str, str, str]] = []

        def _try(path, src, fmt):
            if not path or not path.exists(): return
            try:
                md = _mtime_date(path)  # YYYYMMDD, exact match
                if md == today:
                    ts = _mtime(path)
                    if ts:
                        entries.append((ts.split(" ")[1], src, fmt(path)))
            except Exception: pass

    _try(_last_scores(), "Factor Scores", lambda p: f"{json.loads(p.read_text()).get('scored_count', 0)} tickers")
    _try(_last_basket(), "Factor Basket", lambda p: f"{len(_parse_basket_md(p))} tickers re-ranked")
    _try(Path("data/insider_trades/insider_scores.json"), "Insider SEC", lambda p: f"{len(json.loads(p.read_text()).get('scores', {}))} tickers")
    _try(_last_portfolio(), "Alpaca Paper", lambda p: f"${json.loads(p.read_text()).get('account', {}).get('equity', 0):,.0f} equity")
    _try(_last_news(), "News Backfill", lambda p: f"{len(json.loads(p.read_text()).get('scores', {}))} tickers")
    trends = sorted(Path("data/google_trends").glob("*.json"))
    _try(trends[-1] if trends else None, "Google Trends", lambda p: f"{len(json.loads(p.read_text()).get('scores', {}))} tickers")
    receipts = sorted(Path("artifacts/evals").glob("alpaca_receipt_*.json"))
    _try(receipts[-1] if receipts else None, "Alpaca Rebal", lambda p: f"{len(json.loads(p.read_text()).get('target_tickers', []))} orders")

    entries.sort(key=lambda x: x[0] or "", reverse=True)
    for i, (ts, src, detail) in enumerate(entries):
        self.feed_tree.insert("", tk.END, tags=("odd" if i % 2 else "even",), values=(ts, src, detail))
    if not entries:
        self.feed_tree.insert("", tk.END, values=("—", "Waiting for data", "Snapshots accumulate over time"))
```

**Feed date window**: Instead of `today in ts` (which breaks because `"20260706"` is not a substring of `"2026-07-06"`), use `_mtime_date()` which returns `"YYYYMMDD"`. Also, show runs from the last **3 days** instead of just today — otherwise the feed is empty after a weekend:

```python
td = date.today()
if md and abs(date.fromisoformat(datetime.strptime(md, "%Y%m%d").isoformat()[:10]) - td).days <= 3:
```

## Live activity feed (_lactiv)

When the user clicks a button (scores, rebalance, basket), post an immediate entry to the Today's Data feed so they see activity NOW, not just on the next refresh:

```python
def _lactiv(self, source: str, msg: str, ok: bool = True):
    ts = datetime.now().strftime("%H:%M:%S")
    icon = "\u2713" if ok else "\u2717"
    self.feed_tree.insert("", 0, tags=("odd",), values=(ts, f"{icon} {source}", msg))
    while len(self.feed_tree.get_children()) > 50:
        self.feed_tree.delete(self.feed_tree.get_children()[-1])
```

Call from `_run` on start and completion:
```python
def _run(self, cmd, desc):
    self._lactiv(desc, "starting…", ok=False)
    # ... subprocess ...
    if success:
        self._lactiv(desc, "completed", ok=True)
```

## Factor Basket matches bar chart

The Factor Basket panel should display the top 5 tickers from `self.smap` (the factor score map), not from a separate basket file. This keeps the bar chart and Factor Basket in sync:

```python
def _lfactor(self):
    for r in self.mt.get_children(): self.mt.delete(r)
    if not self.smap:
        p = _last_basket()
        if p:  # fallback
            for i, t in enumerate(_parse_md(p), 1): ...
        return
    top5 = sorted(self.smap.items(), key=lambda x: -x[1])[:5]
    for i, (t, sc) in enumerate(top5, 1):
        self.mt.insert("", tk.END, ..., values=(i, t, f"{sc:.4f}"))
```

Vesper Selection should fall back to factor picks when no report file exists.

## Clear button clears both panels

```python
def _clr(self):
    self.lg.configure(state=tk.NORMAL)
    self.lg.delete("1.0", tk.END)
    self.lg.configure(state=tk.DISABLED)
    for r in self.ft.get_children():
        self.ft.delete(r)
```

## Bar chart auto-redraw on window resize

```python
self.bar.bind("<Configure>", lambda e: self._lbars())
```
## Python 3.10 compat

`from datetime import UTC` only works in Python 3.11+. Use `timezone.utc`:
```python
from datetime import date, datetime, timedelta, timezone
```

## Alpaca stale order cleanup

Before placing new orders, cancel all existing open orders to prevent duplicate stacking:

```python
try:
    from alpaca.trading.requests import GetOrdersRequest
    stale = client.get_orders(filter=GetOrdersRequest(status="open"))
    for o in stale:
        try: client.cancel_order_by_id(o.id)
        except: pass
    if stale: print(f"  Cancelled {len(stale)} stale orders")
except Exception:
    pass
```

## References

- `references/tkinter-patterns.md`
- `references/tkinter-font-tuple.md` — font specification bug: strings vs tuples
- `references/pyside6-markdown-editor.md` — document-centric Qt architecture, lifecycle, PDF export, packaging, and tests
- `references/windows-release-publishing.md` — branded portable builds, archive/checksum validation, GitHub Release publication, and public-download verification
- `references/windows-icon-palette-refresh.md` — deterministic SVG/ICO recolors, small-size raster checks, `.lnk` rewriting, and non-disruptive Shell cache refresh
- `references/windows-desktop-tool-relocation.md` — Desktop-to-project relocation, shortcut rewrites, nested-repo preservation, and rollback-safe Windows service migration
- `references/worker-monitor-command-split.md` — HTML-to-native Command Split fidelity, read-only Kanban lineage, and Win32 lifecycle gates
- `references/worker-monitor-provider-usage.md` — OpenAI/OpenRouter account snapshots, truthful scope separation, async refresh, and palette/app-bar presentation
- `references/dense-monitor-typography.md` — legible font floors, coordinated scaling, AST contracts, popup resizing, and focus-safe Tk capture
- `references/alpaca-trading-integration.md` — Alpaca API setup, notional rounding, order cleanup
- `references/tkinter-no-window-flashing.md` — CREATE_NO_WINDOW patch for pythonw.exe apps that spawn subprocesses
- `references/tkinter-refresh-scroll-and-zoom.md` — stable Text-widget reading position across polling refreshes plus bounded, pannable Canvas zoom and real Tk regression tests
- `references/windows-tk-background-capture-and-canvas-probes.md` — exact-HWND `PrintWindow` capture for occluded Tk windows and mapped-transparent Canvas interaction probes
- `references/tkinter-kanban-integration.md` — operator-action Kanban panel: task list, detail view, comments, approve/reject/unblock, workforce roster, inline confirmation (not popups)
- `references/realtime-sqlite-polling.md` — direct SQLite reads for real-time polling, signature-based change detection, static sync labels, scroll preservation, agent-specific issue prefixes
- `references/patch-tool-backslash-escaping.md` — `patch` tool writes `\\\\n` instead of `\\n` when `new_string` contains backslash escapes in string literals; detection with `cat -A`, fix, and prevention patterns
- `references/tkinter-widget-rebuild-leak.md` — memwatch case study: 100.7% growth over 150 samples from Tkinter destroy+recreate, fix via Treeview, self-PID skip, and win32gui tray icon recipe (memwatch v0.1.0)