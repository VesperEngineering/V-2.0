# Hermes Asset Portability Audit Reference

Use this reference for read-only reviews of project-canonical Hermes skills and profile identities synchronized into one or more runtime profile homes.

## Threat and correctness model

Treat all manifest strings, live runtime trees, and backup metadata as untrusted inputs to a copy boundary. The safe contract is:

- only declared canonical assets and declared runtime targets are reachable;
- every managed tree has exact file-and-byte parity;
- unrelated sibling skills remain untouched;
- credentials, runtime state, caches, links, and executable plugins are excluded unless separately reviewed;
- all sources and targets validate before any write;
- backup and receipt evidence is independently reproducible;
- role identity is semantically correct, not merely hash-equal.

## Windows path mutation matrix

Probe the actual validator—not a reimplementation—and resolve the resulting path under both source and destination roots.

| Input class | Examples | Required result |
|---|---|---|
| POSIX traversal | `../outside`, `a/../../outside` | reject |
| Native traversal | `..\\outside`, `a\\..\\..\\outside` | reject |
| POSIX absolute | `/outside` | reject |
| Drive absolute | `C:\\outside`, `C:/outside` | reject |
| Drive relative | `C:outside` | reject |
| UNC/device | `\\\\server\\share`, `\\\\?\\C:\\outside` | reject |
| Empty/current dir | ``, `.`, `./` | reject |
| Valid relative | `software-development/example` | accept and remain beneath root |

Validation should normalize separators, reject anchors/drives and `.`/`..` components, resolve against the intended root, and then assert containment. Apply the same rule to skill paths, named profile targets, and portable profile identities.

## Exact parity

For each managed source/target pair compute maps of `relative/path -> SHA-256` and report separately:

- missing files;
- changed files;
- extra files.

A check equivalent to `all(actual[name] == expected[name] for name in expected)` is only subset equality. It must not emit “synchronized” when extras exist. “Do not delete unrelated skills” does not justify stale files inside a managed skill directory.

## Preflight and transaction boundary

Before the first copy, require:

1. manifest schema and exact key/type validation;
2. all paths contained by their roots;
3. every skill has a regular, non-link `SKILL.md`;
4. every declared profile has a regular, non-link `SOUL.md`;
5. each named target is declared or explicitly excepted;
6. no source or destination link/junction escape;
7. secret/runtime-state scan passes;
8. destination collisions and duplicate semantic paths are rejected.

Only then perform deployment/import. If atomic multi-tree replacement is unavailable, document rollback and ensure late validation cannot produce a partial update.

## Secret and link boundary

Directory allowlisting alone does not prove that credentials are excluded. Inspect names and content for `.env`, auth/OAuth stores, API keys/tokens, private keys, sessions, memory databases, caches, logs, and unredacted provider configuration. Reject symlink and Windows reparse-point inputs unless the contract explicitly handles and confines them. Never print discovered secret values—report path, line, and pattern class only.

## Backup verification

Without extracting into the audited repository:

1. verify archive SHA-256 against the receipt;
2. enumerate members and compare with the managed allowlist;
3. parse the embedded manifest;
4. map manifest source paths to archive member names explicitly;
5. recompute every member hash;
6. require one-to-one manifest/member coverage;
7. scan archived bytes for credential patterns;
8. report unexpected members separately.

## Concurrent drift

Freeze project-source hashes before static inspection and repeat them at the end. Independently compare current runtime trees immediately before verdict. If runtime changes during review:

- keep implementation findings bound to unchanged project bytes;
- report runtime delta as current operational state;
- do not repeat a historical receipt’s “synchronized” claim as present truth;
- state whether the no-change proof covers the full session or only a measured window.

## Profile-role semantics

For every portable profile, compare profile name, intended lane/manifest role, and `SOUL.md` behavior. Flag duplicate generic identities under distinct role names, contradictory authority, wrong workspace boundaries, or a role that can review/approve its own work. Preserve the distinction between a faithful migration and a correct configuration: migration can faithfully preserve a pre-existing role defect.

## Minimum regression tests

- `test_manifest_rejects_windows_backslash_traversal`
- `test_manifest_rejects_drive_absolute_and_drive_relative_paths`
- `test_manifest_rejects_undeclared_profile_target`
- `test_check_reports_extra_file_inside_managed_skill`
- `test_check_requires_skill_md_not_merely_nonempty_directory`
- `test_deploy_preflights_all_sources_before_first_copy`
- `test_import_rejects_secret_shaped_or_runtime_state_files`
- `test_import_rejects_symlink_or_reparse_escape`
- `test_plugin_enablement_remains_explicit_and_separate`

Under a strict no-modification review, inspect these tests and use in-memory/static probes only; do not run test frameworks that create caches or temporary artifacts.