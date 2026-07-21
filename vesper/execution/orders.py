"""Order fill tracker. Polls open orders so the engine doesn't act on unfilled ones."""

import logging
import threading
import time

from .broker import BrokerBase, Order, OrderStatus

logger = logging.getLogger("vesper.orders")


class OrderTracker:
    def __init__(self, broker: BrokerBase, poll_seconds: int = 2):
        self.broker = broker
        self.poll_seconds = poll_seconds
        self._orders: dict[str, Order] = {}
        self._callbacks: dict[str, list] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def track(self, order: Order, on_fill=None, on_reject=None):
        with self._lock:
            self._orders[order.id] = order
            self._callbacks[order.id] = []
            if on_fill:
                self._callbacks[order.id].append(("fill", on_fill))
            if on_reject:
                self._callbacks[order.id].append(("reject", on_reject))

    def get_pending_count(self) -> int:
        with self._lock:
            return sum(
                1 for o in self._orders.values()
                if o.status in (OrderStatus.SUBMITTED, OrderStatus.PENDING,
                                OrderStatus.PARTIALLY_FILLED)
            )

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            try:
                self._poll()
            except Exception as e:
                logger.error("Order poll error: %s", e)
            time.sleep(self.poll_seconds)

    def _poll(self):
        with self._lock:
            pending = [
                (oid, o) for oid, o in self._orders.items()
                if o.status in (OrderStatus.SUBMITTED, OrderStatus.PENDING,
                                OrderStatus.PARTIALLY_FILLED)
            ]
        for oid, local in pending:
            try:
                remote = self.broker.get_order(oid)
                if remote is None or remote.status == local.status:
                    continue
                with self._lock:
                    self._orders[oid] = remote
                logger.info("Order %s (%s): %s -> %s",
                            oid, local.symbol, local.status.value, remote.status.value)
                if remote.status == OrderStatus.FILLED:
                    self._fire(oid, "fill", remote)
                elif remote.status in (OrderStatus.REJECTED, OrderStatus.CANCELLED):
                    self._fire(oid, "reject", remote)
            except Exception as e:
                logger.error("Poll error for %s: %s", oid, e)

    def _fire(self, oid, event, order):
        for evt, cb in self._callbacks.get(oid, []):
            if evt == event:
                try:
                    cb(order)
                except Exception as e:
                    logger.error("Callback error for %s: %s", oid, e)