# Compounding Long-Term Memory Governance

Use this design when the goal is for Hermes to become better adapted over time without turning memory growth into stale context, cross-worker contamination, or unnecessary token cost.

## What can improve over time

Separate five mechanisms:

1. **Session adaptation:** temporary context in the current conversation.
2. **Persistent memory:** durable preferences, corrections, facts, and relationships retrieved in later sessions.
3. **Curated behavior:** skills, profile SOUL files, tool policies, schedules, and operating procedures.
4. **Evidence accumulation:** tests, reports, manifests, receipts, incident records, and project indexes.
5. **Model training:** actual weight updates. Do not imply this occurs unless a training pipeline changed the model artifact.

A deployed system can become more personalized and reliable through layers 2–4 while the foundation model weights remain unchanged.

## Recommended ownership model

- One human-facing coordinator profile is the durable-memory steward.
- Specialist workers use isolated profile memory or no durable write capability by default.
- Workers submit evidence-backed findings through project artifacts and task receipts.
- The coordinator promotes only validated lessons into shared or canonical memory.
- Shared cross-agent memory contains compact, stable metadata—not raw transcripts, hidden reasoning, secrets, or speculative research claims.

This is a promotion pipeline, not unrestricted collective journaling.

## Storage decision table

| Information class | Store |
|---|---|
| Stable human identity/preferences | Canonical provider slots |
| Stable authority/safety boundaries | Canonical or compact shared memory plus source pointer |
| Ordinary durable facts/corrections | Semantic working memory with provenance and validity |
| Explicit subject/relationship/time facts | Knowledge graph/triples |
| Reusable procedure or tool workaround | Class-level skill |
| Project truth and research evidence | Versioned/checksummed file or receipt |
| Current task state | Kanban/task ledger |
| Temporary thought/work note | Session scratchpad |
| Full prior conversation detail | Session search |
| Credential/secret | Dedicated secret store; never memory |

Prefer pointers to authoritative artifacts over copying large artifact bodies into memory.

## Quality loop

```text
experience
→ validate lesson
→ classify storage layer
→ write narrowly with provenance
→ retrieve only when relevant
→ apply
→ verify outcome
→ correct/invalidate if wrong
→ promote to skill/artifact when procedural
→ consolidate or expire when stale
```

## Consolidation and maintenance

- Do not store every turn as a durable fact.
- Consolidate after substantial work periods or when working memory has accumulated enough eligible material; do not force consolidation merely to reduce a count.
- Run provider health/stat diagnostics periodically and before migrations.
- Measure useful recall, irrelevant recall, stale-memory rate, contradiction handling, correction/deletion success, cross-worker leakage, secret leakage, latency, and prompt overhead.
- Back up provider state before consolidation, migration, mass invalidation, or cleanup.
- Keep Hermes Curator conceptually separate: Curator maintains agent-created skills, while the memory provider maintains facts/preferences/episodes. Routine deterministic curation is not model learning.
- Leave automatic LLM skill consolidation off until duplication is measured and a backup/review path exists.

## Token economics

Persistent memory may reduce repeated explanations, exploration, and rework, but retrieval and injected context also consume tokens. Optimize for **cost per successful task**, not maximum stored memory.

- Retrieve a few high-relevance memories, not the entire store.
- Use session search for detailed history instead of bloating durable memory.
- Use task packets and narrow worker toolsets.
- Use deterministic scripts for mechanical work.
- Route routine tasks to appropriately priced models.
- Track whether memory actually prevents repetition and errors.

Do not promise that longer use always lowers bills. Provider billing, subscription quotas, retrieval overhead, and task complexity all matter.

## Fresh-session identity rule

Persistent memory alone does not make a fresh session the main coordinator. Stable coordinator identity requires:

- the intended profile to be selected by routing;
- that profile's `SOUL.md` to define its role;
- a canonical identity record for durable recall;
- a fresh-session verification on each relevant surface.

See the `hermes-profile-configuration` skill reference `references/profile-identity-routing.md` for the full routing recipe.

## Fail-closed rules

- Current external sources outrank remembered state.
- Known-wrong memory must be corrected or invalidated; passive aging is not enough.
- A retrieval miss is not proof that an event or decision never occurred.
- Never allow one worker's unreviewed output to become global truth automatically.
- Never use production memory databases or raw transcripts in platform benchmarks; seed disposable reviewed facts instead.
