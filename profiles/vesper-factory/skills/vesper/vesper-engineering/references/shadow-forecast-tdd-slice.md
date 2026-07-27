# Inert shadow-forecast TDD slice

Use this pattern for a narrow research-only forecast API built on an existing trading strategy.

## Contract shape

- Keep the output in memory; do not add writers, persistence, engine wiring, orders, risk, or promotion paths.
- Use a frozen, slotted record so the schema is closed and immutable.
- Carry symbol, as-of timestamp, fixed horizon, finite standardized score, deterministic rank, loaded model path/hash, and caller-supplied dataset/adjustment/feature SHA-256 identities.
- Hard-code and validate the authority boundary: `research_only=True`, `execution_authority=False`, `authority_state="shadow"`.
- Reject blank/non-64-hex provenance, nonfinite scores, and stale/mismatched daily as-of data.

## Safe factorization sequence

1. Before extraction, add a characterization test that captures the exact existing signal sequence: symbol, action, strength, reason, timestamp, and metadata including rank and predicted return. Run it green against the original method.
2. Add the forecast test and observe RED because the API is absent.
3. Extract only feature computation/model prediction into a private score helper. Keep legacy rebalance timing, score ordering, thresholds, rank metadata, reasons, and signal construction in their original method.
4. Give shadow output its own deterministic tie-break (`score desc`, then `symbol asc`) without changing legacy tie behavior.
5. Compute loaded-model provenance at strategy initialization and propagate it into every record. Caller identities stay explicit keyword inputs.
6. Assert the forecast call creates no files.
7. Rerun the characterization test after extraction; before/after green output is the behavioral-equivalence evidence.

## Strict-TDD recovery

If a general branch was implemented while only a special case was under test (for example, nonconstant standardization while only zero-variance scores were asserted), remove the untested branch, prove the special-case baseline green, add the general-case test and observe RED, then reimplement minimally and observe GREEN. Do not relabel an immediately passing test as RED evidence.

## Provenance-completion slice

When an existing inert forecast needs to become provenance-complete, keep the schema responsibilities explicit:

- Fixed semantics belong to validated record invariants, for example `schema_version`, `expert_id`, `score_units`, and score `direction`. Reject attempts to override them rather than treating them as advisory labels.
- Run-specific identities such as `expert_version`, `feature_version`, and `run_manifest_sha256` remain required keyword-only caller inputs. Do not invent defaults that could make two materially different runs look identical.
- Validate versions as nonblank and every hash identity as full 64-hex SHA-256. Propagate the caller-owned values into every emitted record.
- Preserve the caller's timestamp object and existing V20 timezone convention. Freshness checks may compare dates, but must not silently localize, convert, or replace the emitted as-of timestamp.
- Keep this as two vertical TDD slices: first prove the record contract RED→GREEN, then update every generator call site explicitly, prove the required generator arguments RED, and propagate them minimally to reach GREEN.

## Independent acceptance review

A green focused suite is necessary but does not override the authoritative migration contract. Review the frozen candidate against that contract itself, not only a narrower field list or claims in a handoff packet.

1. **Check semantic schema completeness.** Require every field named by the governing contract. For the V20 forecast contract this includes an explicit target definition, valid-until timestamp, and data-freshness status. Score units or horizon do not silently substitute for a target definition, and an up-front date check does not substitute for carrying freshness/validity evidence in the record.
2. **Treat annotations as documentation, not validation.** Adversarially construct the record and call the producer with non-`datetime` as-of values, booleans where integers are expected, malformed/blank identifiers, and nonfinite scores. Preserve the caller's valid timestamp object, but verify it is a valid timestamp before date comparison and emission; do not parse one representation for comparison and then retain an unvalidated original object.
3. **Separate hash shape from compatibility.** A 64-hex feature or dataset identity is syntactically valid but may still be incompatible. If the contract requires rejection of incompatible feature identity or unknown symbols, the producer needs an explicit frozen expected-identity and approved-universe binding; caller-supplied self-consistent hashes and arbitrary mapping keys are insufficient.
   - Do not mistake extra per-call parameters for an independent authority boundary. A method that accepts `approved_universe`, `expected_feature_identity_sha256`, and `feature_identity_sha256` together can still let one caller self-approve any symbol and any arbitrary hash by supplying a matching set/value in that invocation.
   - Add an adversarial probe that uses an obviously arbitrary symbol and a fresh valid 64-hex value as both expected and actual identity. If output is produced, record the behavior explicitly and return HOLD when the governing contract requires authoritative compatibility rather than caller consistency.
   - The smallest credible repair binds the expected feature identity and universe to a separately established immutable compatibility contract—such as reviewed model/run-manifest metadata or construction-time frozen configuration—and gives generation only the actual data/provenance to check against it.
   - A verifier may exit successfully while characterizing this self-authorization behavior. Reviewer verdict logic must evaluate the printed semantic result; a green process exit is not itself an acceptance verdict.
