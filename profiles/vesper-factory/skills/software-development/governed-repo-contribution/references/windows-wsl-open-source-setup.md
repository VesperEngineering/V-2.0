# Windows + WSL2 setup for large C++ open-source repositories

Use this when a project officially supports Linux/macOS but the operator works on Windows.

## Durable setup pattern

1. Inspect WSL before installing anything:
   - `wsl.exe --status`
   - `wsl.exe -l -v`
   - `wsl.exe -d <distro> -- bash -lc 'id -un; printf "%s\n" "$HOME"'`
2. If the distro defaults to `root` and has no normal account, stop and obtain approval before creating one. Create a regular user, add it to `sudo`, set it under `[user] default=<name>` in `/etc/wsl.conf`, terminate the distro, and verify the restart uses the new account.
3. Clone build-heavy repositories into WSL's native filesystem (for example, `~/src/project`), not `/mnt/c/...`. This avoids poor I/O performance and Windows/WSL line-ending interference.
4. Preserve LF explicitly:
   - `git config --global core.autocrlf false`
   - clone with `git -c core.autocrlf=false clone ...`
   - inspect a representative golden/test file before the first build.
5. Re-establish GitHub authentication inside WSL. A safe bridge when Windows `gh` is already authenticated is:
   - `gh auth token | wsl.exe -d <distro> -- bash -lc 'gh auth login --hostname github.com --with-token'`
   - Then run `gh auth setup-git` inside WSL before the first authenticated push.
   - Do not print or persist the token manually.
6. Configure fork remotes conventionally:
   - `origin` = contributor fork
   - `upstream` = canonical project
   - Fetch upstream, fast-forward local trunk, then push the synchronized trunk to origin.
7. Install project-declared compiler/runtime versions rather than distribution defaults. For Carbon on Ubuntu 24.04, the versioned LLVM 19 packages are available directly (`clang-19`, `libc++-19-dev`, `libc++abi-19-dev`, `lld-19`, `lldb-19`). Point the build system at `/usr/bin/clang-19` when unversioned `clang` resolves to an older release or is absent.
8. Install repository hooks only after the native clone exists and required tooling is on PATH.
9. Treat the first build of a compiler/LLVM-scale repository as a long bounded job. Start it with tracked background execution and completion notification rather than repeatedly using a foreground timeout. A timed-out first build can usually be resumed because Bazel retains its cache; rerun the same target and verify the final exit status.
10. Keep personal notes out of the project diff. If a notebook lives inside the checkout, add only that local filename to `.git/info/exclude` and verify with `git check-ignore -v` plus a clean `git status`.

## Verification checklist

- WSL starts as the regular user, not root.
- Passwordless/noninteractive sudo works if intentionally configured.
- Repository path is under `/home/...`, not `/mnt/c/...`.
- `origin` and `upstream` point to the expected repositories.
- GitHub CLI reports the intended account and Git credential setup works.
- Compiler version matches project requirements.
- Hook is installed.
- Local trunk equals upstream and fork trunk.
- Working tree is clean.
- Baseline build/test completed with a real zero exit status; progress alone is not success.
