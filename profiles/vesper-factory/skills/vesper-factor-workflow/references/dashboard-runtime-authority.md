# Dashboard Runtime Authority and Safe Launcher Pattern

Use this when a localhost dashboard can be served from more than one checkout or an old process can reclaim the port.

## Failure mode

A healthy HTTP response is not proof that the intended code is running. A shadow checkout may serve stale assets, hardcoded health, old basket semantics, or unsafe API routes while the data pipeline itself is healthy. Generic process checks such as “any `pythonw.exe` exists” make this worse.

## Authoritative identity contract

The repository server should expose immutable identity fields from `/api/status`, independent of payload health:

- a versioned contract such as `vesper-dashboard-truth-v2`;
- the resolved dashboard source root;
- the normal derived status and payload freshness.

Every launcher, tray supervisor, health probe, and browser verification must require both the contract and source root. HTTP 200 alone is insufficient.

## Safe launcher pattern

1. Bind the dashboard to `127.0.0.1`, not `0.0.0.0`, unless authenticated network exposure is explicitly required.
2. Probe `/api/status` for the expected identity contract.
3. If the expected server is absent, launch the server by absolute script path with an explicit working directory.
4. Use an OS singleton primitive (on Windows, a named mutex) for the tray supervisor. Do not infer singleton state from executable names.
5. Open `http://127.0.0.1:<port>` only after startup.
6. Re-launch the shortcut during verification and prove the tray count and server PID do not change.
7. Inspect the listening address and served bundle/version after launch.

## Shadow-server recovery

- Identify the port-owning PID and its full command line before termination.
- Confirm whether a shadow checkout or orphaned supervisor spawned it.
- Stop only the identified shadow process tree.
- Start the authoritative launcher, then verify contract, source root, listener address, API safety, and browser assets.
- Disable obsolete startup entries, but retain evidence until the new startup path survives a login/restart.

## Separate runtime layers

Explain incidents as separate layers:

1. data ingestion and scoring;
2. artifact admission and provenance;
3. scheduler execution;
4. broker/order authority;
5. dashboard server and browser assets.

A broken GUI does not prove internal scripts failed. Conversely, successful scripts do not prove the GUI is serving the right code.

## Order-safety check

When a scheduled rebalance consumes a basket, compare it with the current governance board before allowing the task to remain enabled. A fresh artifact, passing tests, and a paper-only client do not grant authority. Require exact agreement on strategy/lane, basket producer, account scope, order scope, notional envelope, paper-only mode, and source-session date. If board and scheduled target differ, pause or convert to preview-only pending explicit reconciliation.
