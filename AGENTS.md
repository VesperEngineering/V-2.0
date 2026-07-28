# VESPER 2.0 Agent Rules

Scope: this file applies to the `C:\Users\bgonn\Desktop\v20` repository.

## 0. Mandatory Pre-Flight Checklist

**Before writing or editing any code, you MUST:**

1. **Load relevant skills.** Scan the available skill list (`skills_list`) and load any skill that matches the task — even partially. Err on the side of loading. Skills encode API endpoints, tool-specific commands, and proven workflows that outperform general-purpose approaches. If a skill is missing steps or has wrong commands, patch it immediately.
2. **Query the CodeGraph index.** v20 has a `.codegraph/` index at project root. Use `codegraph_explore` on the exact symbols/files you plan to change before editing. Do not rely on memory or prior file reads alone.
3. **Read `SKILLS/CODE.md` and `SKILLS/EXAMPLES.md`.** These are the project's coding constitution. `CODE.md` states the principles; `EXAMPLES.md` shows concrete right/wrong patterns. If your planned change violates any example in `EXAMPLES.md`, stop and reconsider.
4. **State assumptions explicitly.** If uncertain, ask. If multiple interpretations exist, present them — don't pick silently. See `EXAMPLES.md` "Hidden Assumptions" and "Multiple Interpretations" sections.

**Failure to follow this checklist is a protocol violation.** Do not skip it because the task "seems simple."

---

## 1. Product Direction

- **Default strategy: `ml_model`.** This is the intended V2 default. The engine recognizes both `ml_model` and `momentum`; `config/settings.yaml` selects the active strategy. Adding strategies beyond these two is not in scope unless explicitly requested.
- **Simple, understandable quant machine.** The goal is a lean system that can eventually rival HRT and Renaissance Technologies. Ambition is high, but the path is through simplicity and clarity — not bloat, abstractions, or speculative features.
- **No speculative features.** If a feature isn't needed for the current task, don't add it. If you write 200 lines and it could be 50, rewrite it. See `EXAMPLES.md` "Over-abstraction" and "Speculative Features" sections.

---

## 2. Code Principles (from `SKILLS/CODE.md`)

### 2.1 Think Before Coding
- State assumptions explicitly before implementing.
- If something is unclear, stop. Name what's confusing. Ask.
- If a simpler approach exists, say so. Push back when warranted.

### 2.2 Simplicity First
- Minimum code that solves the problem. Nothing speculative.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.

### 2.3 Surgical Changes
- Touch only what you must. Clean up only your own mess.
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- The test: **Every changed line should trace directly to the user's request.**
- See `EXAMPLES.md` "Drive-by Refactoring" and "Style Drift" sections.

### 2.4 Goal-Driven Execution
- Transform tasks into verifiable goals:
  - "Add validation" → "Write tests for invalid inputs, then make them pass"
  - "Fix the bug" → "Write a test that reproduces it, then make it pass"
  - "Refactor X" → "Ensure tests pass before and after"
- For multi-step work, state a brief plan with verification at each step.
- "Looks right" and unrecorded manual inspection are not verification.
- See `EXAMPLES.md` "Vague vs. Verifiable" and "Test-First Verification" sections.

---

## 3. Data Boundaries

### 3.1 The `/data` Folder Is Sacred
- **DO NOT modify, delete, move, or write to anything under `vesper/data/massive/` or `vesper/data/model_research/`.**
- This data was retrieved from Massive and is read-only for v20. Treat it as an external dependency.
- If you need to cache or store derived data, use `data/market_cache.db` or a new path outside `vesper/data/massive/`.

### 3.2 Massive Is the Data Provider
- The configured data provider in `config/settings.yaml` is `massive` (local SQLite).
- The `MassiveFeed` class in `vesper/data/feed.py` reads from `vesper/data/massive/sp500/sp500_ohlcv.sqlite`.
- Do not revert the provider to `yfinance` without explicit user approval.
- The SP500 SQLite contains **raw unadjusted prices**. Split adjustment must be applied before using prices for features, backtests, or model training. See `vesper/data/features.py` for the current feature computation logic.

### 3.3 Data Source of Truth
- `D:\vesper\vesper_data` is the canonical massive data store (190+ GB). The v20 `vesper/data/massive/` folder is a subset/copy.
- If data appears stale, check `D:\vesper\vesper_data\massive\sp500\sp500_ohlcv.sqlite` before assuming data loss.
- The 33-ticker adjusted/total_return datasets are for validation only, not for broad backtesting. The 502-ticker SP500 store is the primary backtest data source.

