# Docker Codex sandbox boundary receipt

## Outcome

On 2026-07-27, Docker Sandboxes `sbx` 0.37.0 successfully ran Codex through the
host-managed OpenAI OAuth proxy. The initial canary exposed Docker's default shared
skills mount and was rejected. After recovery, one-shot provisioning with
`--no-share-skills` verified the hardened boundary and was accepted for the bounded
M2 controlled exercise.

## Observed boundary

- Sandbox: `v20-codex-canary`
- Agent: `codex`
- MCP gateway: disabled
- Initial canary workspace: `C:\Users\bgonn\AppData\Local\Temp\opencode\v20-codex-canary-lf`
- Allowed network hosts: `api.openai.com`, `chatgpt.com`, and `openai.com`
- `example.com`: denied by implicit default-deny
- OpenRouter and unrelated destinations: not allowed
- Authentication metadata: `oauth · openai`; no credential value was read or recorded
- Initial rejected boundary: `/home/agent/.agents/skills` was mounted read-write
- Accepted boundary: one exact task subdirectory, with no shared skills or extra host mounts

The read-only canary returned exactly `V20_CODEX_SANDBOX_READY`. The initial
workspace-write canary eventually created only `V20_DOCKER_WRITE_CANARY.txt` with
the requested bytes, but Codex's nested Bubblewrap repeatedly failed to remount the
Windows-backed workspace. A second workspace-write canary used Codex's documented
`--dangerously-bypass-approvals-and-sandbox` mode inside the Docker microVM. It
created only `V20_DOCKER_BYPASS_CANARY.txt`, containing
`V20_DOCKER_EXTERNAL_SANDBOX_OK\n`, and emitted no Bubblewrap errors.

## Implemented adapter policy

`vesper.platform.codex_sandbox.DockerCodexAdapter` now:

- requires an exact approved model and exact sandbox-bound task subdirectory;
- verifies an initially stopped Codex sandbox, OpenAI OAuth, disabled MCP, no kits or
  sessions, one exact workspace, no published ports, no shared host mounts,
  exact provider hosts, effective allows, and implicit default-deny before execution;
- retains Codex's inner sandbox for read-only requests;
- permits externally-sandboxed mode only for workspace-write requests after preflight;
- rejects nested `.codex` and `.agents` policy trees and overrides MCP servers to an empty map;
- fingerprints all `.git` metadata before and after a turn;
- force-removes the one-shot sandbox and confirms its absence after every outcome;
- parses size-bounded, lifecycle-complete JSONL into typed non-acceptance receipts; and
- fails closed on malformed output, policy drift, workspace mismatch, or unconfirmed stop.

Deterministic coverage is in `tests/platform/test_codex_sandbox.py` and
`tests/platform/test_sandbox_runtime.py`. The adapter is connected to the native
CLI composition. Each turn receives a fresh uniquely named sandbox with skills
sharing disabled and confirmed force-removal. The operator approved one-shot
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

The integrated controller additionally mounts only the approved task directory,
rejects concurrent repository operations, binds profile bytes to the persisted run,
rolls back rejected turns, requires typed specialist output and Risk compliance,
and binds operator approval to the Risk-checkpoint workspace hash plus all verified
Product, Development, validation, and Risk evidence.

## Controlled exercise acceptance

Run `16e14c0e-2496-4e28-a04f-803ae008e5a8` executed against revision
`549f7a36e9f4917aa76e80a43e15fcc1d763788e` in a disposable standalone clone.
Product routed the bounded task, Development changed only
`docs/m2-controlled-exercise/RESULT.md`, and all three controller checks passed:

- `git diff HEAD --check -- .`;
- `path-exists::RESULT.md`; and
- `file-contains::RESULT.md::m2-controlled-exercise-complete`.

Independent Risk Review returned `approve` with scope, evidence ownership, and
prohibited-action compliance all `true`. The approval request bound nine Product,
Development, validation, and Risk artifacts to workspace SHA-256
`a593657d1f7d3bfbfd813cae5048bc28bd290f20f356106653e842c0226ed7b6`.
The operator persisted approval for checkpoint
`1f18a14a-ce3b-64cd-8004-d0dc29a713a4`; explicit resume completed with status
`accepted`, zero corrections, and no pending nodes. Sandbox inventory was empty
after every specialist turn and after final acceptance.

The pre-acceptance attempts also failed closed as designed: the first exposed a
Windows lease-file fingerprint conflict, the second exposed Codex's required
`--skip-git-repo-check` option for exact non-Git subdirectory mounts, and a later
exercise stopped at operator intervention when a harmless Git line-ending warning
was misclassified as validation failure. Each issue was reproduced, covered by a
regression test, fixed, and retried from a fresh revision and clone; no failed run
reached Risk Review approval or operator acceptance.
