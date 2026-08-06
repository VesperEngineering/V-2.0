# V20 Qwen Terminal Shortcut

## Goal

Provide a minimal double-clickable entrypoint for a local V20 Qwen chat.

## Design

Add one Windows command script at the V20 repository root.

- The script changes the working directory to the V20 repository root.
- It invokes exactly `ollama run qwen:64k`.
- Ollama owns the visible terminal chat; the wrapper adds no banner, prompt,
  persistence, UI, tools, scheduler, or V20 control behavior.
- The model remains the approved V20 model and no fallback is attempted.
- If Ollama is unavailable, its native error is shown and the terminal exits.

## Verification

- Static-check the script target, repository-root resolution, and exact model
  command.
- Run the launcher with a disposable non-interactive Ollama prompt and confirm
  it reaches `qwen:64k`, when the local Ollama service is available.
- Inspect the final diff and confirm unrelated dirty files are untouched.
