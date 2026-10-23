param([string]$Python = "")

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $projectRoot '.venv\Scripts\python.exe' }
$previousPlatform = $env:QT_QPA_PLATFORM
Push-Location $projectRoot
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    & $Python -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Static checks failed.' }
    & $Python -m ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw 'Formatting check failed.' }
    & $Python -m pytest -q --cov=shrimpit --cov-report=term
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
} finally {
    Pop-Location
    $env:QT_QPA_PLATFORM = $previousPlatform
}
