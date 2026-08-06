# V20 Qwen Chat CLI

## Goal

Provide a native V20 terminal chat that lets the local `qwen:64k` model inspect
and continue repository work through controller-owned, role-scoped tools.

## CLI contract

```text
uv run --locked vesper-agent chat
  --role v20-development
  --model qwen:64k
  [--skill knowledge/skills/<approved-skill>.md ...]
  [--tool <allowed-tool> ...]
  [--session-id <id>]
  [--workspace <repository-relative-path>]
  [--json]
```

The default interactive mode reads prompts from the terminal until Ctrl-C or
EOF. `--json` emits one JSON object per assistant/tool event for a future TUI
or script consumer. Human mode also supports local `/help`, `/status`, `/model`,
`/mode`, `/skills`, `/tools`, `/clear`, `/compact`, `/diff`, `/search`,
`/graph`, `/test`, and `/quit` commands. `/model coding` and `/model daily`
select bounded instruction profiles while keeping the actual model pinned to
`qwen:64k`; switching profiles clears history. These commands do not invoke
Qwen. The first slice accepts only `qwen:64k`; model diversity is not silently
introduced.

Human mode prints a compact runtime header with model, mode, context window,
input budget, output reserve, loaded rules/skills, and workspace. During each
turn it reports observed prompt tokens, remaining input budget, generated
tokens, and controller tool start/completion events. Markers are ASCII-safe for
Windows terminals; `--json` emits equivalent telemetry events.

## Tool boundary

The controller exposes only explicit tools:

- `read_file`, `search_text`
- `codegraph_query`, `codegraph_explore`, `codegraph_node`, `codegraph_affected`
- `write_file`, `git_diff_check`
- `run_test` with fixed local pytest/Cargo command forms

CodeGraph commands run from the repository root with bounded time and output.
The model cannot execute arbitrary shell, invoke CodeGraph administration,
access credentials or protected data, use network/broker/scheduler controls, or
commit/push Git history. Writes remain repository-relative and protected paths
are denied by the controller.

## Context and persistence

Every first turn includes the root `AGENTS.md`, applicable nested `AGENTS.md`
files from the selected workspace, the default engineering skill, and approved
skills matched to the workspace/task tags. Explicit `--skill` files are added
to that set. The controller caps injected context at 45,000 characters; the
Qwen runtime separately rejects prompts over its 49,152-token input budget.
Full redacted transcripts are persisted under the existing V20 local state
root, isolated by session and role. Repository instructions and controller
policy outrank model text, skills, and chat history.

## Verification

- Unit-test model/tool/skill validation, CodeGraph argument validation, path and
  command safety, session persistence, and CLI routing.
- Run a fake-client interactive turn proving read/search/codegraph flow and a
  guarded write/test flow.
- Run a live no-write Qwen canary against `qwen:64k` and a CodeGraph query.
- Run focused platform tests and inspect the final diff without touching
  unrelated dirty work.
