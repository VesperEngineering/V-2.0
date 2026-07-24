# Learning and Bounded Code Autonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build evidence-backed learning, bounded routing/template improvement, an inspectable Memory view, and fail-closed automatic acceptance of non-critical code only into local `factory/accepted`.

**Architecture:** Plan 05 upgrades the Plan 04 database from schema `2` to
schema `3`, then projects immutable attempts, manifests, evidence, and evaluator
receipts into SQLite learning records. FTS5 indexes bounded summaries and
references only. Candidates do not alter active context, routing, policy, or
templates until a frozen-budget canary beats the active version; accepted code
is independently reviewed, canaried, rollback-ready, and merged locally only.

**Tech Stack:** Python 3.11, stdlib SQLite FTS5/hashlib/subprocess, pytest, React 19, TypeScript, Vitest, React Testing Library, Tauri 2.

## Global Constraints

- Requires accepted Plans 01–04: Plan 01 provides schema/events/evidence/receipts/snapshot/authentication; Plan 03 provides isolated local worktrees and runtime identity; Plan 04 provides immutable manifests and independent evaluator receipts.
- Before every edit read `AGENTS.md`, `SKILLS/CODE.md`, and `SKILLS/EXAMPLES.md`; query the current CodeGraph for every changed symbol and record query results as evidence. Stop if the canonical checkout has no current `.codegraph`.
- Serialize and rebase shared changes to
  `vesper/factory/learning_migration.py`, `vesper/factory/migrations.py`,
  `vesper/factory/contracts.py`, `vesper/factory/commands.py`,
  `vesper/factory/snapshot.py`, `vesper/factory/kernel.py`, and
  `apps/desktop/src/contracts/factory.ts`.
- Do not edit `config/`, `vesper/risk.py`, `vesper/execution/`, `vesper/scheduler/`, `vesper/data/massive/`, `vesper/data/model_research/`, `models/xgb_ranker.json`, `models/xgb_ranker.metadata.json`, or an active model artifact.
- No remote push, release, deployment, protected edit, active model promotion, live effect, broker call, credential change, risk/capital change, or paid compute is permitted.
- Episode IDs are existing `atm_...` attempt IDs; lesson IDs are `lsn_...`. Use canonical UTF-8 JSON, SHA-256 hashes, and UTC RFC 3339 `Z` timestamps.
- Every task is test-first, runs `python -m py_compile` for changed Python modules, checks `git diff --check`, `git diff --stat`, its focused diff, and ends with one focused commit.

## M5 Acceptance Gate

M5 requires one temporary-SQLite/local-Git integration test proving the
`2 → 3` migration and readiness/health schema `3`, authoritative episodes and
bounded FTS, three-episode/reproduced-defect promotion, canary
activation/rollback, Memory inspection, and local-only code acceptance. Any
missing preflight, CodeGraph query, protected-path check, test/compile result,
evaluator receipt, canary receipt, rollback receipt, or local target blocks
without merge.

## File Structure

- Create: `vesper/factory/learning_migration.py` — database migration `3`
  with learning records and FTS5.
- Modify: `vesper/factory/migrations.py` — register migration `3` after the
  Plan 04 migration.
- Create: `vesper/factory/learning.py` — episodes, FTS documents/search, lesson promotion, context selection.
- Create: `vesper/factory/routing.py` — runtime stats, candidates, canaries, activation, rollback.
- Create: `vesper/factory/autonomy.py` — automatic local code acceptance.
- Modify: `vesper/factory/contracts.py`,
  `vesper/factory/research/evaluation.py`, `vesper/factory/commands.py`,
  `vesper/factory/snapshot.py`, `vesper/factory/kernel.py`.
- Create: `tests/factory/test_learning.py`, `tests/factory/test_routing.py`, `tests/factory/test_autonomy.py`, `tests/factory/test_learning_api.py`.
- Modify: `apps/desktop/src/contracts/factory.ts`, `apps/desktop/src/App.tsx`.
- Create: `apps/desktop/src/features/memory/MemoryView.tsx`, `apps/desktop/src/features/memory/MemoryView.test.tsx`.

## New Interfaces

~~~python
from dataclasses import dataclass
from typing import Literal

LessonStatus = Literal["CANDIDATE", "CANARY", "ACTIVE", "REJECTED", "REVERTED"]
LessonKind = Literal["CONTEXT", "ROUTING", "POLICY", "TEMPLATE", "DEFECT"]

@dataclass(frozen=True)
class VerifiedEpisodeV1:
    attempt_id: str
    task_id: str
    campaign_id: str
    work_kind: str
    runtime: str
    template_id: str
    template_version: str
    context_hash: str
    contract_hash: str
    input_hash: str
    manifest_id: str
    outcome: Literal["VERIFIED", "REJECTED", "FAILED", "BLOCKED", "INCONCLUSIVE", "INTERRUPTED", "AMBIGUOUS"]
    evaluator_receipt_id: str
    duration_ms: int
    retry_count: int
    completed_at: str

@dataclass(frozen=True)
class ContextSelectionV1:
    work_kind: str
    query: str
    lesson_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    text: str
    context_hash: str

@dataclass(frozen=True)
class CodeAcceptanceRequestV1:
    campaign_id: str
    attempt_id: str
    source_commit: str
    target_branch: Literal["factory/accepted"]
    factory_repo: str
    worktree: str
    changed_symbols: tuple[str, ...]
    focused_test_commands: tuple[tuple[str, ...], ...]
    full_suite_command: tuple[str, ...]
    evaluator_receipt_id: str
    canary_receipt_id: str
    rollback_receipt_id: str

