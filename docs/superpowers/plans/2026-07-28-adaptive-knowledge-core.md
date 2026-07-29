# Adaptive Knowledge Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an adaptive, human-governed V20 knowledge core that automatically drafts durable candidates, keeps approved active knowledge within 3,000 Markdown lines, searches a complete Obsidian archive, and retrieves no more than two archived notes temporarily per run.

**Architecture:** Extend the current Markdown-to-LangGraph/FTS5 knowledge service rather than replacing it. `vesper/platform/knowledge.py` remains responsible for canonical active/archive parsing, budget enforcement, derived indexing, retrieval, and immutable snapshots; a focused `vesper/platform/knowledge_lifecycle.py` owns observation consolidation, safe inbox writes, usage accounting, and review proposals. Specialist outputs and repository-agent CLI calls submit structured observations, while the existing human-approval node is the only workflow point that credits a run and consolidates its proposed knowledge.

**Tech Stack:** Python 3.11, Pydantic v2 contracts, LangGraph SQLite Store/checkpointer, SQLite FTS5, PyYAML, Typer, pytest, Ruff, Obsidian-compatible Markdown.

## Global Constraints

- **Execution precondition:** review and commit the already-verified Obsidian/LangGraph knowledge-standard changes currently present in the working tree before creating an implementation worktree. Current `HEAD` contains the adaptive design specification but not the uncommitted `vesper/platform/knowledge.py`, related contracts/service/CLI integration, tests, vault, ADR-0002, runbook, or receipt that this plan extends. Preserve the two unrelated untracked research reports and exclude them from that baseline commit.
- Canonical knowledge remains repository-owned UTF-8 Markdown under `knowledge/`; Store and FTS5 remain derived and rebuildable.
- Approved notes under `knowledge/memory/` and `knowledge/skills/` have a hard combined ceiling of exactly 3,000 complete source lines, including frontmatter and excluding README files.
- `knowledge/archive/`, `knowledge/inbox/`, `knowledge/raw/`, `knowledge/wiki/`, templates, and README files do not count toward the active ceiling.
- Agents may create or update candidate notes only. Only the operator may approve, archive, permanently reactivate, change retention class, or delete a note.
- Active and archived retrieval remains role-scoped to `shared` plus the requesting specialist role.
- A role snapshot contains at most five documents, at most 8,000 content characters, and at most two archived documents.
- Temporary archive retrieval never changes canonical file location, status, retention, authority, or the active line budget.
- Run snapshots remain immutable across resume and across later vault, ranking, archive, or usage changes.
- Knowledge remains context, never evidence, policy, permission, validation, risk approval, trading authority, or model-promotion authority.
- Do not add embeddings, vector storage, graph databases, hosted services, new credentials, paid model calls, background scheduling, automatic archival, automatic permanent reactivation, or deletion.
- Do not modify `vesper/data/massive/`, `vesper/data/model_research/`, trading/risk parameters, active model artifacts, broker/provider configuration, or scheduler configuration.
- Use test-first development, surgical diffs, exact file staging, and one Conventional Commit per task.

---

## File Structure

### Create

- `vesper/platform/knowledge_lifecycle.py` — observation ledger, candidate consolidation and atomic inbox writes, successful-use ledger, deterministic compaction/reactivation proposals.
- `tests/platform/test_knowledge_lifecycle.py` — focused lifecycle, idempotency, prohibited-content, usage, and proposal tests.
- `knowledge/archive/README.md` — archive contract and Obsidian usage.
- `knowledge/archive/memory/README.md` — archived-memory placement rules.
- `knowledge/archive/skills/README.md` — archived-skill placement rules.
- `knowledge/raw/README.md` — immutable source boundary.
- `knowledge/wiki/README.md` — LLM-maintained synthesis boundary.
- `docs/adr/ADR-0003-adaptive-knowledge-core.md` — accepted extension to ADR-0002.
- `docs/receipts/adaptive-knowledge-core-receipt.md` — final implementation and verification receipt.

### Modify

- `vesper/platform/contracts.py` — tier, retention, observation, and lifecycle metadata contracts; optional observation proposals on specialist outputs.
- `vesper/platform/knowledge.py` — active/archive corpus loader, 3,000-line validation, tier-aware FTS rows, bounded archive selection, status reporting.
- `vesper/platform/composition.py` — observation instructions in specialist prompts while preserving the separate validated runtime-memory contract.
- `vesper/platform/workflow.py` — consolidate accepted-run observations and credit successful selected knowledge only after operator approval.
- `vesper/platform/service.py` — construct the lifecycle service, record snapshot selections, and expose observation/proposal operations.
- `vesper/platform/cli.py` — `knowledge-observe`, `knowledge-compaction-plan`, and `knowledge-reactivation-plan` commands.
- `tests/platform/test_contracts.py` — strict validation for new contracts.
- `tests/platform/test_knowledge.py` — corpus budget, archive indexing, tier ranking, and snapshot bounds.
- `tests/platform/test_composition.py` — prompt/output-schema behavior and archive provenance.
- `tests/platform/test_workflow.py` — accepted/rejected run lifecycle behavior and replay idempotency.
- `tests/platform/test_service.py` — production wiring, repository boundary, status, and operator operations.
- `tests/platform/test_cli.py` — new command routing and help safety.
- `knowledge/templates/memory.md` — active retention metadata.
- `knowledge/templates/skill.md` — active retention metadata.
- `knowledge/README.md` — adaptive core and archive overview.
- `knowledge/inbox/README.md` — automatic-candidate contract.
- `docs/runbooks/obsidian-knowledge.md` — observation, review, budget, archive, compaction, and reactivation workflow.
- `README.md` — concise operator command summary.
- `AGENTS.md` — instruct repository agents to submit durable observations through the controlled command instead of writing approved notes.

