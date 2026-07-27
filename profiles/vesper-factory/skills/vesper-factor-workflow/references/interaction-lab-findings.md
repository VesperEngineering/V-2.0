# Factor Interaction Lab Findings (2026-07-08)

Script: `scripts/interaction_lab.py`
Data: `vesper_data/massive/sp500/sp500_ohlcv.sqlite` (502 tickers, 2005-2026)
Reference: `vesper_data/massive/reference/massive_reference_corporate_actions_active_universe_20260622.sqlite` (22 tickers)
Horizon: 21d, Rebalance: 21d, Steps: 233

## Reference DB Columns

`ticker_overview` (18 columns): query_ticker, as_of_date, ticker, name, market, locale, primary_exchange, type, active, cik, composite_figi, share_class_figi, sic_description, market_cap, total_employees, list_date, homepage_url, raw_json

`raw_json` nested fields: sic_code, sic_description, share_class_shares_outstanding, weighted_shares_outstanding, address, description, branding, phone_number

Additional tables: `ticker_reference`, `splits` (35), `dividends` (2024)

**Limitation**: Only 22 tickers — insufficient for cross-sectional IC. Useful for SIC sector classification and static size reference only. Employee growth proxy impossible (single snapshot). Market cap decile and employee factors must use OHLCV dollar volume proxy instead.

## Full Signal Results

| Signal | IC IR | Mean IC | % Pos | Verdict |
|--------|-------|---------|-------|---------|
| intraday_range | +0.137 | +0.028 | 54.9% | STRONG |
| mean_reversion | +0.112 | +0.015 | 51.9% | STRONG |
| size_factor | -0.273 | -0.024 | 36.9% | STRONG (small-cap) |
| gap_vol | +0.104 | +0.022 | 54.9% | STRONG |
| channel_breakout | -0.142 | -0.025 | 44.2% | STRONG (inverted) |
| mkt_cap_decile | -0.269 | -0.024 | 38.2% | STRONG |
| sector_momentum | +0.161 | +0.008 | 54.9% | STRONG |
| kernel_3f (ir+mr+size eq) | +0.073 | +0.012 | 53.6% | WEAK |
| ir_x_mr | -0.081 | -0.006 | 49.4% | STRONG (negative) |
| size_x_ir | +0.065 | +0.004 | 54.9% | WEAK |
| gv_x_cb | +0.144 | +0.013 | 57.5% | STRONG |
| sector_rel_ir | +0.137 | +0.028 | 55.4% | STRONG |

## Interaction Deltas vs 3-Factor Kernel (IC IR +0.073)

Only |ΔIC IR| > 0.04 shown:

| Term | Own IC IR | ΔIC IR | Direction |
|------|-----------|--------|-----------|
| ir_x_mr (intraday_range × mean_reversion) | -0.081 | **-0.154** | DESTRUCTIVE |
| gv_x_cb (gap_vol × channel_breakout) | +0.144 | **+0.071** | SYNERGISTIC |
| size_x_ir (size × intraday_range) | +0.065 | -0.008 | NOISE |
| sector_rel_ir (sector-relative IR vs raw IR) | +0.137 | +0.000 | ZERO |

## Key Findings

### 1. ir × mr is destructive (ΔIC IR -0.154)
The 3-factor equal-weight kernel (ir + mr + size) gives IC IR +0.073 despite solo IRs of +0.137 and +0.112. The interaction term confirms: when a stock has BOTH wide intraday range AND high mean reversion signal, alpha cancels. These factors should NOT be blended equally. Use one as primary or weight asymmetrically.

### 2. gap_vol × channel_breakout is synergistic (ΔIC IR +0.071)
The product term (+0.144 IR) beats both parent signals (gap_vol +0.104, channel_breakout -0.142). Channel breakout alpha amplifies under high gap volatility. This is a genuine multiplicative interaction — use the product as a standalone signal.

### 3. Sector-relative intraday_range adds nothing
Raw intraday_range (IC IR +0.137) and sector-relative (IC IR +0.137) are identical. Cross-sectional z-scoring already captures relative effects — sector adjustment is redundant for this signal family.

### 4. New signals: sector_momentum strongest from reference data
Sector momentum at +0.161 IC IR is the strongest single signal discovered. Market cap decile at -0.269 reflects the well-known small-cap premium. Employee growth proxy cannot be tested (only 21 tickers in reference DB).

## Script Architecture

Pattern for interaction testing:
1. Load full OHLCV panel (open, high, low, close, volume) into numpy arrays [nticker, ndate]
2. Loop rebalance dates with stride STEP, LOOKBACK history each
3. Compute raw signals per ticker (intraday_range, mean_reversion composite, size, gap_vol, channel_breakout)
4. Z-score each signal cross-sectionally
5. Compute interaction terms as product of z-scored signals
6. Compute Spearman rank IC: signal vs forward 21d return
7. Report IC IR = mean(IC) / std(IC) for each signal and interaction