@dataclass(frozen=True)
class CodeAcceptanceResultV1:
    accepted: bool
    receipt_id: str
    merge_commit: str | None
    denial_code: str | None
~~~

An episode is valid only with a complete/hash-valid immutable manifest and latest receipt `kind="evaluation.verdict"`, `authority="independent-evaluator-v1"`, and an authoritative terminal outcome. Context contains only lesson statements and bounded evidence/contract summaries, never raw reports, secrets, tokens, or database handles.

### Task 1: Add Learning Schema and Contracts

**Files:**
- Create: `vesper/factory/learning_migration.py`
- Modify: `vesper/factory/migrations.py`
- Modify: `vesper/factory/contracts.py`
- Test: `tests/factory/test_learning.py`

**Dependencies:** accepted Plan 01 migration/event/receipt contracts, database
schema `2` from Plan 04, and the Plan 04 evaluator receipt contract.
Reuse Plan 04's real schema-2 temporary-database fixture as `db_path_v2`; do
not construct a synthetic subset of predecessor tables.

**Interfaces:**
- Consumes: `attempts`, `tasks`, `campaigns`, `receipts`, `evidence`, `FactorySnapshotV1`.
- Produces: learning tables plus additive `LessonSummaryV1`, `RoutingStatV1`, `FactorySnapshotV1.lessons`, and `FactorySnapshotV1.routing_stats`.

- [ ] **Step 1: Query CodeGraph and write the failing migration test**

~~~python
def test_learning_migration_upgrades_schema_two_to_three(db_path_v2):
    migrate_factory(db_path_v2)
    with sqlite3.connect(db_path_v2) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        names = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        )}
    assert {
        "learning_episodes", "lessons", "lesson_episode_links",
        "routing_stats", "learning_canaries", "learning_documents", "learning_fts",
    } <= names
~~~

- [ ] **Step 2: Run the test to verify it fails**

Run:

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_learning.py::test_learning_migration_upgrades_schema_two_to_three -q
~~~

Expected: FAIL because the Plan 05 migration does not exist.

- [ ] **Step 3: Implement the transaction migration and additive snapshot contracts**

~~~python
SCHEMA_V3 = """
CREATE TABLE learning_episodes (
 attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id),
 task_id TEXT NOT NULL REFERENCES tasks(task_id), campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
 work_kind TEXT NOT NULL, runtime TEXT NOT NULL, template_id TEXT NOT NULL, template_version TEXT NOT NULL,
 context_hash TEXT NOT NULL, contract_hash TEXT NOT NULL, input_hash TEXT NOT NULL,
 manifest_id TEXT NOT NULL REFERENCES evidence(evidence_id),
 outcome TEXT NOT NULL CHECK(outcome IN ('VERIFIED','REJECTED','FAILED','BLOCKED','INCONCLUSIVE','INTERRUPTED','AMBIGUOUS')),
 evaluator_receipt_id TEXT NOT NULL REFERENCES receipts(receipt_id),
 duration_ms INTEGER NOT NULL CHECK(duration_ms >= 0), retry_count INTEGER NOT NULL CHECK(retry_count >= 0),
 completed_at TEXT NOT NULL
);
CREATE TABLE lessons (
 lesson_id TEXT PRIMARY KEY,
 kind TEXT NOT NULL CHECK(kind IN ('CONTEXT','ROUTING','POLICY','TEMPLATE','DEFECT')),
 status TEXT NOT NULL CHECK(status IN ('CANDIDATE','CANARY','ACTIVE','REJECTED','REVERTED')),
 work_kind TEXT NOT NULL, statement TEXT NOT NULL, scope_hash TEXT NOT NULL, version TEXT NOT NULL,
 predecessor_lesson_id TEXT REFERENCES lessons(lesson_id),
 contradiction_count INTEGER NOT NULL DEFAULT 0 CHECK(contradiction_count >= 0),
 created_at TEXT NOT NULL, decided_at TEXT, decision_receipt_id TEXT REFERENCES receipts(receipt_id),
 UNIQUE(kind, work_kind, scope_hash, version)
);
CREATE TABLE lesson_episode_links (
 lesson_id TEXT NOT NULL REFERENCES lessons(lesson_id),
 attempt_id TEXT NOT NULL REFERENCES learning_episodes(attempt_id),
 relation TEXT NOT NULL CHECK(relation IN ('SUPPORTS','CONTRADICTS','REPRODUCTION','FIX')),
 PRIMARY KEY(lesson_id, attempt_id, relation)
);
CREATE TABLE routing_stats (
 runtime TEXT NOT NULL, template_id TEXT NOT NULL, template_version TEXT NOT NULL, work_kind TEXT NOT NULL,
 verified_count INTEGER NOT NULL DEFAULT 0, rejected_count INTEGER NOT NULL DEFAULT 0,
 total_duration_ms INTEGER NOT NULL DEFAULT 0, total_retries INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
 PRIMARY KEY(runtime, template_id, template_version, work_kind)
);
CREATE TABLE learning_canaries (
 lesson_id TEXT NOT NULL REFERENCES lessons(lesson_id), baseline_lesson_id TEXT NOT NULL REFERENCES lessons(lesson_id),
 attempt_id TEXT NOT NULL REFERENCES learning_episodes(attempt_id),
 allocation TEXT NOT NULL CHECK(allocation IN ('BASELINE','CANDIDATE')),
 result TEXT NOT NULL CHECK(result IN ('PENDING','VERIFIED','REJECTED','FAILED','BLOCKED','INCONCLUSIVE','INTERRUPTED','AMBIGUOUS')),
 created_at TEXT NOT NULL, completed_at TEXT, PRIMARY KEY(lesson_id, attempt_id)
);
CREATE TABLE learning_documents (
 source_kind TEXT NOT NULL CHECK(source_kind IN ('EVIDENCE','CONTRACT','LESSON')),
 source_id TEXT NOT NULL, work_kind TEXT NOT NULL, summary TEXT NOT NULL, content_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(source_kind, source_id)
);
CREATE VIRTUAL TABLE learning_fts USING fts5(
 source_kind UNINDEXED, source_id UNINDEXED, work_kind UNINDEXED, summary,
 tokenize='unicode61 remove_diacritics 2'
);
"""
~~~