---

### Task 1: Define strict adaptive-knowledge contracts

**Files:**
- Modify: `vesper/platform/contracts.py:93-102`
- Modify: `vesper/platform/contracts.py:241-281`
- Modify: `vesper/platform/contracts.py:491-505`
- Test: `tests/platform/test_contracts.py`

**Interfaces:**
- Produces: `KnowledgeTier`, `KnowledgeRetention`, `KnowledgeObservationProposal`, `KnowledgeObservation`, and the extended `KnowledgeDocument` fields consumed by every later task.
- Preserves: the existing `MemoryProposal`, `MemoryCandidate`, and receipt-derived memory authority contracts without conversion or inheritance.

- [ ] **Step 1: Write failing contract tests**

Add tests proving the new types are strict, archive status matches archive tier, archived notes cannot remain pinned, observation concept keys are bounded slugs, and every specialist output accepts at most one optional observation proposal:

```python
def test_knowledge_document_requires_consistent_tier_status_and_retention():
    with pytest.raises(ValidationError, match="archived knowledge must use archived status"):
        KnowledgeDocument(
            knowledge_id="brief-writing",
            kind=KnowledgeKind.MEMORY,
            scope=KnowledgeScope.SHARED,
            approval_status="approved",
            tier=KnowledgeTier.ARCHIVE,
            retention=KnowledgeRetention.ADAPTIVE,
            title="Brief writing",
            content="Prefer brief wording.",
            source_path="archive/memory/brief-writing.md",
            source_sha256="a" * 64,
            source_line_count=10,
        )


def test_observation_proposal_rejects_non_slug_key_and_long_summary():
    with pytest.raises(ValidationError):
        KnowledgeObservationProposal(
            concept_key="Not A Stable Key",
            title="Brief writing",
            kind=KnowledgeKind.MEMORY,
            scope=KnowledgeScope.SHARED,
            summary="x" * 601,
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_contracts.py -q
```

Expected: FAIL because the adaptive knowledge types and fields do not exist.

- [ ] **Step 3: Add the minimal enums and models**

Implement these exact public contracts and add `knowledge_observations` with `max_length=1` and default `()` to `ProductSpecialistOutput`, `DevelopmentSpecialistOutput`, and `RiskSpecialistOutput`:

```python
class KnowledgeTier(StrEnum):
    ACTIVE = "active"
    ARCHIVE = "archive"


class KnowledgeRetention(StrEnum):
    PINNED = "pinned"
    ADAPTIVE = "adaptive"


class KnowledgeObservationProposal(ContractModel):
    concept_key: Annotated[
        str,
        Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    ]
    title: Annotated[str, Field(min_length=1, max_length=120)]
    kind: KnowledgeKind
    scope: KnowledgeScope
    summary: Annotated[str, Field(min_length=1, max_length=600)]
    explicit: bool = False


class KnowledgeObservation(KnowledgeObservationProposal):
    source_ref: Annotated[str, Field(min_length=1, max_length=200)]
    observed_at: AwareDatetime

    @field_validator("observed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("observation timestamps must use UTC")
        return value.astimezone(timezone.utc)
```

Extend `KnowledgeDocument` with:

```python
approval_status: Literal["approved", "archived"]
tier: KnowledgeTier
retention: KnowledgeRetention
source_line_count: Annotated[int, Field(ge=1)]
supersedes: tuple[NonEmptyStr, ...] = ()
review_after: date | None = None
contested: bool = False
```

Add a model validator enforcing:

```python
if self.tier is KnowledgeTier.ACTIVE and self.approval_status != "approved":
    raise ValueError("active knowledge must use approved status")
if self.tier is KnowledgeTier.ARCHIVE and self.approval_status != "archived":
    raise ValueError("archived knowledge must use archived status")
if self.tier is KnowledgeTier.ARCHIVE and self.retention is KnowledgeRetention.PINNED:
    raise ValueError("archived knowledge must use adaptive retention")
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_contracts.py tests/platform/test_composition.py -q
uv run --locked python -m py_compile vesper/platform/contracts.py
```

Expected: PASS; existing specialist outputs remain valid because the new tuple defaults to empty.

- [ ] **Step 5: Commit the contracts**

```powershell
git add vesper/platform/contracts.py tests/platform/test_contracts.py
git diff --cached --check
git commit -m "feat(knowledge): define adaptive lifecycle contracts"
```

---

### Task 2: Load and validate the active/archive corpus and enforce 3,000 lines

**Files:**
- Modify: `vesper/platform/knowledge.py:26-43`
- Modify: `vesper/platform/knowledge.py:244-328`
- Modify: `tests/platform/test_knowledge.py`
- Modify: `knowledge/templates/memory.md`
- Modify: `knowledge/templates/skill.md`

**Interfaces:**
- Consumes: `KnowledgeTier`, `KnowledgeRetention`, and extended `KnowledgeDocument` from Task 1.
- Produces: `KnowledgeCorpus`, `load_knowledge_corpus(vault_root)`, and the backward-compatible `load_approved_documents(vault_root)` active-only wrapper.
- Guarantees: complete validation and budget checks finish before Store or FTS mutation.

- [ ] **Step 1: Extend the test note helper and write failing corpus tests**

Update `_write_note` to accept `retention`, `supersedes`, `review_after`, and `contested`, then add these tests:

