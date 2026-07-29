# Adaptive Knowledge Core with Guarded Archive Retrieval

- Status: Accepted
- Date: 2026-07-28
- Owner: V20 operator
- Scope: Agent-created knowledge candidates, active-set retention, archival, and
  temporary archive retrieval

## Goal

Keep V20's approved working knowledge concise and useful without losing older
knowledge. Agents perform observation, candidate drafting, retrieval, and
bookkeeping. The operator remains the gate for approval into the working set,
archival, permanent reactivation, and deletion.

The approved active knowledge base has a hard 3,000-line ceiling. Knowledge
outside that budget remains available in a searchable Obsidian archive and may
be retrieved temporarily for a relevant run.

## Relationship to the existing standard

This design extends the accepted Obsidian and LangGraph knowledge standard; it
does not replace it.

- Repository-owned Markdown remains canonical.
- `knowledge/memory/` and `knowledge/skills/` remain the only approved active
  runtime knowledge.
- LangGraph Store and SQLite FTS5 remain derived, rebuildable state.
- Each run still receives a bounded, role-scoped, immutable knowledge context.
- Knowledge remains context rather than evidence, policy, permission, or
  execution authority.
- Current instructions, repository state, typed evidence, validation, risk
  limits, and human approvals continue to outrank every knowledge note.

Receipt-derived runtime memory remains separate from operator-authored
knowledge. This design does not grant agents trading, deployment, model
promotion, risk, scheduler, credential, or provider authority.

## Design principles

1. **Agents do the bookkeeping.** They detect repeated durable patterns, draft
   candidates, update observation counts, and recommend retention changes.
2. **The operator controls durable state.** No agent may approve, archive,
   permanently reactivate, or delete a note.
3. **Archive instead of delete.** Inactive knowledge remains readable and
   searchable in Obsidian. Deletion is a separate explicit operator action.
4. **Utility is evidence, not authority.** Frequent use affects recommendations,
   but rarely used safety, authority, and foundational knowledge may be pinned.
5. **Active knowledge is not the prompt.** The 3,000-line active corpus is still
   retrieved into the existing much smaller per-run packet; it is never injected
   wholesale.
6. **No raw conversation warehouse.** Observation records retain compact
   provenance and counts, not full private transcripts.

## Vault layout

```text
knowledge/
├── memory/                 approved active facts and preferences
├── skills/                 approved active reusable procedures
├── archive/
│   ├── memory/             inactive facts and preferences
│   └── skills/             inactive reusable procedures
├── inbox/                  automatically created candidate notes
├── raw/                    immutable source material for the working wiki
├── wiki/                   LLM-maintained synthesis, links, index, and log
└── templates/
```

Only approved notes in `memory/` and `skills/` count toward the active budget.
The archive, inbox, raw sources, wiki, templates, and README files do not count
toward the 3,000-line limit.

Archived notes retain their stable `vesper_id`, kind, scope, title, tags,
content, source provenance, and Git history. Archive location and status prevent
them from entering ordinary active synchronization. An archived note uses
`vesper_status: archived`; a candidate uses `vesper_status: candidate`.

## Active-set budget

The controller counts every logical line in the complete UTF-8 source of each
approved Markdown note under `knowledge/memory/` and `knowledge/skills/`,
including frontmatter. README files are excluded. The combined total must not
exceed 3,000 lines.

The budget is enforced before synchronization mutates LangGraph Store or the
FTS5 index. If the active corpus exceeds the limit, synchronization fails closed
and reports:

- the current line total;
- the amount over budget;
- per-note line counts;
- pinned notes that cannot be proposed for archival; and
- a ranked, non-binding compaction proposal.

Pinning protects a note from archival but does not exempt its lines from the
budget. If pinned knowledge consumes the entire budget, the controller reports
the conflict and requires the operator to revise the corpus or its retention
labels. It never raises the limit silently.

## Retention classes

Approved active notes have one of two retention classes:

- `pinned`: never proposed for automatic archival;
- `adaptive`: eligible for a compaction proposal based on observed utility,
  recency, supersession, contradiction, and staleness.

Pinned knowledge normally includes:

- safety and authority boundaries;
- core architectural decisions;
- essential operating and recovery procedures; and
- explicit durable operator preferences whose omission would repeatedly degrade
  agent behavior.

