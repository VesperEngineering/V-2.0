# Docker Codex sandbox boundary receipt

## Outcome

On 2026-07-27, Docker Sandboxes `sbx` 0.37.0 successfully ran Codex through the
host-managed OpenAI OAuth proxy in a disposable standalone V20 clone. The canary
verified model access, network policy, read-only behavior, and bounded writes, but
it is not accepted as a production isolation boundary because later mount
inspection found Docker's default read-write shared host skills store.

## Observed boundary

- Sandbox: `v20-codex-canary`
- Agent: `codex`
- MCP gateway: disabled
- Workspace: `C:\Users\bgonn\AppData\Local\Temp\opencode\v20-codex-canary-lf`
- Allowed network hosts: `api.openai.com`, `chatgpt.com`, and `openai.com`
- `example.com`: denied by implicit default-deny
- OpenRouter and unrelated destinations: not allowed
- Authentication metadata: `oauth · openai`; no credential value was read or recorded
- Additional mount found after the canaries: `/home/agent/.agents/skills` as read-write

The read-only canary returned exactly `V20_CODEX_SANDBOX_READY`. The initial
workspace-write canary eventually created only `V20_DOCKER_WRITE_CANARY.txt` with
the requested bytes, but Codex's nested Bubblewrap repeatedly failed to remount the
Windows-backed workspace. A second workspace-write canary used Codex's documented
`--dangerously-bypass-approvals-and-sandbox` mode inside the Docker microVM. It
created only `V20_DOCKER_BYPASS_CANARY.txt`, containing
`V20_DOCKER_EXTERNAL_SANDBOX_OK\n`, and emitted no Bubblewrap errors.

## Implemented adapter policy

`vesper.platform.codex_sandbox.DockerCodexAdapter` now:

- requires an exact approved model and exact sandbox-bound standalone repository;
- verifies an initially stopped Codex sandbox, OpenAI OAuth, disabled MCP, no kits or
  sessions, one exact workspace, no published ports, no shared host mounts,
  exact provider hosts, effective allows, and implicit default-deny before execution;
- retains Codex's inner sandbox for read-only requests;
- permits externally-sandboxed mode only for workspace-write requests after preflight;
- rejects project-local Codex configuration and overrides MCP servers to an empty map;
- fingerprints all `.git` metadata before and after a turn;
- force-removes the one-shot sandbox and confirms its absence after every outcome;
- parses size-bounded, lifecycle-complete JSONL into typed non-acceptance receipts; and
- fails closed on malformed output, policy drift, workspace mismatch, or unconfirmed stop.

Deterministic coverage is in `tests/platform/test_codex_sandbox.py`. The adapter is
not yet connected to the CLI. Each turn must receive a fresh uniquely named sandbox
with skills sharing disabled, and the separately owned M2 specialist composition
must be adapted from the host SDK and reviewed. The operator approved one-shot
force-removal on 2026-07-27.

The original `v20-codex-canary` was then force-removed. Two initial replacement
attempts failed at Windows Hypervisor Platform VM creation with access denied
`0x80070005`; daemon logs confirmed the hidden `--no-share-skills` flag itself was
accepted. After the operator-approved removal of three stopped OpenCode test
sandboxes and a `sandboxd` restart, secure provisioning succeeded. Mount inspection
showed only the writable disposable clone plus read-only hosts and resolver mounts,
with no shared skills or published ports.

The Docker-managed Codex config is required for its ChatGPT OAuth route. V20 keeps
that config while overriding MCP servers to an empty map and disabling skills,
plugins, hooks, memory, apps, multi-agent, and web features. The controller-approved
model token `docker-codex-default` deliberately omits `--model`, selecting Docker's
managed ChatGPT-backed default rather than falling back to the public Responses API.
The real hardened adapter canary completed with exactly
`V20_SECURE_ADAPTER_READY`, emitted a typed receipt, and force-removed its one-shot
sandbox; `sbx ls --json` was empty afterward.
