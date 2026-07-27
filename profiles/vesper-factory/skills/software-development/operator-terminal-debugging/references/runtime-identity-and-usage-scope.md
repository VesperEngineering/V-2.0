# Runtime identity and usage scope

Use this reference when verifying Vesper display PIDs, worker processes, or provider token usage.

## PID classification

Separate these identities before reporting:

- dedicated display/TUI process;
- browser host loading a static `file://` HTML visual;
- live web server owning a listener;
- worker runtime;
- supervisor/launcher parent.

On Windows, inspect each candidate with `psutil.Process(pid).cmdline()`, `.cwd()`, `.children()`, and listener data. A browser PID proves only that the document is open. “No dedicated display PID” does not mean “no workers running.” Report command line, cwd, and parent/child relationships.

## Usage authority

- Provider management/activity APIs prove account-level activity for that provider.
- Local provider receipt ledgers prove only explicitly attributed application/worker requests.
- Workspace/session JSONL scanners prove discovered local model-session counters, often filtered by workspace and including cached tokens.
- Quota data is remaining allowance, not consumed usage.

An empty `openai-codex` receipt ledger must be reported as “no Codex receipts in this ledger,” never as account-wide zero. If the receipt ledger and session scanner disagree, show both with source, scope, observation time, stale/estimated status, and cached-token semantics. Do not silently merge them.