```python
def test_corpus_separates_active_and_archived_and_counts_complete_active_lines(tmp_path):
    vault = tmp_path / "knowledge"
    active = _write_note(vault, "memory/active.md", retention="pinned")
    _write_note(
        vault,
        "archive/skills/archived.md",
        knowledge_id="archived-procedure",
        kind="skill",
        status="archived",
        retention="adaptive",
    )

    corpus = _knowledge_module().load_knowledge_corpus(vault)

    assert [item.knowledge_id for item in corpus.active] == ["split-adjustment-policy"]
    assert [item.knowledge_id for item in corpus.archived] == ["archived-procedure"]
    assert corpus.active_lines == len(active.read_text(encoding="utf-8").splitlines())


def test_active_corpus_over_3000_lines_fails_before_sync_mutates_store(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/too-large.md", body="\n".join("line" for _ in range(3000)))
    paths = PlatformPaths.below(tmp_path / "platform")

    with open_persistence(paths) as persistence:
        service = _service(vault, persistence)
        with pytest.raises(KnowledgeSyncError, match=r"3,000.*active lines"):
            service.sync()
        assert service.status()["documents"] == 0
```

Also cover duplicate IDs across active/archive/inbox, missing retention, pinned archive notes, wrong archive kind directory, linked archive paths, and README exclusion.

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_knowledge.py -q
```

Expected: FAIL because archive parsing, retention validation, corpus inventory, and line-budget enforcement do not exist.

- [ ] **Step 3: Implement one deterministic corpus loader**

Add:

```python
_MAX_ACTIVE_LINES = 3_000


@dataclass(frozen=True, slots=True)
class KnowledgeCorpus:
    active: tuple[KnowledgeDocument, ...]
    archived: tuple[KnowledgeDocument, ...]
    active_lines: int

    @property
    def documents(self) -> tuple[KnowledgeDocument, ...]:
        return self.active + self.archived


def load_approved_documents(vault_root: Path) -> tuple[KnowledgeDocument, ...]:
    return load_knowledge_corpus(vault_root).active
```

Scan exactly these roots and statuses:

```python
_KNOWLEDGE_ROOTS = (
    ("memory", KnowledgeKind.MEMORY, KnowledgeTier.ACTIVE, "approved"),
    ("skills", KnowledgeKind.SKILL, KnowledgeTier.ACTIVE, "approved"),
    ("archive/memory", KnowledgeKind.MEMORY, KnowledgeTier.ARCHIVE, "archived"),
    ("archive/skills", KnowledgeKind.SKILL, KnowledgeTier.ARCHIVE, "archived"),
)
```

Require `vesper_retention` for every admitted note. Parse optional `vesper_supersedes`, `vesper_review_after`, and `vesper_contested`. Set `source_line_count=len(text.splitlines())`. Inventory candidate IDs under `inbox/` and fail on duplicate stable IDs across all three tiers without admitting candidates as documents.

Calculate active lines from admitted approved active source files. Raise `KnowledgeSyncError` with total, overage, and per-note counts when the total exceeds 3,000.

- [ ] **Step 4: Update templates and run tests**

Add this field to both active templates:

```yaml
vesper_retention: adaptive
```

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_knowledge.py -q
uv run --locked python -m py_compile vesper/platform/knowledge.py
```

Expected: PASS, including unchanged candidate exclusion and active-only compatibility tests.

- [ ] **Step 5: Commit corpus validation**

```powershell
git add vesper/platform/knowledge.py tests/platform/test_knowledge.py knowledge/templates/memory.md knowledge/templates/skill.md
git diff --cached --check
git commit -m "feat(knowledge): enforce adaptive corpus budget"
```

---

### Task 3: Index archived knowledge and build bounded mixed-tier snapshots

**Files:**
- Modify: `vesper/platform/knowledge.py:61-237`
- Modify: `tests/platform/test_knowledge.py`
- Modify: `tests/platform/test_composition.py`

**Interfaces:**
- Consumes: `KnowledgeCorpus` and tiered `KnowledgeDocument` from Tasks 1-2.
- Produces: `KnowledgeSearchHit`, tier-aware `SqliteKnowledgeIndex.search`, mixed-tier `ObsidianKnowledgeService.search`, and immutable bounded snapshots.
- Preserves: existing Store namespace, role scope, five-document cap, 8,000-character cap, and historical-run behavior.

- [ ] **Step 1: Write failing archive retrieval tests**

Add tests proving the same query can return active and archive notes, archive results never cross role scope, relevance order is deterministic, a snapshot contains at most two archive documents, and changing archive contents after snapshot does not change resume context:

```python
def test_snapshot_allows_at_most_two_archived_documents_inside_existing_bounds(tmp_path):
    vault = tmp_path / "knowledge"
    for index in range(4):
        _write_note(
            vault,
            f"archive/memory/archive-{index}.md",
            knowledge_id=f"archive-{index}",
            status="archived",
            retention="adaptive",
            body=f"rare recovery evidence {index}",
        )
    _write_note(vault, "memory/active.md", knowledge_id="active", body="recovery evidence")

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        service = _service(vault, persistence)
        service.sync()
        service.snapshot(_task(objective="rare recovery evidence"))
        context = service.context("run-knowledge", SpecialistRole.DEVELOPMENT)

    assert context is not None
    assert sum(item.tier is KnowledgeTier.ARCHIVE for item in context.documents) <= 2
    assert len(context.documents) <= 5
    assert sum(len(item.content) for item in context.documents) <= 8_000
```

In `tests/platform/test_persistence.py`, create the old tierless FTS table before opening persistence and assert setup replaces it with a table whose `PRAGMA table_info(v20_knowledge_fts)` includes `tier`. This proves the derived schema migration is local and rebuildable.

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_knowledge.py tests/platform/test_composition.py -q
```

Expected: FAIL because FTS rows and snapshots have no tier behavior.

- [ ] **Step 3: Add tier-aware FTS rows and deterministic hits**

Add:

```python
@dataclass(frozen=True, slots=True)
class KnowledgeSearchHit:
    knowledge_id: str
    tier: KnowledgeTier
    score: float
