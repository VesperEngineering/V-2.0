# Session transcripts

The controller appends redacted event-level transcripts from V20-routed Product,
Development, Risk Review, and bounded Qwen quant-agent turns. They include user
instructions, assistant messages, controller-mediated tool calls and results,
and runtime receipts when the adapter exposes them. Full system prompts,
external Codex chat, hidden reasoning, credentials, and raw protected data are
not stored. Event content is bounded per event and per session.

Files use `YYYY-MM-DD/<role>--<session-id>.md`. They are cold storage: Dream
Gate reads them, but runtime knowledge synchronization ignores them. Dream Gate
writes proposals only; human review is required before anything becomes active.
Notes without recorder event headings, such as handoffs, are not dream inputs.
