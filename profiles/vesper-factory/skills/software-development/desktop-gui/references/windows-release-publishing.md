# Publishing a verified portable Windows desktop release

Use this checklist for public Python/Qt desktop releases intended for nontechnical Windows users.

## Build

1. Confirm project version, intended tag, clean `main`, and green CI.
2. Use one visual identity everywhere: packaged PNG for the runtime window and multi-resolution ICO for the executable.
3. Build with both `--icon` and `--add-data`:
   ```bash
   unset PYTHONPATH
   uv sync --extra dev
   uv run pytest
   uv run pyinstaller --noconfirm --clean --windowed \
     --name "App Name" --paths src \
     --icon src/package/assets/icon.ico \
     --add-data "src/package/assets/icon.png;package/assets" \
     src/package/app.py
   ```
4. Launch the packaged EXE with a sample document. Verify it stays alive, then close the test instance.

## Assemble and validate

1. Add `README.md` and `LICENSE` to the portable app directory.
2. ZIP the entire directory beneath one top-level app folder.
3. Use `ZipFile.testzip()` and assert that the EXE, README, and license exist in the archive.
4. Generate the checksum *from inside the output directory* so the manifest records only the filename:
   ```bash
   cd dist
   sha256sum App-v0.1.0-windows-x64.zip > App-v0.1.0-windows-x64.zip.sha256
   sha256sum -c App-v0.1.0-windows-x64.zip.sha256
   ```

## Publish and prove the public artifact

```bash
gh release create v0.1.0 \
  dist/App-v0.1.0-windows-x64.zip \
  dist/App-v0.1.0-windows-x64.zip.sha256 \
  --repo OWNER/REPO --target main --title "App v0.1.0" \
  --notes-file release-notes.md --latest
```

After publishing:

1. Confirm the release is not draft/prerelease and both assets report `uploaded`.
2. Confirm the remote tag points to the intended commit.
3. Download the uploaded ZIP and checksum into a fresh directory and run `sha256sum -c`. This verifies the public download, not just the local file.
4. Put a prominent `/releases/latest` link in the README and state that the portable build needs no Python or installer.
5. Wait for CI on any post-release README commit.

## GitHub Actions version pitfall

Do not infer that a floating major alias exists from a release tag. Query the current release:

```bash
gh api repos/OWNER/ACTION/releases/latest --jq '[.tag_name,.published_at] | @tsv'
```

If `owner/action@vN` cannot resolve, pin the exact published tag (for example, `@v8.3.2`) and rerun CI. Never leave the default branch red after a workflow-only upgrade.