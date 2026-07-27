# Isolating Hermes inside a third-party orchestrator

Use this pattern when another application drives the local `hermes` CLI as a subprocess, selects a Hermes profile by setting `HERMES_HOME`, or installs helper skills into the selected profile.

## Safe onboarding sequence

1. Verify the integration against the exact installed orchestrator version and its official source. Do not infer an adapter from marketing copy.
2. Probe only `hermes --version` first. Detection does not require credentials, project access, or a privileged profile.
3. Create a dedicated Hermes profile for the orchestrator. Do not select `default`, a production worker, or a project-specific profile during initial setup.
4. Do not use `--clone` or `--clone-all` from a privileged profile unless the user explicitly approves copying its `.env`, `SOUL.md`, skills, and configuration.
5. Configure authentication inside the dedicated profile. Keep credentials scoped to the minimum provider/account needed for the sandbox.
6. Keep dangerous-command bypass (`--yolo`, auto-approve, unrestricted shell) disabled for onboarding.
7. Leave provider/model overrides blank when the profile is intended to own routing; avoid split authority between profile config and the orchestrator UI.
8. Use a synthetic throwaway project for the first prompt. Do not attach the canonical project, Hermes runtime state, private data, broker systems, or deployment infrastructure.
9. Verify read/write roots, shell approvals, network exposure, session persistence, and any automatic skill installation before expanding scope.
10. Treat auto-installed skills as writes to the selected profile. A dedicated profile confines those writes and makes rollback auditable.

## RunFusion Fusion v0.72 example

Fusion v0.72 includes `fusion-plugin-hermes-runtime`. It:

- probes the local binary with `hermes --version`;
- runs `hermes chat -q <prompt> -Q --source tool` and resumes the captured session ID on later turns;
- delegates provider, model, authentication, skills, and memory to the selected local Hermes profile;
- exposes settings for binary path, profile, optional model/provider overrides, max turns, hard timeout, and `yolo`;
- may mirror Fusion's bundled `fusion` skill into the selected profile's skill directory.

Recommended first configuration:

- **Binary:** leave blank for PATH detection; if needed, use the exact path returned by `where hermes`.
- **Profile:** a new dedicated sandbox profile, not `default` or a production/V20 worker.
- **Model/provider overrides:** blank while the profile owns routing.
- **Max turns:** retain the bounded default initially.
- **Timeout:** retain the bounded default initially.
- **Yolo/auto-approve:** off.

Test binary detection before saving broader runtime settings. No canonical project should be loaded during this test.

## Fail-closed conditions

Stop onboarding if the orchestrator:

- cannot isolate a dedicated Hermes profile;
- requires copying privileged credentials or runtime state;
- requires auto-approval of dangerous shell actions for a basic test;
- exposes the control surface publicly by default;
- silently writes to the canonical project or shared Hermes home;
- cannot identify which profile, binary, or provider it invokes.
