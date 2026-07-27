# M1 Dependency Receipt

- Recorded: 2026-07-27
- Branch: `main`
- Baseline commit: `9f9df7cf483bd77603dd5bf8c145c80c58aeb0e2`
- Python: `3.11.15`
- uv: `0.11.32`
- Resolution: 79 packages
- Decision: compatible LangGraph/SQLite stack accepted; LangMem remains deferred

## Scope and policy decision

The operator approved `langsmith` only as an inert transitive dependency required by
LangGraph's `langchain-core` closure. It is not a direct V20 dependency and is not an approved V20
service. V20 does not import LangSmith application APIs, configure an account or key, enable
tracing/telemetry/Studio/hosted evaluation, or use remote persistence.

Before importing LangGraph runtime modules, V20 force-sets:

```text
LANGSMITH_TRACING=false
LANGSMITH_TRACING_V2=false
LANGCHAIN_TRACING_V2=false
LANGGRAPH_CLI_NO_ANALYTICS=1
```

A fresh-process test begins with all of those controls deliberately enabled, installs a socket
deny-egress guard before platform/LangGraph imports, confirms V20 overrides the environment, and
executes Store setup/read/write/search, graph execution, checkpoint history, a real interrupt, a
persisted operator decision, and resume. The test observes no network attempt.

## Direct platform dependencies

| Distribution | Resolved | License | Purpose |
| --- | ---: | --- | --- |
| `langgraph` | `1.2.9` | MIT | State graph, routing, interrupts, and resume. |
| `langgraph-checkpoint-sqlite` | `3.1.0` | MIT | Local synchronous SQLite checkpoints and Store. |
| `openai-codex` | `0.144.4` | Apache-2.0 | Existing lazy local SDK boundary; not invoked by this slice. |
| `pydantic` | `2.13.4` | MIT | Strict typed contracts. |
| `typer` | `0.27.0` | MIT | Local control surface. |
| `pyyaml` | `6.0.3` | MIT | Existing profile configuration dependency; not duplicated. |

All resolved direct packages support V20's `>=3.11,<3.12` Python range.

## LangGraph transitive closure changes

| Distribution | Resolved | Declared license | Role |
| --- | ---: | --- | --- |
| `langgraph-checkpoint` | `4.1.1` | MIT | Checkpoint protocols and serialization. |
| `langgraph-prebuilt` | `1.1.0` | MIT | LangGraph prebuilt support. |
| `langgraph-sdk` | `0.4.2` | MIT | Required LangGraph distribution dependency; not used for hosted access. |
| `langchain-core` | `1.5.1` | MIT | Required LangGraph core abstractions; the full `langchain` package is absent. |
| `langchain-protocol` | `0.0.18` | MIT | Shared protocol types. |
| `langsmith` | `0.10.10` | MIT | Accepted inert transitive only; no V20 service approval. |
| `aiosqlite` | `0.22.1` | MIT (project metadata/classifier) | SQLite async support required by checkpoint package. |
| `sqlite-vec` | `0.1.9` | MIT / Apache-2.0 | SQLite Store dependency; no hosted vector database. |
| `ormsgpack` | `1.12.2` | Apache-2.0 OR MIT | Checkpoint serialization. |
| `orjson` | `3.11.9` | MPL-2.0 AND (Apache-2.0 OR MIT) | SDK/LangSmith serialization. |
| `xxhash` | `3.8.1` | BSD-2-Clause | LangGraph hashing. |
| `zstandard` | `0.25.0` | BSD-3-Clause | LangSmith package dependency; no remote use. |
| `jsonpatch` / `jsonpointer` | `1.33` / `3.1.1` | Modified BSD | `langchain-core` structured updates. |
| `requests-toolbelt` | `1.0.0` | Apache-2.0 | LangSmith package dependency; denied in the tested graph path. |
| `uuid-utils` | `0.17.0` | BSD-3-Clause | Core identifiers. |

The resolution also changes `websockets` from the earlier accepted lock's `16.1.1` to `15.0.1`
because both `langgraph-sdk==0.4.2` and the existing `alpaca-py` range resolve compatibly there.
`uv pip check` is the final compatibility gate. No critical package is removed.

## LangMem decision

`langmem` is not present in `pyproject.toml` or `uv.lock`. The evaluated current package requires
the full `langchain` distribution plus OpenAI and Anthropic provider integrations. V20 instead uses
its typed memory contracts and controller-owned local Store boundary. Adding LangMem remains a
separate future dependency/provider review.

## Security and compatibility findings

- `langgraph-checkpoint-sqlite==3.1.0` is newer than the `3.0.1` fix for
  [GHSA-9rwj-6rc7-p77c](https://github.com/advisories/GHSA-9rwj-6rc7-p77c).
- No comprehensive vulnerability scanner was added. Review was limited to official metadata,
  published advisories, lock inspection, import/network tests, `uv lock --check`, and
  `uv pip check`.
- The lock contains no `langmem`, full `langchain`, `langchain-openai`, or
  `langchain-anthropic` record.
- Source inspection finds no direct `langsmith` import in V20 or its platform tests.
- No package was installed globally, and no credential or external runtime service was used.

## Material commands

```powershell
uv lock
uv tree --locked --package langgraph --depth 4
uv tree --locked --invert --package langsmith
uv tree --locked --invert --package langchain-core
rg -n '^name = "(langmem|langchain|langchain-openai|langchain-anthropic)"' uv.lock
rg -n '^\s*(from|import)\s+langsmith' vesper tests
$env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\Temp\v20-langgraph-20260727"
uv sync --locked --all-groups
python -m pytest tests/platform/test_dependencies.py tests/platform/test_runtime_environment.py -q
python -m pytest tests/platform/test_langsmith_network_isolation.py -q
```

Final locked-environment results are recorded in `M1-M7-offline-slice-receipt.md`.
