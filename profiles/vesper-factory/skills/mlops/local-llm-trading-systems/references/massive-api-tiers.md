# Massive API Plan Tiers and Real-Time Data Access

## Plan Comparison (as of July 2026)

| Plan | Price | Real-time? | WebSockets | Key Data |
|---|---|---|---|---|
| Basic | Free | End-of-day only | No | Minute aggregates, 2yr history, 5 calls/min |
| Starter | $29/mo | **15-min delayed** | Yes | Minute + second aggregates, 5yr history |
| Developer | $79/mo | **15-min delayed** | Yes | + trades, 10yr history |
| **Advanced** | **$199/mo** | **Real-time** | Yes | + quotes, financials, 20yr history, unlimited calls |

## Critical Notes

- **Only Advanced is real-time.** Starter and Developer are 15-minute delayed — unusable for intraday swing trading.
- User is on Advanced ($199/mo) as of July 2026.
- Unlimited API calls on all paid tiers.
- "Non-pro" individual use only on personal plans.

## WebSocket Endpoints

| Endpoint | URL | Access |
|---|---|---|
| Real-time | `wss://socket.massive.com/stocks` | Advanced only |
| Delayed (15min) | `wss://delayed.massive.com/stocks` | Starter+ |

## Minute Aggregates (AM) — Primary for Swing Trading

Subscribe to all tickers: `{"action":"subscribe", "params":"AM.*"}`

Response fields:
- `sym`: ticker symbol
- `o/h/l/c`: OHLC for the minute
- `v`: volume, `av`: accumulated volume
- `vw`: tick VWAP, `a`: today's VWAP
- `op`: official opening price
- `s/e`: start/end timestamps (Unix ms)
- `z`: average trade size

## Additional Data Products

| Product | Price | Use Case |
|---|---|---|
| Benzinga News | $99/mo add-on | Real-time financial news + analyst ratings (LLM context layer input) |
| NYSE Order Imbalances | $49/mo | Real-time buy/sell pressure at auctions |
| Financials & Ratios | $29/mo standalone or included in Advanced | Company fundamentals |

## Free Alternatives for Paper Trading Phase

- **SEC EDGAR**: Real-time filings, free, no API key
- **RSS feeds**: Major financial outlets, free
- **Reddit API**: Rate-limited but free
- **Wikipedia pageviews**: Free, no rate limit (already used in Vesper)
