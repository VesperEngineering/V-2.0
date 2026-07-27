# Candidate Refreeze Checklist

Use when a report-only observer candidate has intended working-tree repairs but an older staged index.

## Read-only inspection

```bash
git status --short
git diff --name-status
git diff --cached --name-status
git diff -- <each AM path>
git diff --cached -- <each AM path>
```

Review the working-tree version as the intended candidate only after confirming every change preserves the report-only denylist and all artifact/evidence contracts.

## Curate the index

```bash
git add -- <explicit intended source/test paths only>
git diff --cached --check
git diff --name-only
```

Never use `git add -A` on a dirty observer worktree. Explicitly exclude pytest basetemps, lock files, emitted JSON/JSONL receipts, artifacts, caches, and unrelated local changes.

## Freeze evidence

```bash
git diff --name-only
git diff --cached --check
comm -12 <(git diff --cached --name-only | sort) \
          <(git ls-files --others --exclude-standard | sort)
for f in $(git diff --cached --name-only); do
  git diff --quiet -- "$f" || printf 'MISMATCH %s\n' "$f"
done
git status --short
```

Require: no tracked unstaged candidate changes, no staged/untracked intersection, no staged whitespace errors, and no `AM` paths.

## Verification discipline

1. Write and observe the focused regression test fail before implementation.
2. Run focused observer/evidence tests after final staging, using a new basetemp outside the worktree.
3. Run the broader observer + read-only UI projection suite, then lint, compile, and a final `git diff --cached --check`.
4. Do not commit, integrate, launch, schedule, or self-approve the candidate. Passing checks only freeze it for independent review.
