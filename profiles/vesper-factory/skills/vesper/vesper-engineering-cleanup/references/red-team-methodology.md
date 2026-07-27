# Red-Team Methodology for Quant Systems

Reusable adversarial review template. Use when independently attacking Vesper claims, receipts, or readiness assertions. The red-team reviewer must not inherit conclusions from other workers and must assume every claim is false until proven otherwise.

## Report Structure

Every red-team review must:

1. **Rank findings by severity**: CRITICAL (blockers to any promotion or live-gate claim), HIGH (undermine production readiness or evidence quality), MEDIUM (material issues requiring attention before credibility claims).
2. **Use exact evidence**: path + line range, concrete contradiction, active caller proof. Never "appears to," "seems like," or filename-only claims.
3. **State required proof**: for each finding, specify exactly what evidence would be sufficient to accept a repair or promotion. "Look at it again" is not a proof standard.
4. **Include cross-cutting observations**: patterns that span multiple findings — receipt-to-decision ratios, absence of external review, systemic biases.

## Detection Patterns (What to Look For)

### False-green receipts
- Receipts that claim PASS/PROVEN but trace to no executable artifact
- Test suites that report "all passing" but exclude 42-58 known failures
- Automation registry entries pointing at removed paths
- Dry-run success presented as operational readiness

### Contradictory state
- Boolean fields immediately qualified by contradictory prose (`Execution allowed: true` ... `paper only`)
- Status fields that combine conflicting terms (`APPLIED_REPORT_ONLY`)
- Review aliases with `candidate` status that share parameters with `APPLIED` accepted aliases

### Deadlocked chains
- Sequential receipts all producing the same negative conclusion with no change in approach
- Blocker conditions that reference themselves (e.g. "needs more confirmation windows" after 20 receipts all requesting more windows)
- Receipts dated the same day forming a self-referential loop

### Governance gaps
- Domains registered without lanes (no evidence-producing surface)
- Monthly review targets with zero days of underlying data
- Missing SKILL.md files referenced by governance documents
- 49M-row staged datasets that zero active model paths consume

### Temporal leakage
- Fill reads compared against OHLCV bars that haven't finalized for the same session
- Same-day evidence rules that don't account for after-hours settlement

### Receipt-to-decision ratio
- Count receipts and count substantive decisions (model admission, source switch, promotion, risk change). If receipts >> decisions (e.g. 300:0), the system is optimized for generating PASS receipts, not forward progress.

## Cross-cutting questions every review must answer

1. Has any external third party (separate codebase, different model family, unrelated data source) validated any Vesper claim?
2. Does the active universe contain survivorship bias (only currently-listed tickers, no delisted backfill)?
3. Is the waiting state self-reinforcing — do receipts confirm waiting rather than resolving it?
4. Are performance benchmarks fair (e.g. does the model trail equal-weight by a material margin)?