Retention class does not change note authority. A pinned note is still context,
not evidence or permission.

## Automatic candidate creation

Agents may submit structured observations to a controller-owned consolidator.
They do not write approved knowledge directly and do not receive direct vault
access.

Before a pattern reaches the candidate threshold, the controller stores its
compact observations in a derived LangGraph Store ledger keyed by the proposed
concept. The same interaction may increment a concept only once. The ledger is
rebuildable operational state rather than canonical knowledge and contains no
raw conversation text.

An observation contains:

- a stable proposed concept key;
- proposed kind and scope;
- a concise paraphrase of the durable pattern;
- an opaque run, task, or interaction reference;
- an observation timestamp; and
- whether the operator explicitly requested that it be remembered.

It must not contain a raw transcript, credential, secret, protected market data,
temporary task state, or an unsupported authority claim.

The consolidator follows these rules:

1. An explicit request such as "remember this" creates or updates a candidate
   immediately.
2. Otherwise, three matching observations from distinct interactions create a
   candidate.
3. Further matching observations update the existing candidate rather than
   create duplicates.
4. A durable fact, decision, convention, or preference becomes a memory
   candidate.
5. A repeatable, bounded procedure with a trigger and verification becomes a
   skill candidate.
6. The same observation does not create both kinds unless each candidate has a
   distinct purpose.
7. One-off instructions, session progress, temporary TODOs, and speculative
   inferences remain outside durable knowledge.

Candidate notes record the observation count, first and last observation times,
confidence, rationale, and compact provenance references. They remain under
`knowledge/inbox/` with candidate status. Agents may refine or merge candidates
there, but candidate creation never makes a note active.

For example, repeated requests for brief writing create a preference memory
candidate such as "The operator prefers brief, direct wording unless detail is
requested." A separate skill is appropriate only if the observations establish
a reusable procedure rather than the preference alone.

## Human approval boundary

The operator is the only actor allowed to:

- approve an inbox candidate into `memory/` or `skills/`;
- move an active note into `archive/`;
- permanently reactivate an archived note;
- change a note between pinned and adaptive retention; or
- permanently delete a note.

If approving or reactivating a note would exceed 3,000 lines, the controller
produces a displacement proposal showing eligible active notes and the effect of
each possible archival choice. The requested note does not enter runtime
knowledge until the operator makes the movements and the corpus passes budget
validation.

## Usage and compaction signals

Search results alone do not count as use. A note receives successful-use credit
only when it was selected into a run that subsequently reached the applicable
validated or operator-accepted outcome.

The derived usage ledger records, by stable knowledge ID:

- selection count;
- successful-run count;
- last successful-use time;
- active or archive tier at selection time; and
- the referencing run and task IDs.

It does not store note contents or model conversations. The ledger is derived
controller state, not canonical knowledge and not evidence for trading or model
promotion.

The compaction planner ranks only adaptive notes. Ranking considers successful
use, recency, explicit supersession, unresolved contradiction, and review age.
It produces a review proposal; it never moves files. Popularity alone cannot
displace pinned knowledge or override current correctness.

During the initial rollout, there is no scheduled or automatic compaction.
Compaction is operator-invoked when the corpus approaches or exceeds its budget.

## Guarded archive retrieval

The searchable FTS5 corpus includes active and archived notes with an explicit
tier. Role scopes apply equally to both tiers. Active notes receive deterministic
ranking preference, while a highly relevant archived note remains eligible.

For each role and run:

1. The controller searches active and archived knowledge using the task
   objective.
2. It selects no more than two archived documents.
3. Active and archived selections together remain within the existing maximum
   of five documents and 8,000 content characters.
4. Archived documents are marked clearly as temporary archive context, including
   stable ID, path, tier, and source hash.
5. The complete selection is persisted in the run's immutable role-scoped
   snapshot before the specialist uses it.
6. Resume reuses the snapshot and never silently replaces it with current vault
   contents.

Temporary retrieval does not move the archive file, change its status, add it to
the active line budget, or grant authority. A later successful run contributes
usage evidence that may cause the reactivation planner to recommend the note.
Permanent reactivation still requires operator approval.

