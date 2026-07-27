# Session: Truth-Layer Repair (2026-07-19)

Six-lens audit of VOT ↔ Kanban ↔ autoresearch integration, followed by same-session TDD repairs. Commits `86fb99b` (watchdog) and `e925a2d` (dispatcher) on branch `vesper`.

## What was found

| Finding | Evidence | Severity |
|---|---|---|
| `_check_data_freshness` returned `healthy` unconditionally | OHLCV 2026-07-14 (5d stale) reported healthy in 04:30 receipt | High |
| `_check_research_receipt` healthy for ANY status incl. FAIL | code inspection | High |
| Fixed 48h EOD staleness false-alerts every weekend on Mon–Fri 17:00 ET schedule | arithmetic: Fri→Mon = 72h | Medium |
| Manual `dry_run: true` receipt counted as scheduled EOD evidence | receipt `vesper-daily-eod.json` | Medium |
| `~/vesper-ranker` is a stale clone of the MAIN repo, not a research codebase | same AGENTS.md/ARCHITECTURE.md, scheduler/governance git log, no queue, no candidates | High (lane unbuilt) |
| ~144 green no-op receipts/day (`no_queue`, `candidates_found: 0`) | receipts | High |
| Agent layer paused since Jul 15 (steward/Thomas/audit/pipeline); 2 blocked needs_input cards aging silently (51h, 39h) | cronjob list + kanban DB | Medium |
| Alert dispatcher moved FAILED alerts to `dispatched/` — alerts lost | live receipt: `alerts_found: 2, dispatched: 0, failed: 2`, files in dispatched/ | High |
| Telegram platform unconfigured — first-ever alert dispatch failed at last hop | dispatcher stderr | config gap |
| Kanban card `t_cf7ed479` has literal `%s` as `created_at` (writer format bug, outside repo) | sqlite query | Low |

## Repairs shipped

- `scripts/cron_health_watchdog.py`: date comparison (`MAX_OHLCV_AGE_DAYS=4`), `_last_scheduled_eod_run` (America/New_York, Mon–Fri 17:00 + 3h grace), dry-run exclusion, research FAIL→unhealthy, new `_check_kanban_blocked` (48h). Check functions take injectable `path`/`now`.
- `scripts/cron_alert_dispatcher.py`: `process_alert_file()` with durable retry (attempts sidecar, `MAX_DISPATCH_ATTEMPTS=24`, parks in `failed/`). Two wrongly-archived alerts restored to pending.
- Tests: `tests/test_cron_health_watchdog.py` (18), `tests/test_cron_alert_dispatcher.py` (5). 87 passed across adjacent suites.
- Issues logged: VQ-20260719-001 … VQ-20260719-005 in `docs/ISSUES.md`.

## Verification evidence

- First post-fix live watchdog run: `Overall: degraded` — correct stale/unknown verdicts, two real alert files written (first alerts the system ever produced).
- Dispatcher receipt then showed `failed: 2` with Telegram-unconfigured stderr — alert chain proven end-to-end up to the gateway send.
- NOTE: `zoneinfo.ZoneInfo("America/New_York")` works in the Vesper venv on Windows (tzdata present). Verify before relying on it elsewhere.

## Follow-up same session (commit `9dd25ee`)

- **Telegram delivery configured by operator** — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `TELEGRAM_HOME_CHANNEL` in `~/AppData/Local/hermes/.env`. All 4 pending alerts (2 conditions × 2 watchdog ticks) delivered to Telegram; files in `alerts/dispatched/`. Chain fully live.
- **`hermes send` needs NO running gateway** for bot-token platforms (Telegram/Discord/Slack/Signal) — credentials in `.env` + config suffice. `hermes send --list telegram` showing empty means only that channel *discovery* hasn't run (populated by a gateway run); delivery via `TELEGRAM_HOME_CHANNEL` works regardless. Empty list ≠ broken.
- **Alert repeat cooldown shipped** — without it, a persistent condition writes a new alert every 30-min tick (~48 Telegram msgs/day). `_alert_recently_raised()` checks pending + dispatched filenames for the same alert name within `ALERT_REPEAT_COOLDOWN_HOURS = 6` and suppresses repeats. 5 new tests (28 passed across watchdog+dispatcher).

## Open at session end (operator decisions)

1. ~~Configure a delivery platform for alerts~~ — DONE (Telegram, this session).
2. Research island fate: build real ranker repo (blocked on WSL2 CUDA 12.0 < sm_120) or mark lane IDLE.
3. Un-pause agent-layer cron jobs (paused 2026-07-15).
4. 37 git worktrees with duplicate-HEAD pairs — reconciliation debt vs AGENTS.md root-reconciliation rule.
