[CmdletBinding()]
param(
    [string]$ReceiptPath,
    [string]$WorkRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ([string]::IsNullOrWhiteSpace($ReceiptPath)) {
    $ReceiptPath = Join-Path $repoRoot 'TUI testing\results\verification-commands.json'
}
$receipt = [IO.Path]::GetFullPath($ReceiptPath)
$allowedRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot 'TUI testing\results'))
$allowedPrefix = $allowedRoot.TrimEnd('\') + '\'
if (-not $receipt.StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Verification receipt must stay below TUI testing\results.'
}

if ([string]::IsNullOrWhiteSpace($WorkRoot)) {
    $WorkRoot = Join-Path ([IO.Path]::GetTempPath()) 'vesper-v20-tui-verify'
}
$work = [IO.Path]::GetFullPath($WorkRoot)
$repoPrefix = $repoRoot.TrimEnd('\') + '\'
if ($work -eq $repoRoot -or $work.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'TUI verification scratch files must stay outside the repository.'
}

function Assert-DedicatedScratchRoot {
    param([Parameter(Mandatory)] [string]$Path)

    $normalized = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($Path))
    $volume = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetPathRoot($normalized))
    $profile = [IO.Path]::TrimEndingDirectorySeparator(
        [IO.Path]::GetFullPath([Environment]::GetFolderPath('UserProfile'))
    )
    $systemTemp = [IO.Path]::TrimEndingDirectorySeparator(
        [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    )
    if ($normalized -in @($volume, $profile, $systemTemp)) {
        throw 'TUI verification WorkRoot must be a dedicated scratch directory, not a broad filesystem root.'
    }

    $cursor = $normalized
    while (-not [string]::IsNullOrWhiteSpace($cursor)) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'TUI verification WorkRoot cannot contain a reparse point.'
            }
        }
        $parent = [IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) {
            break
        }
        $cursor = $parent.FullName
    }
}

function Assert-ScratchPath {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$WorkRoot
    )

    $normalized = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($Path))
    $root = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($WorkRoot))
    $rootPrefix = $root + [IO.Path]::DirectorySeparatorChar
    if (-not $normalized.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'TUI scratch path must stay below WorkRoot.'
    }

    $cursor = $normalized
    while ($true) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'TUI scratch path cannot contain a reparse point.'
            }
        }
        if ($cursor -eq $root) {
            return
        }
        $parent = [IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) {
            throw 'TUI scratch path must stay below WorkRoot.'
        }
        $cursor = $parent.FullName
    }
}

function Assert-ReceiptPath {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$AllowedRoot,
        [Parameter(Mandatory)] [string]$RepositoryRoot
    )

    $normalized = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($Path))
    $allowed = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($AllowedRoot))
    $root = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($RepositoryRoot))
    $cursor = $normalized
    $sawAllowedRoot = $false
    while ($true) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Verification receipt path cannot contain a reparse point.'
            }
        }
        if ($cursor -eq $allowed) {
            $sawAllowedRoot = $true
        }
        if ($cursor -eq $root) {
            break
        }
        $parent = [IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) {
            break
        }
        $cursor = $parent.FullName
    }
    if (-not $sawAllowedRoot -or $cursor -ne $root) {
        throw 'Verification receipt path is outside the approved repository directory.'
    }
}

Assert-DedicatedScratchRoot -Path $work
Assert-ReceiptPath -Path $receipt -AllowedRoot $allowedRoot -RepositoryRoot $repoRoot