Register `Migration(version=3, name="learning_autonomy", sql=SCHEMA_V3)` after
the Plan 04 migration without changing either earlier migration or its stored
checksum. Add at the end of `FactorySnapshotV1` with defaults:

~~~python
@dataclass(frozen=True)
class LessonSummaryV1:
    lesson_id: str; kind: LessonKind; status: LessonStatus; work_kind: str
    statement: str; version: str; supporting_attempt_ids: tuple[str, ...]
    contradiction_count: int; created_at: str

@dataclass(frozen=True)
class RoutingStatV1:
    runtime: str; template_id: str; template_version: str; work_kind: str
    verified_count: int; rejected_count: int; mean_duration_ms: int; mean_retries: float

lessons: tuple[LessonSummaryV1, ...] = ()
routing_stats: tuple[RoutingStatV1, ...] = ()
~~~

- [ ] **Step 4: Run the test to verify it passes**

Run:

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_learning.py::test_learning_migration_upgrades_schema_two_to_three -q
python -m py_compile vesper/factory/learning_migration.py vesper/factory/migrations.py vesper/factory/contracts.py
~~~

Expected: PASS; compilation is silent.

- [ ] **Step 5: Commit**

~~~bash
git diff --check
git diff --stat
git diff -- vesper/factory/learning_migration.py vesper/factory/migrations.py vesper/factory/contracts.py tests/factory/test_learning.py
git add vesper/factory/learning_migration.py vesper/factory/migrations.py vesper/factory/contracts.py tests/factory/test_learning.py
git commit -m "feat(factory): add learning storage contracts"
~~~

### Task 2: Record Verified Episodes and Search FTS5

**Files:**
- Create: `vesper/factory/learning.py`
- Modify: `vesper/factory/research/evaluation.py`
- Test: `tests/factory/test_learning.py`

**Dependencies:** Task 1 and the Plan 04 receipt append path.

**Interfaces:**
- Produces: `LearningService.record_episode(attempt_id: str) -> VerifiedEpisodeV1` and `search(query: str, work_kind: str, limit: int) -> tuple[SearchHitV1, ...]`.

- [ ] **Step 1: Write failing recorder/search tests**

~~~python
def test_record_episode_is_authoritative_and_idempotent(factory):
    attempt_id = factory.seed_completed_attempt(
        outcome="VERIFIED", manifest_complete=True, evaluator_authority="independent-evaluator-v1"
    )
    first = factory.learning.record_episode(attempt_id)
    assert factory.learning.record_episode(attempt_id) == first
    assert factory.count_rows("learning_episodes") == 1

def test_fts_indexes_bounded_summary_not_raw_report(factory):
    attempt_id = factory.seed_completed_attempt(
        outcome="VERIFIED", evidence_summary="split-adjusted chronology passed", raw_report="x" * 50000
    )
    factory.learning.record_episode(attempt_id)
    hits = factory.learning.search("chronology", "research", 5)
    assert hits[0].source_kind == "EVIDENCE"
    assert "x" * 100 not in hits[0].summary
    assert hits[0].content_hash.startswith("sha256:")
~~~

- [ ] **Step 2: Run the tests red**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_learning.py::test_record_episode_is_authoritative_and_idempotent tests/factory/test_learning.py::test_fts_indexes_bounded_summary_not_raw_report -q
~~~

Expected: FAIL because `LearningService` does not exist.

- [ ] **Step 3: Implement episode and FTS behavior**

Validate the latest evaluator receipt, immutable manifest, and terminal outcome inside the existing transaction wrapper. Return an existing row for repeated `attempt_id`. Cap evidence, contract, and lesson index summaries at 2,000 Unicode code points before canonical hashing.

~~~python
MAX_INDEXED_SUMMARY_CHARS = 2_000

def record_episode(self, attempt_id: str) -> VerifiedEpisodeV1:
    with self._store.transaction() as connection:
        existing = self._load_episode(connection, attempt_id)
        if existing is not None:
            return existing
        source = self._load_authoritative_attempt(connection, attempt_id)
        self._require_complete_manifest(source.manifest_id)
        episode = VerifiedEpisodeV1(
            source.attempt_id, source.task_id, source.campaign_id, source.work_kind,
            source.runtime, source.template_id, source.template_version, source.context_hash,
            source.contract_hash, source.input_hash, source.manifest_id, source.outcome,
            source.evaluator_receipt_id, source.duration_ms, source.retry_count, source.completed_at,
        )
        self._insert_episode(connection, episode)
        for document in self._documents_for_episode(source):
            self._upsert_document_and_fts(connection, document)
        return episode
~~~

At the existing Plan 04 evaluator-success seam, after its receipt append and before its completion event:

~~~python
self._learning.record_episode(attempt.attempt_id)
~~~