```

Recreate the derived FTS table during schema setup when the `tier` column is absent. Its columns are:

```sql
knowledge_id UNINDEXED, kind UNINDEXED, scope UNINDEXED, tier UNINDEXED,
title, tags, content
```

Query a candidate pool of 25 matching rows and order by BM25 score, then active tier, then stable ID:

```sql
ORDER BY bm25(v20_knowledge_fts, 0.0, 0.0, 0.0, 0.0, 5.0, 2.0, 1.0),
         CASE tier WHEN 'active' THEN 0 ELSE 1 END,
         knowledge_id
LIMIT ?
```

Return `KnowledgeSearchHit` objects. In `ObsidianKnowledgeService.search`, walk ordered hits until the requested total limit is reached, skipping archive hits after two have been selected.

- [ ] **Step 4: Sync the full corpus and preserve snapshot caps**

Change `sync()` to persist and index `corpus.documents`, while `status()` returns:

```python
{
    "documents": len(documents),
    "active": len(active),
    "archived": len(archived),
    "memory": memory_count,
    "skill": skill_count,
    "active_lines": corpus.active_lines,
    "active_line_limit": 3_000,
}
```

Keep snapshot selection at five total documents and 8,000 characters. Because tier is part of `KnowledgeDocument`, the existing JSON prompt injection includes explicit archive provenance without a second prompt format.

- [ ] **Step 5: Run retrieval, prompt, and persistence tests**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_knowledge.py tests/platform/test_composition.py tests/platform/test_persistence.py -q
uv run --locked python -m py_compile vesper/platform/knowledge.py
```

Expected: PASS with zero cross-role archive leakage and stable run snapshots.

- [ ] **Step 6: Commit tier-aware retrieval**

```powershell
git add vesper/platform/knowledge.py tests/platform/test_knowledge.py tests/platform/test_composition.py tests/platform/test_persistence.py
git diff --cached --check
git commit -m "feat(knowledge): add guarded archive retrieval"
```

---

### Task 4: Consolidate observations into safe, idempotent inbox candidates

**Files:**
- Create: `vesper/platform/knowledge_lifecycle.py`
- Create: `tests/platform/test_knowledge_lifecycle.py`

**Interfaces:**
- Consumes: `KnowledgeObservation`, `KnowledgeCorpus`, `KnowledgeKind`, `KnowledgeRetention`, `KnowledgeTier`, and `KnowledgeStorePort`.
- Produces: `KnowledgeLifecycleService.observe(observation) -> dict[str, object]`.
- Store namespace: `("knowledge", "adaptive", "observations")` keyed by concept key.
- Filesystem output: `knowledge/inbox/<concept-key>.md`, written atomically with candidate status only.

- [ ] **Step 1: Write failing consolidation tests**

Cover distinct-source counting, replay idempotency, explicit immediate creation, threshold creation at three, update-in-place, active/archive ID handling, candidate path collision, and prohibited content:

```python
def test_three_distinct_observations_create_one_candidate_and_replay_is_idempotent(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    for index in range(3):
        result = service.observe(observation(source_ref=f"task-{index}"))

    candidate = vault / "inbox" / "brief-writing.md"
    assert result["status"] == "candidate-created"
    assert candidate.is_file()
    assert "vesper_status: candidate" in candidate.read_text(encoding="utf-8")

    replay = service.observe(observation(source_ref="task-2"))
    assert replay["status"] == "candidate-unchanged"
    assert "observation_count: 3" in candidate.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "summary",
    (
        "password = hunter2",
        "api_key: sk-abcdefghijklmnopqrstuvwxyz123456",
        "-----BEGIN PRIVATE KEY-----",
    ),
)
def test_prohibited_secret_like_observation_never_writes_candidate(tmp_path, summary):
    service, vault = lifecycle_service(tmp_path)
    with pytest.raises(KnowledgeLifecycleError, match="prohibited content"):
        service.observe(observation(summary=summary, explicit=True))
    assert not (vault / "inbox").exists()
```

- [ ] **Step 2: Run the new tests to verify failure**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_knowledge_lifecycle.py -q
```

Expected: FAIL because `knowledge_lifecycle.py` does not exist.

- [ ] **Step 3: Implement the observation ledger and deterministic statuses**

Define:

```python
OBSERVATION_NAMESPACE = ("knowledge", "adaptive", "observations")
_CANDIDATE_THRESHOLD = 3


class KnowledgeLifecycleError(RuntimeError):
    pass


class KnowledgeLifecycleService:
    def __init__(
        self,
        *,
        vault_root: Path,
        store: KnowledgeStorePort,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._vault_root = vault_root.resolve()
        self._store = store
        self._clock = clock

    def observe(self, observation: KnowledgeObservation) -> dict[str, object]:
        self._validate_observation(observation)
        state, changed = self._merge_observation(observation)
        if changed:
            self._store.put(OBSERVATION_NAMESPACE, observation.concept_key, state)
        return self._materialize_candidate(observation, state, changed=changed)
```

The stored observation state contains sorted unique source refs, first/last UTC observation times, current proposal fields, and explicit flag. Replaying the same source ref is a no-op. A changed proposal for the same key updates the latest title/kind/scope/summary but never resets provenance.

Implement `_validate_observation`, `_merge_observation`, and `_materialize_candidate` as private methods in the same class. `_merge_observation` returns `(state, changed)`; `_materialize_candidate` returns one of `recorded`, `candidate-created`, `candidate-updated`, `candidate-unchanged`, `already-active`, or `archived-observed` plus the concept key and observation count.

Before writing, inventory active, archive, and inbox IDs:

- active ID: return `already-active` and retain only the derived observation signal;
- archive ID: return `archived-observed` and do not create a new inbox file;
- existing candidate: update its observation metadata atomically;
- missing ID: create only when explicit or when three distinct refs exist.

- [ ] **Step 4: Implement fail-closed content checks and atomic Markdown writes**

Reject NUL/control characters and these value-bearing patterns from every observation field:

```python
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:api[_-]?key|password|secret|token|credential)\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
```

Render candidate YAML in a stable field order with `yaml.safe_dump(sort_keys=False, allow_unicode=True)`. Include `vesper_id`, kind, candidate status, scope, title, tags, observation count, first/last observation timestamps, confidence, source refs, and a body containing only the concise proposal summary. Write to a sibling temporary file, flush and close it, then use `Path.replace` so a failed write leaves the prior candidate unchanged.

Use these exact candidate-only metadata keys:

```yaml
vesper_observation_count: 3
vesper_first_observed_at: 2026-07-28T12:00:00Z
vesper_last_observed_at: 2026-07-28T12:10:00Z
vesper_confidence: medium
vesper_source_refs:
  - task-0
  - task-1
  - task-2
