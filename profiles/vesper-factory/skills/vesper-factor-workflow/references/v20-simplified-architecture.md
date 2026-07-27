# V20 Simplified Architecture Notes

> Session: 2026-07-22. V20 is the lean Desktop copy of Vesper (C:\Users\bgonn\Desktop\v20), distinct from the full D:/vesper estate.

## Data Pipeline

- **Primary source:** Massive S3/REST → local SQLite (`vesper/data/massive/sp500/sp500_ohlcv.sqlite`).
- **Feed adapter:** `MassiveFeed` in `vesper/data/feed.py` reads from local SQLite, not Yahoo Finance.
- **Do not use raw prices for features** — the SP500 store is raw/unadjusted. Split adjustment must be applied before feature computation or ranking.

## Model Pipeline

- **Configured default:** `ml_model` strategy in `config/settings.yaml`.
- **Expected artifact:** `models/xgb_ranker.json` (XGBoost regressor).
- **Reality check:** The D:/vesper production estate has PyTorch transformer artifacts, not XGBoost. V20 trains its own XGBoost from scratch via `scripts/train_model.py`.
- **Training gotcha:** In-sample IC of 0.95+ signals severe overfitting. Use chronological train/test split (e.g., train 2003–2020, test 2021–2026) and report out-of-sample IC only.

## Strategy Factory

- `vesper/engine.py` wires `ml_model` → `MLModelStrategy` and `momentum` → `MomentumStrategy`.
- Missing artifact raises `FileNotFoundError` with clear message: "Run: python scripts/train_model.py first."

## Dashboard

- `vesper/dashboard/app.py` — Tkinter monitor view, polls `data/engine_state.json` every 2s.
- Dark flat theme. 5 panels: Account, Risk, Portfolio, Signals, Orders.
- Launch: `python scripts/dashboard.py`

## Key Files

| File | Role |
|------|------|
| `config/settings.yaml` | Provider selection (`massive`), strategy name, risk params |
| `vesper/data/feed.py` | `MassiveFeed` + `create_feed` factory |
| `scripts/train_model.py` | XGBoost trainer from SP500 SQLite |
| `scripts/dashboard.py` | Dashboard launcher |
| `AGENTS.md` | Project constitution (skills + codegraph mandatory) |

## Boundaries

- `/data` folder is read-only for agents — do not modify Massive SQLite stores.
- Credentials (Massive REST/S3) via environment variables only; never hardcode.
