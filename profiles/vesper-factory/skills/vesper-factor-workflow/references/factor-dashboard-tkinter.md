# Factor Dashboard — Tkinter Desktop GUI

> **Session update 2026-07-06**: Migrated to Monitor View layout (Option A).
> Removed tabs, added Today's Data feed, 1920x1080 default, Alpaca button,
> compact bottom strip with baskets + log side by side.

A boring, functional Windows-native dashboard for interacting with the factor model
in real time. Designed for an audience that wants to "react to the model, push the
buttons and be done."

## Design Philosophy
- **Boring over flashy**: Dark flat panels, no animations, no gradients, no rounded corners.
- **Native over web**: Tkinter + ttk renders as a standard Windows dialog. No Streamlit,
  no HTML, no CSS, no server.
- **Functional over aesthetic**: Every element has a job. No decorative chrome.
- **One-button actions**: Each button does one thing. No multi-step wizards.
- **Monitor View**: Everything visible at once in a 1920x1080 window. No tabs, no scrolling.
  Only the log has a scrollbar for overflow.

## File Location
`scripts/factor_dashboard.py` — single file, ~400 lines, no package structure, no config.

## Monitor View Layout (Current)

```
| Schedule | Countdown | Progress Bar | Status Dot               |
| [Refresh] | [1.Scores] [2.Rerank] [3.Basket] | [Run All] | [4.Alpaca]  Clear |
| ☐ Factor only  ☐ Auto rerank       Ctrl+R 1/2/3/4 Refresh Scores Rerank Basket Alpaca |
┌── Factor Scores (20 rows, 7 cols) ──┬── Alpaca Portfolio ──────────┐
│ Ticker Score Entropy Hurst Vol Sent │ E: $106,563  C: $106,558    │
│ AAPL   0.564  0.355 1.281 2.635 0.01│ 1 pos BP: $325,012           │
│ ...14 rows...                      │ ┌─Equity Curve─────────────┐  │
│             Insider column          │ │  ▁▄▇▆▅▄▃  +$0           │  │
│ ┌─Bar Chart (110px)──────────────┐ │ └──────────────────────────┘  │
│ │ ██ AAPL ██ AVGO ██ NVDA ██    │ │ Today's Data                  │
│ └────────────────────────────────┘ │ 06:45  Factor Scores 14 tkrs │
└────────────────────────────────────┴── 02:30  Insider SEC   4 tkrs ─┘
┌─ Nova Basket ──────┬─ Factor Basket ──────┬─ Log (compact) ────────┐
│ # Ticker Weight %  │ # Ticker  Score       │ Sel All Copy Clear     │
│ 1 XLK   23.00%     │ 1 COST   0.715        │ 20:01  ✓ Scores done   │
│ 2 NFLX  22.00%     │ 2 NFLX   0.417        │                        │
└────────────────────┴───────────────────────┴────────────────────────┘
```

### Key differences from the earlier tab-based version
- **No tabs**: The old Portfolio/Performance/History tabs are gone. All data is visible at once.
- **Right column**: Stacks Alpaca Portfolio (equity curve + summary) above Today's Data feed.
- **Bottom strip**: Three panels side by side: Nova Basket, Factor Basket, Log.
- **1920x1080 default**: `master.geometry("1920x1080")` with `minsize(1200, 800)`.
- **Insider column**: 7th column in the scores tree, shows `details.insider` from the factor scores JSON.
- **All scored entries**: Loads all `data.get("scored")` entries, not just `top_10`.
- **Alpaca button**: "4. Alpaca" runs `alpaca_portfolio.py` then `alpaca_rebalance.py`, then refreshes.
- **Keyboard shortcuts**: Ctrl+R, Ctrl+1/2/3/4 (Ctrl+4 for Alpaca).

## Dark Theme Implementation

```python
BG      = "#1e1e1e"
FG      = "#d4d4d4"
SELECT  = "#264f78"
ALT_ROW = "#252526"
BTN_BG  = "#333333"
HEADER  = "#2d2d2d"

style = ttk.Style(root)
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
style.configure("TProgressbar", background="#0e639c", troughcolor=BG)
style.configure("TSeparator", background="#444")
```

**TTK option pitfalls**: Always use string values for ttk options
(`relief="sunken"`, `anchor="w"`). The integer constants (`tk.SUNKEN`, `tk.W`)
cause silent Tcl errors. Font specs must be tuples: `("Segoe UI", 10)` not
`"Segoe UI 10"` — spaces in font names break the Tcl parser.

## Schedule Panel & Real-Time Countdown

Located at the top of the window inside a `ttk.LabelFrame`. Shows next-run times,
progress bar, and a live dot indicator. **Prevent timestamp truncation** by using
smaller font (8pt) and giving the last column extra stretch weight:

