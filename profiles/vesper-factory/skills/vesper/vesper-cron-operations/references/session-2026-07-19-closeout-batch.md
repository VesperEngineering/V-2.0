# Closeout batch (2026-07-19, evening) — directions pipeline, news, ledger parity, tuning

Second-wave build that closed the architecture doc's remaining-work list (items 2,4,5,6,7,8,9).
Commits: repo `d8a000a`, island `bb5aab3`. 31 new tests.

## New cron jobs (all no_agent, thin wrappers in ~/AppData/Local/hermes/scripts/)

| Job | Schedule | Repo script | Purpose |
|-----|----------|-------------|---------|
| Research Directions Sync | `*/30 * * * *` | `scripts/research_directions_sync.py` | Kanban `Research direction:` cards → island queue |
| News Attention Collector | `0 */2 * * *` | `scripts/news_attention_collector.py` | Google News RSS × 33 symbols → SQLite |
| Weekly Bounded Tuning | `0 10 * * 6` | `scripts/cron_weekly_tuning.py` | 8-config grid over spec_probe, evidence + card |
| Approval Ledger Sync | `15 * * * *` | `scripts/approval_ledger_sync.py` | Kanban operator decisions → VOT approval ledger |

Schedule changes same day: steward `30 8,13 * * 1-5`, Thomas `20 13 * * 1-5`,
repair `0 21 * * 1-5`. Removed: Daily Factor Basket (`ec44f11e95d3`),
jepa-isolated-research-hour (`f638382fca42`). Alpaca Rebalance stays paused.

## Directions pipeline (kanban → GPU work as pure data)

- Card convention: title prefix `Research direction:` (case-insensitive), status in
  `ready|todo|approved`, body with a fenced ```` ```json ```` spec block.
- Spec vocabulary is gated: features ⊆ {mom_12_1, mom_6_1, mom_3_1, rev_1m, rvol_21,
  rvol_63}; anything else → card skipped, never partial-runs.
- Sync appends to `D:/vesper-research/research_directions.json` as `dir_<card_id>`,
  idempotent by card id; producer turns it into a PENDING queue item; the batch tick
  leases it inside the window; `island/runner.py` passes `--spec` to
  `experiments/spec_probe.py` when the item has a spec.
- `spec_probe.py` = generic walk-forward ridge probe on the total-return-adjusted
  33-ticker universe. Verified live: rev_1m+rvol_63 spec → IC 0.058, t=10.4.
- Research Engineer cron prompt (job `2763a0f176df`, in jobs.json) has a Step 4 that
  emits these cards from its Monday paper scan — the loop self-feeds.

## News attention collector

- URL shape: `https://news.google.com/rss/search?q=%22<SYM>%22+stock&hl=en-US&gl=US&ceid=US:en`
  (100 items/feed). Schema: `articles(hash PK, symbol, published_at, title, source,
  collected_at)` at `data/news/attention.db` (gitignored — data never committed).
- Dedup: sha1(symbol|title|published_at), `INSERT OR IGNORE`. Proven live on day one:
  seed pass inserted 3,032; an immediate second pass inserted only 11 genuinely-new.
- Known noise: short tickers ("A", "IT") match common words — acceptable for
  attention-count features; titles are metadata, not signal, until IC evaluation.
- Per-symbol network failure is caught per symbol; the pass completes and the
  receipt counts errors rather than dying on the first timeout.

## Approval ledger parity (Telegram → VOT ledger)

- Detection: `unblocked` events preceded (≤120s) by a human comment
  (author ∈ {brennan, default}) → approve; `blocked` with reason starting
  "Rejected by operator" → reject. Agent self-unblocks are skipped.
- Mirroring writes VALID hash-chained pairs via the real API:
  `request_approval(requested_by="thomas", ttl_hours=168, now=event_time)` then
  `decide_approval(decided_by="brennan", now=event_time)`. Principals are restricted
  to {brennan, thomas} and self-approval is forbidden — thomas-as-proposer /
  brennan-as-decider is the only shape that passes.
- Replay shows these as `expired` (decision window lapsed; VOT execution stays
  fail-closed — `execute_approved_action` always raises until VOT has authenticated
  identities). The parity record is the decision fields, not the replay status.
- State file `artifacts/cron/processed/approval_ledger_mirror.txt` keeps it
  idempotent. First live pass mirrored 18 historical decisions.

## Weekly bounded tuning

- Runs the GRID (≤8 configs) IN-PROCESS by importing `spec_probe` (no queue, no
  subprocess per config), hard wall-clock 1200s, writes
  `artifacts/tuning/tuning_<yyyymmdd>.json` + a kanban card for Thomas.
- Fail-closed: a config that raises records an error row and the grid continues;
  budget exceeded → FAIL receipt naming how many configs completed.

## Worktree sweep (6 → 2)

- `fix/vot-telemetry-panels`: dirty files were all retired `operator_terminal*`
  (Prompt Toolkit), not the Tkinter VOT — archived diff (1,788 lines) + removed.
- 3 stage lanes (local-delivery shadow/coordinator handoff experiments, 2.6–4k
  lines each): superseded by the shipped kanban+Telegram delivery path; patches
  already archived in `.hermes/audits/worktree-sweep-20260719/`; removed.
- `paper-capacity-kernel` (9 commits, 16.5k lines paper shadow ledger): kept —
  unreviewed content, deletion is a review verdict not housekeeping. Review card
  `t_09ee02c1` assigned to Thomas.
- Rule reinforced: archive dirty diffs + commit lists BEFORE `worktree remove`;
  check dirty-file paths against retired surfaces before treating a worktree as
  live work.
