[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [string]$WorkRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$distRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot 'dist\tui'))
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = $distRoot
}
$output = [IO.Path]::GetFullPath($OutputDirectory)
if ($output -ne $distRoot) {
    throw 'TUI build output must be exactly dist\tui.'
}

if ([string]::IsNullOrWhiteSpace($WorkRoot)) {
    $WorkRoot = Join-Path ([IO.Path]::GetTempPath()) 'vesper-v20-tui-build'
}
$work = [IO.Path]::GetFullPath($WorkRoot)
$repoPrefix = $repoRoot.TrimEnd('\') + '\'
if ($work -eq $repoRoot -or $work.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'TUI build scratch files must stay outside the repository.'
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
        throw 'TUI build WorkRoot must be a dedicated scratch directory, not a broad filesystem root.'
    }

    $cursor = $normalized
    while (-not [string]::IsNullOrWhiteSpace($cursor)) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'TUI build WorkRoot cannot contain a reparse point.'
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

function Assert-PackagePath {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$RepositoryRoot
    )

    $normalized = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($Path))
    $root = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($RepositoryRoot))
    $cursor = $normalized
    while ($true) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'TUI package path cannot contain a reparse point.'
            }
        }
        if ($cursor -eq $root) {
            return
        }
        $parent = [IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) {
            throw 'TUI package path must stay below the repository root.'
        }
        $cursor = $parent.FullName
    }
}

Assert-DedicatedScratchRoot -Path $work
Assert-PackagePath -Path $output -RepositoryRoot $repoRoot

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
$allowedPackageNames = @(
    'vesper-ratatui-console.exe',
    'README.md',
    'build-receipt.json'
)

function Invoke-Checked {
    param(
        [Parameter(Mandatory)] [scriptblock]$Action,
        [Parameter(Mandatory)] [string]$Label
    )
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

Push-Location $repoRoot
try {
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
    if (Test-Path -LiteralPath $output) {
        foreach ($entry in Get-ChildItem -LiteralPath $output -Force) {
            if (
                $entry.PSIsContainer -or
                ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
                $allowedPackageNames -notcontains $entry.Name
            ) {
                throw "Unapproved package entry: $($entry.Name)"
            }
        }
    }

    Invoke-Checked -Label 'Python TUI verification' -Action {
        uv run --locked python -m pytest --basetemp $pytestTemp -o "cache_dir=$pytestCache" tests/platform/tui tests/platform/ops -q
    }
    Invoke-Checked -Label 'Rust format verification' -Action {
        cargo fmt --manifest-path 'TUI testing/ratatui-console/Cargo.toml' -- --check
    }
    Invoke-Checked -Label 'Rust lint verification' -Action {
        cargo clippy --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --all-targets --locked -- -D warnings
    }
    Invoke-Checked -Label 'Rust tests' -Action {
        cargo test --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --all-targets --locked
    }
    Invoke-Checked -Label 'Rust release build' -Action {
        cargo build --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --release --locked
    }

    $sourceExe = Join-Path $env:CARGO_TARGET_DIR 'release\vesper-ratatui-console.exe'
    if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf)) {
        throw 'Release executable was not produced.'
    }
    $packageStage = Join-Path $work ('.package-stage-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $packageStage | Out-Null
    $stagedExe = Join-Path $packageStage 'vesper-ratatui-console.exe'
    $stagedReadme = Join-Path $packageStage 'README.md'
    Copy-Item -LiteralPath $sourceExe -Destination $stagedExe
    Copy-Item -LiteralPath 'TUI testing/ratatui-console/README.md' -Destination $stagedReadme

    $hash = (Get-FileHash -LiteralPath $stagedExe -Algorithm SHA256).Hash.ToLowerInvariant()
    $receipt = [ordered]@{
        executable = 'dist/tui/vesper-ratatui-console.exe'
        sha256 = $hash
        built_at_utc = [DateTimeOffset]::UtcNow.ToString('O')
        tools = [ordered]@{
            cargo = (& cargo --version)
            rustc = (& rustc --version)
            uv = (& uv --version)
        }
    }
    $receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $packageStage 'build-receipt.json') -Encoding utf8
    $packagedEntries = @(Get-ChildItem -LiteralPath $packageStage -Force)
    if ($packagedEntries.Count -ne $allowedPackageNames.Count) {
        throw 'Package staging does not contain the exact approved file set.'
    }
    foreach ($entry in $packagedEntries) {
        if (
            $entry.PSIsContainer -or
            ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
            $allowedPackageNames -notcontains $entry.Name
        ) {
            throw "Unapproved package entry: $($entry.Name)"
        }
    }

    $outputParent = Split-Path -Parent $output
    New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
    $transactionId = [Guid]::NewGuid().ToString('N')
    $installStage = Join-Path $outputParent ('.tui-install-' + $transactionId)
    $backup = Join-Path $outputParent ('.tui-backup-' + $transactionId)
    New-Item -ItemType Directory -Path $installStage | Out-Null
    foreach ($name in $allowedPackageNames) {
        Copy-Item -LiteralPath (Join-Path $packageStage $name) -Destination (Join-Path $installStage $name)
    }
    $installedStageEntries = @(Get-ChildItem -LiteralPath $installStage -Force)
    if ($installedStageEntries.Count -ne $allowedPackageNames.Count) {
        throw 'Install staging does not contain the exact approved file set.'
    }
    foreach ($entry in $installedStageEntries) {
        if (
            $entry.PSIsContainer -or
            ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
            $allowedPackageNames -notcontains $entry.Name
        ) {
            throw "Unapproved install staging entry: $($entry.Name)"
        }
    }
    $installedHash = (Get-FileHash -LiteralPath (Join-Path $installStage 'vesper-ratatui-console.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($installedHash -ne $hash) {
        throw 'Install staging executable hash does not match the verified package.'
    }

    $movedExisting = $false
    if (Test-Path -LiteralPath $output) {
        Move-Item -LiteralPath $output -Destination $backup
        $movedExisting = $true
    }
    try {
        Move-Item -LiteralPath $installStage -Destination $output
    }
    catch {
        if ($movedExisting -and -not (Test-Path -LiteralPath $output)) {
            Move-Item -LiteralPath $backup -Destination $output
        }
        throw
    }
    if ($movedExisting) {
        $backupItem = Get-Item -LiteralPath $backup -Force
        if (($backupItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'TUI package backup cannot be a reparse point.'
        }
        $backupEntries = @(Get-ChildItem -LiteralPath $backup -Force)
        foreach ($entry in $backupEntries) {
            if (
                $entry.PSIsContainer -or
                ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
                $allowedPackageNames -notcontains $entry.Name
            ) {
                throw "Unapproved package backup entry: $($entry.Name)"
            }
        }
        foreach ($entry in $backupEntries) {
            Remove-Item -LiteralPath $entry.FullName -Force
        }
        Remove-Item -LiteralPath $backup -Force
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
}