```

Set confidence to `high` for an explicit request or five or more distinct observations; set it to `medium` at the three-observation threshold. Use the fixed tag `agent-observed` unless a human adds reviewed tags during approval.

- [ ] **Step 5: Run lifecycle and corpus tests**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_knowledge_lifecycle.py tests/platform/test_knowledge.py -q
uv run --locked python -m py_compile vesper/platform/knowledge_lifecycle.py
```

Expected: PASS with no approved-note write path in `KnowledgeLifecycleService`.

- [ ] **Step 6: Commit candidate consolidation**

```powershell
git add vesper/platform/knowledge_lifecycle.py tests/platform/test_knowledge_lifecycle.py
git diff --cached --check
git commit -m "feat(knowledge): consolidate agent observations"
```

---

### Task 5: Record usage and produce review-only compaction/reactivation proposals

**Files:**
- Modify: `vesper/platform/knowledge_lifecycle.py`
- Modify: `tests/platform/test_knowledge_lifecycle.py`

**Interfaces:**
- Produces: `record_selections(contexts)`, `accept_run(task, receipts)`, `compaction_plan(target_lines=3000)`, and `reactivation_plan()`.
- Store namespaces: `("knowledge", "adaptive", "usage")` by knowledge ID and `("knowledge", "adaptive", "accepted-runs")` by run ID.
- Guarantees: repeated snapshot, resume, or approval processing is idempotent and no proposal mutates Markdown.

- [ ] **Step 1: Write failing usage and proposal tests**

Add tests for selection without success credit, accepted-run credit, replay idempotency, rejected-run absence, pinned exclusion, superseded/overdue/contested ranking, deterministic proposal hashes, line impacts, and repeated archive-use reactivation:

```python
def test_accepted_run_credits_selected_documents_once(tmp_path):
    service, _vault = lifecycle_service(tmp_path)
    contexts = (knowledge_context("active-id", KnowledgeTier.ACTIVE),)
    service.record_selections(contexts)

    service.accept_run(task(), receipts=())
    service.accept_run(task(), receipts=())

    usage = service.usage("active-id")
    assert usage["selection_count"] == 1
    assert usage["successful_run_count"] == 1


def test_compaction_excludes_pinned_and_never_moves_files(tmp_path):
    service, vault = lifecycle_service_with_active_notes(tmp_path)
    before = sorted(path.relative_to(vault) for path in vault.rglob("*.md"))

    proposal = service.compaction_plan(target_lines=20)

    assert "pinned-policy" not in {item["knowledge_id"] for item in proposal["entries"]}
    assert proposal["projected_active_lines"] <= 20
    assert sorted(path.relative_to(vault) for path in vault.rglob("*.md")) == before
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_knowledge_lifecycle.py -q
```

Expected: FAIL because usage and proposal methods do not exist.

- [ ] **Step 3: Implement idempotent selection and accepted-run ledgers**

Use stable refs `f"{run_id}:{role.value}"`. `record_selections` adds each context document to its usage record once. `accept_run`:

1. returns the persisted result when the run is already in the accepted-run namespace;
2. collects each receipt output's `knowledge_observations` and calls `observe` with source ref `run_id:role:attempt`;
3. promotes selected refs for the run to successful refs;
4. stores `accepted_at`, affected knowledge IDs, and observation results under the run ID.

Never call `accept_run` for rejected, failed, cancelled, interrupted, or merely awaiting-approval workflows.

- [ ] **Step 4: Implement deterministic, non-mutating proposals**

`compaction_plan(target_lines=3_000)` must reject targets outside `0..3000`, exclude pinned notes, and rank adaptive active notes by:

1. explicitly superseded first;
2. overdue `review_after` first;
3. contested first for operator review;
4. lower successful-run count;
5. older or missing last successful use;
6. larger source line count;
7. stable knowledge ID.

Add entries until projected active lines meet the target. Each entry includes source path/hash, lines released, usage counts, and reasons. The proposal ID is SHA-256 of canonical sorted JSON excluding creation time.

`reactivation_plan()` includes archived notes with at least three successful runs, ordered by successful-run count descending, last successful use descending, then stable ID. Each entry reports whether it fits under 3,000 lines without displacement and, when it does not, embeds the matching compaction plan. It never moves a file.

