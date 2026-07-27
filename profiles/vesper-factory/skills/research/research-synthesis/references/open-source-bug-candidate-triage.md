# Low-Contention Open-Source Bug Candidate Triage

Use this when researching a contribution candidate from a repository's open issues and PRs.

## Discovery queries

With `gh`, gather independent views in parallel:

```sh
gh issue list -R OWNER/REPO --state open --limit 100 \
  --json number,title,createdAt,updatedAt,comments,labels,assignees,author,url

gh pr list -R OWNER/REPO --state open --limit 100 \
  --json number,title,createdAt,updatedAt,author,labels,isDraft,reviewDecision,url,body

gh api 'search/issues?q=repo:OWNER/REPO+is:issue+is:open+(crash+OR+assert+OR+incorrect+OR+wrong+OR+bug)+sort:created-desc&per_page=100'
```

For every shortlisted issue, search PR bodies for explicit references:

```sh
gh api 'search/issues?q=repo:OWNER/REPO+is:pr+ISSUE_NUMBER+in:body&per_page=100'
```

Do not infer "unclaimed" from an empty assignee or zero issue comments alone. A contributor may be working in a linked PR or a related issue.

## Candidate filter

Prefer all of the following:

- Reproducer is short and deterministic.
- Failure still occurs on current trunk/latest nightly.
- No assignee, open PR, or recent human claim.
- Fix is localizable to one subsystem.
- Existing test infrastructure can express the regression narrowly.
- Expected behavior is clear: successful compilation, stable diagnostic, or specific correct output.

Deprioritize:

- Design questions and long-term architecture work.
- Failures whose issue discussion or PR is active.
- Reports fixed on trunk but left open.
- Crashes whose apparent one-line guard would only hide malformed internal state.

## Live reproduction

Use the project's normal current build when available. A hosted compiler or playground API is useful when cloning/building is disproportionately expensive. Record the exact version or commit, exit code, and top stack frames/error text.

Compiler Explorer-compatible instances commonly expose:

```text
GET  /api/compilers/<language>
POST /api/compiler/<compiler-id>/compile
```

Send JSON containing `source` and `options`; inspect the response's `code`, `stderr`, and compilation version. Discover the compiler ID first rather than guessing it.

## Source localization

1. Use the current stack to find the assertion or crash site.
2. Follow the invalid value/state backward to the producer.
3. Read any closed PR review. Maintainers often explain why an assertion guard or fallback diagnostic is symptom-only.
4. Report separately:
   - **Root-fix area:** where bad state is produced.
   - **Crash site:** where the invariant finally fails.
   - **Test location:** narrow existing file-test/unit-test family.

A good recommendation uses calibrated language such as "start in" or "likely root-fix area" when the exact patch has not been implemented and tested.

## Reporting template

```markdown
## Best candidate: #NNNN — Title

Why it wins:
- current and reproducible on <version/commit>
- no assignee, active thread, or open PR
- narrow expected behavior and test surface

Reproducer:
```language
...
```

Observed: <exit/status and key failure>
Expected: <normal behavior/diagnostic>

Likely fix location:
- Root: `path/file.cpp`, function/path
- Symptom: `path/assertion.cpp`, function
- Regression test: `path/to/existing/test_family`

Contention check:
- issue comments/assignee status
- linked open PR result
- relevant closed PR review, if any

Rejected alternatives:
- #... fixed on trunk
- #... actively claimed
- #... broader architectural work
```

## Session-derived pitfall

A stale open crash can already be fixed by unrelated refactoring, while a different low-comment issue can have a recent closed PR. Therefore, selection order matters: **check contention, reproduce live, then localize**. Do not spend source-analysis time on a candidate before confirming it still fails.
