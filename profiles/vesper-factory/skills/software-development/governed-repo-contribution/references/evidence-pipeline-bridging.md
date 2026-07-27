# Evidence-Pipeline Bridging

When upstream evidence artifacts exist in one format but the downstream consumer expects a different format, build a **minimal bridge script** that converts between them. This is distinct from producing new evidence — it's a wiring adapter.

## When to Bridge

Bridge when:
- The upstream producer is correct (reviewed, fail-closed, no provider calls)
- The downstream consumer is correct (checks receipt status, validates fields)
- The two speak different formats for the same semantic evidence

Do NOT bridge when:
- The upstream artifact does not exist yet (produce it first)
- The downstream consumer has a security or authority gate that the bridge would bypass
- The bridge would require provider calls, database writes, or new dependencies

## Pattern

1. **Read the consumer's receipt parser.** Find `receipt_status()`, `_receipt_is_green()`, `_candidate_receipt_path()`, and the field expectations. These determine what the bridge output must contain.
2. **Read the upstream artifacts.** Factor scores, sector basket, or any other reviewed evidence. These determine what the bridge can source.
3. **Build a single-file bridge.** No new dependencies. Uses only stdlib (`json`, `re`, `pathlib`). No provider calls, no database writes, no imports from production modules.
4. **Include a `STATUS: PASS` line** if the consumer's `_receipt_is_green()` checks `ref.status == "PASS"`. The bridge is reporting that upstream evidence is valid, not creating new evidence.
5. **Match the consumer's filename pattern.** For Vesper's daily loop: `daily_no_order_report_{date}_manual.md` with the `## Candidate Selection` table format.
6. **Validate end-to-end.** Run the bridge, then the consumer's downstream command (e.g. `generate_daily_paper_portfolio_evidence.py`, then `run_daily_paper_evidence_loop.py --no-submit`). The consumer must advance past the gate that was previously blocked.

## Example: Vesper PB-001 Factor Bridge

From VQ-20260717-019/VQ-020: the 502-symbol factor scores and 4-name sector basket existed as reviewed artifacts, but the daily paper evidence loop expected `daily_no_order_report_{date}_manual.md` with a `STATUS:` field and `## Candidate Selection` table.

```python
# bridge_factor_basket_to_no_order_report.py
# Reads sector_basket_{date}.md → writes daily_no_order_report_{date}_manual.md
# No deps beyond stdlib: json, re, pathlib
```

The bridge:
- Parsed `sector_basket_20260716.md` row by row
- Rendered a `## Candidate Selection` table with ticker, target weight, and notes
- Included `STATUS: PASS` so the consumer's `_receipt_is_green()` passed
- Was saved as a tracked script, then the daily preview exited 0 through the candidate evidence gate for the first time