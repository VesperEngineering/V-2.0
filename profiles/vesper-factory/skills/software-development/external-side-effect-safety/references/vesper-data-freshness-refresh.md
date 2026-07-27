# Vesper Data Freshness Refresh: Source Identity and Evidence

**Context:** Vesper, observed 2026-07-17. This is a project-specific reference; verify paths and provider configuration before reuse.

## Surface map

| Surface | Provider / identity | Operational role | Freshness evidence | Authority boundary |
|---|---|---|---|---|
| Active daily OHLCV | `alpaca_market_data_daily_bars_raw` | Configured active 30-symbol operational source | `backend/app/services/active_ohlcv_refresh.py` plan/result and local freshness actionability receipt | Explicit guarded active-source refresh approval; market-data GETs plus validated local SQLite insert only. No broker/account/order calls. |
| Macro cache | `yahooquery` using `^VIX`, `^TNX`, `CL=F`, with configured USD fallback | Active macro cache | `deploy/data/cache_macro_yq.parquet`, local freshness actionability receipt | Explicit macro refresh scope; cache refresh only. No source switch or trading authority. |
| Massive OHLCV | `Massive OHLCV` | Non-active / staged research evidence surface | `operator_data_check_<date>_post_ingest.md` | Do not infer admission from active-source freshness. The adapter enforces a separate exact approval contract; generic "approved" language is insufficient. |

## Guarded active OHLCV sequence

1. Read-only plan from `plan_active_ohlcv_refresh`: require `refresh_required`, bounded date window, expected session, row count, and active-universe count.
2. Run credential-presence preflight; log only required names and source class, never values.
3. Execute `refresh_active_ohlcv` only if the plan exactly matches the approved window. Record provider, request range, row counts, validation state, transaction state, and post-write date coverage.
4. Replan read-only. Require `fresh`, zero expected missing rows, and all active symbols through the required session.
5. Generate canonical local-freshness actionability receipt and structural validator receipt. Read both the actionability decision and validator status.
6. Compare macro and Massive receipts separately. Neither a fresh active Alpaca source nor a fresh macro cache makes Massive admitted or active.
7. Preserve source-of-truth tracker updates and receipt checksums. Do not push without separate authorization.

## Vesper-specific pitfalls

- `operator_data_check` identifies Massive in its receipt; it must not be reported as the active operational OHLCV source.
- A local actionability `PASS` can route to a no-network next task; it is not paper-order permission.
- Macro refresh is an existing YahooQuery cache path. Its fallback symbol selection must be reported as configured behavior, not labeled a provider switch.
- The Massive adapter approval boundary prohibits by default: active SQLite mutation, provider switching, Qlib export/runs, model training/promotion, broker/account/order access, scheduler/risk/target changes, secrets disclosure, overwriting staged artifacts, and generated-artifact commits. Read the current boundary module before requesting the exact attestation.