- [ ] **Step 4: Run the tests green**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_learning.py::test_record_episode_is_authoritative_and_idempotent tests/factory/test_learning.py::test_fts_indexes_bounded_summary_not_raw_report -q
python -m py_compile vesper/factory/learning.py vesper/factory/research/evaluation.py
~~~

Expected: PASS; no raw report is searchable.

- [ ] **Step 5: Commit**

~~~bash
git diff --check
git diff --stat
git diff -- vesper/factory/learning.py vesper/factory/research/evaluation.py tests/factory/test_learning.py
git add vesper/factory/learning.py vesper/factory/research/evaluation.py tests/factory/test_learning.py
git commit -m "feat(factory): record searchable learning episodes"
~~~

### Task 3: Promote Lessons and Select Bounded Context

**Files:**
- Modify: `vesper/factory/learning.py`
- Test: `tests/factory/test_learning.py`

**Dependencies:** Task 2. Only Task 2 episodes are eligible support.

**Interfaces:**
- Produces: `create_lesson`, `link_episode`, `evaluate_promotion`, and `select_context(work_kind, query, max_chars, limit) -> ContextSelectionV1`.

- [ ] **Step 1: Write failing promotion/context tests**

~~~python
def test_general_lesson_needs_three_independent_verified_episodes(factory):
    lesson = factory.learning.create_lesson("CONTEXT", "research", "Inspect chronology before fitting", "chronology-v1")
    for index in range(3):
        factory.learning.link_episode(lesson.lesson_id, factory.seed_verified_episode(f"task-{index}", f"input-{index}"), "SUPPORTS")
    assert factory.learning.evaluate_promotion(lesson.lesson_id).status == "ACTIVE"
    factory.learning.link_episode(lesson.lesson_id, factory.seed_verified_episode("task-x", "input-x"), "CONTRADICTS")
    assert factory.learning.evaluate_promotion(lesson.lesson_id).status == "CANDIDATE"

def test_defect_lesson_needs_reproduction_and_fix(factory):
    lesson = factory.learning.create_lesson("DEFECT", "development", "Reject unadjusted split inputs", "split-v1")
    factory.learning.link_episode(lesson.lesson_id, factory.seed_rejected_episode("repro"), "REPRODUCTION")
    factory.learning.link_episode(lesson.lesson_id, factory.seed_verified_episode("fix", "fix-input"), "FIX")
    assert factory.learning.evaluate_promotion(lesson.lesson_id).status == "ACTIVE"

def test_context_is_ranked_and_bounded(factory):
    factory.seed_active_lesson("research", "Inspect chronology before fitting")
    factory.seed_learning_document("EVIDENCE", "evd_alpha", "research", "chronology audit passed")
    packet = factory.learning.select_context("research", "chronology", 80, 5)
    assert packet.lesson_ids and packet.evidence_ids == ("evd_alpha",)
    assert len(packet.text) <= 80 and packet.context_hash.startswith("sha256:")
~~~

- [ ] **Step 2: Run the tests red**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_learning.py::test_general_lesson_needs_three_independent_verified_episodes tests/factory/test_learning.py::test_defect_lesson_needs_reproduction_and_fix tests/factory/test_learning.py::test_context_is_ranked_and_bounded -q
~~~

Expected: FAIL because promotion and context interfaces are absent.

- [ ] **Step 3: Implement exact promotion rules**

Independence requires distinct `attempt_id`, `task_id`, `input_hash`, and evaluator receipt ID. General activation requires three independent `SUPPORTS` with `VERIFIED` outcome and no `CONTRADICTS`. A defect requires independent `REPRODUCTION`/`REJECTED` and `FIX`/`VERIFIED` episodes in one scope. A contradiction sets the lesson back to `CANDIDATE` through a superseding receipt, never deletion.

~~~python
def evaluate_promotion(self, lesson_id: str) -> LessonSummaryV1:
    lesson, links = self._load_lesson_with_episodes(lesson_id)
    independent = self._independent_links(links)
    if lesson.kind == "DEFECT":
        repro = [x for x in independent if x.relation == "REPRODUCTION" and x.outcome == "REJECTED"]
        fix = [x for x in independent if x.relation == "FIX" and x.outcome == "VERIFIED"]
        active = bool(repro and fix and repro[0].attempt_id != fix[0].attempt_id)
    else:
        support = [x for x in independent if x.relation == "SUPPORTS" and x.outcome == "VERIFIED"]
        active = len(support) >= 3 and not any(x.relation == "CONTRADICTS" for x in links)
    return self._decide_lesson(lesson, "ACTIVE" if active else "CANDIDATE")
~~~

Select active lessons by `created_at DESC, lesson_id ASC`, then FTS rank/source ID; stop before adding text over `max_chars` (1–12,000). Packet text is only `Lesson: <statement> [<lsn>]` and `Evidence: <summary> [<evd>]`.

- [ ] **Step 4: Run the tests green**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_learning.py::test_general_lesson_needs_three_independent_verified_episodes tests/factory/test_learning.py::test_defect_lesson_needs_reproduction_and_fix tests/factory/test_learning.py::test_context_is_ranked_and_bounded -q
python -m py_compile vesper/factory/learning.py
~~~

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git diff --check
git diff --stat
git diff -- vesper/factory/learning.py tests/factory/test_learning.py
git add vesper/factory/learning.py tests/factory/test_learning.py
git commit -m "feat(factory): promote evidence-backed lessons"
~~~

### Task 4: Derive Routing Stats and Canary/Rollback Decisions

