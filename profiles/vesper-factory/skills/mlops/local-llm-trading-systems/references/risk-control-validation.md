# Position-Risk Controls: Validation Before Broker Integration

Use this note when adding stops, time exits, crash breakers, or other position-manager controls to an automated trading system.

## Safe implementation sequence

1. Build a **pure, broker-free risk engine** first. Inputs are policy parameters and price bars; outputs are deterministic exit decisions.
2. Unit-test execution semantics before historical testing.
3. Run a report-only historical comparison against the actual reconstructable strategy.
4. Keep broker, account, scheduler, and deployed risk settings unchanged until evidence supports a specific policy.
5. Only then design the broker integration around confirmed fills and reconciliation.

## Execution semantics that must be explicit

- A resting stop crossed intraday may fill at the stop price in a daily-bar approximation.
- A gap through a stop must fill at the opening price, not the unreachable stop price.
- When multiple downside thresholds are active, the **highest threshold triggers first** as price falls. Do not evaluate a lower crash threshold before a higher fixed stop.
- Overnight-gap and intraday-crash rules are distinct. Avoid conditions such as `change <= -8% or change <= -10%`, which collapse into one rule.
- A time stop evaluated at a session close exits at the next tradable open. Do not backtest it as an exit at the close used to make the decision.
- Require the complete holding window and valid positive OHLC inputs; fail closed rather than returning partial evidence.

## Backtest contract

- Compute signals using data available through the signal close.
- Enter at the next session open to avoid look-ahead.
- Compute ATR only from bars known before entry.
- Apply realistic round-trip costs to every position, including early exits.
- After an early exit, keep that allocation in cash until the strategy's next scheduled rebalance unless the real strategy explicitly reallocates it.
- Build a daily marked-to-market equity path. Rebalance-point returns alone understate intraperiod drawdowns.
- Report each exit reason and rate, tail returns, Sharpe, CAGR/annualized return, and daily max drawdown.
- Compare controls independently (`ATR only`, `time only`, `gap only`) and in combinations so one harmful tier cannot hide behind another.
- State data limitations explicitly: current-constituent universes and current sector maps create survivorship/classification bias in long historical tests.

## Historical-data admission gate

Do not emit primary performance statistics unless all of these gates pass:

- **Split-adjusted OHLC:** raw bars can turn stock splits into false gaps, crashes, factor values, returns, and stop events. Preserve raw bars separately for audit, but use split-adjusted bars for signal, ATR, and trigger logic.
- **Point-in-time membership:** selecting today's constituents throughout history is a survivor-cohort diagnostic, not strategy evidence. Include removed, renamed, bankrupt, and delisted securities during their actual membership intervals.
- **Point-in-time classification:** a current sector map leaks future classification and excludes former constituents. Do not silently infer GICS from SIC when the strategy contract requires GICS; treat an explicit proxy as a separate sensitivity, never the primary replay.
- **As-of enforcement:** every signal and volatility query must enforce `observation_date <= signal_cutoff` and deterministic chronological ordering. A factor helper that accepts but ignores an as-of date is unsafe for historical replay.
- **Corporate-action and identifier integrity:** bound reused symbols and aliases to the correct security lifecycle. A provider returning old history for a reused ticker is not enough without membership dates and identifier provenance.

If any gate fails, stop before calculating Sharpe, CAGR, or drawdown. Produce a readiness report listing the failed gates instead of a plausible-looking backtest.

Daily OHLC cannot determine whether an entry-day low occurred before or after a 09:35 entry. Either use minute bars for entry sessions or report explicit bounds (ignore the entry-day touch versus pessimistically trigger it). Never hide this ambiguity inside one point estimate.

Freeze and pre-register the primary stop specification before inspecting outcomes: ATR estimator/lookback, multiplier, floor, ceiling, fallback, time-stop day, gap threshold, intraday threshold, cooldown, rebalance cadence, costs, and slippage. Conflicting design documents are a blocker, not a parameter sweep opportunity.

Use paired ablations and block/stationary bootstrap confidence intervals on daily return differences. Report drawdown duration/recovery, CVaR or expected shortfall, cash exposure, turnover, stop frequency by tier/regime, gap slippage, cooldown effects, and post-stop opportunity cost. The stop overlay may be incremental in-sample evidence when the underlying factors were selected on the same history; require forward paper confirmation.

## Production deployment gates

Do not place protective orders from an intended notional buy. First obtain the confirmed fill and reconcile the resulting position quantity.

The production position manager must handle:

- deterministic, namespaced `client_order_id` ownership; never cancel every open order during rebalance because that removes protective orders;
- the invariant that every broker-confirmed long position has exactly one protective closing-order lineage covering the confirmed remaining quantity;
- rejected, cancelled, late, and partially filled entry orders;
- fractional-share quantities, decimal precision, and broker time-in-force restrictions (for example, do not assume fractional GTC stops are supported);
- partial stop fills, stop replacement, add-on buys, and position reductions;
- rebalance sells, protective stops, and emergency exits racing one another;
- one serialized command path for rebalance and all exits, so two independent writers cannot liquidate the same position;
- deterministic idempotency keys and recovery of timeout-ambiguous submissions before retrying;
- broker trade-event consumption plus startup and periodic REST reconciliation for fills, rejects, cancels, replacements, and externally changed positions;
- broker positions and orders as the operational authority, with local durable transactional events as the audit journal; a mutable JSON registry may be a dashboard projection only;
- market calendars, exchange time zones, DST, holidays, early closes, and durable session counters;
- stale, missing, crossed, halted, or out-of-session market data with explicit fail-closed behavior;
- singleton leases so duplicate schedulers cannot issue duplicate commands;
- completion based on reconciled broker quantity, never merely on order acceptance.

A fast monitor should primarily reconcile health and produce Tier-2/alert signals. It must not be an independent competing liquidation writer beside broker-resting stops and rebalance logic.

## Design principle

Risk controls are not automatically beneficial because they reduce individual losses. Promote them only when they improve the strategy's risk-adjusted evidence without destroying the intended holding-horizon edge.