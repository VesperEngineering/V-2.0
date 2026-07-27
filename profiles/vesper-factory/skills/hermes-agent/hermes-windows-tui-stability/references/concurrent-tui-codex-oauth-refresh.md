# Isolating OpenAI Codex OAuth expiry in concurrent Hermes TUIs

Use this when the operator intentionally runs multiple Hermes TUIs and one reports:

```text
HTTP 401: Provided authentication token is expired. Please try signing in again.
```

## Diagnosis

1. Run `hermes auth status openai-codex` and `hermes auth list openai-codex`.
2. Compare the credential refresh time with the failing session/process start time.
3. Inspect recent session logs for the exact 401 and identify the failing session ID.
4. Treat a credential that is currently logged in/refreshed plus one older failing worker as a process-local token synchronization race, not proof that every session is unauthenticated.

OpenAI Codex refresh tokens can rotate while another long-lived TUI still holds an older access/refresh token in memory. Concurrent TUIs are a supported intentional workflow; do not solve this by closing unrelated sessions.

## Least-disruptive repair

1. Leave healthy TUIs and their workstreams running.
2. In Git Bash, clear only the provider pool exhaustion state:

```bash
hermes auth reset openai-codex
```

3. In the failing TUI only, run `/retry` so it can reload the refreshed credential.
4. If that same TUI still returns 401, quit only that TUI and resume its exact session:

```bash
hermes --resume <failing-session-id> --tui
```

5. Perform a full logout/login only if a newly started/resumed TUI still immediately fails and `hermes auth status openai-codex` is not healthy:

```bash
hermes auth logout openai-codex && hermes auth add openai-codex
```

Restart the gateway only when evidence shows the gateway process is the failing consumer. Do not restart it merely because a separate local TUI failed.

## Reporting

State the exact failing session, healthy session(s) left untouched, current credential status, and the smallest restart performed. Never recommend shutting down every parallel Hermes TUI when only one stale worker is implicated.
