# Artifact Commit-Policy Registry

Vesper's CI enforces a commit-policy check on every push via `scripts/validate_artifact_commit_policy.py`. Any file that doesn't match a registered path pattern in `app/services/artifact_schema_registry.py` gets **BLOCKED_UNKNOWN_ARTIFACT_FAMILY** — the commit itself succeeds (git push works), but the GitHub Actions "Local Validation" workflow fails.

## Symptoms

- Git push succeeds (`origin/vesper` advances)
- CI run shows `STATUS: FAIL` in "Validate artifact commit policy" step
- Log lines like: `BLOCKED_UNKNOWN_ARTIFACT_FAMILY` with `blocked_unknown_artifact_family`

## Root Cause

`classify_artifact_path()` in `artifact_schema_registry.py` iterates a tuple of registry entries and matches against `fnmatch` path patterns. No match = blocked.

## Fix: Register the Missing Families

1. **Identify the blocked files** from the CI log — they appear in a table under the "Validate artifact commit policy" step.

2. **Determine the proper entry type:**
   - `_source_entry(artifact_id, path_pattern, file_type)` — for committed source, branding assets, and curated docs (sets `commit_policy=COMMIT_SOURCE`)
   - `_entry(...)` — for generated runtime artifacts (sets `commit_policy=COMMIT_GENERATED`, more fields needed); use when the file should NOT be committed

3. **Add the entry** to the `ARTIFACT_REGISTRY` tuple. For committed source files, add to the `_source_entry` inner tuple near the end of the file (~line 1192):

   ```python
   ("your_artifact_id", "path/to/file.ext", "ext"),
   ```

4. **Verify locally** before pushing:
   ```bash
   # Test specific paths
   python scripts/validate_artifact_commit_policy.py --paths \
     "path/to/blocked/file1" "path/to/blocked/file2"

   # Also verify CI workflow tests still pass
   python -m pytest tests/test_ci_validation_workflow.py -q
   ```

5. **Commit and push** — the "Validate artifact commit policy" step will pass.

## Common Blocked File Types Recently Registered

| Path | Artifact ID | Reason |
|---|---|---|
| `assets/vesper-applied-terminal.ico` | `vesper_applied_terminal_ico` | Branding icon, committed source |
| `assets/vesper-applied-terminal.svg` | `vesper_applied_terminal_svg` | Branding icon, committed source |
| `docs/VESPER_AGENTIC_OPERATING_LOOP.html` | `vesper_agentic_operating_loop_html` | Curated docs report |

## Pitfalls

- The `_source_entry` function signature is `(artifact_id, path_pattern, file_type)` — match the indentation of surrounding entries (8 spaces inside the inner tuple).
- Use unique `artifact_id` strings (lowercase snake_case).
- The `path_pattern` is an `fnmatch` glob — `*` matches across directories only within the pattern string (e.g., `assets/*.ico` matches `assets/foo.ico` but NOT `subdir/assets/foo.ico`).
- After adding the entry, run the full CI-relevant tests; the artifact policy gate might pass while a different CI step (e.g. pytest contracts) fails from a pre-existing condition — check the full run.