**Files:**
- Create: `vesper/factory/routing.py`
- Modify: `vesper/factory/learning.py`
- Test: `tests/factory/test_routing.py`

**Dependencies:** Tasks 1–3. Campaign contract freezes `canary_min_verified_episodes`, `canary_max_attempts`, and local-compute bounds.

**Interfaces:**
- Produces: `record_episode`, `assign_canary`, `compare_canary`, `activate_candidate`, `rollback`.

- [ ] **Step 1: Write failing routing/canary tests**

~~~python
def test_stats_use_evaluator_outcomes_and_runtime(factory):
    factory.routing.record_episode(factory.episode(outcome="VERIFIED", duration_ms=120, retry_count=1))
    factory.routing.record_episode(factory.episode(outcome="REJECTED", duration_ms=80, retry_count=0))
    stat = factory.routing.stats("codex", "development", "v1", "development")
    assert (stat.verified_count, stat.rejected_count, stat.mean_duration_ms, stat.mean_retries) == (1, 1, 100, 0.5)

def test_canary_beats_active_then_rollback_restores_predecessor(factory):
    baseline = factory.seed_active_version("TEMPLATE", "development", "v1")
    candidate = factory.seed_candidate_version("TEMPLATE", "development", "v2", predecessor=baseline.lesson_id)
    factory.seed_canary_results(candidate.lesson_id, baseline.lesson_id, candidate_verified=3, baseline_verified=2, candidate_latency=80, baseline_latency=100)
    assert factory.routing.compare_canary(candidate.lesson_id).winner == candidate.lesson_id
    assert factory.routing.activate_candidate(candidate.lesson_id).status == "ACTIVE"
    assert factory.routing.rollback(candidate.lesson_id).active_lesson_id == baseline.lesson_id
~~~

- [ ] **Step 2: Run the tests red**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_routing.py -q
~~~

Expected: FAIL because `RoutingService` does not exist.

- [ ] **Step 3: Implement measured stats and deterministic canary**

Count `VERIFIED` as success and `REJECTED` as rejection only after evaluator validation. Canary allocation is SHA-256 deterministic and may not exceed frozen attempts or compute.

~~~python
def assign_canary(self, lesson_id: str, attempt_id: str) -> Literal["BASELINE", "CANDIDATE"]:
    candidate, baseline, policy = self._load_candidate_baseline_and_policy(lesson_id)
    if candidate.status != "CANARY" or self._canary_attempt_count(lesson_id) >= policy.canary_max_attempts:
        raise CanaryBlockedError("CANARY_BUDGET_EXHAUSTED")
    allocation = "CANDIDATE" if hashlib.sha256(f"{lesson_id}:{attempt_id}".encode()).digest()[0] % 2 else "BASELINE"
    self._insert_canary(lesson_id, baseline.lesson_id, attempt_id, allocation)
    return allocation

def compare_canary(self, lesson_id: str) -> CanaryComparisonV1:
    candidate, baseline, policy = self._load_candidate_baseline_and_policy(lesson_id)
    challenger, control = self._canary_metrics(lesson_id, "CANDIDATE"), self._canary_metrics(lesson_id, "BASELINE")
    if min(challenger.verified_count, control.verified_count) < policy.canary_min_verified_episodes:
        return CanaryComparisonV1(lesson_id, None, "INSUFFICIENT_VERIFIED_EPISODES")
    wins = challenger.success_rate > control.success_rate or (
        challenger.success_rate == control.success_rate and
        (challenger.mean_duration_ms, challenger.mean_retries) < (control.mean_duration_ms, control.mean_retries)
    )
    return CanaryComparisonV1(lesson_id, lesson_id if wins else baseline.lesson_id, "COMPARED")
~~~

Activation marks predecessor `REVERTED`, candidate `ACTIVE`, and appends `learning.version_activated`. Rollback marks active candidate `REVERTED`, restores predecessor `ACTIVE`, and appends `learning.version_rolled_back`. Neither affects models.

- [ ] **Step 4: Run the tests green**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_routing.py -q
python -m py_compile vesper/factory/routing.py vesper/factory/learning.py
~~~

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git diff --check
git diff --stat
git diff -- vesper/factory/routing.py vesper/factory/learning.py tests/factory/test_routing.py
git add vesper/factory/routing.py vesper/factory/learning.py tests/factory/test_routing.py
git commit -m "feat(factory): add learning canary routing"
~~~

### Task 5: Version Policy and Task-Packet Templates

**Files:**
- Modify: `vesper/factory/routing.py`
- Modify: `vesper/factory/contracts.py`
- Test: `tests/factory/test_routing.py`

**Dependencies:** Task 4. Scope is retry/decomposition policy and template body only; it cannot change grants, executable selection, authority, resource limits, model selection, or effects.

**Interfaces:**
- Produces: `PolicyCandidateV1`, `TemplateCandidateV1`, `RoutingDecisionV1`, `choose_version(work_kind, runtime, attempt_id)`.

- [ ] **Step 1: Write failing candidate tests**

~~~python
def test_policy_and_template_candidates_are_unused_until_activation(factory):
    policy = factory.routing.create_policy_candidate("research", "retry-v2", ("codex", "hermes"), 1)
    template = factory.routing.create_template_candidate("research", "packet-v2", "Use {task_contract} {context_packet} {acceptance_criteria} {authority} {receipt_schema}.")
    decision = factory.routing.choose_version("research", "codex", "atm_before")
    assert decision.policy_version != policy.version
    assert decision.template_version != template.version