- [ ] **Step 5: Run lifecycle tests**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_knowledge_lifecycle.py -q
uv run --locked python -m py_compile vesper/platform/knowledge_lifecycle.py
```

Expected: PASS with byte-identical proposal IDs across repeated calls over unchanged state.

- [ ] **Step 6: Commit usage and proposals**

```powershell
git add vesper/platform/knowledge_lifecycle.py tests/platform/test_knowledge_lifecycle.py
git diff --cached --check
git commit -m "feat(knowledge): add usage-based review proposals"
```

---

### Task 6: Connect specialist observations and successful use to the approval workflow

**Files:**
- Modify: `vesper/platform/composition.py:1114-1174`
- Modify: `vesper/platform/workflow.py:266-316`
- Modify: `vesper/platform/workflow.py:645-700`
- Modify: `vesper/platform/service.py:291-323`
- Modify: `vesper/platform/service.py:582-632`
- Modify: `tests/platform/test_composition.py`
- Modify: `tests/platform/test_workflow.py`
- Modify: `tests/platform/test_service.py`

**Interfaces:**
- Consumes: optional `knowledge_observations` on specialist outputs and `KnowledgeLifecycleService` from Tasks 1 and 4-5.
- Changes: add keyword-only `knowledge_lifecycle: KnowledgeLifecycleService | None = None` to the existing `build_workflow` signature without changing its other parameters.
- Guarantees: only an operator-approved accepted run consolidates specialist observations and credits selected knowledge.

- [ ] **Step 1: Write failing prompt and workflow tests**

Add tests proving the prompt distinguishes knowledge observations from validated runtime memory, output schemas permit one proposal, approval processes it once, rejection processes none, and resume replay remains idempotent:

```python
def test_operator_approval_consolidates_knowledge_observation_once():
    lifecycle = FakeKnowledgeLifecycle()
    controller = workflow_controller(
        product_output=product_output_with_observation(),
        knowledge_lifecycle=lifecycle,
    )
    view = controller.start(task())
    controller.record_decision(task().run_id, approve_decision(view))
    accepted = controller.resume(task().run_id)

    assert accepted.state.status is RunStatus.ACCEPTED
    assert lifecycle.accepted_runs == [(task().run_id, 3)]
```

Also assert rejection leaves `accepted_runs == []` and a repeated inspection/resume cannot add a second call.

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_composition.py tests/platform/test_workflow.py tests/platform/test_service.py -q
```

Expected: FAIL because prompts and workflow wiring do not expose the new lifecycle.

- [ ] **Step 3: Add concise observation instructions to specialist prompts**

After the separate `memory` instructions, tell each specialist:

```text
Set knowledge_observations to an empty array unless the current task contains an
explicit durable operator request or reveals a repeated reusable procedure.
At most one candidate-only observation is allowed. Use a stable lowercase slug,
paraphrase without transcript text or secrets, and never treat the proposal as
approved knowledge, evidence, or authority.
```

The output schema remains Pydantic-generated. Do not map these proposals into `MemoryCandidate` or `_memory_candidates`.

- [ ] **Step 4: Wire lifecycle processing into the accepted approval branch**

Add `knowledge_lifecycle` as an optional `build_workflow` dependency captured by `human_approval_node`. After integrity checks and only when `decision.decision is ApprovalDecision.APPROVE`, call:

```python
if knowledge_lifecycle is not None:
    knowledge_lifecycle.accept_run(request, tuple(_parse(SpecialistReceipt, item) for item in state["receipts"]))
```

Keep the lifecycle idempotency marker responsible for replay safety. Rejection and every nonterminal path must not call it.

- [ ] **Step 5: Construct one lifecycle service per persistence scope**

In `LocalPlatformService`, add a private helper:

```python
def _knowledge_lifecycle(
    self,
    persistence: PlatformPersistence,
    repository_root: Path,
) -> KnowledgeLifecycleService:
    return KnowledgeLifecycleService(
        vault_root=self._knowledge_root_for_repository(repository_root),
        store=persistence.store,
        clock=self._clock,
    )
```

During create, keep the contexts returned by `knowledge.snapshot(task)` and call `lifecycle.record_selections(contexts)` before graph start. Pass the same lifecycle behavior into `build_workflow`. Resume reconstructs it from persisted repository metadata, as the existing controller already does for the knowledge context reader.

- [ ] **Step 6: Run workflow integration tests**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_composition.py tests/platform/test_workflow.py tests/platform/test_service.py -q
uv run --locked python -m py_compile vesper/platform/composition.py vesper/platform/workflow.py vesper/platform/service.py
```

Expected: PASS; accepted runs write only candidate notes, and rejected runs do not alter inbox or usage-success state.

- [ ] **Step 7: Commit workflow integration**

```powershell
git add vesper/platform/composition.py vesper/platform/workflow.py vesper/platform/service.py tests/platform/test_composition.py tests/platform/test_workflow.py tests/platform/test_service.py
git diff --cached --check
git commit -m "feat(knowledge): connect observations to approval"
```

---

### Task 7: Add the controlled repository-agent and operator CLI surface

**Files:**
- Modify: `vesper/platform/cli.py:30-62`
- Modify: `vesper/platform/cli.py:261-279`
- Modify: `vesper/platform/service.py:479-513`
- Modify: `tests/platform/test_cli.py`
- Modify: `tests/platform/test_service.py`

**Interfaces:**
- Produces: `LocalPlatformService.observe_knowledge(concept_key, title, kind, scope, summary, source_ref, explicit)`, `knowledge_compaction_plan(target_lines)`, and `knowledge_reactivation_plan()`.
- CLI commands: `knowledge-observe`, `knowledge-compaction-plan`, `knowledge-reactivation-plan`.
- Preserves: side-effect-free `--help`; no approval, archive, reactivation, or deletion command is added.

- [ ] **Step 1: Write failing CLI routing and service boundary tests**

Extend `FakeService` and the parameterized CLI test with:

```python
(
    [
        "knowledge-observe",
        "--concept-key", "brief-writing",
        "--title", "Prefer brief writing",
        "--kind", "memory",
        "--scope", "shared",
        "--summary", "Prefer brief, direct wording.",
        "--source-ref", "codex-task-123",
        "--explicit",
    ],
    (
        "knowledge-observe", "brief-writing", "Prefer brief writing", "memory",
        "shared", "Prefer brief, direct wording.", "codex-task-123", True,
    ),
),
(["knowledge-compaction-plan", "--target-lines", "2800"], ("knowledge-compaction-plan", 2800)),
(["knowledge-reactivation-plan"], ("knowledge-reactivation-plan",)),
```

Service tests must reject an external vault, invalid role/kind/scope, non-UTC observation time, and secret-like summary before any candidate write.

- [ ] **Step 2: Run CLI and service tests to verify failure**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_cli.py tests/platform/test_service.py -q
```