---

## 4. Model & Strategy Constraints

### 4.1 Current Model Artifact
- `config/settings.yaml` references `models/xgb_ranker.json`, which currently exists with companion evidence in `models/xgb_ranker.metadata.json`.
- Treat the metadata and current artifact bytes as the source of truth for hash, parameters, samples, and reported metrics; verify them before use rather than copying stale values into policy.
- The artifact is research evidence only. Its existence and engine wiring do not establish deployment, live-trading, capital-allocation, or model-promotion authority.
- Do not fabricate, silently replace, or substitute model artifacts. New training or model-family changes require an admitted experiment contract and the authority gates in Section 5.

### 4.2 Engine Wiring
- `vesper/engine.py` recognizes `momentum` and `ml_model` as first-class strategy options and rejects unknown names.
- `MLModelStrategy` fails closed when its configured model artifact is missing.
- Do not add fallback logic that silently switches to `momentum` when `ml_model` fails to load. Fail closed.

---

## 5. Execution Authority

### 5.1 Denied Authority
The following require explicit human approval. Do not attempt them:
- Broker or provider credential changes
- Risk limit modifications (`config/settings.yaml` `risk:` section)
- Trading parameter changes (position sizing, thresholds, intervals)
- Order execution or position modification
- Capital allocation changes
- Deployment to live trading
- Scheduler configuration changes
- Any paid compute or paid provider use, including GPU/cloud training
- Modifying `vesper/data/massive/` or `vesper/data/model_research/` in any way
- Model promotion or replacement of active model artifacts

### 5.2 Allowed Authority
- Code reading and inspection
- Test writing and running
- Documentation updates
- Bug fixes in non-critical paths
- Strategy research code (read-only analysis, not execution)
- Writing feed adapters and data pipelines (read-only from Massive data)
- Any change reviewed and approved by the user

### 5.3 Private-Chat Credential Handling
- The user may share API keys and other credentials in the current private chat, and agents may acknowledge, reference, and discuss them there when needed for the task.
- This permission is limited to the chat itself. Never reproduce a credential in repository files, patches, commands or tool calls, terminal output or logs, tests, fixtures, screenshots, reports, generated artifacts, Git staging/commits/history, external messages or services, or any public display.
- Outside the private chat, refer to credentials only in redacted or masked form. If a task requires a raw credential to leave the chat or be persisted, stop and request a secure alternative.
- Sharing or discussing a credential does not authorize using, validating, rotating, revoking, or changing it, and does not expand any other authority in this file.

---

## 6. Verification Requirements

### 6.1 Before Declaring Done
1. Inspect the final diff for scope and accidental churn.
2. Run the smallest relevant tests, then the required project suite when practical.
3. Run `python -m py_compile <file>` on any modified Python file.
4. Distinguish actual results from assumptions in your report.

### 6.2 No Fabrication
- Never substitute plausible-looking fabricated output (made-up data, invented file contents, synthesized API responses) for results you couldn't actually produce.
- Reporting a blocker honestly is always better than inventing a result.
- If a tool fails and blocks the real path, say so directly and try an alternative.

---

## 7. Anti-Patterns (from `SKILLS/EXAMPLES.md`)

| Principle | Anti-Pattern | Fix |
|-----------|-------------|-----|
| Think Before Coding | Silently assumes file format, fields, scope | List assumptions explicitly, ask for clarification |
| Simplicity First | Strategy pattern for single discount calculation | One function until complexity is actually needed |
| Surgical Changes | Reformats quotes, adds type hints while fixing bug | Only change lines that fix the reported issue |
| Goal-Driven | "I'll review and improve the code" | "Write test for bug X → make it pass → verify no regressions" |

---

## 8. Session Handoff

- If you are leaving work incomplete, state exactly what was done, what remains, and what the next agent should do first.
- Do not claim work is verified or complete when a required check was skipped, failed, or was not available. State the open gate precisely.
- Record durable facts (user preferences, environment details, stable conventions) to Mnemosyne memory. Do not record task progress, session outcomes, or temporary TODO state.

## 8. Worker Heartbeats

- A worker assigned a `running` V20 Kanban task must emit `hermes kanban --board v20 heartbeat <task-id> --note "<short current action>"` when work starts and at least every 60 seconds while it is actively working.
- A worker that cannot continue must block or complete its card; it must not leave a stale `running` status.

---

*Last updated: 2026-07-28. If this file conflicts with `SKILLS/CODE.md`, `SKILLS/CODE.md` wins on coding style and `AGENTS.md` wins on project-specific authority boundaries.*
