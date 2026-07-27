# Mission-control card layout reference

## Trigger

Use when a fullscreen Windows Terminal dashboard looks like a widened log wall, has large unused space, clips at pane boundaries, or presents long operational prose as unreadable wrapped text.

## Observed failure pattern

The VOT launcher resized the native window to 2500×1015 px while Windows Terminal was started at a much smaller cell grid. The result was a large black region below the dashboard. A later weighted three-column composition reduced the empty region but still looked like the old panes. A single wide canvas plus a narrow rail then left most text left-aligned and visually empty.

## Durable composition

Use a status band followed by a bordered-card layout:

```text
status strip
────────────────────────────────────────────
main canvas                                      workforce rail
┌ account ┐ ┌ market ┐                           ┌ workforce ┐
┌ authority / system details ────────────────┐  ┌ next safe ┐
┌ primary blocker ──────────────────────────┐  ┌ activity  ┐
┌ pipeline / evidence ─────────────────────┐  └───────────┘
┌ provider accounting ─────────────────────┐
```

The main canvas should be dominant (roughly 72%) and the workforce rail should be a dedicated secondary rail (roughly 28%). Account and market cards may sit side-by-side at the top of the main canvas; do not make three equal top-level panes.

## Card rules

- Use fixed borders and consume the allocated width.
- Wrap long details inside the card; never let outer composition clip them.
- Use labeled decision fields for operational instructions: `TASK`, `MODE`, `GATE`, `DETAIL`.
- Keep worker state as a fixed aligned table with a separate indented detail row.
- Keep recent activity as `TIME / ACTIVITY / WORKER`; do not wrap preformatted activity strings as prose.
- Preserve governance-critical labels such as `Model training LOCKED`, `Next <task-id>`, and timer names in the header or a compact card.

## Width verification

For outer width `W`, subtract separator cells before allocating weighted columns. If the main/rail weights are 72/28, use the same rounded result for inner card widths. A one-cell mismatch produces visible `…` at the rail boundary. Verify:

```text
rendered rows == requested height
footer row == height - 2
max line length <= requested width
unexpected ellipsis count == 0
```

## Acceptance workflow

1. Run a pure render probe at the target cell dimensions.
2. Relaunch the real Windows Terminal window; an existing VOT process still shows the prior renderer.
3. Inspect a fresh screenshot and ask whether the user accepts the visual direction.
4. Only after visual acceptance run focused layout/controller/hardening and telemetry/provider tests.
5. Report renderer verification separately from visual acceptance; passing tests do not prove the design looks good.
