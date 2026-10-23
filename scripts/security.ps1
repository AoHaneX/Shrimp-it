param([string]$Python = "")

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $projectRoot '.venv\Scripts\python.exe' }
Push-Location $projectRoot
try {
    & $Python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency consistency check failed.' }
    & $Python -m bandit -r src -q
    if ($LASTEXITCODE -ne 0) { throw 'Security analysis failed.' }
    & $Python -m pip_audit --skip-editable --progress-spinner off
    if ($LASTEXITCODE -ne 0) { throw 'Dependency vulnerability audit failed or unavailable.' }
} finally {
    Pop-Location
}
