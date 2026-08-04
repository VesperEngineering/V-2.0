[CmdletBinding()]
param(
    [string]$ReceiptPath
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
if ($receipt -ne $allowedRoot -and -not $receipt.StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Verification receipt must stay below TUI testing\results.'
}

$env:TEMP='C:\tmp\v20-tui-operations-temp'
$env:TMP='C:\tmp\v20-tui-operations-temp'
$env:UV_CACHE_DIR='C:\tmp\v20-tui-operations-uv-cache'
$env:CARGO_TARGET_DIR='C:\tmp\v20-tui-verification-target'
$results = [Collections.Generic.List[object]]::new()

function Invoke-Recorded {
    param(
        [Parameter(Mandatory)] [string]$Command,
        [Parameter(Mandatory)] [scriptblock]$Action
    )
    $timer = [Diagnostics.Stopwatch]::StartNew()
    & $Action
    $exitCode = $LASTEXITCODE
    $timer.Stop()
    $script:results.Add([ordered]@{
        command = $Command
        exit_code = $exitCode
        duration_ms = $timer.ElapsedMilliseconds
    })
}

Push-Location $repoRoot
try {
    New-Item -ItemType Directory -Force -Path $env:TEMP, $env:CARGO_TARGET_DIR, (Split-Path -Parent $receipt) | Out-Null
    Invoke-Recorded -Command 'uv run --locked python -m pytest --basetemp C:\tmp\v20-tui-operations-pytest -o cache_dir=C:\tmp\v20-tui-operations-cache tests/platform/tui tests/platform/ops -q' -Action {
        uv run --locked python -m pytest --basetemp C:\tmp\v20-tui-operations-pytest -o cache_dir=C:\tmp\v20-tui-operations-cache tests/platform/tui tests/platform/ops -q
    }
    Invoke-Recorded -Command 'cargo fmt --manifest-path TUI testing/ratatui-console/Cargo.toml -- --check' -Action {
        cargo fmt --manifest-path 'TUI testing/ratatui-console/Cargo.toml' -- --check
    }
    Invoke-Recorded -Command 'cargo clippy --all-targets --locked -- -D warnings' -Action {
        cargo clippy --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --all-targets --locked -- -D warnings
    }
    Invoke-Recorded -Command 'cargo test --all-targets --locked' -Action {
        cargo test --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --all-targets --locked
    }
}
finally {
    Pop-Location
    [ordered]@{
        generated_at_utc = [DateTimeOffset]::UtcNow.ToString('O')
        commands = $results
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receipt -Encoding utf8
}

if ($results.Where({ $_.exit_code -ne 0 }).Count -gt 0) {
    exit 1
}
