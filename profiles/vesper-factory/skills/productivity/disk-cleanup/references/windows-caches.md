# Windows Cache Locations & Cleanup Commands

## Python Ecosystem

### pip
- **Location**: `%LOCALAPPDATA%\pip\cache\`
- **Command**: `pip cache purge`
- **Typical size**: 1-10 GB
- **Safe**: Yes — packages re-download on next install

### uv
- **Location**: `%LOCALAPPDATA%\uv\cache\`
- **Command**: `uv cache clean`
- **Typical size**: 1-5 GB
- **Safe**: Yes

### conda
- **Location**: `%USERPROFILE%\miniconda3\pkgs\` (package cache)
- **Command**: `conda clean --all`
- **Typical size**: 1-5 GB
- **Note**: Also check for unused environments with `conda env list`

## .NET / NuGet

- **Location**: `%USERPROFILE%\.nuget\packages\`, `%USERPROFILE%\.nuget\http-cache\`
- **Command**: `dotnet nuget locals all --clear`
- **Typical size**: 1-5 GB
- **Safe**: Yes

## Node.js / npm

- **Location**: `%APPDATA%\npm-cache\`
- **Command**: `npm cache clean --force`
- **Typical size**: 0.5-3 GB
- **Safe**: Yes

## AI/LLM Tool Caches

### Gemini CLI (.gemini)
- **Location**: `%USERPROFILE%\.gemini\antigravity\browser_recordings\`
- **Typical size**: 1-15 GB (browser session recordings)
- **Safe**: Yes — old recordings only

### Codex CLI (.codex)
- **Location**: `%USERPROFILE%\.codex\archived_sessions\`
- **Typical size**: 1-5 GB
- **Safe**: Yes — archived sessions

### Hermes Agent
- **Location**: `%LOCALAPPDATA%\hermes\sessions\`, `%LOCALAPPDATA%\hermes\cache\`
- **Safe**: Old sessions can be pruned; don't delete active ones

## Windows System

### Temp Files
- **Location**: `%LOCALAPPDATA%\Temp\`, `C:\Windows\Temp\`
- **Command**: `del /q %TEMP%\*` or `rm -rf $LOCALAPPDATA/Temp/*`
- **Safe**: Yes (files in use will fail to delete, which is fine)

### Browser Caches
- **Chrome**: `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cache\`
- **Firefox**: `%LOCALAPPDATA%\Mozilla\Firefox\Profiles\*\cache2\`
- **Edge**: `%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Cache\`
- **Safe**: Yes

### Disk Cleanup (built-in)
- **Command**: `cleanmgr /sagerun:1` (pre-configured) or `cleanmgr` (interactive)
- Clears: Recycle Bin, Temp, Thumbnails, Windows Update leftovers, Delivery Optimization files

## System Space Hogs (Conditional)

| File | Location | Typical Size | How to Reduce |
|------|----------|-------------|---------------|
| pagefile.sys | `C:\` | 1-4× RAM | System Properties → Advanced → Performance → Virtual Memory |
| hiberfil.sys | `C:\` | 0.75× RAM | `powercfg -h off` (disables hibernation) |
| swapfile.sys | `C:\` | ~256 MB | Tied to pagefile; shrinks with it |

## WSL2

- **Location**: `%LOCALAPPDATA%\wsl\*\ext4.vhdx`
- **Shrink**: `wsl --shutdown` then in PowerShell (admin): `Optimize-VHD -Path <path> -Mode Full`
- **Typical saving**: 10-40 GB (VHDs grow but never auto-shrink)
- **WARNING**: Do NOT delete the VHDX — it IS your Linux filesystem
