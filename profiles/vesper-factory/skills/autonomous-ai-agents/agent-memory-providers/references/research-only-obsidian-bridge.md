# Research-only Obsidian bridge while Mnemosyne stays active

## Use case

The user wants visible Markdown research capture in an Obsidian vault, but does not want a second provider to automatically inject context, retain non-research material, or replace Mnemosyne.

## Architecture

```text
Hermes default profile: Mnemosyne is the only active external provider
  └─ explicit local plugin tools
       ├─ research_memory_capture → <vault>/Brain/research/inbox/*.md
       └─ research_memory_search  → explicit read only

Open Second Brain native provider: disabled for this flow
```

This is not an automatic O2B-to-Mnemosyne sync. Mnemosyne-backed agents read the vault only by explicitly invoking the search tool. Do not add `prefetch`, `sync_turn`, `system_prompt_block`, or lifecycle hooks: those violate receive-only behavior.

## Deterministic capture gate

Implement a plugin whose capture tool:

1. Accepts only a finite allow-list of research scopes and record kinds.
2. Generates its own note identifier and writes exclusively under `Brain/research/inbox/`.
3. Records status (`candidate`), provenance, timestamp, title, and sources in Markdown frontmatter.
4. Rejects non-allowlisted scopes before creating a file.
5. Keeps all search traversal rooted under `Brain/research/`; resolve paths and reject paths escaping that root.
6. Uses no network, MCP server, subprocess, cloud embeddings, or auto-promotion.

A tool-level gate does not stop a general-purpose file-writing agent from bypassing it. If the user needs enforcement against untrusted code with raw filesystem access, use a separate OS identity/broker or remove that raw write capability; do not overclaim that a plugin alone provides OS-level isolation.

## Hermes plugin contract

Plugin tool schemas must use Hermes's full wrapper shape. Supplying only a JSON Schema object can cause the model to send `{}`.

```python
SCHEMA = {
    "name": "research_memory_capture",
    "description": "...",
    "parameters": {
        "type": "object",
        "properties": {"scope": {"type": "string"}},
        "required": ["scope"],
        "additionalProperties": False,
    },
}
```

Register the tools in the existing `memory` toolset so they are available alongside Mnemosyne without changing `memory.provider`. Configure the vault path under `plugins.entries.<plugin-id>.config` in Hermes config, not through a new behavioral environment variable.

## Verification

- `hermes memory status` shows Mnemosyne active in the default profile.
- The former O2B profile/provider is disabled or isolated.
- Unit test an allowed capture, rejected scope with no file, private-region redaction, research-root-only search, and the wrapped schema contract.
- Use a fresh verbose Hermes chat to confirm the model sends non-empty arguments to the actual capture tool and the returned path is under `Brain/research/inbox/`.
- Use a fresh Hermes chat to exercise explicit search and confirm it returns a stored note.
- Static-scan the plugin for network/process launch and confirm it registers no lifecycle hook or memory-provider injection path.

## AgentMemory comparison cue

A provider with broad automatic turn capture, pre-LLM injection, a local HTTP server, and many MCP tools is not automatically a better fit for this model. Evaluate its actual hook behavior, Windows support, operational ports/services, storage inspectability, and provider-replacement effect before suggesting a switch. Vendor retrieval benchmarks are not a substitute for a constrained local trial.
