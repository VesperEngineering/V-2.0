# Durable Planning-Proposal Ledger

Use this pattern when agents should propose work autonomously but authenticated approval and atomic Kanban creation are not ready.

## Why Kanban status is not the approval ledger

- `--initial-status blocked` may be promoted because it lacks a durable manual `block_kind`.
- `--triage` is decomposable work, not a human hold. With `kanban.auto_decompose: true`, the gateway may call an auxiliary model, rewrite/promote the root, create ready children, and dispatch workers.
- A short probe under temporary `HERMES_HOME` does not exercise the production gateway.
- A mutable global `auto_decompose=false` check is not a per-card guarantee.

## Safe staged architecture

1. Build bounded deterministic proposals from local System Spine evidence.
2. Default to provider-free dry-run; require explicit `--record` for the local ledger.
3. Store proposals outside runnable Kanban tables under canonical `D:\vesper\.hermes`.
4. Separate immutable proposal identity from repeat observations: changing `observed_at` appends an observation instead of causing identity conflict.
5. Validate the exact complete proposal schema and every authority flag on append and replay. All authority remains built-in `false`; never normalize unsafe durable evidence into safe defaults.
6. Until identity is authenticated, expose proposals read-only in VOT and through a Telegram-compatible list command. Do **not** expose `approve`, `review`, or card-creation commands, even as attestations.
7. Add human approval and automatic Kanban creation only after trustworthy VOT/Telegram principals and an atomic idempotent ledger-to-Kanban handoff exist. Then the human approves and the system creates the card; the human never manually duplicates it.
8. Ordinary non-gated agents may still create normal work cards autonomously. Broker/order, risk, scheduler, and promotion remain separately human-gated.

## SQLite and path discipline

- Missing DB on read returns an empty queue without creating directories/files.
- Existing empty or malformed DB is `UNAVAILABLE`; reads must not initialize or repair it.
- Use SQLite URI `mode=ro` for VOT/list reads.
- Initialize only in a write transaction; validate tables, columns/types/nullability/PKs, unique bindings, and foreign keys.
- Enforce observation limits before insert; return transaction-derived state without a post-commit reread; close every connection explicitly on Windows.
- Bind production writes to canonical `D:\vesper` and reject `.hermes`/DB symlink, junction, or reparse indirection.
- Report committed IDs and the currently attempted ID when a bounded batch partially fails.
- Do not claim deletion resistance from an unkeyed hash chain in the same writable DB; suffix truncation needs a separately trusted checkpoint/signature.

## Provider-free planning reads

Display-oriented dashboard loaders may call provider accounting and write usage caches. Planning must explicitly disable that source. Test the real default path with provider calls trapped and compare canonical `.hermes` inventory before/after a real dry-run.

## Minimum verification

- Stable repeat and later-observation idempotency.
- Changed canonical payload under the same ID fails.
- True/non-boolean authority flags and extra/malformed durable fields fail.
- Controls are rejected before normalization.
- Missing/malformed read paths perform zero writes and render `UNAVAILABLE` truthfully.
- Bound is enforced before commit; connection close and concurrent first use are tested on Windows.
- Canonical-root, reparse-path, partial-batch, and removed review/publish flags are tested.
- Real canonical dry-run: proposals generated, recorded count zero, no DB, no `.hermes` changes.
- Independent review inspects the exact staged diff hash; any edit invalidates the verdict.

## Reporting to Brennan

Keep updates brief and specific: what changed, exact verification, mutation result, remaining gate, and one recommendation. Describe the eventual authority sequence precisely as **agent proposes → human approves → system creates the card**, while stating clearly when authenticated approval/card creation is not implemented yet.
