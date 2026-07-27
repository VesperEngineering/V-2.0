# Canonical Text Hashing and Read-Only Review

Use this reference when a provenance contract intentionally makes tracked text stable across Git checkout newline filters.

## Required provenance model

A canonicalization rule is part of the evidence identity, not an implementation comment. Bind an exact object in both the frozen task contract and run receipt, for example:

```json
{
  "algorithm": "sha256",
  "text_canonicalization": "crlf_to_lf",
  "scope": "tracked_text_content"
}
```

The validator must require exact keys and exact values. The contract's canonical JSON hash and the receipt's self-hash must include the profile. A generated candidate, receipt file, or other untracked artifact remains a raw-byte hash unless its own field explicitly says otherwise.

For the profile above, every path must implement the same byte transform:

```python
hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
```

Audit prepare, finalize, unattended/replay, evaluator binding, input binding, and receipt construction together. A declaration without matching producers is false provenance; matching producers without a declaration are ambiguous provenance.

## Fail-closed tests

1. Hash equivalent LF and CRLF fixtures through every producer/finalizer helper and require one digest.
2. Mutate each profile field, recompute the enclosing receipt hash, and still require semantic validation to fail. This distinguishes profile enforcement from a mere stale-hash failure.
3. Reject missing and extra profile keys.
4. Verify the contract hash changes when the declared profile changes, while the fixed-profile validator rejects that changed contract.
5. Keep candidate/generated artifact tests byte-exact so tracked-text normalization does not silently spread beyond its scope.
6. For restart tests, create one contract once and pass it to both controller instances. Do not call a timestamp-producing contract factory separately before and after restart. Ensure a post-restart state transition presents the same contract hash to durable storage.

## Read-only audit harness

When the user forbids source modifications, freeze repository identity before running tests:

```bash
baseline='<commit>'
git rev-parse HEAD
git rev-parse "$baseline^{commit}"
git status --porcelain=v2 --untracked-files=all
git diff --cached --name-status --
git diff --no-ext-diff --name-status "$baseline" --
git diff --no-ext-diff --check "$baseline" --
git diff --no-ext-diff --binary "$baseline" -- | sha256sum
```

Inspect the exact diff by authorized file. If a code index reports that it belongs to another worktree, treat it as advisory and use direct Git/file reads; do not initialize an index when writes are forbidden.

Prevent verification tools from writing into the repository. Install cleanup before the first fallible verification command so `set -e` cannot strand review scratch after a failed or mistyped test target:

```bash
set -euo pipefail
review_tmp='<approved-external-temp>'
rm -rf "$review_tmp"
mkdir -p "$review_tmp/pytest" "$review_tmp/pycache"
cleanup() { rm -rf "$review_tmp"; }
trap cleanup EXIT

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$review_tmp/pycache"
export TEMP="$review_tmp"
export TMP="$TEMP"
export TMPDIR="$TEMP"
'<exact-python>' -m pytest -q -p no:cacheprovider \
  --basetemp="$review_tmp/pytest" <focused-tests>
'<exact-python>' -m ruff check --no-cache \
  --select '<exact-user-requested-rules>' <authorized-files>
```

For receipt fields shaped as `{path, sha256}`, resolve and hash the path declared by the receipt, while separately asserting any protocol-fixed expected path. A detached hard-coded path plus a receipt-supplied hash is not fail-closed because a path-only receipt mutation remains green.

Do not broaden a user-specified lint selector. Do not stash, format, fix, reset, add, commit, or initialize repository metadata during an independent audit.

After verification, repeat HEAD, staged-state, full-status, authorized-file-set, `diff --check`, and binary-diff SHA-256 checks. Any inspection gap, unexpected path, changed diff identity, or reviewer-caused source modification makes the verdict fail closed. External temp artifacts should be reported separately from repository modifications.
