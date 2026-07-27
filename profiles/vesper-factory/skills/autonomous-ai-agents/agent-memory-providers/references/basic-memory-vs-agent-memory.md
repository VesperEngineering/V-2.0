# Basic Memory versus agent-native memory providers

## Source notes

- Basic Memory: https://basicmemory.com/
- Hermes integration in its repository: https://github.com/basicmachines-co/basic-memory/tree/main/integrations/hermes
- Its Hermes integration documents a native provider/plugin, local Markdown-backed storage, graph/search tools, per-turn capture, and end-of-session summaries.

## Evaluation frame

Basic Memory is a **document-first knowledge system**: prefer it when the user wants an inspectable Markdown vault, cross-tool portability, and project/note navigation. It is not automatically a better replacement for a structured agent-memory provider.

Structured providers such as Mnemosyne are **agent-native memory systems**: prefer them for canonical profile facts, temporal relationships, compact semantic retrieval, and provider-specific structured tools.

Hermes uses one external memory provider at a time. Installing or activating Basic Memory can replace the active provider; do not describe it as an additive second memory layer without verifying the current Hermes integration and configuration.

## Safe comparison and trial procedure

1. State the active provider and confirm whether the user wants to keep it or trial a replacement.
2. Compare desired outcomes: Markdown/cross-tool notes versus structured profile/temporal memory.
3. Back up the active provider before switching.
4. Prefer a separate Hermes profile for a Basic Memory trial when the current provider contains meaningful data.
5. Verify Basic Memory with a write/retrieval in a fresh session, then decide whether to keep it.
6. Preserve either provider's data store unless the user explicitly requests deletion.

## Caveat

Basic Memory's Hermes integration may use a CLI bootstrapper and exposes agent tools through its provider/plugin path. Verify the upstream installation and privacy instructions at the time of installation; do not guess commands from this reference.