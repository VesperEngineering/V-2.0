# Durable Profile Identity and Routing Across Sessions

Use this recipe when a Hermes profile must keep a stable organizational role—such as main coordinator, Development worker, or Risk Review worker—across `/new`, CLI restarts, Telegram topics, gateway restarts, and Kanban dispatches.

## Core distinction

A conversation title, chat group name, or recalled semantic memory does not authoritatively select a profile role. Three independent anchors are required:

1. **Identity:** `$HERMES_HOME/SOUL.md` states who the profile is and its durable responsibilities. Hermes loads it for every session using that profile.
2. **Durable role record:** the active memory provider stores a compact canonical identity record for the profile. This supports recall and correction but does not replace `SOUL.md`.
3. **Routing:** CLI, gateway/channel, cron, delegation, or Kanban configuration explicitly selects that profile. Routing determines which `HERMES_HOME`, config, SOUL, skills, sessions, and memory store are active.

Project files such as `AGENTS.md` define project policy and authority boundaries. They do not establish the agent's organizational identity.

## Recommended coordinator pattern

- Keep one named or default profile as the human-facing coordinator.
- Give its `SOUL.md` a concise identity: coordinator, memory steward, task router, evidence synthesizer, and final reporter.
- Store the same role as a canonical memory slot with owner/project scope and provenance.
- Route the user's home DM and default CLI to that profile.
- Give each specialist worker a separate profile and role-specific `SOUL.md`.
- Let Kanban assignments select worker profiles; do not infer worker identity from task titles.
- Keep shared cross-profile memory compact. Promote verified lessons through the coordinator rather than allowing every worker to write unrestricted global memory.

## Verification matrix

Test every surface that matters:

| Surface | Expected selector | Verification |
|---|---|---|
| `/new` in existing home DM | Existing routed profile | Ask `/profile`; confirm coordinator SOUL is active |
| Plain `hermes` CLI | Sticky/default profile | `hermes profile list`; inspect active marker |
| `hermes -p <worker>` | Explicit worker profile | Confirm profile path and role SOUL |
| New Telegram group/topic | Gateway route, not group title | Inspect routing/profile metadata before relying on it |
| Kanban task | Assigned profile | Inspect task assignee, spawned run profile, and worker context |
| Cron job | Job/profile configuration | Inspect execution metadata; do not infer from prompt wording |

After changing `SOUL.md`, profile config, tools, or routing, start a fresh session or restart the affected gateway as required. Verify actual runtime metadata; file presence alone is not proof.

## Pitfalls

- **Memory-only identity:** semantic recall can miss, rank poorly, become stale, or be intentionally skipped. Never rely on it as the sole role anchor.
- **SOUL-only routing:** the right identity file is useless if the chat or task launches a different profile.
- **Group-name inference:** creating a Telegram group does not create or bind a Hermes worker profile.
- **Project-rule conflation:** `AGENTS.md` governs work in a directory; it is not the stable cross-project identity layer.
- **Shared-memory contamination:** unrestricted worker writes can promote speculation into global truth. Require evidence-backed handoffs and coordinator promotion.
- **Role text copied everywhere:** do not duplicate the full coordinator identity into every skill and project file. Keep one SOUL, one canonical role record, and explicit routing receipts.
