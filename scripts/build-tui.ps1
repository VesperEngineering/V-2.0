[CmdletBinding()]
param(
    [string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$distRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot 'dist\tui'))
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = $distRoot
}
$output = [IO.Path]::GetFullPath($OutputDirectory)
$distPrefix = $distRoot.TrimEnd('\') + '\'
if ($output -ne $distRoot -and -not $output.StartsWith($distPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'TUI build output must stay below dist\tui.'
}

$env:TEMP = 'C:\tmp\v20-tui-operations-temp'
$env:TMP = 'C:\tmp\v20-tui-operations-temp'
$env:UV_CACHE_DIR = 'C:\tmp\v20-tui-operations-uv-cache'
$env:CARGO_TARGET_DIR = 'C:\tmp\v20-tui-release-target'
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
    New-Item -ItemType Directory -Force -Path $env:TEMP, $env:CARGO_TARGET_DIR, $output | Out-Null
    foreach ($entry in Get-ChildItem -LiteralPath $output -Force) {
        if ($entry.PSIsContainer -or $allowedPackageNames -notcontains $entry.Name) {
            throw "Unapproved package entry: $($entry.Name)"
        }
    }

    Invoke-Checked -Label 'Python TUI verification' -Action {
        uv run --locked python -m pytest --basetemp C:\tmp\v20-tui-operations-pytest -o cache_dir=C:\tmp\v20-tui-operations-cache tests/platform/tui tests/platform/ops -q
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
    $destinationExe = Join-Path $output 'vesper-ratatui-console.exe'
    $destinationReadme = Join-Path $output 'README.md'
    Copy-Item -LiteralPath $sourceExe -Destination $destinationExe -Force
    Copy-Item -LiteralPath 'TUI testing/ratatui-console/README.md' -Destination $destinationReadme -Force

    $hash = (Get-FileHash -LiteralPath $destinationExe -Algorithm SHA256).Hash.ToLowerInvariant()
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
    $receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $output 'build-receipt.json') -Encoding utf8
    $packagedEntries = @(Get-ChildItem -LiteralPath $output -Force)
    if ($packagedEntries.Count -ne $allowedPackageNames.Count) {
        throw 'Package output does not contain the exact approved file set.'
    }
    foreach ($entry in $packagedEntries) {
        if ($entry.PSIsContainer -or $allowedPackageNames -notcontains $entry.Name) {
            throw "Unapproved package entry: $($entry.Name)"
        }
    }
}
finally {
    Pop-Location
}
