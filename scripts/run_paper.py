#!/usr/bin/env python3
"""Paper trading with live dashboard."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vesper.secrets import load_secrets
from vesper.engine import TradingEngine
from vesper.dashboard.app import VesperDashboard


def main():
    load_secrets()

    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-25s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/vesper.log"),
        ],
    )

    print("=" * 55)
    print("  VESPER 2.0 — Market-Hours Trading System")
    print("  Mode: PAPER")
    print("=" * 55)

    engine = TradingEngine("config/settings.yaml")
    dash = VesperDashboard(engine, engine.config)
    engine.dashboard = dash
    dash.run()


if __name__ == "__main__":
    main()