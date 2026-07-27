# Safe Hermes Asset Snapshot and Legacy-Path Remediation

## Purpose

Use this pattern when VESPER 2.0 needs a local, inspectable copy of Hermes-owned assets without relocating or modifying the active Hermes runtime.

## Snapshot boundary

Create a non-runtime directory such as `v20/hermes-local/`, not an active `.hermes/` installation path.

Include only useful, reviewable assets:

- shared skill trees and plugin source;
- text memory files (`MEMORY.md`, `USER.md`), not provider databases;
- default and V20 profile `SOUL.md` files;
- V20 profile skills and plans;
- redacted configuration;
- V20-only cron definitions;
- a README and exact SHA-256 manifest.

Exclude:

- `.env`, OAuth/auth files, credentials and private keys;
- session, Mnemosyne, Kanban, verification, or plugin databases;
- logs, caches, locks, backups, checkpoints and generated runtime state;
- Hermes application source, virtual environments and package caches;
- legacy V1 profiles and scripts;
- symlinks, junctions and Windows reparse points.

Build in a sibling staging directory, validate all sources before publishing, scan/redact credential patterns, hash every copied file, verify exact manifest/tree equality, then atomically rename staging to the final directory. Active `HERMES_HOME` remains untouched.

## Legacy path remediation

Do not blindly replace every `D:/vesper` string.

1. Inventory all matches and classify them as:
   - active operational code/config;
   - historical reports/receipts;
   - canonical external data references;
   - read-only snapshot content.
2. Patch only active operational paths unless the user explicitly selects literal historical rewriting.
3. Preserve historical evidence verbatim; changing a past observed path falsifies the receipt.
4. Preserve canonical external-data references when the source still genuinely lives there.
5. For active V20 code, prefer a project-relative path rooted in the checkout. Remove external fallbacks rather than silently loading legacy state.
6. Add a regression test that asserts the exact allowed path list.
7. Verify focused tests, syntax, the wider suite, and a bounded final scan that excludes historical/snapshot/data trees.

## Current V20 split-adjustment contract

The active trainer may look only at:

`vesper/data/massive/split_adjustments.json`

Do not restore `D:/vesper/vesper_data/split_adjustments.json` or `../vesper_data/split_adjustments.json` as runtime fallbacks. If the V20-local adjustment artifact is missing, the training path is not admissible; do not continue on raw prices.

## Reporting

Default to three short facts: what was copied/changed, verification result, and any exclusion or blocker. Provide the full manifest or technical rationale only on request.
