# Signal Mine v4 + Interaction Lab v2 — July 8, 2026

## Signal Mine v4 (10 signals, 21d horizon, 502 tickers, 233 steps)

New signals tested: gap (raw, median-5d, vol-20d), overnight/intraday decomposition,
RSI-14, MA cross, channel breakout, downside deviation ratio, size-decile lead-lag.

| Signal | IC IR | Direction | Verdict |
|---|---|---|---|
| **channel_breakout** | **-0.151** | SHORT | Mean reversion at channel level — stocks at 20d high underperform |
| **gap_vol_20d** | **+0.098** | LONG | Volatile overnight gaps predict returns (amplitude, not direction) |
| rsi_14 | -0.099 | SHORT | High RSI underperforms (already captured by mean_reversion) |
| downside_dev_ratio | -0.089 | SHORT | Asymmetric vol (already captured by mean_reversion) |

**Actionable**: channel_breakout is genuinely new — mean reversion measured from 20d high
instead of 5d or 10d return. Different angle, same theme, IC IR additive.

## Interaction Lab v2 (233 steps, 21d horizon)

| Interaction | ΔIC IR | Direction |
|---|---|---|
| **gv × cb** (gap_vol × channel_breakout) | **+0.071** | Synergistic |
| ir × mr (intraday × mean_reversion) | **-0.154** | Destructive — cancel when both present |

| Signal | IC IR |
|---|---|
| gv_x_cb (gap_vol × channel_breakout) | +0.144 |
| sector_momentum | +0.161 |
| mkt_cap_decile | -0.269 |
| channel_breakout (confirmed) | -0.142 |
| gap_vol (confirmed) | +0.104 |

**Key finding**: gv×cb product term (+0.144 IR) is stronger than either parent alone.
**Destructive**: intraday_range × mean_reversion ΔIC IR = -0.154 — never equal-weight ir and mr.

## SEC Fundamentals Limitation

Agent 2 mined sec_facts — Operating Margin IR -3.14, ROE -2.15. **All from 2-3 months
of data (April-June 2026). Pre-April coverage is 15 stocks/date. IC IR unreliable.**
Do not build SEC factors until 2+ years of broad OHLCV coverage.
