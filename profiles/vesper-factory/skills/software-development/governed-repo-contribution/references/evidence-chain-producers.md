# Evidence-Chain Producer Pattern

Use this pattern when a governed pipeline reports a missing data or candidate receipt.

## Diagnostic sequence

1. Read the consumer, not just the log: enumerate accepted filenames, `STATUS` values, required fields, date semantics, and the first-failure behavior.
2. Trace each accepted receipt backward to the producer and its authoritative source artifact.
3. Check whether the scheduled pipeline actually invokes the producer. A validator can be complete while the pipeline still omits the producer stage.
4. Add the producer at the earliest safe point where its inputs are complete: data receipt immediately after ingest; candidate receipt after scores/basket/model outputs.
5. Run the producer with the exact scheduled interpreter and rerun the downstream no-submit consumer.

## Vesper implementation pattern

- Data producer: `scripts/generate_operator_data_check.py`
  - Reads the Massive OHLCV SQLite database and universe file.
  - Writes `artifacts/evals/operator_data_check_<YYYYMMDD>_post_ingest.md`.
  - PASS requires current admitted data and coverage; no hand-written receipt.
- Candidate producer: `scripts/generate_candidate_evidence.py`
  - Runs the canonical report-only model path.
  - Writes `artifacts/evals/daily_no_order_report_<YYYYMMDD>_post_close.md`.
  - The outer evidence envelope can be PASS when candidate/data/model evidence is valid, while the report's internal `Operator decision` remains `hold for review` or another governed decision.

## Authority distinction

Do not conflate:

- receipt exists;
- receipt is evidence-valid (`STATUS: PASS`);
- pretrade is ready;
- execution is authorized;
- an order was actually submitted.

A candidate receipt with five real rows is not an order approval. The no-submit loop must still run independent pretrade and board gates. In the verified Vesper repair, data and candidate receipts passed while `activation_packet_validation` and `alpaca_margin_observation_validation` kept pretrade fail-closed.

## Verification contract

Minimum proof before reporting completion:

```text
python -m py_compile <new producers> <pipeline>
python <pipeline> --dry-run
pytest <producer/scheduler/evidence-loop focused tests>
<scheduled-venv-python> <data producer>
<scheduled-venv-python> <candidate producer>
<scheduled-venv-python> scripts/run_daily_paper_evidence_loop.py ... --no-submit
```

Report the first remaining blocked gate and confirm `orders submitted: 0` when running preview mode.
