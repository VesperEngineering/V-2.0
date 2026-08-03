# Proposal Evidence Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require every Qwen-generated proposal to cite at least one controller-supplied evidence ID without requiring any proposal to be emitted.

**Architecture:** Tighten only the generated JSON schema in `AutonomousAgentRunner._response_format`. Preserve the global proposal contract and deterministic router as independent fail-closed defenses.

**Tech Stack:** Python 3.11, Pydantic 2 JSON Schema, pytest, Ruff, Ollama `qwen:64k`.

## Global Constraints

- Exact local model remains `qwen:64k` with `num_ctx=65536`, serialized, with no fallback.
- No proposal executes itself; routing remains controller-owned and advisory.
- No broker, order, account, provider, credential, risk, capital, trading, scheduler, training, promotion, deployment, protected-data, integration, push, or external action.
- Maximum three evidence-backed repair/review iterations.

---

### Task 1: Prove the missing nested lower bound

**Files:**
- Modify: `tests/platform/test_quant_agents.py`

**Interfaces:**
- Consumes: `AutonomousAgentRunner._response_format(role, authority, evidence_ids=...) -> dict[str, object]`
- Produces: regression coverage for generated proposal evidence cardinality.

- [ ] **Step 1: Add the failing assertions**

In `test_runner_response_schema_is_compact_and_bounded_for_ollama`, add:

```python
assert properties["proposals"].get("minItems", 0) == 0
assert proposal["properties"]["evidence_ids"]["minItems"] == 1
```

The first assertion preserves valid zero-proposal output. The second catches the
reported defect for every bounded quant role.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/platform/test_quant_agents.py::test_runner_response_schema_is_compact_and_bounded_for_ollama -q -p no:cacheprovider --basetemp C:\Users\bgonn\.codex\visualizations\2026\08\02\019fc120-7303-7be2-a50d-9e4e7a32b724\pytest-proposal-evidence-red
```

Expected: five failures with `KeyError: 'minItems'` at the nested proposal
evidence assertion. Any other result requires test diagnosis before production
code changes.

### Task 2: Add the minimum schema repair

**Files:**
- Modify: `vesper/platform/agent_runner.py`
- Test: `tests/platform/test_quant_agents.py`

**Interfaces:**
- Consumes: deduplicated `allowed_evidence_ids` and each recursively visited JSON
  Schema node.
- Produces: a nested `evidence_ids` array with `minItems >= 1`, bounded items, and
  the existing controller allowlist enum.

- [ ] **Step 1: Add one lower-bound assignment**

Inside the existing `field_name == "evidence_ids" and allowed_evidence_ids`
branch, before binding the item enum, add:

```python
value["minItems"] = max(int(value.get("minItems", 0)), 1)
```

- [ ] **Step 2: Run the focused test and verify GREEN**

Run the exact Task 1 command. Expected: all five parameter cases pass.

- [ ] **Step 3: Run focused regression**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/platform/test_quant_agents.py tests/platform/test_agent_authority.py tests/platform/test_agent_review.py -q -p no:cacheprovider --basetemp C:\Users\bgonn\.codex\visualizations\2026\08\02\019fc120-7303-7be2-a50d-9e4e7a32b724\pytest-proposal-evidence-focused
```

Expected: zero failures. The authority test must continue proving manually empty
proposal evidence is denied.

### Task 3: Verify repository integrity and review the patch

**Files:**
- Verify only: all changed files.

**Interfaces:**
- Consumes: completed Task 2 diff.
- Produces: fresh offline verification and an independent authority verdict.

