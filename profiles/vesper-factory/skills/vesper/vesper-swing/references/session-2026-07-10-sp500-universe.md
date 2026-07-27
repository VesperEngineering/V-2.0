# S&P 500 Universe Expansion — 2026-07-10

## Durable implementation pattern

- `massive.universe: sp500` must produce explicit subscriptions, never `AM.*`.
- Source current constituents from Wikipedia’s S&P 500 table using the `Symbol` column.
- Use a stdlib `HTMLParser` implementation rather than introducing `lxml` solely for one table.
- Normalize uppercase tickers, preserve dots for Massive class-share symbols such as `BRK.B`, dedupe in source order, and validate 450–550 unique symbols.
- Cache the last valid list at `data/sp500_symbols.json`; use it only when live retrieval fails and it independently passes validation.
- Track a validated snapshot at `src/data/sp500_symbols.json` as the final fresh-checkout/offline fallback. Resolution order is live Wikipedia → writable runtime cache → bundled snapshot; validate all three identically.
- If none of live, runtime cache, or bundled snapshot validates, abort startup. Never silently broaden to all-market.
- Build Massive params as `AM.<ticker>` for every symbol.

## Session evidence

- Live Wikipedia load returned 503 ticker symbols; multiple share classes explain counts above 500.
- Generated 503 explicit subscriptions with no `AM.*` wildcard.
- A 70-second Massive smoke test authenticated and delivered more than 200 S&P bars without warnings.
- Minute-bar database count increased to 633; trades remained zero because execution was disabled.

## User-facing operating rule

The desktop icon should remain one-click. The user prefers S&P 500 breadth over a tiny watchlist, but not a raw whole-market firehose. If an old process is already running, restart it after universe/config changes so the new constituent list takes effect.
