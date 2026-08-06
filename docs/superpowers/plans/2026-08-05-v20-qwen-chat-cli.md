# V20 Qwen Chat CLI Implementation Plan

## Scope

Build the smallest native V20 terminal agent surface that lets local `qwen:64k` work on a bounded repository workspace through controller-owned tools. Keep the first slice development-only and fail closed outside the approved role, model, paths, and commands.

## Implementation steps

1. Add a chat policy and controller gateway.
   - Define the only accepted chat role (`v20-development`) and model (`qwen:64k`).
   - Load root and workspace-nearest `AGENTS.md` files in specificity order.
   - Select approved skills by task/workspace tags, always including engineering,
     while honoring explicit skill paths.
   - Cap injected context below the Qwen input budget.
   - Validate approved skill paths under `knowledge/skills/`.
   - Add fixed CodeGraph read operations: `query`, `explore`, `node`, and `affected`.
   - Add a fixed test runner for focused local pytest/Cargo commands.
   - Enforce repository-relative workspace boundaries, protected paths, bounded output, timeouts, and no arbitrary shell.

2. Add interactive Qwen session support.
   - Reuse the existing Ollama/Qwen runner and tool-call protocol.
   - Support system context, multi-turn history, and tool results without changing existing autonomous-agent behavior.
   - Persist redacted session events using the existing V20 session recorder.

3. Expose the CLI.
   - Add `vesper-agent chat` with safe defaults and explicit `--allow-write` for write/test tools.
   - Support repeated `--skill` and `--tool` options, `--workspace`, `--session-id`, and `--json`.
   - Route the command through `LocalPlatformService` while preserving existing CLI commands and exit codes.

4. Point the shortcut at the native CLI.
   - Keep the launcher rooted at the live V20 checkout.
   - Start the bounded TUI workspace chat with the pinned model and approved engineering skill.

5. Verify.
   - Add unit tests for policy, path/command/tool safety, session behavior, runner history, and CLI routing.
   - Run focused tests, CLI help, and a live read-only Qwen/CodeGraph canary.
   - Inspect the diff and report any unrelated dirty files unchanged.

## Acceptance criteria

- `uv run --locked vesper-agent chat --help` exposes the native chat command.
- A default chat can use Qwen and read/search/CodeGraph tools but cannot use arbitrary shell or protected paths.
- Writes and tests require `--allow-write` and remain workspace-scoped.
- Sessions record redacted events under the existing V20 session root.
- Existing platform/Qwen tests remain green.
- The shortcut opens the native CLI, not raw `ollama run`.

## Review

The plan deliberately avoids OpenCode/MCP, model fallback, autonomous scheduling, broker/provider access, credentials, Git mutation, and broad shell execution. Those are separate later slices.
