# Isolated neural-representation research sandbox

Use when exploring JEPA/self-supervised market representations beside a production trading system.

## Isolation contract
- Separate directory, virtual environment, copied data, result artifacts, and monitor from the production system.
- Never connect an exploratory encoder, checkpoint, score, or regime label to broker, factors, scheduler, or production weights without a separately reviewed promotion gate.

## Continuous compute without research fishing
- Keep GPU busy with predeclared seed replications or an ablation matrix; do not use slow cron cadence to pace a known batch.
- Separate this from hypothesis generation: do not automatically invent tests, tune after observing a holdout, or rerun variants until one wins.
- Record every matrix row and fixed seed before running; save JSON results and a written verdict for positive, negative, and invalid measurements.

## Observability
- Use unbuffered Python and print explicit phases after final epoch: embedding extraction, aggregation, probe fitting, evaluation/statistics, artifact write, done.
- A compact terminal monitor should show active script/configuration, GPU telemetry, a small model topology line, queued matrix rows, result bars, and only factual status.
- Avoid flashing `cls` redraw loops. Use a stable terminal renderer and verify the actual launcher path.

## Latent interpretation safeguards
- A numbered latent coordinate is not a durable semantic feature: equivalent neural representations can rotate or flip sign across seeds.
- Test coordinate claims with multi-seed replication. Prefer a full-subspace probe or explicitly aligned basis.
- Separate rank/ordering evidence from calibrated level forecasts. Stable correlation with severely negative OOS R² is descriptive state structure, not an actionable forecast.
