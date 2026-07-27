# Data Grab Levels for Quant Systems

When a user asks "what level of data grab do you recommend?", audit existing data before answering. The correct default is almost always **Level 0**.

## Level 0 — Use existing data (default)

**When to use:** Local data already covers the required history and symbols.

**Example:** v20 has 190 GB of Massive data (SP500 SQLite: 502 tickers, 2003–2026). Asking for more raw data is bloat. The bottleneck is model quality, not data volume.

**Action:** Point out what already exists, its coverage, and why more data won't help. Redirect to:
- Split adjustment (raw → adjusted prices)
- Total-return adjustment (dividends)
- Model overfitting fixes (chronological train/test split)
- Portfolio construction / risk management

## Level 1 — Periodic refresh script

**When to use:** Local data goes stale (>2 trading days behind) and needs lightweight updates.

**Action:** Write a small script that pulls newer daily bars from Massive S3/API when the local SQLite is behind. No new historical data, just gap-filling.

## Level 2 — New data category

**When to use:** A specific gap blocks strategy development (e.g., no intraday, no fundamentals, no alt data).

**Action:** Evaluate whether the new category is actually needed for the current model. If yes, implement a minimal collector. If no, stay at Level 0.

## Level 3+ — Scale / infrastructure

**When to use:** The system is live, profitable, and a specific data advantage is identified.

**Action:** This is rare. Most quant systems fail from model overfitting or poor execution, not from missing data.

## Key lesson

Data volume is not alpha. A simple model on clean, well-understood data beats a complex model on noisy, excessive data. Always ask: "What can we build with what we have?" before asking for more.
