# SPY Momentum CPU Contract v1

**Status:** FROZEN FOR INTEGRITY VERIFICATION ONLY — selection outcomes have not been computed.
**Scope:** SPY-only, research-only CPU evaluation. No final-holdout access, broker action, model promotion, data mutation, paid provider, GPU, schedule, or risk/configuration change is authorized.

## Bound artifacts
- **Adapter:** `vesper/data/massive/adapters/total_return_ohlcv_adapter_20260717T153500Z.sqlite`
- **Adapter SHA-256:** `825252f94efb228df37683d58a1199cbc101828bbe7f53079e9d066c28e5a70c`
- **Evaluator:** `scripts/spy_momentum_cpu_experiment.py`
- **Evaluator SHA-256:** `cc222e5b7f638f2823dccaf5d8af49bc26c6e022aa84d9363fc5a3169aed3e3a`
- **Machine-readable contract:** `reports/research/spy_momentum_cpu_contract_v1.json`
- **Contract SHA-256:** `87653af97402aa9255a5cc986a667e4d96d09117892d2d00daa6ac1d41da64ca`
- **Slice 3 admission receipt:** `reports/research/spy_momentum_cpu_slice3_data_admission_v1.json`

## Frozen input and provenance
The frozen adapter declares `price_basis=total_return_adjusted`, `timeframe=1day`, and covers exactly 5,737 SPY rows from 2003-09-10 through 2026-06-30. Every selected row is source-mapped. Independent read-only admission found zero overlapping historical OHLCV mismatches across the three earlier local snapshots.

**Known limitation:** V20 contains the frozen derived adapter and row-level source hashes, but not a local raw-to-derived reconstruction of the external build inputs. This contract claims deterministic recomputation from its frozen input, not independent reconstruction of those upstream inputs. Adjusted prices are research-accounting values, not executable market prices.

## Predeclared hypothesis and accounting
At formation after session T closes, use the 20-session adjusted-close return. If strictly positive, hold SPY from the next eligible open through the open five eligible sessions later; otherwise hold cash. Compare against always-long SPY on the same blocks. Charge 10 basis points per traded side.

The primary final metric is the paired arithmetic mean of candidate net return minus baseline net return; its predeclared final threshold is at least +0.0005 per block with a 95% moving-block-bootstrap lower endpoint above zero, positive candidate cumulative net return, seed 42, 10,000 resamples, and block length four. Five- and 25-basis-point cases are diagnostics only.

## Chronological partitions
- **Development:** formation blocks through 2018-12-31; implementation/integrity work only.
- **Selection:** starts 2019-01-10 after a five-session purge and embargo beyond the final development label exit; exactly one predeclared candidate/baseline comparison may occur only after independent contract review.
- **Final:** not represented in this contract. A future sealed snapshot and separate ADMIT_FINAL decision are required.

The six-session formation cadence makes closed feature-to-exit intervals strictly disjoint, as required by the evaluator's fail-closed isolation assertion. Exact formation positions and all provenance bindings are in the companion JSON.
