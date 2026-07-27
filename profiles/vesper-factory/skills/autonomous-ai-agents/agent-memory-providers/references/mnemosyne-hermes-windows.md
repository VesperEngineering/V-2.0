# Mnemosyne + Hermes on Windows: tested notes

## Installation shape

Use the Python interpreter inside the active Hermes installation. `mnemosyne-hermes` 0.5.0 installs the `mnemosyne-memory` core with embedding support and exposes a `mnemosyne-hermes` executable.

Prefer the plugin's wrapper installer:

```bash
<hermes-venv>/Scripts/mnemosyne-hermes.exe \
  --hermes-home <HERMES_HOME> install \
  --mode wrapper --python <hermes-python>
```

`status` should report both wrapper import and core-library checks as OK. `hermes memory setup mnemosyne` then selects it as the external provider.

## Important lifecycle behavior

- `hermes memory status` may still label the built-in subsystem as available. Check `memory.memory_enabled` and `memory.user_profile_enabled` explicitly when Mnemosyne is intended to replace Hermes's file/profile injection.
- Provider-specific `hermes mnemosyne` CLI commands may not be exposed by the current Hermes CLI. The standalone `mnemosyne` command remains useful for database stats and diagnostics; provider activation/state belongs to `hermes memory status`.
- A running TUI can retain a lock on a plugin's Git pack/index files even after the gateway stops. Disable and deactivate an old plugin; do not forcibly close the user's TUI just to delete it.

## Correct verification semantics

The provider write path stores ordinary conversation/tool data in working memory with session scope by default. A separate session is not expected to recall session-scoped rows. For a cross-session verification, explicitly write a harmless unique fact with `scope: global`, then retrieve it from a new session. This was verified successfully in a real Hermes write → fresh-session recall test.

Use the provider's delete/forget path to remove the intentional global probe afterwards. Automatic session capture can retain the test prompt as session-scoped working-memory metadata; that is normal and should not be treated as a failed cleanup.