4. **Probe mutability honestly.** `@dataclass(frozen=True, slots=True)` rejects normal assignment, and `dataclasses.replace()` can revalidate authority changes, but `object.__setattr__` bypasses ordinary frozen-dataclass protection. Do not call that representation adversarially immutable. Either use a stronger tuple-like representation or treat every record as untrusted and revalidate it at future consumer boundaries. Keep the severity proportional while the slice is inert and has no consumer.
5. **Prove old-path parity against the frozen base, not only a copied expectation.** Load `HEAD:vesper/strategy/ml_model.py` in memory under a sibling module namespace, feed base and candidate the same deterministic feature/model fixture, and compare the complete signal payload: symbol, action, strength, reason, timestamp, and metadata. Include rebalance-state behavior.
6. **Probe inertness executably.** Set a sentinel `_last_rebalance`, replace `Signal` construction and disk-open primitives with bombs after model initialization, invoke only the shadow method, and verify no signal, file access/write, order, risk, engine, or persistence path is reached. Snapshot the external probe directory before/after and clean it completely.
7. **Fail closed on contract gaps.** Missing required fields, accepted non-timestamp as-of values, unknown-symbol acceptance, or arbitrary incompatible-identity acceptance are HOLD findings even when deterministic ranking, model-byte hashing, signal parity, and all tests pass.

## Worktree review notes

- A parent-worktree CodeGraph index may warn that it cannot see newly added local symbols. Preserve the pre-edit query as discovery evidence, but use on-disk reads, exact diff, tests, and static checks for post-edit verification unless a local index is explicitly within scope.
- Run pytest with the project interpreter, `PYTHONPATH=.`, `PYTHONDONTWRITEBYTECODE=1`, cache disabled, and a unique native external basetemp. Remove and verify the temp leaf after each gate.
- Stage only the authorized source/test paths. Finish with `git diff --cached --check`, focused and relevant suites, the practical non-Tk suite, security/static scans, staged tree ID, and staged binary-diff SHA-256. Do not commit unless requested.
- Before independent review, run one focused **ad-hoc** verifier from an OS-safe temporary `.py` file whose filename begins `hermes-verify-`. Exercise the changed staged behavior directly, confirm the exact staged path set and absence of unstaged changes, then delete the script and assert it is absent. Report this separately as ad-hoc verification rather than relabeling it as canonical suite evidence.
- Run the verifier only after the final source/test edit and final exact-path staging. If either changes afterward, generate and run a fresh verifier; earlier output is stale evidence even when the behavior is unchanged.
- Prefer one `tempfile.mkstemp(prefix="hermes-verify-", suffix=".py")` create→execute→unlink lifecycle driven by a single orchestrating command. The orchestrator should write the verifier source, run it as a child under the canonical project interpreter, preserve stdout/stderr and exit status, unlink it in `finally`, and assert the path is absent before returning the child status. This makes both fresh execution and cleanup explicit to verification systems; do not substitute a manually chosen persistent temp filename.
- On Windows, forward-slash absolute paths inside generated Python source avoid nested-string `\U` escape hazards. Keep `PYTHONDONTWRITEBYTECODE=1` so the verifier does not add repository cache files.
