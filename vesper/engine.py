"""Core trading engine. Ties everything together."""

import logging
import threading
from datetime import datetime, timedelta

import yaml

from vesper.audit.logger import AuditLogger
from vesper.data.calendar import MarketCalendar
from vesper.data.feed import create_feed
from vesper.data.storage import DataCache
from vesper.execution.broker import OrderSide, create_broker
from vesper.execution.orders import OrderTracker
from vesper.notify import Notifier
from vesper.risk.circuit_breaker import CircuitBreaker
from vesper.risk.limits import RiskLimits
from vesper.risk.monitor import RiskMonitor
from vesper.scheduler.engine import MarketScheduler
from vesper.secrets import resolve_env_refs
from vesper.state import StateManager
from vesper.strategy.base import SignalAction
from vesper.strategy.momentum import MomentumStrategy
from vesper.strategy.ml_model import MLModelStrategy

logger = logging.getLogger("vesper.engine")


class TradingEngine:
    def __init__(self, config_path: str = "config/settings.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        self.config = resolve_env_refs(self.config)

        self.calendar = MarketCalendar(
            self.config.get("market", {}).get("timezone", "US/Eastern"))
        self.feed = create_feed(self.config)
        self.cache = DataCache(
            self.config.get("data", {}).get("cache_db", "data/market_cache.db"))
        self.broker = create_broker(self.config)
        self.risk_limits = RiskLimits(self.config)
        self.circuit_breaker = CircuitBreaker(
            self.config.get("risk", {}).get("max_daily_loss", -2000))
        self.risk_monitor = RiskMonitor()
        self.audit = AuditLogger(
            self.config.get("audit", {}).get("log_dir", "logs"))
        self.state_mgr = StateManager()
        self.order_tracker = OrderTracker(self.broker, poll_seconds=2)
        self.notifier = Notifier(self.config)

        with open("config/universe.yaml") as f:
            self.universe: list[str] = yaml.safe_load(f).get("universe", [])

        strat_cfg = self.config.get("strategy", {})
        name = strat_cfg.get("name", "momentum")
        if name == "momentum":
            self.strategy = MomentumStrategy(strat_cfg.get("params", {}))
        elif name == "ml_model":
            self.strategy = MLModelStrategy(strat_cfg.get("params", {}))
        else:
            raise ValueError(f"Unknown strategy: {name}")

        self.scheduler = MarketScheduler(
            self.calendar,
            {
                "on_pre_market": self._pre_market,
                "on_market_open": self._market_open,
                "on_tick": self._tick,
                "on_market_close": self._market_close,
            },
            self.config.get("dashboard", {}).get("refresh_seconds", 5),
        )

        self._running = False
        self._paused = False
        self._daily_pnl = 0.0
        self._signals: list = []
        self._orders: list = []
        self._lock = threading.Lock()
        self.dashboard = None

        logger.info("Engine ready: mode=%s strategy=%s universe=%d symbols",
                     self.config.get("mode"), name, len(self.universe))

    # ── Lifecycle ──────────────────────────────────────────────

    def start(self):
        self._running = True
        report = self.state_mgr.reconcile(self)
        if report["action"] != "none":
            for d in report["details"]:
                logger.warning("RECONCILE: %s", d)
            self.audit.log_session("reconciliation", report)
        self.order_tracker.start()
        self.audit.log_session("start", {"mode": self.config.get("mode")})
        self.notifier.send("start",
                           f"Engine started ({self.config.get('mode')} mode)")
        self.scheduler.start()
        logger.info("Engine started")

    def stop(self):
        self._running = False
        self.scheduler.stop()
        self.order_tracker.stop()
        self.audit.log_session("stop")
        self.notifier.send("stop", "Engine stopped")
        self.audit.close()
        logger.info("Engine stopped")

    def pause(self):
        self._paused = True
        self.audit.log_session("pause")
        logger.info("Engine paused")

    def resume(self):
        self._paused = False
        self.audit.log_session("resume")
        logger.info("Engine resumed")

    # ── Scheduler callbacks ────────────────────────────────────

    def _pre_market(self, ts: datetime):
        lookback = self.config.get("data", {}).get("lookback_days", 60)
        data = self.feed.get_bars(self.universe,
                                  ts - timedelta(days=lookback), ts)
        for sym, df in data.items():
            self.cache.store_bars(sym, df)
        logger.info("Pre-market: cached %d symbols", len(data))

    def _market_open(self, ts: datetime):
        acct = self.broker.get_account()
        self.risk_monitor.start_session(acct["equity"], ts)
        self.strategy.on_market_open(ts)
        logger.info("Market open — equity=$%,.0f", acct["equity"])

    def _tick(self, ts: datetime):
        if self._paused:
            return

        with self._lock:
            try:
                positions = self.broker.get_positions()
                account = self.broker.get_account()
                self.risk_monitor.update(positions, account, ts)
                self._daily_pnl = self.risk_monitor.daily_pnl

                # Circuit breaker
                if self.circuit_breaker.check(self._daily_pnl, ts):
                    self.notifier.circuit_breaker(
                        self._daily_pnl, self.circuit_breaker.max_daily_loss)
                    self.audit.log_risk_event("circuit_breaker",
                                              {"pnl": self._daily_pnl})
                    self.broker.close_all_positions()
                    self._push_dashboard(positions, account, ts)
                    return

                # Don't generate new signals while orders are pending
                if self.order_tracker.get_pending_count() > 0:
                    self._push_dashboard(positions, account, ts)
                    return

                # Prices
                all_syms = list(set(self.universe) | set(positions.keys()))
                prices = self.feed.get_latest_price(all_syms)
                if hasattr(self.broker, "update_prices"):
                    self.broker.update_prices(prices)

                # Data with validation
                lookback = self.config.get("data", {}).get("lookback_days", 60)
                raw = self.feed.get_bars(self.universe,
                                         ts - timedelta(days=lookback), ts)
                valid = {}
                for sym, df in raw.items():
                    if df.empty or df["close"].isna().any():
                        continue
                    if len(df) < self.strategy.lookback + 1:
                        continue
                    valid[sym] = df

                if len(valid) < len(self.universe) * 0.5:
                    self.audit.log_risk_event("data_quality", {
                        "valid": len(valid), "total": len(self.universe)})
                    self._push_dashboard(positions, account, ts)
                    return

                # Signals
                signals = self.strategy.generate_signals(valid, positions, ts)
                for sig in signals:
                    self._process(sig, account, positions, prices)

                self._push_dashboard(positions, account, ts)
                self.state_mgr.save(self)

            except Exception as e:
                logger.error("Tick error: %s", e, exc_info=True)
                self.audit.log_risk_event("tick_error", {"error": str(e)})

    def _process(self, signal, account, positions, prices):
        self._signals.append(signal)
        price = prices.get(signal.symbol, 0)
        result = self.risk_limits.check_signal(
            signal, account, positions, price, self._daily_pnl)
        self.audit.log_signal(signal, result)

        if not result.approved:
            logger.warning("REJECTED %s: %s", signal.symbol, result.reason)
            return

        if signal.action == SignalAction.BUY:
            qty = result.adjusted_qty or 1
            order = self.broker.submit_order(signal.symbol, qty, OrderSide.BUY)
            self.order_tracker.track(
                order,
                on_fill=lambda o: self.audit.log_order(o),
                on_reject=lambda o: self.notifier.order_rejected(
                    o.symbol, o.status.value),
            )
            self._orders.append(order)
            self.audit.log_order(order)

        elif signal.action in (SignalAction.SELL, SignalAction.CLOSE):
            if signal.symbol in positions:
                order = self.broker.close_position(signal.symbol)
                if order:
                    self._orders.append(order)
                    self.audit.log_order(order)

    def _market_close(self, ts: datetime):
        if self.config.get("market", {}).get("flatten_at_close", True):
            orders = self.broker.close_all_positions()
            for o in orders:
                self.audit.log_order(o)
            logger.info("Flattened %d positions at close", len(orders))

        self.strategy.on_market_close(ts)
        summary = self.risk_monitor.get_summary()
        self.audit.log_session("eod", summary)
        self.notifier.eod_summary(summary)
        self.state_mgr.clear()
        logger.info("EOD: P&L=$%+,.0f  exposure=$%,.0f",
                     summary["daily_pnl"], summary["total_exposure"])

    # ── Dashboard ──────────────────────────────────────────────

    def _push_dashboard(self, positions, account, ts):
        if self.dashboard:
            self.dashboard.update_data(
                positions, account,
                self.risk_monitor.get_summary(),
                self.circuit_breaker.get_status(),
                self._signals[-20:], self._orders[-20:],
                self.scheduler.state.value, ts,
            )