def test_template_rejects_missing_fields_and_excess_length(factory):
    with pytest.raises(LearningValidationError, match="required placeholders"):
        factory.routing.create_template_candidate("research", "bad", "Do task")
    with pytest.raises(LearningValidationError, match="12000"):
        factory.routing.create_template_candidate("research", "long", "{context_packet}" + "x" * 12001)
~~~

- [ ] **Step 2: Run the tests red**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_routing.py::test_policy_and_template_candidates_are_unused_until_activation tests/factory/test_routing.py::test_template_rejects_missing_fields_and_excess_length -q
~~~

Expected: FAIL because candidate interfaces do not exist.

- [ ] **Step 3: Implement candidate validation and routing**

Persist policy/template candidates as `lessons` with canonical-payload-hash evidence and active predecessor. Templates require `{task_contract}`, `{context_packet}`, `{acceptance_criteria}`, `{authority}`, `{receipt_schema}` and a 12,000-character cap. Policy retry order is already-probed local runtimes only and `max_retries` is within campaign limit.

~~~python
def choose_version(self, work_kind: str, runtime: str, attempt_id: str) -> RoutingDecisionV1:
    policy = self._active_lesson("POLICY", work_kind)
    template = self._active_lesson("TEMPLATE", work_kind)
    candidate = self._eligible_canary_candidate(work_kind, runtime)
    if candidate is None:
        return RoutingDecisionV1(runtime, policy.version, template.version, "ACTIVE")
    selected = candidate if self.assign_canary(candidate.lesson_id, attempt_id) == "CANDIDATE" else self._lesson(candidate.predecessor_lesson_id)
    return RoutingDecisionV1(
        runtime, selected.version if selected.kind == "POLICY" else policy.version,
        selected.version if selected.kind == "TEMPLATE" else template.version, "CANARY",
    )
~~~

Only active versions run outside a recorded canary; rejected/reverted versions are never selected.

- [ ] **Step 4: Run the tests green**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_routing.py::test_policy_and_template_candidates_are_unused_until_activation tests/factory/test_routing.py::test_template_rejects_missing_fields_and_excess_length -q
python -m py_compile vesper/factory/routing.py vesper/factory/contracts.py
~~~

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git diff --check
git diff --stat
git diff -- vesper/factory/routing.py vesper/factory/contracts.py tests/factory/test_routing.py
git add vesper/factory/routing.py vesper/factory/contracts.py tests/factory/test_routing.py
git commit -m "feat(factory): version learning policy templates"
~~~

### Task 6: Gate Local Non-Critical Code Acceptance

**Files:**
- Create: `vesper/factory/autonomy.py`
- Test: `tests/factory/test_autonomy.py`

**Dependencies:** Tasks 1–5, Plan 03 worktree identity, and Plan 04 independent evaluator receipt.

**Interfaces:**
- Produces: `AutonomyService.accept_noncritical_code(request: CodeAcceptanceRequestV1) -> CodeAcceptanceResultV1`, `code.accepted`, and `code.acceptance_blocked`.

- [ ] **Step 1: Write failing all-gates tests**

~~~python
def test_acceptance_merges_only_to_local_factory_accepted(fake_factory_repo, factory):
    result = factory.autonomy.accept_noncritical_code(factory.valid_code_acceptance_request(fake_factory_repo))
    assert result.accepted and result.merge_commit
    assert fake_factory_repo.current_branch() == "factory/accepted"
    assert fake_factory_repo.remote_pushes == []

@pytest.mark.parametrize("failure", [
    "campaign_authority", "missing_codegraph", "unqueried_symbol", "protected_path",
    "focused_test_failure", "compile_failure", "full_suite_failure", "evaluator_rejected",
    "canary_failed", "rollback_receipt_missing", "target_main", "remote_repo",
])
def test_missing_gate_blocks_without_merge_or_remote_effect(fake_factory_repo, factory, failure):
    result = factory.autonomy.accept_noncritical_code(factory.invalid_code_acceptance_request(fake_factory_repo, failure))
    assert not result.accepted and result.merge_commit is None and result.denial_code
    assert fake_factory_repo.merge_commits == [] and fake_factory_repo.remote_pushes == []
~~~

- [ ] **Step 2: Run the tests red**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_autonomy.py -q
~~~

Expected: FAIL because `AutonomyService` does not exist.

- [ ] **Step 3: Implement the exact fail-closed gate**

Perform this order, stopping at the first failure and appending `code.acceptance_blocked` with evidence hashes:

1. Campaign has `code_mutation=true` and target `factory/accepted`.
2. Request target is exactly `factory/accepted`; factory repo/worktree are local factory-owned paths.
3. Preflight evidence hashes match current `AGENTS.md`, `SKILLS/CODE.md`, `SKILLS/EXAMPLES.md`.
4. Current CodeGraph evidence has a query for every `changed_symbols` member.
5. Changed paths contain none of `config/**`, `vesper/risk.py`, `vesper/execution/**`, `vesper/scheduler/**`, `vesper/data/massive/**`, `vesper/data/model_research/**`, `models/xgb_ranker.json`, `models/xgb_ranker.metadata.json`.
6. Every focused test, compilation check for changed Python files, and frozen practical suite succeeds.
7. Latest exact-diff evaluator receipt is independent, `evaluation.verdict`, and `VERIFIED`.
8. Exact-diff canary receipt is `VERIFIED`, frozen-budget compliant, and beats baseline.
9. Exact-diff rollback receipt names an existing local rollback commit and predecessor head.
10. Switch to local `factory/accepted`, verify predecessor head, run one local `git merge --no-ff --no-edit <source>`, append `code.accepted`.

