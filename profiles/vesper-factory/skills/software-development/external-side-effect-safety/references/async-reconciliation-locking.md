# Async Reconciliation Locking

Use when an asyncio service must reconcile remote state while excluding submissions, cleanup, shutdown mutations, or EOD transitions guarded by a synchronous cross-thread lock.

## Safe shape

1. On the event-loop thread, set the mutation/reconciliation gate to `False` immediately. This prevents a new mutation from winning the lock while reconciliation is queued.
2. Dispatch **one synchronous helper** with `asyncio.to_thread`.
3. Inside that helper, acquire the shared `threading.Lock` and hold it continuously across:
   - setting the gate false again under the lock;
   - remote snapshot/query;
   - all local state updates and commits;
   - publication of the reconciliation result.
4. On an exception, let the lock release but do not restore the gate to true.
5. Keep monitoring and recovery workers alive while the mutation gate is false.

Illustrative structure:

```python
def reconcile_serialized(self) -> bool:
    with self._mutation_lock:
        self._reconciled = False
        result = self.remote_and_local_reconciliation()
        self._reconciled = result
        return result

async def risk_worker(self):
    self._reconciled = False
    await asyncio.to_thread(self.reconcile_serialized)
```

Do not acquire `threading.Lock` on the event-loop thread and then await. Lock contention can freeze WebSocket pings, queue ingress, cancellation, shutdown, and worker supervision for the complete broker timeout.

## Required race probes

- **Pre-lock gate:** hold the lock in another thread, start reconciliation, and verify the gate becomes false before the lock is released.
- **Heartbeat:** while reconciliation waits for the lock, schedule a short asyncio heartbeat and assert it fires on time.
- **Submission exclusion:** block reconciliation mid-call and attempt a mutation; assert zero remote POSTs until reconciliation completes.
- **EOD exclusion:** block reconciliation, concurrently run verified-flat cleanup, then release reconciliation. Assert cleanup waits and the final closed state cannot be overwritten by a stale `submitted`/`open` update.
- **Exception:** raise during remote reconciliation; assert the lock is released and the gate stays false.
- **Single latch:** race two EOD/cleanup callers after reconciliation; assert exactly one remote mutation and one success latch.

## Related reservation invariant

Remote balances and positions may lag immediate fills. Pending, unknown, partially filled, and locally open intents retain their local capacity/cash reservation until authoritative reconciliation or verified-flat cleanup releases it. Reconciliation and release must share the same mutation lock to prevent stale-state resurrection.
