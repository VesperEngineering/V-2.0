# Open Second Brain (O2B) pilot on Hermes / Windows

## Fit

O2B is a Markdown/Obsidian-native **external memory provider**, not merely an Obsidian MCP connector. It stores agent-owned memory in `<vault>/Brain/` and a rebuildable local search index in `<vault>/.open-second-brain/`. Hermes uses its native provider; do not add a user-facing `hermes mcp` server merely to enable the Hermes integration.

Because Hermes selects one external provider per profile, trial O2B in a separate profile rather than replacing a production Mnemosyne profile. Keep the existing profile/provider untouched; configure `memory.provider: open-second-brain` only in the pilot profile.

## Isolation controls

- Initialize a dedicated, empty vault when existing-vault content must not be touched.
- O2B creates only `Brain/` and `.open-second-brain/` in that vault at setup.
- Before running `o2b init`, back up or record the existing global O2B config path. Initialization may persist the disposable vault as the global default even when `--vault` and a process-level `VAULT_DIR` override are supplied. Restore the production vault path immediately afterward and verify the production profile resolves it. Keep installation-secret and credential fields redacted.
- For every pilot/benchmark process, pass the disposable vault binding explicitly; do not depend on the global default.
- Do not use `--clone-all` from a populated memory profile to create an allegedly empty benchmark profile. Clone config only, install/copy only O2B's integration into the disposable profile, and verify the target vault has no learned content before seeding.
- Do not add `notes.read_paths` to `Brain/_brain.yaml`; absent configuration means no operator-authored folders are opted into scanning.
- Do not run optional `brain scan-inline` or marker-writeback features against an existing vault unless source-note annotation is explicitly approved.
- Confirm post-setup that the selected vault has only the expected O2B scaffold before adding benchmark data.
## Windows pilot sequence

1. Create a dedicated Hermes profile cloned from the working profile, then set its provider to `open-second-brain`.
2. Install and enable O2B **inside that profile**; plugin directories are profile-scoped.
3. Create the empty vault and run `o2b init`, `o2b brain init`, and `o2b search index`.
4. Verify `hermes --profile <pilot> memory status`, `o2b brain doctor`, and a fresh `hermes --profile <pilot> chat -q ...` session.
5. Verify the original profile still reports its prior provider.

## Git-Bash launcher compatibility

The upstream `scripts/o2b` wrapper passes an MSYS `/c/...` path to Windows Bun; Bun may report its TypeScript entrypoint as missing. A narrow launcher fix is to convert only the entrypoint on `MINGW*|MSYS*|CYGWIN*`:

```bash
ENTRYPOINT="$REPO_ROOT/src/cli/main.ts"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) ENTRYPOINT=$(cygpath -w "$ENTRYPOINT") ;;
esac
exec bun run "$ENTRYPOINT" "$@"
```

Apply it to the pilot profile's O2B plugin copy, then verify `bash -n scripts/o2b` and `scripts/o2b help`. This is an installation-local compatibility patch; a plugin update may overwrite it.

When a Python benchmark runner invokes the installed extensionless `~/.local/bin/o2b` wrapper, do not pass that Bash script directly to `subprocess.run` as though it were a Win32 executable (`WinError 193`) and do not invent an `.exe` suffix (`WinError 2`). Route it through Git Bash explicitly:

```python
import shutil, subprocess
bash = shutil.which("bash") or r"C:\Program Files\Git\bin\bash.exe"
subprocess.run(
    [bash, "/c/Users/<user>/.local/bin/o2b", "brain", "doctor", "--vault", vault],
    check=True,
)
```

Use argument arrays rather than interpolated shell strings so paths/reasons remain safely quoted. This applies to benchmark maintenance calls such as `brain reject` and `search index` as well as read-only checks.

## Verification caveat

On Windows, distinguish an O2B core failure from upstream test-suite portability failures. The provider can be considered operational after: native bridge handshake/tool discovery, clean `brain doctor`, a fresh Hermes pilot session, and launcher syntax/runtime checks. Record failures from broad third-party suites separately when they concern Windows temporary-directory locks or platform path separators rather than the configured provider path.

### Observed O2B v1.38.0 Windows pitfalls

- `o2b brain bench memory` can fail during its documented warm-up/index phase with `INDEX_MISSING` instead of self-healing. The fixture run is already checkpointed after ingest. Preserve the disposable run directory, run `o2b search index --vault <runs-dir>/<run-id>/vault`, then rerun the benchmark with `--resume <run-id>`. Delete the disposable runs directory after recording the report.
- `o2b brain rollback <run-id> --dry-run` can fail when extracting a snapshot from a `C:\...` vault because Windows `tar` interprets the drive-letter colon as a remote-host separator (`Cannot connect to C`). Do not force rollback merely to bypass this; report the portability blocker.
- `o2b brain reject` can retire a preference correctly while leaving the derived `Brain/active.md` stale. Confirm effective behavior through `brain export` and a genuinely fresh Hermes profile session. In observed testing, the Hermes provider stopped injecting the rejected preference even though `active.md` still displayed it.
- The native Hermes tool surface may expose feedback/query/apply-evidence but not `brain_dream`; use the deterministic CLI dream command for the consolidation pass when the native tool is absent.
