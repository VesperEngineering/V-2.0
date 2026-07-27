# Relocating Windows desktop tool sources without breaking shortcuts or services

## Use when

The Windows Desktop contains source trees, build outputs, backup scripts, or nested repositories and the user wants the Desktop to contain launch shortcuts only. This also applies when a shortcut or Windows service still points into a Desktop-hosted implementation folder.

## Desired boundary

Treat the Desktop as a presentation surface:

- keep only `.lnk` launchers the user wants;
- relocate source, build outputs, and backups under a stable project/local-tool root;
- keep local-only tool containers out of the parent repository with `.git/info/exclude` rather than committing nested repositories accidentally;
- preserve each tool's own `.git` directory, branch, dirty state, untracked outputs, and installed/runtime state.

A useful layout is:

```text
<project>/.local/desktop-tools/
├── <tool-a>/
├── <tool-b>/
└── <monitor>/
    ├── monitor.py
    └── backups/
```

The exact root is user/project-specific. The durable rule is source off Desktop, shortcuts on Desktop, and local nested repositories excluded from the parent worktree.

## Pre-move inventory

1. Enumerate only candidate Desktop entries; do not infer ownership from broad file extensions alone.
2. Read every relevant `.lnk` through `WScript.Shell.CreateShortcut` and record:
   - `TargetPath`;
   - `Arguments`;
   - `WorkingDirectory`;
   - `IconLocation`;
   - description when present.
3. For each source tree, record file count/bytes, nested Git branch/status/remotes, and whether the shortcut targets the source tree or a separately installed executable.
4. Inspect active processes and `Win32_Service` paths for references to the old root. A background service can lock only a small release subtree while the rest of the move succeeds.
5. Check destination capacity and collisions before copying.
6. Search tracked source for hard-coded absolute Desktop paths.

## Cross-volume move

For large Windows trees, use a bounded/resumable copy such as:

```text
robocopy <source> <destination> /E /MOVE /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XJ /SL /NP
```

Important: **do not trust the robocopy exit code alone.** Codes `0–7` are usually nonfatal, and a run can still report access-denied deletion errors while returning a success-like code. Always verify:

- destination exists with expected file count/bytes;
- source root is absent or enumerate exactly what remains;
- remaining source files byte-match destination copies (SHA-256 for locked remainders);
- nested Git status before/after is identical.

Move small monitor sources/backups into a dedicated folder only after destination creation. Do not delete, reset, rebuild, or clean dirty repositories as part of relocation.

## Shortcut migration

Rewrite shortcuts only after their destination artifacts exist. Preserve the complete launcher contract, not just the visible target:

- executable target;
- quoted script arguments;
- working directory;
- icon location;
- description.

Read the shortcut back through COM and assert every path exists. For script-backed apps, validate both the interpreter target and the script path embedded in arguments. Launch the actual `.lnk` once and confirm the process command line uses the relocated source.

## Windows service migration

A running service can leave loaded binaries locked at the old location. Handle this as a privileged migration, never as a force-delete problem.

### Before elevation

1. Copy the complete service release to the destination.
2. SHA-256 compare every locked source file with its destination counterpart.
3. Record service name, state, start mode, process ID, and original `PathName`.
4. Keep the old files until the relocated service is verified running.

### Fail-closed elevated sequence

1. Stop the service and wait for `Stopped`.
2. Change `Win32_Service.PathName` using `Invoke-CimMethod ... Change` (more reliable than fragile `sc.exe config` quoting wrappers).
3. Start the service and wait for `Running`.
4. Re-read `Win32_Service`; require the expected new path, preserved start mode, and live PID.
5. Only then remove the old Desktop remainder.
6. Write a machine-readable receipt containing service, state, start mode, PID, new path, old-path removal, and timestamp.

The migration script must log to disk because output from a UAC-elevated `Start-Process -Verb RunAs` child may not return to the parent terminal.

### Rollback requirements

Rollback must cover failures **before and after** path mutation:

- if the path changed, stop any partial instance and restore the original path;
- whether or not the path changed, restart the original service if the migration left it stopped;
- never remove old files until the new service is verified;
- emit a failure receipt with migration error, rollback status, and rollback error.

A rollback that only runs when `changedPath=True` is insufficient: a config/change failure can occur after the service was stopped but before the path changed.

## Final verification

Require all of the following:

- relevant Desktop entries are shortcuts only;
- every shortcut target, argument source, working directory, and icon exists;
- actual shortcut-launched monitor/app runs from the new path;
- service is `Running`, its start mode is preserved, and `PathName` points to the destination;
- old Desktop source folders are absent;
- nested repository branch/dirty/untracked state matches the pre-move inventory;
- the parent repository ignores the local-tool container and shows no new nested-repo noise;
- focused repository/launcher smoke tests still pass.

## Common failures

- **Move only the visible script:** backups and source repositories remain on Desktop. Inventory all tool-owned entries first.
- **Put nested repositories under a tracked project directory:** the parent worktree becomes polluted. Use a local container plus `.git/info/exclude`.
- **Assume a copied service tree means relocation is complete:** service registration may still point to Desktop.
- **Trust robocopy rc without inspecting source remnants:** locked binaries can remain despite a success-like return code.
- **Use global kill/delete for locked service files:** migrate the service path with elevation and a rollback receipt.
- **Elevated script returns no diagnostic:** write explicit log and JSON receipt inside the elevated child.
- **Failure leaves service stopped:** rollback/recovery must restart the original service even when path mutation never succeeded.
