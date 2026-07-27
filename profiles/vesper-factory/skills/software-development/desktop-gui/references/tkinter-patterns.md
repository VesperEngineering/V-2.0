# Tkinter patterns for quant dashboards

## Dark theme colour palette

| Role | Hex |
|------|-----|
| Background | `#1e1e1e` |
| Foreground | `#d4d4d4` |
| Selection | `#264f78` |
| Alt row | `#252526` |
| Header | `#2d2d2d` |
| Button bg | `#333333` |
| Bar fill | `#4ec9b0` (mint/green) |
| Error | `#f44747` (red) |
| Progress | `#0e639c` (blue) |
| Trough | same as background `#1e1e1e` |

## ttk.Style config (clam theme)

```python
s = ttk.Style(root)
s.theme_use("clam")
s.configure(".", background="#1e1e1e", foreground="#d4d4d4")
s.configure("Treeview", fieldbackground="#1e1e1e")
s.map("Treeview", background=[("selected", "#264f78")])
s.configure("TButton", background="#333", foreground="#d4d4d4")
s.map("TButton", background=[("active", "#264f78")])
s.configure("TProgressbar", background="#0e639c", troughcolor="#1e1e1e")
```

## Real-time countdown (HH:MM:SS)

```python
def _fmt(td: timedelta) -> str:
    neg = "-" if td.total_seconds() < 0 else ""
    s = abs(int(td.total_seconds()))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{neg}{h:02d}:{m:02d}:{s:02d}"
```

## Bar chart padding (anti-clipping)

```python
cw = canvas.winfo_width() or 600
ch = canvas.winfo_height() or 100
pad_l, pad_r = 24, 24
pad_t, pad_b = 22, 24
draw_w = max(cw - pad_l - pad_r, 100)
draw_h = max(ch - pad_t - pad_b, 40)
gap = 3
bw = max((draw_w - gap * (n + 1)) // n, 24)
```

## Subprocess from dashboard

Important: the script lives in `scripts/` but must run from project root.

```python
ROOT = Path(__file__).resolve().parent.parent  # scripts/ => project root
subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=ROOT)
```

## Treeview with alternating rows

```python
tree.tag_configure("odd", background="#252526")
tree.tag_configure("even", background="#1e1e1e")
for i, item in enumerate(items):
    tag = "odd" if i % 2 else "even"
    tree.insert("", tk.END, tags=(tag,), values=(...))
```

## Schedule bar pattern (cron countdown)

Show next run time, last run timestamp, progress bar through 24h window, and green/red dot:

```python
def _tick(self):
    now = datetime.now(timezone.utc)
    nxt = self._next_run(hour, minute)
    # show nxt - now as HH:MM:SS
    self.countdown_var.set(f"→ {name} in {_fmt(nxt - now)}")
    # progress through 24h window
    win_start = nxt - timedelta(days=1)
    pct = (now - win_start).total_seconds() / (nxt - win_start).total_seconds() * 100
    self.progress["value"] = min(max(pct, 0), 100)
    # green dot if today's file exists, red otherwise
    self.dot_canvas.itemconfig(self.dot, fill=GREEN if scores_exist else RED)
    self.master.after(1_000, self._tick)
```

## Date-jump data consistency

When user loads historical scores, ensure rerank uses *that* date:

```python
# In rerank:
ds = self._score_data["date"]        # NOT _last_scores().stem
sp = FACTOR_DIR / f"factor_scores_{ds}.json"
result = apply_factor_scores_to_basket(nova, date_str=ds, ...)
self._load_scores(sp)                # sync _score_map with re-rank