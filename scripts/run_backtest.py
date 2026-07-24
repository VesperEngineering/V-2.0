#!/usr/bin/env python3
"""Backtest runner. No API keys needed."""

import logging
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from vesper.secrets import load_secrets
from vesper.data.feed import create_feed
from vesper.execution.broker import PaperBroker, OrderSide
from vesper.risk.limits import RiskLimits
from vesper.strategy.base import SignalAction
from vesper.strategy.momentum import MomentumStrategy
from vesper.strategy.ml_model import MLModelStrategy


STRATEGIES = {
    "momentum": MomentumStrategy,
    "ml_model": MLModelStrategy,
}


def rebalance_interval_minutes(sessions: int) -> int:
    """Convert daily-session cadence to the strategy's minute interval."""
    return sessions * 24 * 60


def resolve_strategy_name(config_name: str, override: str | None) -> str:
    return override or config_name


def apply_portfolio_overrides(params: dict, top_n: int | None, exit_rank: int | None) -> dict:
    updated = dict(params)
    if top_n is not None:
        updated["top_n"] = top_n
    if exit_rank is not None:
        updated["exit_rank"] = exit_rank
    return updated


def execute_signals(broker, risk, signals, prices: dict[str, float], daily_pnl: float):
    """Apply each signal against the broker state that exists at that moment."""
    for sig in signals:
        positions = broker.get_positions()
        account = broker.get_account()
        price = prices.get(sig.symbol, 0)
        res = risk.check_signal(sig, account, positions, price, daily_pnl)
        if res.approved and sig.action == SignalAction.BUY:
            broker.submit_order(sig.symbol, res.adjusted_qty or 1, OrderSide.BUY)
        elif sig.action in (SignalAction.SELL, SignalAction.CLOSE):
            broker.close_position(sig.symbol)


def main():
    parser = argparse.ArgumentParser(description="Run a no-submit backtest")
    parser.add_argument(
        "--rebalance-days",
        type=int,
        choices=(1, 5, 10),
        help="Override the model rebalance cadence for this run only",
    )
    parser.add_argument(
        "--strategy",
        choices=tuple(STRATEGIES),
        help="Override the configured strategy for this no-submit run only",
    )
    parser.add_argument("--top-n", type=int, choices=(5, 10),
                        help="Override ML portfolio breadth for this no-submit run only")
    parser.add_argument("--exit-rank", type=int, choices=(10, 20, 50),
                        help="Override ML exit rank for this no-submit run only")
    args = parser.parse_args()

    load_secrets()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(message)s")
    log = logging.getLogger("backtest")

    with open("config/settings.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    with open("config/universe.yaml", encoding="utf-8") as f:
        universe = yaml.safe_load(f)["universe"]

    feed = create_feed(config)
    broker = PaperBroker(100_000)
    risk = RiskLimits(config)

    strat_name = resolve_strategy_name(config["strategy"]["name"], args.strategy)
    strat_cls = STRATEGIES.get(strat_name)
    if strat_cls is None:
        log.error("Unknown strategy: %s", strat_name)
        sys.exit(1)
    params = apply_portfolio_overrides(
        config["strategy"]["params"], args.top_n, args.exit_rank,
    )
    if args.rebalance_days:
        params["rebalance_interval"] = rebalance_interval_minutes(args.rebalance_days)
    strat = strat_cls(params)

    lookback = 120  # Need >50 days for SMA_50 to be valid on first rebalance
    end = datetime.now()
    start = end - timedelta(days=lookback)
    log.info("Fetching %d symbols (%s -> %s)...", len(universe), start.date(), end.date())
    data = feed.get_bars(universe, start, end)
    log.info("Got %d symbols", len(data))

    dates = sorted(set().union(*(df.index for df in data.values())))

    previous_equity = 100_000
    for i, d in enumerate(dates):
        cur = {s: df[df.index <= d] for s, df in data.items()}
        prices = {s: float(df["close"].iloc[-1])
                  for s, df in cur.items() if not df.empty}
        broker.update_prices(prices)
        positions = broker.get_positions()
        account = broker.get_account()
        daily_pnl = account["equity"] - previous_equity

        signals = list(strat.generate_signals(cur, positions,
                                          d.to_pydatetime()))
        if signals:
            log.info("Day %s signals: %d", d.date(), len(signals))
            for sig in signals[:3]:
                log.info("  %s %s strength=%.2f", sig.symbol, sig.action.name, sig.strength)

        execute_signals(broker, risk, signals, prices, daily_pnl)

        eq = broker.get_account()["equity"]
        previous_equity = eq
        if i % 10 == 0:
            log.info("Day %d/%d  equity=$%s  P&L=$%s",
                     i + 1, len(dates), f"{eq:,.0f}", f"{eq - 100_000:+.0f}")

    final = broker.get_account()
    ret = (final["equity"] - 100_000) / 100_000
    log.info("=" * 50)
    log.info("BACKTEST COMPLETE")
    log.info("  Final equity: $%s", f"{final['equity']:,.2f}")
    log.info("  Return:       %+.2f%%", ret * 100)
    log.info("  Cash:         $%s", f"{final['cash']:,.2f}")
    log.info("=" * 50)


if __name__ == "__main__":
    main()