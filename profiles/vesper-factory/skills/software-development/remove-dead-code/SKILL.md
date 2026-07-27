---
name: remove-dead-code
description: "Excise dead or superseded code the user has already identified — methods, state, bindings, tabs, UI scaffolding replaced by a newer implementation. Direct-edit cleanup with bottom-up cuts, dangling-reference checks, and ruff + import verification. NOT for identifying dead code (use codebase-architecture-audit) or reviewing a recent diff (use simplify-code)."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [cleanup, dead-code, refactor, removal, excise, superseded]
    related_skills: [codebase-architecture-audit, simplify-code, requesting-code-review]
---

# Remove Dead Code — Directed Excision

Trigger when the user gives a direct instruction of the form
"Remove dead `<X>` code from `<file A>` and `<file B>`. These
`<things>` were superseded by `<newer implementation>`." The user has
already decided what is dead and named the replacement — your job is to
cut safely, not to re-audit.

## Scope boundary — when NOT to use this skill

- **Identifying** dead code (the user asks "is there any dead code?",
  "find dead files", "find what's unused", or "audit the repo for files that
  don't work / aren't needed") → use `codebase-architecture-audit` (its
  `references/dead-file-audit.md`). That skill is read-only and covers caller
  tracing, duplicate detection, and severity rating. This skill assumes
  identification is already done. **Even when the same message also says
  "...and then we can decide about removing," do NOT start cutting — the
  read-only identification pass and the user's review decision come first.
  Cutting is a separate, later, explicitly-approved step.**
- **Reviewing a recent diff** ("simplify my changes") → use `simplify-code`.
  That is parallel 3-agent review of *recent* changes, not directed
  removal of known-dead code.
- **You're unsure whether something is dead** → stop and audit first. Do
  not cut on a guess. Cutting live code because it *looked* dead is the
  classic failure mode.

## PITFALL — Vet audit/sub-agent orphan lists before cutting ANY of them

When a dead-code *identification* comes back as a bulk candidate list
(from `codebase-architecture-audit`, a sub-agent, or an orphan-scan
script), treat every entry as UNVERIFIED until you grep it yourself.
Automated orphan scans have two systematic blind spots:

1. **Incomplete reference corpora.** A scan that greps "which files
   reference X" only searches the directories it was pointed at. In one
   session a scanner flagged a brand-new installer script as a
   zero-reference orphan because its doc corpus didn't include the
   `docs/` contract file that named it — the file was live and freshly
   committed. Spot-check any surprising entry (especially recently-added
   files) with your own grep across the FULL repo before believing it.
2. **Entry-point blindness.** Scripts meant to be run directly (by a
   human, a scheduled task, or a shortcut) often have zero in-repo code
   references *by design* — nothing imports them. "No code references"
   ≠ dead; it can mean "this is a leaf entry point." Cross-check
   scheduled-task XML, `.bat`/`.ps1` launchers, `.lnk` installers, and
   cron registries before classing a script as orphaned.

Rule: never bulk-delete from a generated list. Triage into
delete / archive / keep per family, confirm the high-confidence cluster
with your own grep, and prefer `git mv` into an `archived/` area over
hard deletion when reproducibility of past evidence could matter.

## Process

### Phase 1 — Inventory before cutting

1. **Read every target file fully** with `read_file` (use `offset`/`limit`
   pagination for files >~500 lines — the snapshot tool truncates above ~8K
   chars and you will miss methods at the bottom). You cannot cut safely
   from a partial view.
2. **Build an explicit keep/remove inventory.** List, in your reply to
   the user, every dead method name, every dead state variable, every dead
   binding, every dead UI element — AND everything the user said to keep.
   Naming the scope out loud lets the user catch a misread before you cut.
3. **Verify the replacement exists and covers the surface.** Open the
   named replacement module (`grep -n "^def " replacement_module.py` is
   the fast check). If the replacement is missing or doesn't cover a
   method you're about to delete, stop and report — don't cut into a gap.
4. **Map cross-references.** For each symbol you're removing,
   `grep -n "symbol_name" file.py` (and the wider repo if needed). Note
   which remaining call sites need retargeting to the replacement vs.
   which simply disappear with the dead code.

### Phase 2 — Cut in dependency order, bottom-up

1. **Remove leaves first** — methods called by nothing else you're
   keeping. Then their callers. Then state variables / bindings that
   only the removed methods used. This ordering means an intermediate
   `ruff check` will surface dangling references early, while the cut is
   still small enough to reason about.
2. **Retarget surviving call sites** to the replacement. A call site
   inside kept code that referenced a removed method must be rewired to
   the replacement (or to a different kept method) in the same edit pass
   — don't leave it for "later," it will break import or runtime.
3. **Re-check for dangling references after every cut:**
   `grep -n "removed_symbol_name" file.py` — exit code 1 (no matches)
   means clean. Do this after each method group, not just at the end.

### Phase 3 — Verify

1. `ruff check <files>` — catches F821 undefined-name from missed imports
   or a call site you forgot to retarget.
2. `python -c "from module import Class; print('OK')"` — catches
   import-time failures that ruff's static analysis misses (e.g. a
   module-level side effect that referenced a removed symbol).
3. If the project has targeted tests for the touched module, run them —
   not the full suite.
