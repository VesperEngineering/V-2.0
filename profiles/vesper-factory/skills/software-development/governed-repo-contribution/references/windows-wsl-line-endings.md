# Windows/WSL checkouts for LF-sensitive repositories

Use this when a project is edited from Windows but built or tested in WSL, especially when golden-file parsers treat carriage returns as content.

## Safe setup

Prefer cloning inside WSL's native filesystem with LF conversion disabled:

```bash
git -c core.autocrlf=false clone https://github.com/OWNER/REPO.git ~/src/REPO
cd ~/src/REPO
git config core.autocrlf false
```

If the checkout must live on a Windows-mounted path, disable conversion **before cloning**:

```bash
git -c core.autocrlf=false clone https://github.com/OWNER/REPO.git /mnt/c/path/REPO
cd /mnt/c/path/REPO
git config core.autocrlf false
```

Before a costly first build, verify a representative golden/test file:

```bash
file path/to/testdata/example
```

Expected: plain text without `with CRLF line terminators`.

## Why this matters

Windows Git commonly inherits `core.autocrlf=true` from the system configuration. A WSL test process then reads CRLF bytes from the mounted working tree. Line-oriented golden-test parsers may report misleading errors such as an empty or malformed `CHECK` directive even though the source text looks correct in an editor.

## Recovery

Do not convert an entire established checkout in place unless you first preserve the intentional work. Line-ending conversion can make thousands of tracked files appear modified and obscure the real patch.

The clean recovery is:

1. Save the small intentional patch (`git diff` or a temporary commit).
2. Create a fresh checkout with `git -c core.autocrlf=false clone`.
3. Reapply only the intentional patch.
4. Confirm `git status --short` is clean except for intended files.
5. Re-run one narrow existing baseline test before writing production code.

Avoid assuming `git config core.autocrlf false` followed by `git reset --hard` will rewrite an already-materialized CRLF working tree; it may leave the line endings unchanged. Also avoid bulk archive/extraction over the checkout as a repair shortcut: index/worktree normalization can produce a repository-wide apparent diff.

## Build placement

Large C++/Bazel builds are generally much faster and less error-prone on WSL's native ext4 filesystem than under `/mnt/c`. Keep the canonical build checkout in WSL and expose it to Windows editors through `\\wsl.localhost\DISTRO\home\USER\...` when needed.