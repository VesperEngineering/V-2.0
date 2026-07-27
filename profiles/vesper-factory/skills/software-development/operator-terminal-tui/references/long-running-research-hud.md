# Long-running research HUD: operator visibility without fiction

Use this reference when an operator watches a long-running experiment in a terminal.

## Operating rule

The agent runs and monitors the experiment. The operator should only need to keep the HUD open and observe. Do not make the operator launch individual tests.

## Minimum display

Keep the display boring, compact, and factual:

```text
STATUS / script / phase / elapsed
GPU or other meaningful resource telemetry
NN  [input] -> [hidden] -> [latent] -> [predicted]
evidence bars with measured deltas and explicit PASS / REJECTED
last 5-10 real stdout lines
```

A small model/data-flow line is useful; elaborate card dashboards are not. Do not display invented semantic labels or pretend a descriptive representation is predictive.

## Phase reporting

Never let `epoch N/N` be the last visible output. Emit named stage markers before and after expensive post-training work:

- `training complete`
- `encoding embeddings/windows`
- `aggregating / fitting downstream analysis`
- `computing statistics`
- `writing results`
- `done`

State explicitly that the epoch loop only finishes optimization. Encoding, evaluation, Newey-West/bootstrap work, clustering, serialization, and cleanup may take substantial time afterward.

## Renderer pitfalls

- Do not implement refresh with `cls`, `clear`, or repeated scrolling output: it visibly flashes and can make the screen look broken.
- Keep the content below the terminal viewport height; a supposedly in-place redraw will scroll/jump if it overflows.
- Prefer a stable live renderer / alternate screen, but verify the actual visible window after launch.
- Place the most important model line near the top, not after telemetry or long evidence sections.
- On a renderer change, kill the old HUD process and relaunch a clearly identifiable current instance; stale windows otherwise cause misleading operator feedback.

## Evidence discipline

Persist a protocol, structured result artifact, and verdict for every run. A healthy latent space or good latent-persistence result is architectural evidence only. It must not be displayed as alpha, risk forecasting, a regime claim, or promotion readiness without independent downstream validation.
