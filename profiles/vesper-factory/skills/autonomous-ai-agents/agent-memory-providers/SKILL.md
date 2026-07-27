---
name: agent-memory-providers
description: Safely evaluate, switch, install, and verify long-term memory providers for Hermes and comparable agents, with data-preserving lifecycle controls.
version: 1.1.0
created_by: agent
platforms: [windows, linux, macos]
tags: [hermes, memory, plugins, providers, migration, verification]
---

# Agent Memory Providers

Use when a user asks to compare, install, activate, replace, migrate, or remove an agent memory provider. Treat a provider as durable state infrastructure: switching it changes prompt context, tool behavior, session capture, and potentially creates a new data store.

## Operating principles

- Keep exactly one external Hermes memory provider active at a time (`memory.provider`).
- Do not declare a provider working solely because it appears in a plugin list. Verify a write and a retrieval through the real agent/provider path.
- Preserve user-owned memory unless the user explicitly asks to delete it. A fresh test-only vault/database created in the current task may be removed after confirming it contains no user content.
- Do not force-terminate an active TUI/desktop process merely to unlock an old plugin directory. Deactivate and disable the old provider first; defer physical deletion until all hosts have released it.
- Restart the gateway after changing providers. Start a fresh TUI session (`/reset`) before expecting changed memory tools or system context there.
- Do not equate a document-first Markdown knowledge system with agent-native structured memory. Compare the user's desired retrieval, portability, and curation model before recommending a switch.
- For systems expected to "get better over time," use a governed promotion pipeline: one coordinator stewards durable memory; specialist workers submit evidence-backed artifacts and do not automatically publish speculation to shared memory.
- Keep profile identity separate from memory retrieval. A fresh session is the main coordinator only when routing selects the coordinator profile and its `SOUL.md` defines that role; canonical memory reinforces identity but cannot select the profile.
- Match verification effort to the user's request. For a provider pilot, stop after targeted operational proof (provider status, isolated storage, native write/recall path, and a fresh session); do not run an upstream project-wide test suite unless source-level validation is requested or a failure makes it necessary.

For long-term memory architecture, consolidation, worker isolation, token economics, and quality metrics, see `references/compounding-memory-governance.md`.

For a current comparison frame and safe trial plan for Basic Memory versus structured providers, see `references/basic-memory-vs-agent-memory.md`.

For a reproducible provider bakeoff covering cold-start, controlled-packet, and native-learning conditions, plus correction, leakage, token, latency, and maintenance metrics, see `references/memory-provider-benchmark.md`.

For a dedicated Obsidian-vault provider pilot (Open Second Brain), profile isolation, write-scope controls, and the Windows Git-Bash launcher workaround, see `references/open-second-brain-hermes-windows.md`. The concise isolation and verification runbook is `references/open-second-brain-windows-pilot.md`.

For a research-only, receive-only Obsidian capture layer that preserves Mnemosyne as the active provider, use `references/research-only-obsidian-bridge.md`. This is a separate local plugin/tool pattern, not a second active memory provider.

For a broader governed Obsidian second brain—workspace decisions, project context, procedures, and references—while Mnemosyne remains active, use `references/governed-obsidian-second-brain.md`.

For source-verified evaluation notes on Cognee and the unrelated projects named AgentMemory—including a Hermes plugin persistence gate—see `references/cognee-agentmemory-evaluation.md`.

## Provider-switch workflow

### 1. Discover the current state

Before changing anything, inspect:

```bash
hermes memory status
hermes plugins list --plain --no-bundled
hermes gateway status
```

Identify the old provider's data location and whether it contains user material. Take an export/backup if the provider supports one and the user has not asked to discard that data.

### 2. Deactivate the old provider safely

```bash
hermes memory off
hermes plugins disable <old-provider>
```

If removal reports a Windows file lock, stop the gateway and retry:

```bash
hermes gateway stop
hermes plugins remove <old-provider>
```

If a current TUI/desktop process still holds the files, do not kill it. Report that the provider is disabled/inactive and remove the residual directory after that host exits. Only remove provider-owned data directories when the user explicitly requested full removal or they were created as fresh test artifacts in the same task.

#### Windows: distinguish a plugin shim from its entry-point distribution

`hermes plugins list --plain --no-bundled` can show an **entrypoint** plugin whose displayed name/version is not the Python distribution that supplies it. For a requested full removal:

1. Run `hermes memory off` first, so config stops selecting the provider.
2. Remove any filesystem plugin shim with `hermes plugins remove <plugin-directory-name>`.
3. Re-run `hermes plugins list --plain --no-bundled`. If an entrypoint remains, identify the supplier from the Hermes runtime, then uninstall **only the explicitly requested distribution**:

   ```bash
   <hermes-venv>/Scripts/python.exe -m pip list
   <hermes-venv>/Scripts/python.exe -m pip uninstall -y <distribution>
   ```

4. Preserve provider data unless the user explicitly asked to delete it. Removing a wrapper/package is not the same as deleting its database or export.
5. If an already-disabled git plugin's official removal leaves a residual directory because a nested file could not be removed, retry recursive shell removal only after confirming the plugin is disabled and the user explicitly requested deletion. Verify the path is absent afterward.

