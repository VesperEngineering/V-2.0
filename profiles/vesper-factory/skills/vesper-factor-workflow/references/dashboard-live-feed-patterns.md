# Dashboard Live-Feed & Subprocess Patterns

Added 2026-07-06. Covers patterns discovered while hardening the dashboard.

## Live Activity Feed (`_lactiv`)

The Today's Data panel gets live entries via `_lactiv(source, msg, ok)`:

```python
def _lactiv(self, source: str, msg: str, ok: bool = True):
    """Post a live activity entry to the Today's Data feed."""
    ts = datetime.now().strftime("%H:%M:%S")
    icon = "✓" if ok else "✗"
    self.ft.insert("", 0, tags=("odd",), values=(ts, f"{icon} {source}", msg))
    while len(self.ft.get_children()) > 50:
        self.ft.delete(self.ft.get_children()[-1])
```

Called from `_run()` at job start (`ok=False`) and on completion/success (`ok=True`). Most recent entries appear at the top. Max 50 entries before oldest are trimmed.

## Feed Date Filter

The `_lfeed` method originally required today's date, leaving the feed empty if nothing ran today. Fix: show last 3 days:

```python
td = date.today()  # date object, not string
if md and abs(date.fromisoformat(datetime.strptime(md, "%Y%m%d").isoformat()[:10]) - td).days <= 3:
```

## Clear Button

`_clr()` clears both the Log text widget AND the Today's Data feed tree:

```python
def _clr(self):
    self.lg.configure(state=tk.NORMAL)
    self.lg.delete("1.0", tk.END)
    self.lg.configure(state=tk.DISABLED)
    for r in self.ft.get_children():
        self.ft.delete(r)
    self._lactiv("GUI", "Log cleared")
```

## Bar Chart Auto-Resize

Bind `<Configure>` on the bar canvas to auto-redraw on window resize:

```python
self.bar.bind("<Configure>", lambda e: self._lbars())
```

## Factor Basket from Scores

Instead of reading from a basket file (which shows old Nova picks), the Factor Basket now shows the top 5 scored tickers directly from factor scores:

```python
def _lfactor(self):
    if not self.smap: return  # fall back to file
    top5 = sorted(self.smap.items(), key=lambda x: -x[1])[:5]
    for i, (t, sc) in enumerate(top5, 1):
        self.mt.insert("", tk.END, values=(i, t, f"{sc:.4f}"))
```

## Vesper Selection Fallback

The Vesper Selection panel falls back to factor picks when no no-order report exists:

```python
def _lnova(self):
    p = _last_report()
    if p:
        # Try report first
        for i, e in enumerate(_parse_tickers(p), 1):
            self.nt.insert(...)
        if _parse_tickers(p): return
    # Fallback: top 5 factor picks
    if self.smap:
        top5 = sorted(self.smap.items(), key=lambda x: -x[1])[:5]
        for i, (t, sc) in enumerate(top5, 1):
            self.nt.insert("", tk.END, values=(i, t, f"{abs(sc)*100:.1f}%"))
```

## Position P&L

Alpaca panel shows unrealized P&L from portfolio snapshot:

```python
total_pnl = sum(p.get("unrealized_pl", 0) or 0 for p in d.get("positions", []))
self.pnl.set(f"P&L: ${total_pnl:+,.2f}")
```

The portfolio snapshot script (`alpaca_portfolio.py`) stores `unrealized_pl` and `avg_entry_price` per position.

## Subprocess Isolation for Factors

Google Trends hangs the pipeline because `ThreadPoolExecutor` with timeout doesn't kill the thread on Windows. Solution: run each factor in its own subprocess with `subprocess.run(timeout=N)`:

```python
FACTOR_TIMEOUTS = {"google_trends": 15, "whale_13f": 15, ...}

for name in reg.names:
    timeout = FACTOR_TIMEOUTS.get(name, 30)
    r = subprocess.run(
        [sys.executable, "-c", f"... reg.run('{name}', timeout={timeout-2}) ..."],
        capture_output=True, text=True, timeout=timeout, cwd=ROOT,
    )
```

Per-factor timeouts: `google_trends` and `whale_13f` get 15s (they're network-bound), others get 30s.

## Python PATH Issue

The shell's `python` command may resolve to a broken Python 3.10 venv (`veyr-music/heartlib/.venv`) instead of the Hermes Python 3.11 agent venv. Tests fail with "No module named 'numpy._core._multiarray_umath'" because numpy is compiled for 3.11 but the shell resolves to 3.10.

Use the absolute path to the Hermes venv:

```bash
/c/Users/bgonn/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe -m pytest ...
```

This is a PATH configuration issue, not a code defect.