$scratchTemp = Join-Path $work 'temp'
$scratchUvCache = Join-Path $work 'uv-cache'
$scratchCargoTarget = Join-Path $work 'cargo-target'
$scratchLocalAppData = Join-Path $work 'local-app-data'
$pytestTemp = Join-Path $work 'pytest'
$pytestCache = Join-Path $work 'pytest-cache'
$scratchPaths = @(
    $scratchTemp,
    $scratchUvCache,
    $scratchCargoTarget,
    $scratchLocalAppData,
    $pytestTemp,
    $pytestCache
)
$originalEnvironment = [ordered]@{
    TEMP = [Environment]::GetEnvironmentVariable('TEMP', 'Process')
    TMP = [Environment]::GetEnvironmentVariable('TMP', 'Process')
    UV_CACHE_DIR = [Environment]::GetEnvironmentVariable('UV_CACHE_DIR', 'Process')
    CARGO_TARGET_DIR = [Environment]::GetEnvironmentVariable('CARGO_TARGET_DIR', 'Process')
    LOCALAPPDATA = [Environment]::GetEnvironmentVariable('LOCALAPPDATA', 'Process')
}
$results = [Collections.Generic.List[object]]::new()

function Invoke-Recorded {
    param(
        [Parameter(Mandatory)] [string]$Command,
        [Parameter(Mandatory)] [scriptblock]$Action
    )
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $exitCode = 1
    try {
        & $Action
        $exitCode = $LASTEXITCODE
    }
    catch {
        $exitCode = 1
    }
    finally {
        $timer.Stop()
        $script:results.Add([ordered]@{
            command = $Command
            exit_code = $exitCode
            duration_ms = $timer.ElapsedMilliseconds
        })
    }
}

Push-Location $repoRoot
try {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $receipt) | Out-Null
    foreach ($scratchPath in $scratchPaths) {
        Assert-ScratchPath -Path $scratchPath -WorkRoot $work
    }
    New-Item -ItemType Directory -Force -Path $scratchPaths | Out-Null
    foreach ($scratchPath in $scratchPaths) {
        Assert-ScratchPath -Path $scratchPath -WorkRoot $work
    }
    $env:TEMP = $scratchTemp
    $env:TMP = $scratchTemp
    $env:UV_CACHE_DIR = $scratchUvCache
    $env:CARGO_TARGET_DIR = $scratchCargoTarget
    $env:LOCALAPPDATA = $scratchLocalAppData
    Invoke-Recorded -Command "uv run --locked python -m pytest --basetemp $pytestTemp -o cache_dir=$pytestCache tests/platform/tui tests/platform/ops -q" -Action {
        uv run --locked python -m pytest --basetemp $pytestTemp -o "cache_dir=$pytestCache" tests/platform/tui tests/platform/ops -q
    }
    Invoke-Recorded -Command 'cargo fmt --manifest-path TUI testing/ratatui-console/Cargo.toml -- --check' -Action {
        cargo fmt --manifest-path 'TUI testing/ratatui-console/Cargo.toml' -- --check
    }
    Invoke-Recorded -Command 'cargo clippy --manifest-path TUI testing/ratatui-console/Cargo.toml --all-targets --locked -- -D warnings' -Action {
        cargo clippy --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --all-targets --locked -- -D warnings
    }
    Invoke-Recorded -Command 'cargo test --manifest-path TUI testing/ratatui-console/Cargo.toml --all-targets --locked' -Action {
        cargo test --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --all-targets --locked
    }
}
finally {
    try {
        Pop-Location
    }
    finally {
        foreach ($entry in $originalEnvironment.GetEnumerator()) {
            [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
        }
    }
    $receiptTemp = Join-Path (Split-Path -Parent $receipt) ('.verification-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $receiptDocument = [ordered]@{
        generated_at_utc = [DateTimeOffset]::UtcNow.ToString('O')
        commands = $results
    } | ConvertTo-Json -Depth 5
    try {
        Set-Content -LiteralPath $receiptTemp -Value $receiptDocument -Encoding utf8
        [IO.File]::Move($receiptTemp, $receipt, $true)
    }
    finally {
        if (Test-Path -LiteralPath $receiptTemp) {
            Remove-Item -LiteralPath $receiptTemp -Force
        }
    }
}

if ($results.Where({ $_.exit_code -ne 0 }).Count -gt 0) {
    exit 1
}