The initial ranking and active-tier preference must be frozen and tested against
a V20-specific relevance fixture. Embeddings, vector storage, and graph databases
remain deferred until the lexical baseline fails an evidence-backed benchmark.

## Agent and controller boundaries

Repository agents and V20 specialists may both produce observations through the
same structured contract. The controller owns deduplication, validation,
candidate-file updates, usage accounting, budget enforcement, archive search,
and proposal generation.

Specialists continue to receive no direct read or write access to the vault.
Candidate generation must use the controller boundary or a reviewed repository
agent workflow. A malformed, secret-bearing, unscoped, or unverifiable
observation is rejected before any inbox write.

No background model runner, external memory service, cloud database, new
credential, paid model invocation, or scheduler is introduced by this design.

## Failure behavior

- Invalid active or archived frontmatter fails validation with the relative
  source path.
- Duplicate stable IDs across active, archive, and inbox fail before mutation.
- A linked vault, linked note, invalid UTF-8 source, or path outside the approved
  repository-local vault fails closed.
- Secret-like or prohibited content is rejected from automatic candidates and
  must not be written to diagnostic logs.
- A failed candidate update leaves the previous candidate unchanged.
- A failed synchronization leaves the previous Store and FTS5 corpus intact.
- A missing or corrupt archive index is rebuilt from canonical Markdown.
- A missing historical run snapshot injects no replacement knowledge.
- Usage-ledger loss affects recommendations only; it does not alter canonical
  notes or historical run context.
- No failure falls back to another role's knowledge, live vault reads during
  resume, automatic approval, automatic archival, or automatic deletion.

## Operator workflow

1. Agents observe explicit or repeated durable patterns.
2. The controller creates or updates candidates in `knowledge/inbox/`.
3. The operator reviews candidates in Obsidian.
4. The operator approves selected candidates by moving them to the correct
   active directory and setting approved status and retention class.
5. The controller validates the 3,000-line budget and synchronizes the corpus.
6. Runs receive bounded active knowledge plus, when relevant, no more than two
   temporary archived notes.
7. Successful outcomes update the derived usage ledger.
8. The operator reviews compaction and reactivation proposals and decides which
   file movements to make.

## Acceptance criteria

1. An explicit memory request creates one candidate immediately without making
   it active.
2. Three matching observations from distinct interactions create one candidate;
   later matches update it without duplication.
3. Preferences become memories and repeatable procedures become skills without
   unnecessary paired candidates.
4. Raw transcripts, credentials, secrets, protected data, task progress, and
   one-off instructions never enter automatic candidates.
5. Only the operator can approve, archive, permanently reactivate, change
   retention, or delete knowledge.
6. Active budget counting is deterministic and synchronization fails before
   mutation when approved notes exceed 3,000 lines.
7. Pinned notes remain protected while still counting toward the limit.
8. Compaction and reactivation are proposals with line impacts and provenance,
   not automatic file movements.
9. Archived notes remain searchable in Obsidian and derived FTS5 state while
   staying outside ordinary active synchronization.
10. Archive retrieval respects role scope, contributes no more than two notes,
    and remains inside the existing five-document/8,000-character snapshot.
11. Temporary archive context is visibly marked and cannot become evidence,
    authority, or a permanent active note.
12. Successful-run usage updates derived counts; search exposure alone does not.
13. Run snapshots remain immutable across vault, archive, ranking, and usage
    changes.
14. Existing knowledge synchronization, prompt isolation, validation, resume,
    and execution-authority tests continue to pass.

## Initial implementation boundary

The first implementation should provide deterministic schemas, candidate
consolidation, active-budget validation, archive validation/indexing, bounded
temporary retrieval, derived usage accounting, and human-readable proposals.
It should extend the current knowledge service and contracts rather than create a
second canonical store or adopt a new memory framework.

Automatic archival, automatic permanent reactivation, deletion, background
scheduling, embeddings, semantic graph storage, and external services are
explicitly outside the first implementation.

## References

- [Obsidian and LangGraph knowledge ADR](../../adr/ADR-0002-obsidian-langgraph-knowledge.md)
- [Existing knowledge standard design](2026-07-28-obsidian-langgraph-knowledge-standard-design.md)
- [Knowledge operator runbook](../../runbooks/obsidian-knowledge.md)
