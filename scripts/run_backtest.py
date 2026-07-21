#!/usr/bin/env python3
"""Backtest runner. No API keys needed."""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from vesper.secrets import load_secrets
from vesper.data.feed import YFinanceFeed
from vesper.execution.broker import PaperBroker, OrderSide
from vesper.risk.limits import RiskLimits
from vesper.strategy.base import SignalAction
from vesper.strategy.momentum import MomentumStrategy


def main():
    load_secrets()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(message)s")
    log = logging.getLogger("backtest")

    with open("config/settings.yaml") as f:
        config = yaml.safe_load(f)
    with open("config/universe.yaml") as f:
        universe = yaml.safe_load(f)["universe"]

    feed = YFinanceFeed()
    broker = PaperBroker(100_000)
    risk = RiskLimits(config)
    strat = MomentumStrategy(config["strategy"]["params"])

    end = datetime.now()
    start = end - timedelta(days=90)
    log.info("Fetching %d symbols...", len(universe))
    data = feed.get_bars(universe, start, end)
    log.info("Got %d symbols", len(data))

    dates = sorted(set().union(*(df.index for df in data.values())))

    for i, d in enumerate(dates):
        cur = {s: df[df.index <= d] for s, df in data.items()}
        positions = broker.get_positions()
        account = broker.get_account()
        prices = {s: float(df["close"].iloc[-1])
                  for s, df in cur.items() if not df.empty}
        broker.update_prices(prices)

        for sig in strat.generate_signals(cur, positions,
                                          d.to_pydatetime()):
            price = prices.get(sig.symbol, 0)
            res = risk.check_signal(sig, account, positions, price,
                                    account["equity"] - 100_000)
            if res.approved and sig.action == SignalAction.BUY:
                broker.submit_order(sig.symbol, res.adjusted_qty or 1,
                                    OrderSide.BUY)
            elif sig.action in (SignalAction.SELL, SignalAction.CLOSE):
                broker.close_position(sig.symbol)

        eq = broker.get_account()["equity"]
        if i % 10 == 0:
            log.info("Day %d/%d  equity=$%,.0f  P&L=$%+,.0f",
                     i + 1, len(dates), eq, eq - 100_000)

    final = broker.get_account()
    ret = (final["equity"] - 100_000) / 100_000
    log.info("=" * 50)
    log.info("BACKTEST COMPLETE")
    log.info("  Final equity: $%,.2f", final["equity"])
    log.info("  Return:       %+.2f%%", ret * 100)
    log.info("  Cash:         $%,.2f", final["cash"])
    log.info("=" * 50)


if __name__ == "__main__":
    main()