This avoids a false-success report where `hermes plugins remove` deletes a local shim but the provider remains discoverable through an installed Python entry point.

#### Critical deletion gate: do not infer duplicates from version numbers

A provider can intentionally have both a disabled filesystem shim and an enabled Python entry point. **Do not call them duplicate providers just because their displayed versions differ.** Before removing a memory-related item, make this mapping explicit to the user:

- `hermes memory status` identifies the provider that is actually selected and active.
- `hermes plugins list --plain --no-bundled` reveals whether each registration is a `user`, `git`, or `entrypoint` plugin and whether it is enabled.
- The active entrypoint/package is required for the provider to work; removing it also requires `hermes memory off` and leaves the configuration with no external provider.
- A disabled wrapper/shim may be installed by the provider's official installer and can be required for stable local discovery even when it is not the runtime integration itself.

When a user requests removal based only on two version numbers, pause and state which one is active, which one is a shim, and the resulting provider state. Ask for confirmation if their request would remove the active provider. Treat “remove the old duplicate” as permission to remove only the inactive shim—not the active entry point—unless they explicitly say they want to disable the provider.

#### Mnemosyne Windows layout (observed)

The package-managed Mnemosyne installation can show both:

- `mnemosyne` **entrypoint 0.5.x**, enabled: the active Hermes provider integration supplied by the `mnemosyne-hermes` Python distribution.
- `hermes-mnemosyne` **user 0.4.x**, disabled: a wrapper/shim manifest created by the installer.

This is a single provider arrangement, not two concurrently active memory systems. Keep the wrapper layout intact when restoring Mnemosyne; remove it only as part of a deliberate full provider deactivation/removal.

### 3. Install into the Hermes runtime, not an arbitrary Python

First determine the interpreter that runs Hermes. On Windows, the install directory shown by `hermes --version` identifies the Hermes venv. Install Python-backed providers with that venv's Python so the gateway can import them.

For Mnemosyne, use the package-managed persistent wrapper rather than manual symlink commands:

```bash
# Replace paths with the active Hermes install and its Python.
<hermes-python> -m pip install --upgrade mnemosyne-hermes
<hermes-venv>/Scripts/mnemosyne-hermes.exe \
  --hermes-home <HERMES_HOME> install \
  --mode wrapper --python <hermes-python>
<hermes-venv>/Scripts/mnemosyne-hermes.exe \
  --hermes-home <HERMES_HOME> status
```

The wrapper mode keeps a real plugin shim in the Hermes plugin directory and avoids brittle direct symlinks across OSes or venvs.

### 4. Activate intentionally

```bash
hermes memory setup <provider>
hermes memory status
```

For a provider intended to be the sole durable memory layer, consult its current integration guide before disabling Hermes built-in file/profile injection. For Mnemosyne's documented sole-provider setup:

```bash
hermes config set memory.memory_enabled false
hermes config set memory.user_profile_enabled false
```

Do **not** disable the Hermes `memory` toolset merely to suppress built-in memory; external provider tools may be registered through that toolset.

### 5. Restart and verify the real path

```bash
hermes gateway restart
hermes gateway status
hermes memory status
```

Run two short agent-driven tests:

1. Store a harmless unique probe through the provider's write tool using **global** scope.
2. In a separate fresh Hermes session, retrieve that exact probe with the provider's recall tool.

Use global scope deliberately: a session-scoped memory is expected to be unavailable to a separate session, so it is not a valid cross-session verification probe. After successful retrieval, delete the global probe through the provider's own forget/delete path. Session-capture traces from the test may remain by design.

See `references/mnemosyne-hermes-windows.md` for the tested Windows wrapper sequence and verification interpretation.

## Cross-platform memory comparisons

When memory quality is part of an agent-platform bakeoff, do not call the comparison fair merely because both products have “persistent memory.” Use three separate conditions:

1. **Cold start:** no durable memory on either platform.
2. **Controlled memory:** give both platforms the exact same reviewed, redacted, static memory packet and record its hash. This is the primary condition for comparing task execution without retrieval differences.
3. **Native memory:** configure each platform's normal memory system and score it separately. This intentionally compares deployment experience rather than holding memory constant.

For the native condition, seed the same fact set through each provider's real write path, then verify in fresh sessions: retrieval precision and coverage, correction/invalidation, expiry, per-worker scope, contradiction handling, provenance, deletion/export, secret exclusion, latency, and operator maintenance. Persistence alone is not quality; a provider that stores everything but retrieves stale or cross-scoped facts can be worse than a smaller curated memory.

Never copy production memory databases, raw transcripts, `.env` files, browser profiles, or credentials into a benchmark. Use disposable provider state and delete the test facts through each provider's normal forget path after readback.

## Completion checklist

- [ ] Old provider is inactive and disabled; any undeletable on-disk residue is explicitly disclosed.
- [ ] New provider package and plugin wrapper are installed in the Hermes runtime.
- [ ] `hermes memory status` reports the intended provider as available and active.
- [ ] Gateway has been restarted and is running.
- [ ] A global write → separate-session recall succeeded.
- [ ] The intentional global test fact was removed.
- [ ] The user knows a fresh TUI session is needed for changed tool/context injection.
