#!/usr/bin/env python3
"""Paper trading with live dashboard."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def run_session(engine, root, dashboard):
    stopped = False

    def stop_and_close():
        nonlocal stopped
        if not stopped:
            stopped = True
            try:
                engine.stop()
            finally:
                dashboard.close()

    root.protocol("WM_DELETE_WINDOW", stop_and_close)
    engine.start()
    try:
        root.mainloop()
    finally:
        if not stopped:
            engine.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the Vesper paper-trading engine with the local dashboard",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/settings.yaml"),
        help="Runtime configuration path (default: config/settings.yaml)",
    )
    args = parser.parse_args(argv)

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

    import tkinter as tk

    from vesper.dashboard.app import DashboardApp
    from vesper.engine import TradingEngine
    from vesper.secrets import load_secrets

    load_secrets()
    engine = TradingEngine(str(args.config))
    root = tk.Tk()
    dashboard = DashboardApp(root)
    run_session(engine, root, dashboard)


if __name__ == "__main__":
    main()
