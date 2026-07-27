# Safe Local Snapshot Pattern

Use this pattern when a project wants nearby Hermes assets without changing live discovery or execution.

## Layout

```text
project/
  hermes-local/
    README.md
    manifest.json
    shared/
      skills/
      plugins/
      scripts/                 # target-project helpers only
      memory/
        MEMORY.md
        USER.md
      config.redacted.yaml
      cron/
        project-jobs.redacted.json
    profiles/
      <approved-profile>/
        SOUL.md
        profile.yaml
        config.redacted.yaml
        skills/
        memory/
        plans/
```

Do not use `.hermes/plugins` for an inert archive. That name participates in project-plugin trust/discovery semantics on supported configurations.

## Exclusion Matrix

| Class | Snapshot action | Reason |
|---|---|---|
| Skills and references | Copy after path/secret/reparse checks | Reusable knowledge |
| Plugin source/docs | Copy; exclude runtime data and VCS/package caches | Executable but useful for review |
| `SOUL.md`, `profile.yaml` | Copy selected profiles only | Portable identity/routing metadata |
| `MEMORY.md`, `USER.md` | Copy text only | Human-readable memory |
| Mnemosyne/session/Kanban DB | Exclude | Structured private/runtime state |
| `config.yaml` | Copy redacted and parse-check | Useful settings without credentials |
| Cron definitions | Filter to target project and redact | Avoid importing unrelated authority |
| `.env`, auth, keys, cookies | Exclude | Credentials |
| Logs, sessions, caches, backups | Exclude | Private/runtime clutter |
| Legacy profiles/scripts | Exclude unless explicitly requested | Prevent cross-project governance |
| Hermes source/venv/binaries | Exclude | Installation, not project assets |

## Manifest Receipt

Record at minimum:

```json
{
  "schema_version": 1,
  "created_at_utc": "...",
  "source_root": "...",
  "target": "...",
  "active_runtime_modified": false,
  "profiles_included": ["..."],
  "excluded_categories": ["credentials", "databases", "sessions"],
  "redacted_files": ["..."],
  "files": [
    {
      "path": "shared/skills/example/SKILL.md",
      "source": "...",
      "bytes": 123,
      "sha256": "...",
      "redacted": false
    }
  ]
}
```

The manifest does not list its own digest. Verification compares `manifest.files + manifest.json` with the exact destination tree and recomputes every listed hash.

## Secret-Scan Classification

A second scanner may flag:

- SHA-256 entries in `manifest.json`;
- hashes in bundled-skill manifests or lock metadata;
- cron/task IDs;
- documentation containing words such as “secret” or placeholder API-key examples.

Classify these by file, line, and detector type without printing candidate values. Any finding not mechanically attributable to a redaction marker, documented placeholder, identifier, or checksum remains a blocker.

## Minimal Completion Report

- **Location:** destination path
- **Copied:** asset classes and approved profiles
- **Excluded:** credentials, databases, sessions, caches, legacy assets
- **Verification:** file count/size, zero hash errors, zero unknown secret findings, test result