4. Report the before/after line counts and the verification output. The
   user asked for removal; a line-count delta is the receipt.

## PITFALL — `patch` tool corrupts large multi-method deletions

The `patch` tool uses **fuzzy matching**, not exact matching. When
`old_string` spans many methods (hundreds of lines) and `new_string` is
much shorter, the fuzzy matcher can match only a **partial** span — e.g.
just the first `def foo` signature line — and replace only that, leaving
the orphaned method body behind. The file is silently corrupted: you end
up with `def close` followed by the body of `_fetch_kanban_assignees`,
and a *second* real `def close` further down.

### Symptom
After a big `patch` replace, `grep -n "^    def "` shows a method whose
docstring/body belongs to a *different* method, or two definitions of
the same method name.

### Fix — use `sed` line-range deletion for bulk method removal
When you need to delete a contiguous block of whole methods whose
start/end line numbers you've already confirmed with
`grep -n "^    def "`, prefer `sed` over `patch`:

```bash
# Delete lines START through END-1 (END is the next method to KEEP)
sed -i '1192,1530d' app/foo.py
```

Then immediately re-grep to confirm the structure is clean:

```bash
grep -n "^    def close\|^    def _show_tab\|^def main" app/foo.py
```

### Rule of thumb
- **Small, unique edits** (a few lines, with unique surrounding context)
  → use `patch`. Its fuzzy matching handles minor whitespace drift well.
- **Bulk deletion of many consecutive methods** (dozens/hundreds of
  lines) → use `sed -i 'START,ENDd'` after confirming line numbers with
  `grep`. Patch the *boundaries* (the line before the cut, the line
  after) if needed, but don't ask `patch` to swallow the whole interior.

## PITFALL — Don't leave backward-compat shims when asked to remove

When the task says "remove X, it was superseded by Y," do NOT leave a
shim like:

```python
def _fetch_kanban_tasks(self):
    """Deprecated: use fetch_tasks instead."""
    from app.vot_kanban_data import fetch_tasks
    return fetch_tasks()
```

This is not removal — it's a rename that keeps the dead name alive.
Delete the method entirely and update the call site to use the
replacement directly. Shims accumulate; the user asked for removal, not
indirection. If you genuinely think a shim is needed, ask the user
before adding it — don't decide unilaterally.

## PITFALL — Concurrent sibling-subagent edits can drop imports

When a sibling subagent edits the same file mid-session (the `patch`
tool warns: "modified by sibling subagent ... after this agent's last
read"), an import line can silently disappear. `ruff check` catches the
resulting F821 "undefined name" — treat any F821 that names a symbol you
did NOT touch as a signal to re-read the file and restore the dropped
import. Do not "fix" it by removing the call site — the call site is
legitimate; the import is what got lost. This is a concurrent-edit
artifact, not a dead-code finding.

## PITFALL — Removing a UI tab requires rewiring its entry points

When the dead code includes a tab in a tabbed UI (e.g. a "KANBAN" tab in
a focus panel, replaced by an integrated full-window view), removing
the tab entry from the tabs dict is necessary but not sufficient. Also
find and rewire:

- The `if tab == "kanban":` branch in the tab-switch dispatcher.
- Any keyboard bindings that targeted the removed tab's actions.
- Any rail/sidebar click handlers that called `_show_tab("kanban")` —
  retarget them to open the integrated view (`_open_kanban` +
  `_select_in_view`) instead.
- Any entry bar / input field whose `<Return>` handler lived in the
  removed tab's workflow.

A removed tab with a live dispatcher branch raises `KeyError` or calls a
deleted method at runtime even though ruff passes.

## PITFALL — Cutting a method that a kept handler calls

The hardest bug to spot: a *kept* click handler (e.g. a rail card
click) internally calls a *removed* method (e.g. `_show_tab("kanban")`).
The kept handler survives the cut, so ruff sees no undefined name — but
at runtime the click crashes. Always grep each kept handler's body for
calls into the removed set and retarget them in the same pass. The
inventory in Phase 1 is what makes this catchable: if you listed the
handler as "keep" and the method it calls as "remove," the mismatch is
visible before you cut.

## Verification checklist (before declaring done)

- [ ] `ruff check` clean on every touched file
- [ ] `python -c "from module import Class; print('OK')"` prints `OK`
- [ ] `grep -n "removed_symbol_name" file.py` returns no matches for
      every removed symbol
- [ ] Every kept handler that used to call a removed method now calls
      the replacement (or an equivalent kept method)
- [ ] Before/after line counts reported
- [ ] No backward-compat shims left behind unless the user asked for them

## Related

- `codebase-architecture-audit` — run FIRST when the user is unsure what
  is dead. This skill assumes that audit is done.
- `simplify-code` — parallel 3-agent review of a *recent diff*. Use that
  for "clean up what I just wrote," not for directed removal of legacy
  dead code.
- `requesting-code-review` — pre-commit security/quality gate. Run after
  a removal if the dead code touched security-sensitive paths.
- `references/dead-code-removal-vot-20260718.md` — session record of the
  VOT Kanban excision that produced this skill: 12 methods, 6 bindings,
  2 state vars, a focus-panel tab, and an entry bar removed across two
  files (1600 → 1220 lines), with the `patch`-corruption and `sed`
  recovery detailed.