~~~python
PROTECTED_PATHS = (
    "config/", "vesper/risk.py", "vesper/execution/", "vesper/scheduler/",
    "vesper/data/massive/", "vesper/data/model_research/",
    "models/xgb_ranker.json", "models/xgb_ranker.metadata.json",
)
ALLOWED_GIT_SUBCOMMANDS = frozenset({"diff", "merge-base", "rev-parse", "status", "switch", "merge", "show"})

def accept_noncritical_code(self, request: CodeAcceptanceRequestV1) -> CodeAcceptanceResultV1:
    try:
        self._require_campaign_target(request.campaign_id, "factory/accepted")
        self._require_local_target(request)
        self._require_document_preflight(request.attempt_id)
        self._require_codegraph_queries(request.attempt_id, request.changed_symbols)
        paths = self._git.changed_paths(request.factory_repo, request.source_commit)
        self._require_unprotected(paths)
        self._run_test_and_compile_gates(request, paths)
        self._require_exact_evaluator(request)
        self._require_passing_canary(request)
        self._require_rollback_receipt(request)
        merge_commit = self._merge_local_accepted(request)
    except AcceptanceBlocked as blocked:
        return CodeAcceptanceResultV1(False, self._append_blocked_receipt(request, blocked.code), None, blocked.code)
    return CodeAcceptanceResultV1(True, self._append_accepted_receipt(request, merge_commit), merge_commit, None)
~~~

The runner accepts argument arrays only. It has no shell, push, fetch, pull, tag, release, deployment, broker, paid-compute, or model-artifact command.

- [ ] **Step 4: Run the tests green**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_autonomy.py -q
python -m py_compile vesper/factory/autonomy.py
~~~

Expected: PASS; denial creates no merge or remote effect.

- [ ] **Step 5: Commit**

~~~bash
git diff --check
git diff --stat
git diff -- vesper/factory/autonomy.py tests/factory/test_autonomy.py
git add vesper/factory/autonomy.py tests/factory/test_autonomy.py
git commit -m "feat(factory): gate local code acceptance"
~~~

### Task 7: Add Authenticated Snapshot and Memory View

**Files:**
- Modify: `vesper/factory/contracts.py`
- Modify: `vesper/factory/commands.py`
- Modify: `vesper/factory/snapshot.py`
- Modify: `vesper/factory/kernel.py`
- Modify: `apps/desktop/src/contracts/factory.ts`
- Create: `apps/desktop/src/features/memory/MemoryView.tsx`
- Create: `apps/desktop/src/features/memory/MemoryView.test.tsx`
- Modify: `apps/desktop/src/App.tsx`
- Test: `tests/factory/test_learning_api.py`

**Dependencies:** Tasks 1–6 and accepted Plan 02 typed Tauri transport. Preserve frozen routes/authentication; enrich existing snapshot/command dispatch only.

**Interfaces:**

~~~ts
export interface MemoryViewProps {
  snapshot: Pick<FactorySnapshotV1, "lessons" | "routing_stats">;
  executeCommand: (
    kind: "lesson.rollback",
    payload: { lesson_id: string },
    expectedVersion: number,
  ) => Promise<void>;
}
~~~

- [ ] **Step 1: Write failing API/component tests**

~~~python
def test_snapshot_exposes_lessons_without_raw_reports(api_client, factory):
    factory.seed_active_lesson("research", "Use chronology evidence before fitting")
    snapshot = api_client.snapshot()
    assert snapshot["lessons"][0]["status"] == "ACTIVE"
    assert snapshot["lessons"][0]["supporting_attempt_ids"]
    assert "raw_report" not in snapshot["lessons"][0]
~~~

~~~tsx
it("renders states and enables rollback only for active lessons", () => {
  render(<MemoryView snapshot={snapshotWithLessons} executeCommand={executeCommand} />);
  expect(screen.getByRole("heading", { name: "Memory" })).toBeVisible();
  for (const state of ["ACTIVE", "CANDIDATE", "REJECTED", "REVERTED"]) expect(screen.getByText(state)).toBeVisible();
  expect(screen.getAllByRole("button", { name: "Rollback version" })).toHaveLength(1);
});
~~~

- [ ] **Step 2: Run the tests red**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_learning_api.py -q
cd apps/desktop && pnpm test --run src/features/memory/MemoryView.test.tsx
~~~

Expected: FAIL because snapshot fields and Memory view do not exist.

- [ ] **Step 3: Implement additive API and read-only view**

Snapshot appends `LearningService.snapshot_lessons()` and `RoutingService.snapshot_stats()`. `lesson.rollback` uses frozen idempotency/expected-version checks then `RoutingService.rollback`; non-active lessons return `TRANSITION_DENIED`. It cannot call autonomy, launch workers, promote models, or call brokers.

~~~ts
export type LessonStatus = "CANDIDATE" | "CANARY" | "ACTIVE" | "REJECTED" | "REVERTED";
export interface LessonSummaryV1 {
  lesson_id: string; kind: "CONTEXT" | "ROUTING" | "POLICY" | "TEMPLATE" | "DEFECT";
  status: LessonStatus; work_kind: string; statement: string; version: string;
  supporting_attempt_ids: string[]; contradiction_count: number; created_at: string;
}
~~~

Render each lesson as an `article` headed `"<status>: <statement>"`, with kind/version/work kind, contradictions, and `atm_...` links; render routing stats in a semantic table. Only an active lesson with predecessor gets `Rollback version`. No source editor, remote/push/release, model, live, or broker control is included.

