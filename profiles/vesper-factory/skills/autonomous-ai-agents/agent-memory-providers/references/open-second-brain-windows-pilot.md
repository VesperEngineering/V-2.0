# Open Second Brain (O2B) pilot on Windows

Use this when a user wants an Obsidian-native agent second brain with inspectable Markdown, recall, and deterministic consolidation.

## Architecture decision

- O2B is a native Hermes external memory provider; it is **not** an additive provider beside Mnemosyne.
- Keep the established provider on the default profile. Create a dedicated pilot profile and set only that profile's `memory.provider: open-second-brain`.
- O2B's native Hermes adapter uses an internal stdio bridge; do not add a user-facing `hermes mcp` server unless separately requested.

## Isolation contract

Initialize a new, dedicated vault when existing vault content must remain untouched. O2B creates only:

```text
<vault>/Brain/                 # agent-owned Markdown state
<vault>/.open-second-brain/    # rebuildable local search index
```

Do not configure `notes.read_paths`, run inline scanning, or enable marker writeback during an isolation pilot. Verify that `_brain.yaml` has no `notes.read_paths` and that the vault root contains only the intended O2B directories.

## Windows setup and verification

1. Preflight the candidate vault path is absent/empty and make a dedicated Hermes profile.
2. Install and enable O2B in that profile; set that profile's provider only.
3. Run `o2b init`, `o2b brain init`, and `o2b search index` against the dedicated vault.
4. Verify `hermes --profile <pilot> memory status`, `o2b brain doctor`, the native bridge handshake, and one fresh Hermes session.
5. Verify the default profile still reports its prior provider.

### Git Bash / Bun launcher issue

O2B's `scripts/o2b` can pass an MSYS `/c/...` module path to Windows Bun, which Bun does not resolve. Normalize its TypeScript entrypoint with `cygpath -w` only on `MINGW*|MSYS*|CYGWIN*` before `bun run`. Re-check after plugin updates because an update can overwrite the local wrapper adjustment.

## Verification scope discipline

For a user-requested installation, stop after targeted operational proof: provider status, isolated vault layout, native bridge/tool discovery, and one fresh profile session. Do **not** launch the third-party project's full upstream suite unless the user asks for source-level validation or a failure requires it. Report nonessential upstream lint/test limitations only if they materially block the requested pilot.

## Cleanup note

If Windows locks a disabled plugin's Git pack/index file, leave the plugin disabled and disclose the residual directory; do not force-terminate user processes merely to delete it.
