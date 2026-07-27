# Vesper Dashboard Design Reference

## Layout: Monitor View (1920×1080)
Derived from Bloomberg Terminal's "maximum information density" (Tufte) principle and quant finance color palettes research (Phoenix Strategy Group, 2025).

## Color Palette (6 colors max)
| Role | Color | Hex |
|---|---|---|
| Background | Near-black | #1e1e1e |
| Foreground (text) | White/grey | #d4d4d4 |
| Alt row | Dark grey | #252526 |
| Selection | Blue | #264f78 |
| Positive (green) | Teal | #4ec9b0 |
| Negative (red) | Crimson | #f44747 |
| Headers | Dark grey | #2d2d2d |
| Progress bar | Blue | #0e639c |

## Font Hierarchy
| Size | Usage |
|---|---|
| 7px | Status dot labels, canvas text |
| 8px | Cron schedule, secondary data |
| 9px | Main data text, buttons, tree values |
| 10px | Section headers, countdown |
| 11px | Used for bold emphasis |

## Column Schema (10 columns)
1. Ticker (65px, left-aligned)
2. Trend (55px, center) — Unicode sparkline ▁▂▃▄▅▆▇
3. Score (90px, center) — color-encoded green/red
4. Entropy (90px, center)
5. Hurst (90px, center)
6. Vol (90px, center) — realized_vol_z60_lag1
7. Sent (90px, center) — sentiment z-score
8. Insider (90px, center)
9. Massive (90px, center) — market cap + momentum
10. Top (50px, center) — factor with highest z-score contribution

## Schedule: 8 Cron Jobs
Each row: status dot → job name (16ch) → next HH:MM (6ch) → countdown HH:MM:SS (11ch bold) → progress bar (flex) → last run (18ch)

Day constraints:
- `mon`: only Monday (Research Engineer)
- `mon-fri`: weekdays (Alpaca, Portfolio)
- `daily`: every day (all others)
- Weekend: grey dots, inactive

## Known Patterns

### Editing the dashboard
- `patch` tool mangles the compact dashboard → use `sed -i` for targeted edits or Python `open-read-str.replace-write` for multi-line changes
- Do NOT commit with pre-commit hooks active — ruff-format expands 399-line compact style to 800+ lines. Use `--no-verify` for GUI commits, or accept the reformatting

### Python venv conflict
- Terminal `python` resolves to `veyr-music/heartlib/.venv` (Python 3.10, broken numpy)
- Always use full path for cron scripts and pytest:
  `/c/Users/bgonn/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe`

### Unicode Sparklines
The sparkline column uses Unicode block characters at 7 intensity levels:
```python
blocks = "▁▂▃▄▅▆▇"
idx = min(int((value - min) / (max - min) * 6), 6)
```
Only works when 2+ days of score history exist. Single-day shows "—".