Expected: FAIL because the service protocol and commands do not exist.

- [ ] **Step 3: Add service methods using the validated operator vault**

Implement:

```python
def observe_knowledge(
    self,
    concept_key: str,
    title: str,
    kind: str,
    scope: str,
    summary: str,
    source_ref: str,
    explicit: bool,
) -> dict[str, object]:
    try:
        observation = KnowledgeObservation(
            concept_key=concept_key,
            title=title,
            kind=KnowledgeKind(kind),
            scope=KnowledgeScope(scope),
            summary=summary,
            source_ref=source_ref,
            observed_at=self._clock(),
            explicit=explicit,
        )
    except (ValueError, ValidationError) as exc:
        raise SpecialistRuntimeUnavailable(f"invalid knowledge observation: {exc}") from exc
    with open_persistence(self.paths) as persistence:
        return self._operator_knowledge_lifecycle(persistence).observe(observation)

def knowledge_compaction_plan(self, target_lines: int) -> dict[str, object]:
    with open_persistence(self.paths) as persistence:
        return self._operator_knowledge_lifecycle(persistence).compaction_plan(target_lines)

def knowledge_reactivation_plan(self) -> dict[str, object]:
    with open_persistence(self.paths) as persistence:
        return self._operator_knowledge_lifecycle(persistence).reactivation_plan()
```

Add `_operator_knowledge_lifecycle(persistence)` beside `_operator_knowledge_root()`; it constructs `KnowledgeLifecycleService(vault_root=self._operator_knowledge_root(), store=persistence.store, clock=self._clock)`. Convert validation errors into the existing `SpecialistRuntimeUnavailable` boundary so CLI errors remain exit code 4.

- [ ] **Step 4: Add Typer commands and protocol methods**

Add exact options shown in Step 1. `--explicit` is a boolean flag defaulting to false. `knowledge-compaction-plan --target-lines` defaults to `3000`. Help text must say every command creates candidates or proposals only and cannot approve or move knowledge.

- [ ] **Step 5: Run CLI and service tests**

Run:

```powershell
uv run --locked python -m pytest tests/platform/test_cli.py tests/platform/test_service.py -q
uv run --locked vesper-agent --help
uv run --locked python -m py_compile vesper/platform/cli.py vesper/platform/service.py
```

Expected: PASS; help lists all three commands without opening persistence or constructing the service.

- [ ] **Step 6: Commit the command surface**

```powershell
git add vesper/platform/cli.py vesper/platform/service.py tests/platform/test_cli.py tests/platform/test_service.py
git diff --cached --check
git commit -m "feat(knowledge): expose governed lifecycle commands"
```

---

### Task 8: Update the Obsidian vault contract and operator documentation

**Files:**
- Create: `knowledge/archive/README.md`
- Create: `knowledge/archive/memory/README.md`
- Create: `knowledge/archive/skills/README.md`
- Create: `knowledge/raw/README.md`
- Create: `knowledge/wiki/README.md`
- Create: `docs/adr/ADR-0003-adaptive-knowledge-core.md`
- Modify: `knowledge/README.md`
- Modify: `knowledge/inbox/README.md`
- Modify: `docs/runbooks/obsidian-knowledge.md`
- Modify: `README.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Documents: exact authority boundaries, candidate thresholds, line counting, archive status, temporary retrieval caps, CLI examples, recovery, and human review.
- Agent rule: submit observations through `knowledge-observe`; never write approved, archived, reactivated, or deleted state automatically.

- [ ] **Step 1: Write the accepted ADR and vault README files**

ADR-0003 must state that it extends ADR-0002 and records these exact decisions:

- active approved corpus capped at 3,000 complete Markdown lines;
- `pinned` and `adaptive` retention;
- `vesper_status: archived` under archive memory/skills;
- automatic candidate creation after an explicit request or three distinct observations;
- automatic temporary archive retrieval capped at two documents inside five/8,000;
- operator-only approval, archival, permanent reactivation, retention changes, and deletion;
- accepted-run usage only;
- no external service, embedding, background scheduler, or automatic movement.

- [ ] **Step 2: Update the runbook with copy/paste commands**

Include:

```powershell
uv run --locked vesper-agent knowledge-observe `
  --concept-key brief-writing `
  --title "Prefer brief writing" `
  --kind memory `
  --scope shared `
  --summary "Prefer brief, direct wording unless detail is requested." `
  --source-ref "operator-task-reference" `
  --explicit

uv run --locked vesper-agent knowledge-compaction-plan --target-lines 2800
uv run --locked vesper-agent knowledge-reactivation-plan
```

Document that candidate review occurs in Obsidian, file movement is manual, `knowledge-sync` enforces the hard limit, archive retrieval is temporary, and deletion has no controller command.

- [ ] **Step 3: Update repository-agent guidance**

Replace the current generic inbox-draft instruction in `AGENTS.md` with concise rules:

