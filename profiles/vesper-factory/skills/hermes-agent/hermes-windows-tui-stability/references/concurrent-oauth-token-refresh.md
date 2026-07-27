# Concurrent OAuth Token Refresh in Windows TUIs

Use this when several Hermes TUIs/gateways intentionally run at once and one session starts returning an OAuth 401 such as `token_expired`.

## Why it happens

OAuth access tokens expire normally. Refresh tokens for providers such as OpenAI Codex may be single-use. One Hermes process can refresh the shared `auth.json` while another long-lived process still holds the old access/refresh pair in memory. The second process then receives 401 even though `hermes auth status` reports logged in and a fresh token exists on disk.

Concurrent TUIs are a supported operating pattern. Do not solve this by telling the user to close every session or stop unrelated work.

## Diagnose the exact failing session

1. Check current credential state:

```bash
hermes auth status openai-codex
hermes auth list openai-codex
hermes status --all
```

2. Search `~/AppData/Local/hermes/logs/agent.log` or `errors.log` for the exact 401 text. Capture:
   - timestamp
   - bracketed session ID
   - provider/model
   - error code (`token_expired`, `invalid_grant`, etc.)

3. Compare that timestamp with the auth refresh time shown by `hermes status --all`.

4. Inspect active process command lines and start times. A TUI/slash worker that predates the successful token refresh is the likely stale process.

5. Distinguish:
   - **one stale TUI session** — repair only that session
   - **gateway-wide failures** — restart the gateway
   - **new processes also fail** — full re-authentication may be required

## Least-disruptive recovery

When the stored credential is currently valid:

```bash
hermes auth reset openai-codex
```

Then use `/retry` in the failing TUI only. This clears pool exhaustion and gives the session a chance to adopt the newer `auth.json` token pair.

If the same session still returns 401, quit only that TUI and resume its exact session:

```bash
hermes --resume <failing-session-id> --tui
```

Leave unrelated TUIs and their work running.

Only restart `hermes gateway` when the failing log/session belongs to the messaging gateway or failures are gateway-wide. A standalone TUI OAuth failure is not evidence that the gateway must restart.

If a newly started resumed TUI immediately returns the same 401, perform a full provider re-login:

```bash
hermes auth logout openai-codex
hermes auth add openai-codex
```

Then resume the affected session.

## Reporting contract

State the evidence, not a generic diagnosis:

- which session failed
- exact failure time and provider
- whether stored auth is currently valid
- whether auth refreshed after the failure
- which processes predate that refresh
- the least-disruptive action

Avoid “close all Hermes windows” when the user intentionally runs parallel design/backend sessions. Preserve independent workstreams and restart only the stale owner.

## Durable implementation expectation

A robust credential pool should, before refresh/retry, re-read the provider state from shared `auth.json` and adopt changed access or refresh tokens. It should distinguish refreshable `token_expired` from terminal states such as revoked/invalidated grants. If current source contains this resync path but a long-lived process still fails, suspect that the process loaded older code or retained pre-fix in-memory state; restart only that process before changing global configuration.
