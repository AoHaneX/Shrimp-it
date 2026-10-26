# Build the Windows deliverables: portable ZIP and Inno Setup installer, both tested.
param(
    [string]$Python = "",
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $projectRoot '.venv\Scripts\python.exe' }
$dist = Join-Path $projectRoot 'dist'
$work = Join-Path $projectRoot 'build\pyinstaller'
$bundle = Join-Path $dist 'Shrimpit'

function Find-InnoSetup {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($folder in @("$env:LOCALAPPDATA\Programs", ${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
        if (-not $folder) { continue }
        $candidate = Join-Path $folder 'Inno Setup 6\ISCC.exe'
        if (Test-Path $candidate) { return $candidate }
    }
    throw 'Inno Setup 6 is required (winget install JRSoftware.InnoSetup) or use -SkipInstaller.'
}

function Test-FrozenBuild([string]$Executable) {
    # Run the self-test with no Python on PATH and no PYTHON* variable, from an unrelated folder,
    # to make sure the build only relies on its own files.
    $report = Join-Path $env:TEMP "shrimpit-selftest-$PID.txt"
    $savedPath = $env:PATH
    $savedPython = Get-ChildItem Env: | Where-Object { $_.Name -like 'PYTHON*' }
    try {
        $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem"
        $savedPython | ForEach-Object { Remove-Item "Env:$($_.Name)" }
        $process = Start-Process -FilePath $Executable -ArgumentList '--self-test', "`"$report`"" `
            -WorkingDirectory $env:TEMP -Wait -PassThru
        Get-Content $report -Encoding UTF8 | Write-Host
        if ($process.ExitCode -ne 0) { throw "Self-test failed for $Executable." }
    } finally {
        $env:PATH = $savedPath
        $savedPython | ForEach-Object { Set-Item "Env:$($_.Name)" $_.Value }
        Remove-Item $report -ErrorAction SilentlyContinue
    }
}

Push-Location $projectRoot
try {
    $version = (& $Python -c "import shrimpit; print(shrimpit.__version__)").Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Shrimp''It is not installed in this environment.' }
    Write-Host "Shrimp'It $version"

    & $Python -m PyInstaller --noconfirm --clean --log-level WARN --distpath $dist --workpath $work packaging\shrimpit.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    Test-FrozenBuild (Join-Path $bundle 'Shrimpit.exe')

    $zip = Join-Path $dist "Shrimpit-$version-windows-x64-portable.zip"
    Remove-Item $zip -ErrorAction SilentlyContinue
    Compress-Archive -Path $bundle -DestinationPath $zip -CompressionLevel Optimal
    $deliverables = @($zip)

    if (-not $SkipInstaller) {
        $iscc = Find-InnoSetup
        $icon = Join-Path $work 'shrimpit\shrimpit.ico'
        & $iscc /Q "/DAppVersion=$version" "/DSourceDir=$bundle" "/DOutputDir=$dist" "/DIconFile=$icon" packaging\shrimpit.iss
        if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
        $deliverables += Join-Path $dist "Shrimpit-$version-windows-x64-setup.exe"
    }

    foreach ($file in $deliverables) {
        $hash = (Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant()
        $size = [math]::Round((Get-Item $file).Length / 1MB, 1)
        Write-Host "$([IO.Path]::GetFileName($file))  $size Mo  SHA-256 $hash"
    }
} finally {
    Pop-Location
}
