---
name: brand-identity-design
description: Develop original visual identities and logo systems from user references, brand meaning, and practical use constraints. Use for logo concepts, emblem/wordmark lockups, identity directions, and image-generation briefs.
---

# Brand Identity Design

Create identity systems, not generic “industry logos.” The goal is a memorable visual idea that remains credible, reproducible, and useful across real applications.

## Core workflow

1. **Gather the actual brief**
   - Confirm the exact brand name and descriptor.
   - Identify the organization type, audience, desired mood, and practical applications.
   - Capture layout requirements such as emblem above the words, horizontal lockup, or symbol-only variant.
   - Note production constraints: shirt printing, embroidery, favicon size, monochrome use, dark background, ink count.

2. **Inspect references before generating**
   - Open every supplied image or website and examine it visually.
   - If a reference is a collage, ask which specific examples matter instead of treating the collage as one design.
   - Separate what the user likes into transferable principles: reduction, visual hierarchy, geometry, typography, spacing, palette, conceptual surprise, and brand-system consistency.
   - Do not copy a reference’s distinctive emblem, signature silhouette, or proprietary letter treatment.

3. **Synthesize a design thesis**
   - Explain the shared direction in a few concrete points.
   - Determine whether the user values **semantic concept** or **immediate visual character**. Do not force a metaphor when they are responding mainly to an odd silhouette, abstraction, or degree of reduction.
   - Find conceptual territory in the brand name, purpose, behavior, or worldview—not merely its industry—but allow the final mark to remain unexplained if its visual form is the real appeal.
   - For technical or financial firms, avoid defaulting to charts, candlesticks, nodes, orbits, arrows, convergence marks, and generic monograms unless the brief explicitly calls for them.
   - Reduce the thesis to one memorable visual decision that could plausibly support a full identity system.

4. **Develop distinct concepts**
   - Create 2–4 concepts only after the direction is sufficiently clear.
   - Each concept must start from a different idea, not a cosmetic change of accent color or geometry.
   - Give each concept a short rationale covering meaning, silhouette, and real-world usability.
   - Keep typography quiet when the emblem is intended to carry the personality.
   - If repeated full-lockup rounds are not converging, stop generating complete logos. Produce numbered monochrome symbol contact sheets (for example 5×5 grids), let the user shortlist by number, then isolate only the finalists into identical wordmark lockups. This separates symbol taste from typography and makes comparison efficient.
   - When the user prefers a wordmark-led identity, keep candidate symbols small and cap-height aligned. Treat the emblem as a signature, operator, or punctuation mark rather than a mascot.

5. **Generate and evaluate**
   - Use explicit prompts stating exact spelling, hierarchy, background, line weight, placement, and exclusions.
   - Generate concepts in parallel only when their underlying ideas are genuinely different.
   - Check spelling, symbol placement, legibility, and small-size strength.
   - Treat image-model output as concept exploration, not automatically as production-ready vector artwork.

6. **Refine the selected direction**
   - Preserve the core idea while adjusting weight, spacing, proportion, and color.
   - Prepare emblem-only, primary lockup, monochrome, and small-size versions.
   - Verify that the mark works in one color before relying on effects or gradients.

## Quality bar

A strong minimal identity:

- Can be described in one sentence.
- Can be recognized from its silhouette.
- Is simple enough to draw from memory.
- Has a defensible relationship to the brand.
- Works without gradients, glow, mockups, or explanatory text.
- Feels distinctive because of the idea, not because detail was added.
- Remains credible in the organization’s actual sector.

## Pitfalls

- **Generating too early:** Do not produce batches after only a vague style request when the user is still supplying references.
- **Story-first rationalization:** Do not invent a dusk/signal/outlier/system metaphor to justify arbitrary geometry. If the user likes a mark because it is odd, abstract, black, and simple, optimize the silhouette first and explain less.
- **Overdesigning minimalism:** Cuts, dots, accent colors, asymmetry, and hidden-data metaphors quickly turn one primitive into generic AI-tech decoration. Start in pure black and white; add nothing unless the user asks or the mark demonstrably needs it.
- **Generic industry symbolism:** “Quant” does not automatically mean signal lines, charts, nodes, or mathematical ornaments.
- **Cosmetic variations:** Different colors on essentially the same mark are not different concepts.
- **Over-explaining instead of observing:** When references are supplied, inspect them and update the brief concisely.
- **Ignoring hierarchy corrections:** Treat exact lockup wording as a hard constraint. “Emblem above” and “company name on one line” are independent requirements; do not stack the descriptor just because the emblem is stacked above.
- **Confusing minimal with arbitrary:** A sparse shape without deliberate visual character is generic, not minimal.
- **Imitating famous marks:** Borrow the degree of reduction or system discipline, never the recognizable primitive itself.
- **Backend failure loops:** If image generation fails for a specific managed model, inspect the configured image provider before retrying. Prefer switching to another already-authenticated provider (for example OpenAI Codex image generation) over repeating the same failing call.

## Reference notes

- See `references/vesper-engineering-direction.md` for a worked reference-synthesis example combining conceptual originality, severe reduction, and institutional credibility.