- [ ] **Step 1: Run the full repository suite**

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --basetemp C:\Users\bgonn\.codex\visualizations\2026\08\02\019fc120-7303-7be2-a50d-9e4e7a32b724\pytest-proposal-evidence-full
```

- [ ] **Step 2: Run static and repository checks**

```powershell
.\.venv\Scripts\ruff.exe check vesper/platform/agent_runner.py tests/platform/test_quant_agents.py
.\.venv\Scripts\ruff.exe format --check vesper/platform/agent_runner.py tests/platform/test_quant_agents.py
.\.venv\Scripts\python.exe -m py_compile vesper/platform/agent_runner.py tests/platform/test_quant_agents.py
uv lock --check
git diff --check
```

- [ ] **Step 3: Inspect the final diff and obtain independent review**

The review must confirm: generated proposals require supplied evidence; zero
proposals remains valid; global contracts and router defenses are unchanged; no
authority, model, runtime, or scheduling boundary changed.

### Task 4: Run the isolated positive-routing canary

**Files:**
- Write only beneath the approved external canary state root.
- Do not modify repository production files.

**Interfaces:**
- Consumes: exact `qwen:64k`, one synthetic evidence record, an isolated review
  gate fixture, and the verified branch revision.
- Produces: one completed agent result, an admitted safe route, valid journal
  chain, and an unacknowledged daily digest.

- [ ] **Step 1: Prepare fresh isolated state**

Run these commands once. The target must not exist before the canary. The prior
session is an empty synthetic fixture used only to open this disposable test
gate; it does not touch or replace the operator's prior digest.

```powershell
$stateRoot = 'C:\Users\bgonn\.codex\visualizations\2026\08\02\019fc120-7303-7be2-a50d-9e4e7a32b724\bounded-agent-proposal-evidence-state-20260803'
if (Test-Path -LiteralPath $stateRoot) { throw 'Canary state already exists' }
New-Item -ItemType Directory -Path $stateRoot | Out-Null
$agentArgs = @(
    '--state-db', "$stateRoot\checkpoints.sqlite3",
    '--evidence-root', "$stateRoot\evidence",
    '--profiles-root', 'profiles/native',
    '--json'
)
& .\.venv\Scripts\vesper-agent.exe @agentArgs agent-digest 2026-08-02
& .\.venv\Scripts\vesper-agent.exe @agentArgs agent-review 2026-08-02 e2e-bootstrap
```

- [ ] **Step 2: Run one serialized no-tool agent turn**

Use Quant Research Lead with exactly one synthetic evidence record:

```powershell
$revision = (git rev-parse HEAD).Trim()
$evidence = '{"synthetic-evidence":{"kind":"offline-test-fixture","claim":"A hypothetical signal returned 0.02 with volatility 0.01.","live_market_data":false}}'
$objective = 'Use only synthetic-evidence. Do not call tools. Return exactly one safe research proposal, and cite synthetic-evidence inside that proposal. No code, trading, risk, training, provider, scheduler, or protected action.'
$run = & .\.venv\Scripts\vesper-agent.exe @agentArgs agent-run `
    --role v20-quant-research-lead `
    --session-id proposal-evidence-canary-20260803 `
    --objective $objective `
    --repository-revision $revision `
    --evidence-json $evidence `
    --prior-session-date 2026-08-02 | ConvertFrom-Json
```

- [ ] **Step 3: Verify controller outcomes**

Assert the response contract before rendering the digest:

```powershell
$proposal = @($run.output.proposals)[0]
$decision = @($run.decisions)[0]
if ($run.runtime -ne 'qwen:64k') { throw 'Wrong runtime' }
if (@($run.output.proposals).Count -ne 1) { throw 'Expected one proposal' }
if (@($proposal.evidence_ids).Count -ne 1 -or @($proposal.evidence_ids)[0] -ne 'synthetic-evidence') { throw 'Proposal evidence not bound' }
if ($decision.status -ne 'admitted') { throw 'Safe proposal was not admitted' }
if ($decision.routed_to -ne 'v20-quant-research-lead') { throw 'Unexpected route' }
ollama ps
```

`agent-run` returns routing decisions only and has no proposal-execution path.
The digest command in the next step re-verifies the journal chain.

- [ ] **Step 4: Render but do not acknowledge the digest**

Verify eight role sections, stable digest hash, no tool calls, the admitted route,
and a closed new-proposal gate until operator review:

```powershell
$digest1 = & .\.venv\Scripts\vesper-agent.exe @agentArgs agent-digest 2026-08-03 | ConvertFrom-Json
$digest2 = & .\.venv\Scripts\vesper-agent.exe @agentArgs agent-digest 2026-08-03 | ConvertFrom-Json
$gate = & .\.venv\Scripts\vesper-agent.exe @agentArgs agent-gate 2026-08-03 | ConvertFrom-Json
$document = Get-Content -Raw -LiteralPath $digest1.json_path | ConvertFrom-Json
$events = @($document.sections | ForEach-Object { $_.events })
$proposalEvent = @($events | Where-Object event_type -eq 'proposal-created')
$routeEvent = @($events | Where-Object event_type -eq 'routing-decision')
if (@($digest1.sections).Count -ne 8) { throw 'Digest roster incomplete' }
if ($digest1.sha256 -ne $digest2.sha256) { throw 'Digest is not stable' }
if (@($events | Where-Object event_type -in @('tool-request', 'tool-result')).Count -ne 0) { throw 'Unexpected tool event' }
if ($proposalEvent.Count -ne 1 -or $proposalEvent[0].payload.evidence_ids -ne 'synthetic-evidence') { throw 'Digest proposal evidence missing' }
if ($routeEvent.Count -ne 1 -or $routeEvent[0].payload.status -ne 'admitted') { throw 'Digest route missing' }
if ($gate.new_proposals_admitted) { throw 'Unreviewed digest opened the gate' }
```

- [ ] **Step 5: Record receipts and commit the focused repair**

Update the bounded receipt with exact commands/results and remaining risk. Commit
only the intended test and production repair after the already-reviewed design
and plan commit. Do not integrate or push.
