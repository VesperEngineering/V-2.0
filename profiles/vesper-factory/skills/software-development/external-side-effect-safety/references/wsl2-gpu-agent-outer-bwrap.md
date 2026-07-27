# WSL2 GPU Agent Workloads Behind Outer Bubblewrap

Use this reference when a Linux/WSL coding agent needs CUDA or another special device, but the agent runtime's native filesystem sandbox hides the device or misclassifies it as a writable directory.

## Version-specific Codex finding

Codex CLI 0.144.5 (`rust-v0.144.5`, commit `87db9bc18ba5bc82c1cb4e4381b44f693ee35623`) constructs its Linux filesystem sandbox by making `/` read-only and replacing `/dev` with Bubblewrap's minimal device tree. That hides WSL's `/dev/dxg`.

Adding `/dev/dxg` or `/dev` as an ordinary writable root is unsafe in this version. Writable roots receive protected metadata handling for `.git`, `.agents`, and `.codex`; device nodes are not directories, so policy construction can inspect paths such as `/dev/dxg/.codex` or attempt to create `/dev/.git`.

`danger-full-access` maps to a disabled permission profile and normally selects no native platform sandbox. Managed-network requirements are an exception: they can still request a platform sandbox. An outer sandbox should therefore disable optional inner network-proxy enforcement and disable nested user namespaces so unexpected native sandboxing fails closed.

## Outer boundary pattern

Use one outer Bubblewrap process with this mount order:

```bash
bwrap \
  --new-session \
  --die-with-parent \
  --ro-bind / / \
  --dev /dev \
  --dev-bind /dev/dxg /dev/dxg \
  --bind "$WORKSPACE" "$WORKSPACE" \
  --ro-bind "$FAKE_MNT" /mnt \
  --ro-bind "$DENY" /run \
  --ro-bind "$DENY" /tmp \
  --ro-bind "$DENY" /path/to/forbidden-tree \
  --unshare-user \
  --disable-userns \
  --unshare-pid \
  --unshare-ipc \
  --proc /proc \
  --chdir "$WORKSPACE" \
  -- COMMAND ...
```

Key points:

- `--dev /dev` creates a minimal synthetic `/dev`; `--dev-bind` then restores only the required real device with device access.
- Do not use `--unshare-net` when direct network access is required.
- Redirect `TMPDIR`, package caches, and agent logs/state into a workspace-owned runtime directory. Do not make host `/tmp` writable merely for compatibility.
- Mask `/run` and `/tmp` when existing Unix sockets would violate the boundary.
- Resolve and reject symlinked workspace roots before launch when exact path identity is required.
- Reject tool binaries under mounts that will be hidden (for WSL, commonly `/mnt/c`). Pin and verify the expected native Linux version before entering Bubblewrap.

## WSL resolver carveout

WSL commonly makes `/etc/resolv.conf` a symlink to `/mnt/wsl/resolv.conf`. Blindly masking `/mnt` preserves filesystem confidentiality but breaks DNS.

Before Bubblewrap:

1. Create a temporary synthetic `mnt/wsl` tree.
2. Copy `cp -L /etc/resolv.conf FAKE_MNT/wsl/resolv.conf`.
3. Set the copied file to `0444`.
4. Set `FAKE_MNT` and `FAKE_MNT/wsl` to traverse-only mode `0111`.
5. Read-only bind `FAKE_MNT` over `/mnt`.

The original `/mnt`, including `/mnt/c`, is hidden. The sandbox cannot list `/mnt`, but libc can reach the copied resolver file by its known path. Recreate the copy on every launch because WSL DNS settings can change.

## Independent verification matrix

Run the outer boundary without the agent first. Require all checks to pass:

| Invariant | Probe |
|---|---|
| GPU/device | `test -c /dev/dxg` and `nvidia-smi` |
| Workspace write | Create and remove a unique file in the workspace |
| Outside read-only | Attempt a unique write under `/etc`; require failure |
| Forbidden trees | Require `test ! -r` for each masked root |
| Windows mounts hidden | Require `test ! -e /mnt/c` |
| Host sockets hidden | Require `/run` and `/tmp` unreadable when masked |
| No nesting | Attempt a minimal nested `bwrap`; require failure |
| DNS | `getent hosts` for the package endpoint |
| Package network | HTTPS request to the package index |
| Model network | HTTPS request to the model endpoint; an HTTP auth error still proves transport |

Use cleanup traps for temporary host-side mask trees and workspace probes. Do not report the agent launch as tested when only the boundary probe ran.

## Inner agent launch

After the probe passes, launch the agent with its native sandbox disabled relative to the outer namespace. For Codex this can be `--dangerously-bypass-approvals-and-sandbox` or explicit `danger-full-access`; the former also avoids approval retries. Prefer ephemeral non-interactive execution when the CLI supports it.

Never run this mode outside the verified outer Bubblewrap command. “Danger full access” means full access to whatever namespace contains Codex.

## Auth and confidentiality limitations

- A read-only agent config/auth directory may prevent OAuth refresh, login persistence, migrations, or normal session-state writes. Pre-authenticate and use ephemeral execution where possible.
- Masking `/run` can make D-Bus/keyring-backed credentials unavailable; file-backed auth is more compatible but becomes readable in the namespace.
- Plain mount namespaces do not distinguish the Codex parent from model-generated child commands. If the parent can read `auth.json`, children can generally read it too. With outbound network enabled, read-only credentials can still be exfiltrated.
- Solving parent-only credential access requires a credential broker or privilege-separated launcher, not another mount flag.

## Session evidence

An analogous WSL2 probe with Bubblewrap 0.9.0 passed on an RTX 5070 Ti. It verified `/dev/dxg`, `nvidia-smi`, workspace writes, outside-write denial, forbidden-tree masks, nested-Bubblewrap denial, WSL DNS, package-index access, and model-endpoint access. The Codex launch itself was not executed in that probe, so this evidence applies only to the outer boundary.
