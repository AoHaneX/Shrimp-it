param([string]$Python = "")

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $projectRoot '.venv\Scripts\python.exe' }
$previousPlatform = $env:QT_QPA_PLATFORM
Push-Location $projectRoot
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    # Compile the ExoQuant palette engine when it is missing or older than its sources, then require it:
    # the PNG tests must exercise the native engine instead of skipping it.
    $engine = 'src\shrimpit\native\exoquant.dll'
    $sources = Get-Item 'src\shrimpit\native\exoquant.c', 'src\shrimpit\native\exoquant.h'
    if (-not (Test-Path $engine) -or ($sources | Where-Object { $_.LastWriteTime -gt (Get-Item $engine).LastWriteTime })) {
        & $Python scripts\build_png_engine.py
        if ($LASTEXITCODE -ne 0) { throw 'Could not compile the PNG engine: pip install -e ".[build]".' }
    }
    $env:SHRIMPIT_REQUIRE_PNG_ENGINE = '1'
    & $Python -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Static checks failed.' }
    & $Python -m ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw 'Formatting check failed.' }
    & $Python -m pytest -q --cov=shrimpit --cov-report=term
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
} finally {
    Pop-Location
    $env:QT_QPA_PLATFORM = $previousPlatform
    Remove-Item Env:SHRIMPIT_REQUIRE_PNG_ENGINE -ErrorAction SilentlyContinue
}
