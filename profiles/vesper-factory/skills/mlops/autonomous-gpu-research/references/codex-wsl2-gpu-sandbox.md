# Codex WSL2 GPU-device sandbox preflight

Use this reference when Codex must edit a training repository and launch CUDA work under WSL2.

## Version-pinned evidence

Observed with:

- Codex CLI `0.144.5`
- Ubuntu 24.04 under WSL2
- distribution Bubblewrap `0.9.0`
- NVIDIA GeForce RTX 5070 Ti through `/dev/dxg`

These are reproduction facts, not permanent claims. After any Codex upgrade, rerun the CLI help, GPU probe, and a real patch/write probe before carrying forward a workaround.

## Probe the effective sandbox

Host-side `nvidia-smi` is insufficient. Ordinary `workspace-write` produced:

```text
dxg=missing
Failed to initialize NVML: GPU access blocked by the operating system
```

Installing the distro package is a sound prerequisite:

```bash
sudo apt install -y bubblewrap
bwrap --version
```

It does not by itself expose `/dev/dxg`; the effective mount policy still controls device visibility.

## A GPU probe is not a patch probe

This launch made a bounded `nvidia-smi` check succeed:

```bash
codex --cd "$WORKSPACE" --add-dir /dev/dxg \
  --ask-for-approval on-request --sandbox workspace-write
```

Observed evidence:

```text
dxg=present
NVIDIA GeForce RTX 5070 Ti
```

However, when the same session later attempted normal patch preparation, Codex treated the character device like a directory while inspecting protected metadata and failed before editing:

```text
failed to inspect synthetic bubblewrap mount target /dev/dxg/.codex:
Not a directory (os error 20)
```

Therefore, a read-only GPU probe does **not** establish that a long autonomous coding run can patch files. Require both:

1. GPU visibility through the exact launch boundary.
2. A harmless workspace create/patch/delete probe through the same boundary.

## Custom-profile failure evidence

A custom profile with `/dev/dxg = "write"` hit the same character-device metadata failure. Broadening the custom entry to `/dev = "write"` then failed while creating protected metadata under `/dev`:

```text
bwrap: Can't mkdir /dev/.git: Permission denied
```

Both failures occurred before the requested probe command ran. Confirm that distinction from stderr and Git state; do not claim a prohibited path was accessed merely because sandbox construction failed.

Do not generalize these errors to later releases. Re-test the current build before applying a workaround, and do not repeatedly broaden native permissions blindly.

## Verified outer-Bubblewrap boundary pattern

When the native device policy cannot support both patching and GPU access, a separate Bubblewrap mount boundary can provide the isolation while Codex runs without its inner sandbox.

The session-specific boundary probe verified:

```text
workspace=writable
outside-workspace=read-only
windows-mounts=masked
other-clones=masked
real-codex-home=masked
dxg=present
NVIDIA GeForce RTX 5070 Ti
```

The pattern is:

- read-only bind of `/`;
- writable bind of only the research workspace;
- writable private `/tmp` for package/tool caches;
- `/dev` bind so `/dev/dxg` remains usable;
- masks over Windows mounts, sibling production clones, and real credential directories;
- a separate runtime Codex home containing a copy of CLI auth;
- Codex launched with its native sandbox disabled **only inside this verified outer boundary**.

Use `scripts/codex-wsl2-gpu-bwrap.sh` as a parameterized implementation. Run `test` first, inspect every receipt, verify clean Git state, and only then use `launch`.

Example:

```bash
export CODEX_GPU_WORKSPACE="$HOME/research-repo"
export CODEX_MASK_PATHS="$HOME/production-repo:$HOME/other-clone"
bash scripts/codex-wsl2-gpu-bwrap.sh test
bash scripts/codex-wsl2-gpu-bwrap.sh launch
```

## Caveats to state honestly

- The outer boundary shares host networking because Codex needs its API connection and bootstrap may need package downloads. It is not a command-level network allowlist.
- The runtime Codex home contains an auth copy needed by the CLI. Masking the real `~/.codex` prevents modification of the original credential store, but the runtime copy is still inside the outer boundary. Continue to prohibit credential inspection in the control prompt.
- Binding `/dev` does not elevate Unix user permissions, but it is broader than binding only `/dev/dxg`.
- The verified receipt above proves the mount boundary test. It does not by itself prove a complete bootstrap or training run; verify the first real patch, exact interpreter, PyTorch CUDA state, and baseline separately.
- If read isolation must be stronger than this trade-off permits, use a dedicated WSL distro or container and validate GPU, data, network, and credential boundaries there.

## Reporting rule

Separate technical enforcement from prompt governance:

- technically enforced: writable roots, read-only roots, masked paths, visible devices;
- prompt-governed: which readable runtime files the agent chooses to inspect and which network destinations commands contact.

Never call a program-file instruction an OS-level denial, and never call a GPU-only probe a complete autonomous-run preflight.