- [ ] **Step 4: Run the tests green**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_learning_api.py -q
cd apps/desktop && pnpm lint && pnpm test --run src/features/memory/MemoryView.test.tsx && pnpm build
~~~

Expected: PASS; React receives no sidecar or worker token.

- [ ] **Step 5: Commit**

~~~bash
git diff --check
git diff --stat
git diff -- vesper/factory/contracts.py vesper/factory/commands.py vesper/factory/snapshot.py vesper/factory/kernel.py apps/desktop/src/contracts/factory.ts apps/desktop/src/features/memory/MemoryView.tsx apps/desktop/src/features/memory/MemoryView.test.tsx apps/desktop/src/App.tsx tests/factory/test_learning_api.py
git add vesper/factory/contracts.py vesper/factory/commands.py vesper/factory/snapshot.py vesper/factory/kernel.py apps/desktop/src/contracts/factory.ts apps/desktop/src/features/memory/MemoryView.tsx apps/desktop/src/features/memory/MemoryView.test.tsx apps/desktop/src/App.tsx tests/factory/test_learning_api.py
git commit -m "feat(desktop): add factory memory view"
~~~

### Task 8: Verify M5 End-to-End

**Files:**
- Modify: `tests/factory/test_learning.py`
- Modify: `tests/factory/test_routing.py`
- Modify: `tests/factory/test_autonomy.py`
- Modify: `tests/factory/test_learning_api.py`

**Dependencies:** Tasks 1–7. This task adds no product behavior.

- [ ] **Step 1: Write the failing M5 integration test**

~~~python
def test_m5_learning_and_local_autonomy(factory, fake_factory_repo, api_client):
    lesson = factory.create_candidate_lesson("CONTEXT", "research", "Use chronology evidence", "chronology-v1")
    for index in range(3):
        factory.learning.link_episode(lesson.lesson_id, factory.seed_verified_episode(f"task-{index}", f"input-{index}"), "SUPPORTS")
    assert factory.learning.evaluate_promotion(lesson.lesson_id).status == "ACTIVE"
    assert factory.learning.select_context("research", "chronology", 500, 10).lesson_ids == (lesson.lesson_id,)

    candidate = factory.seed_candidate_version("TEMPLATE", "research", "packet-v2")
    factory.seed_winning_canary(candidate.lesson_id)
    assert factory.routing.activate_candidate(candidate.lesson_id).status == "ACTIVE"
    assert factory.routing.rollback(candidate.lesson_id).active_lesson_id

    result = factory.autonomy.accept_noncritical_code(factory.valid_code_acceptance_request(fake_factory_repo))
    assert result.accepted and fake_factory_repo.current_branch() == "factory/accepted"
    assert fake_factory_repo.remote_pushes == [] and api_client.snapshot()["lessons"]
~~~

- [ ] **Step 2: Run the test red**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_learning.py::test_m5_learning_and_local_autonomy -q
~~~

Expected: FAIL until all Plan 05 components compose in temporary SQLite/local Git.

- [ ] **Step 3: Correct only fixtures needed by the accepted interfaces**

Fixtures create complete manifests, independent evaluator receipts, CodeGraph query evidence, exact-diff canary evidence, and pre-merge local rollback evidence. Assert no prohibited effect:

~~~python
assert fake_factory_repo.commands == [
    ("git", "diff"), ("git", "merge-base"), ("git", "status"),
    ("git", "switch", "factory/accepted"), ("git", "merge", "--no-ff", "--no-edit"),
]
assert factory.effect_log == []
~~~

- [ ] **Step 4: Run focused and practical verification green**

~~~bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/factory/test_learning.py tests/factory/test_routing.py tests/factory/test_autonomy.py tests/factory/test_learning_api.py -q
TMPROOT="$LOCALAPPDATA/Temp/v20-pytest-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" .venv/Scripts/python.exe -m pytest -q --basetemp="$TMPROOT/pytest"
python -m py_compile vesper/factory/learning_migration.py vesper/factory/migrations.py vesper/factory/learning.py vesper/factory/routing.py vesper/factory/autonomy.py vesper/factory/contracts.py vesper/factory/commands.py vesper/factory/snapshot.py vesper/factory/kernel.py vesper/factory/research/evaluation.py
cd apps/desktop && pnpm lint && pnpm test --run && pnpm build && cd src-tauri && cargo fmt --check && cargo clippy --all-targets --all-features -- -D warnings && cargo test
~~~

Expected: all commands PASS. Missing predecessors, unavailable desktop project, stale CodeGraph, or skipped verification leaves M5 open.

- [ ] **Step 5: Commit M5 evidence**

~~~bash
git diff --check
git diff --stat
git diff -- tests/factory/test_learning.py tests/factory/test_routing.py tests/factory/test_autonomy.py tests/factory/test_learning_api.py
git add tests/factory/test_learning.py tests/factory/test_routing.py tests/factory/test_autonomy.py tests/factory/test_learning_api.py
git commit -m "test(factory): verify learning autonomy gate"
~~~

## Final Review Checklist

- [ ] Frozen contracts are additive and retain receipts, evaluator independence, and recovery guarantees.
- [ ] Tests cover episode/FTS, promotion, context, runtime stats, policy/template candidates, canary/rollback, CodeGraph/preflight/protected path/tests/evaluator/canary/rollback gate, API, and Memory view.
- [ ] Automatic acceptance targets only local `factory/accepted`; protected edits, remote push, release, active model promotion, live effects, and paid compute remain denied.
