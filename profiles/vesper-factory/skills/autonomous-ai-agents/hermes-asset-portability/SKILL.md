---
name: hermes-asset-portability
description: Safely create portable, inactive local snapshots of Hermes skills, plugins, profiles, memory text, and redacted configuration without moving or disrupting the live Hermes runtime.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [hermes, portability, backup, skills, plugins, profiles, redaction]
    related_skills: [hermes-profile-configuration, agent-memory-providers, external-side-effect-safety]
---

# Hermes Asset Portability

Create project-local or machine-local copies of reusable Hermes assets while keeping the active Hermes installation intact, secret-safe, and independently verifiable.

## When to Use

Use when the user asks to:

- put Hermes skills/plugins/memory/profile files beside an active project;
- create a portable Hermes bundle or audit snapshot;
- preserve agent-created assets before cleanup or migration;
- inspect what is project-owned versus installation/runtime state.

Do **not** treat a request for “local copies” as authority to relocate `HERMES_HOME`, deploy project plugins, rewrite runtime profiles, or synchronize canonical/runtime trees.

## Choose the Correct Operation

### Default: inactive snapshot

Use a clearly non-discovery directory such as `project/hermes-local/`. Copy assets there; leave live originals untouched. This is safest and usually matches “keep a local copy.”

### Runtime migration or synchronization

Only use this when the user explicitly wants Hermes discovery/runtime behavior changed. It requires a separate contract, live backup, exact target allowlist, drift handling, rollback, and post-deployment discovery verification.

**Never silently upgrade a snapshot request into a runtime migration.** Canonical project ownership and Hermes runtime discovery are different problems.

## Snapshot Contract

State these assumptions before writing:

1. Copy, do not move.
2. The snapshot is inert and will not be auto-loaded.
3. Active Hermes runtime files remain unchanged.
4. Only named profiles/workspaces are included; unrelated or legacy profiles remain excluded.
5. Secrets and runtime databases are excluded, not merely hidden in the report.

If any assumption conflicts with the request, ask one short decision question before proceeding.

## Include

Typical safe assets:

- shared `skills/` trees;
- plugin **source** and documentation, excluding plugin runtime data;
- selected profile `SOUL.md`, `profile.yaml`, skills, text plans, and text memory files;
- root `SOUL.md`;
- `MEMORY.md` and `USER.md` when the active provider actually uses them;
- redacted `config.yaml` copies;
- filtered/redacted cron definitions for the target project;
- a README explaining that the copy is inactive;
- a machine-readable manifest with source, destination, size, SHA-256, and redaction status.

## Exclude by Default

- `.env`, `auth.json`, OAuth pools, API keys, tokens, passwords, cookies, private keys, credential files;
- SQLite databases and sidecars (`*.db`, `*.sqlite*`, `*-wal`, `*-shm`), including sessions, Kanban, Mnemosyne, and evidence databases;
- sessions, logs, caches, audio/image caches, temporary files, PID/lock files, backups, and process state;
- Hermes source checkout, installers, binaries, virtual environments, package caches, `.git`, and `node_modules`;
- plugin-generated data/checkpoints;
- unrelated and legacy profiles, cron jobs, scripts, and workspaces;
- symlinks, junctions, and reparse points unless a separately reviewed dereference policy exists.

Structured providers such as Mnemosyne are not safely represented by blindly copying a supposed `MEMORY.md`. Use provider-native export under a separate privacy/data-retention decision if structured memory portability is required.

## Safe Build Procedure

1. **Inventory names, counts, and sizes without printing file contents or secret values.** Confirm available disk space.
2. **Define an explicit allowlist** of source roots, profile names, file classes, and target path.
3. **Build in a sibling staging directory.** Refuse to overwrite an existing destination unless a separately verified backup/replacement transaction is approved.
4. **Reject unsafe sources:** traversal, reparse points, sensitive filenames, databases/locks, unsupported binary files, and oversized files.
5. **Redact textual copies.** Cover structured secret keys and recognizable token/private-key formats. Preserve syntax and record every redacted destination.
6. **Filter operational definitions.** Export only target-project cron jobs; do not carry unrelated schedules into the project.
7. **Remove historical/runtime clutter.** Curator backups, plugin databases, generated checkpoints, and legacy helper scripts are not active reusable assets.
8. **Hash every copied file** and write a manifest. Do not hash the manifest into itself; verify the listed set plus the manifest equals the exact target tree.
9. **Run a second secret scanner.** Classify hash/ID/example-placeholder findings explicitly; do not equate scanner noise with a clean result or dismiss unknown findings.
10. **Publish atomically** by renaming the completed staging directory into place.
11. **Verify project health** with the smallest relevant suite and confirm the active runtime was not modified.

## Plugin Safety

Plugins are executable code. A snapshot directory must not be named or configured so Hermes discovers it automatically. Do not set `HERMES_ENABLE_PROJECT_PLUGINS`, install, import, or execute copied plugins merely because they were included. Enabling plugin code is a separate security decision.

## Exact Verification

Before completion, require:

- destination file set equals manifest file set exactly;
- every listed SHA-256 matches;
- zero symlinks/junctions/reparse points;
- zero forbidden filenames or database/runtime suffixes;
- redacted configs still parse;
- second secret scan has zero **unknown** findings;
- only approved profiles and project cron jobs are present;
- active Hermes paths were not written;
- project tests still pass.

Report only: destination, included classes, excluded sensitive classes, file/size totals, hash result, secret result, and test result.

## Pitfalls

- **Moving instead of copying:** breaks active workers and profiles.
- **Using `.hermes/` for an inert archive:** can create accidental discovery or executable project-plugin risk. Prefer `hermes-local/`.
- **Copying the entire Hermes home:** pulls in credentials, private conversations, runtime databases, caches, binaries, and unrelated projects.
- **Calling a subset comparison “synchronized”:** runtime parity requires exact trees, including extra-file detection.
- **Overlay copying:** leaves stale files. Runtime deployment, when explicitly authorized, needs staged replacement and rollback.
- **Overwriting unexplained live drift:** preserve and review it before any replacement.
- **Treating detector entropy hits as credentials or harmless noise without classification:** manifests and IDs are common false positives; unknown hits remain blockers.
- **Verbose failure dumps:** give one short result/blocker/decision; retain detailed evidence in the manifest or a reference file.

## Reference

See `references/safe-local-snapshot.md` for a compact VESPER-style layout, exclusion matrix, and verification receipt shape.