```python
for i, job in enumerate(SCHEDULE):
    v = StringVar(value=f"{job['name']}: —")
    self.cron_vars[job["name"]] = v
    w = 1 if i == len(SCHEDULE) - 1 else 0
    ttk.Label(info_f, textvariable=v, font=("Segoe UI", 8)).grid(
        row=0, column=i, padx=4, sticky="w")
    info_f.columnconfigure(i, weight=w)
```

### 1-second tick

```python
SCHEDULE = [
    {"name": "Factor Scores", "hour": 2,  "minute": 0},
    {"name": "Factor Basket",  "hour": 2,  "minute": 30},
    {"name": "News Backfill",  "hour": 9,  "minute": 0},
]

def _next_run(self, h: int, m: int) -> datetime:
    now = datetime.now(timezone.utc)
    c = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return c if c > now else c + timedelta(days=1)

def _tick(self):
    now = datetime.now(timezone.utc)
    for job in SCHEDULE:
        nxt = self._next_run(job["hour"], job["minute"])
        p = {"Factor Scores": _last_scores, "Factor Basket": _last_basket,
             "News Backfill": _last_news}[job["name"]]()
        ts = _mtime(p)
        self.cron_vars[job["name"]].set(
            f"{job['name']}: next {nxt.strftime('%H:%M')} UTC"
            f"{'  last ' + ts if ts else '  —'}")
    nearest = min(events, key=lambda x: x[0])
    nxt_dt, name = nearest
    delta = nxt_dt - now
    self.countdown_var.set(f"→ {name} in {_fmt(delta)}")
    win = nxt_dt - timedelta(days=1)
    tot = (nxt_dt - win).total_seconds()
    el = (now - win).total_seconds()
    self.progress["value"] = min(max(el / tot * 100, 0), 100) if tot else 0
    sp = _last_scores()
    today_str = date.today().strftime("%Y%m%d")
    self.sd.itemconfig(self.dot, fill=GREEN if sp and today_str in sp.name else RED)
    self.master.after(1_000, self._tick)
```

### Countdown formatter (HH:MM:SS)

```python
def _fmt(td: timedelta) -> str:
    neg = "-" if td.total_seconds() < 0 else ""
    s = abs(int(td.total_seconds()))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{neg}{h:02d}:{m:02d}:{s:02d}"
```

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+R | Refresh all data |
| Ctrl+1 | Compute Scores |
| Ctrl+2 | Re-rank Basket |
| Ctrl+3 | Generate Basket |
| Ctrl+4 | Alpaca (portfolio + rebalance) |
| Ctrl+A | Select all log text |

## Bar Chart — Avoid Clipped Labels

24px padding on all four sides. Without padding, the leftmost value clips
the leading `1`, and the rightmost ticker/label truncate (e.g. `MS` instead
of `MSFT`).

```python
pl, pr, pt, pb = 24, 24, 22, 24
dw = max(cw - pl - pr, 100)
dh = max(ch - pt - pb, 40)
```

## All Scored Entries (Not Just Top 10)

The `daily_factor_scores.py` `score_universe()` must store **all** scored entries
under `"scored"`. Dashboard loads from `"scored"` and falls back to `"top_10"`.

## Today's Data Feed

The right-column bottom panel shows a timestamped timeline of today's cron results.
Uses `_mtime_date()` helper (returns `YYYYMMDD`) for exact date comparison:

```python
def _mtime_date(path: Path | None) -> str | None:
    if not path or not path.exists():
        return None
    ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return ts.strftime("%Y%m%d")
```

The old `today in ts` substring check fails because `_mtime` returns
`YYYY-MM-DD` format with dashes, while `today` is `YYYYMMDD` without dashes.

## Alpaca Button

The "4. Alpaca" button runs both the portfolio snapshot and the rebalance:

```python
def reb(self):
    self._run(["python", "scripts/alpaca_portfolio.py"], "Portfolio")
    self._run(["python", "scripts/alpaca_rebalance.py"], "Alpaca")
    self.refresh()
```

## Subprocess Integration

```python
ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> vesper/
subprocess.run(
    ["python", "-m", "app.services.daily_factor_scores", ".", yesterday_stamp],
    cwd=ROOT, capture_output=True, text=True, timeout=120,
)
```

**Critical**: Subprocesses MUST run from the project root, not the script's
directory. Without this, `python -m app.services.daily_factor_scores` fails with
`ModuleNotFoundError: No module named 'app'`.

## Launch
```bash
python scripts/factor_dashboard.py
```
Or double-click `scripts/factor_dashboard.bat` from Explorer.