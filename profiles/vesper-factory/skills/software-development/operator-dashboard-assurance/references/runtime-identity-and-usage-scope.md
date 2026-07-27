# Runtime identity and usage scope

Use this reference when a user asks whether a Vesper display or worker is running, or whether the dashboard shows provider token usage.

## Process identity checklist

Classify the target before searching for a PID:

1. **Dedicated display/TUI process** — e.g. `operator_terminal.py`, `operator_tui`, or a named worker-display executable.
2. **Browser host** — Chrome/Edge loading a static `file://` HTML visual. This proves only that the browser has the document open; it does not prove a live backend or worker display.
3. **Live web server** — a process owning a listening socket. Verify exclusive listener ownership and inspect bind address, command line, cwd, and parent/child tree.
4. **Worker runtime** — the actual model worker process, such as `tui_gateway.slash_worker`.
5. **Supervisor parent** — a launcher/gateway process whose child is the worker.

On Windows, use `psutil` or `netstat -ano` plus per-PID `cmdline()`, `cwd()`, `children()`, and listener inspection. Report these as separate facts. “No dedicated display PID” must never be summarized as “no workers running.”

## Usage authority checklist

Keep these sources separate:

- **Provider management/activity API:** account-level activity for one provider; report freshness and whether the result is daily, historical, cached, or estimated.
- **Local provider receipt ledger:** only requests explicitly attributed to the application/workers; empty provider rows mean “no receipts in this ledger,” not “provider account used zero tokens.”
- **Workspace/session telemetry:** local JSONL session counters, often filtered by workspace and sometimes including cached input tokens; report the workspace scope and do not call it billing usage without reconciliation.
- **Quota telemetry:** remaining allowance; never label it as tokens consumed.

If values disagree, expose the disagreement and source scopes. Do not silently substitute an empty receipt ledger for a provider account reading. For OpenAI/Codex specifically, an application receipt ledger may show zero Codex receipts while local Codex session files show substantial usage, including usage from unrelated Hermes chats or workspaces.

## Minimum verification output

A good report contains:

- target classification and exact command line;
- dedicated display PID, browser PID, worker PID(s), and supervisor PID(s), if present;
- provider/source/scope for every usage number;
- token totals separated from cached-token totals;
- observation time and stale/estimated markers;
- one explicit trust verdict, with any unverified account-wide claim called out.