```text
When the operator explicitly asks to remember a durable fact/preference, submit one
explicit knowledge observation. For a non-explicit durable pattern, submit the same
stable concept key across distinct tasks; the controller creates a candidate at three.
Never include transcript text, secrets, temporary state, or unsupported authority.
Never move, approve, archive, reactivate, or delete knowledge files.
```

Keep the existing rule that task progress and temporary session outcomes are not durable knowledge.

- [ ] **Step 4: Verify documentation consistency**

Run:

```powershell
rg -n "3,000|knowledge-observe|knowledge-compaction-plan|knowledge-reactivation-plan|vesper_status: archived" README.md AGENTS.md knowledge docs/adr docs/runbooks
uv run --locked vesper-agent --help
git diff --check
```

Expected: every documented command appears in CLI help, relative links resolve, and no document implies agent approval or automatic movement.

- [ ] **Step 5: Commit documentation**

```powershell
git add AGENTS.md README.md knowledge/README.md knowledge/inbox/README.md knowledge/templates/memory.md knowledge/templates/skill.md knowledge/archive/README.md knowledge/archive/memory/README.md knowledge/archive/skills/README.md knowledge/raw/README.md knowledge/wiki/README.md docs/adr/ADR-0003-adaptive-knowledge-core.md docs/runbooks/obsidian-knowledge.md
git diff --cached --check
git commit -m "docs(knowledge): document adaptive core operations"
```

---

### Task 9: Run full verification and record the implementation receipt

**Files:**
- Create: `docs/receipts/adaptive-knowledge-core-receipt.md`
- Verify: every file changed in Tasks 1-8

**Interfaces:**
- Produces: a durable receipt with exact commands, exit results, test counts, final diff scope, and known deferred features.
- Requires: all focused task tests pass before the full suite starts.

- [ ] **Step 1: Run focused adaptive-knowledge tests**

```powershell
$testRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-adaptive-knowledge-$PID"
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
uv run --locked python -m pytest `
  tests/platform/test_contracts.py `
  tests/platform/test_knowledge.py `
  tests/platform/test_knowledge_lifecycle.py `
  tests/platform/test_composition.py `
  tests/platform/test_workflow.py `
  tests/platform/test_service.py `
  tests/platform/test_cli.py `
  -q --basetemp (Join-Path $testRoot "focused")
```

Expected: PASS with zero failures.

- [ ] **Step 2: Run formatting, lint, and compilation**

Format only changed Python files, then check them:

```powershell
uv run --locked ruff format `
  vesper/platform/contracts.py `
  vesper/platform/knowledge.py `
  vesper/platform/knowledge_lifecycle.py `
  vesper/platform/composition.py `
  vesper/platform/workflow.py `
  vesper/platform/service.py `
  vesper/platform/cli.py `
  tests/platform/test_contracts.py `
  tests/platform/test_knowledge.py `
  tests/platform/test_knowledge_lifecycle.py `
  tests/platform/test_composition.py `
  tests/platform/test_workflow.py `
  tests/platform/test_service.py `
  tests/platform/test_cli.py

uv run --locked ruff format --check `
  vesper/platform/contracts.py `
  vesper/platform/knowledge.py `
  vesper/platform/knowledge_lifecycle.py `
  vesper/platform/composition.py `
  vesper/platform/workflow.py `
  vesper/platform/service.py `
  vesper/platform/cli.py `
  tests/platform/test_contracts.py `
  tests/platform/test_knowledge.py `
  tests/platform/test_knowledge_lifecycle.py `
  tests/platform/test_composition.py `
  tests/platform/test_workflow.py `
  tests/platform/test_service.py `
  tests/platform/test_cli.py

uv run --locked ruff check vesper scripts tests

$compileRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-adaptive-compile-$PID"
$env:PYTHONPYCACHEPREFIX = Join-Path $compileRoot "pycache"
uv run --locked python -m compileall -q vesper scripts tests
```

Expected: every command exits 0.

- [ ] **Step 3: Run the required full project suite and import gate**

```powershell
$fullRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-adaptive-full-$PID"
New-Item -ItemType Directory -Force -Path $fullRoot | Out-Null
uv run --locked python -m pytest tests -q --basetemp (Join-Path $fullRoot "pytest")

$importRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-adaptive-imports-$PID"
New-Item -ItemType Directory -Force -Path $importRoot | Out-Null
uv run --locked python -m pytest tests/test_imports.py -q --basetemp (Join-Path $importRoot "pytest")
```

Expected: zero failures in both runs.

- [ ] **Step 4: Run lock, CLI, and diff gates**

```powershell
uv lock --check
uv run --locked vesper-agent --help
uv run --locked vesper-agent knowledge-status
git diff --check
git status --short
```

Expected: lock check and commands exit 0; status shows only intended task files plus any documented pre-existing user changes.

- [ ] **Step 5: Write the receipt from actual results**

Record:

- implementation commit hashes from Tasks 1-8;
- exact focused and full pytest pass/skip counts;
- Ruff, compileall, import, lock, CLI, and diff results;
- the active-line and archive status output from the smoke test;
- confirmation that no protected data, risk/trading configuration, model artifact, external service, scheduler, or credential changed;
- deferred items: embeddings, automatic archival/reactivation/deletion, scheduling, and external memory services.

Do not enter expected values before commands run; copy only fresh observed results.

- [ ] **Step 6: Commit the receipt and inspect the final range**

```powershell
git add docs/receipts/adaptive-knowledge-core-receipt.md
git diff --cached --check
git commit -m "docs(knowledge): record adaptive core verification"
git log --oneline --decorate -10
git diff HEAD~9..HEAD --stat
git status --short
```

Expected: the receipt is the only file in the final commit and the complete implementation range contains no unrelated changes.
