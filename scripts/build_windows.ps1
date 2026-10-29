# Build the Windows deliverables into release\: a portable ZIP and an Inno Setup installer, both tested.
# The version comes from src\shrimpit\__init__.py and names every deliverable.
param(
    [string]$Python = "",
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not $Python) { $Python = $venvPython }
$dist = Join-Path $projectRoot 'dist'
$work = Join-Path $projectRoot 'build\pyinstaller'
$release = Join-Path $projectRoot 'release'
$bundle = Join-Path $dist 'ShrimpIt'
$exeName = 'ShrimpIt.exe'

function Get-AppVersion {
    $source = Get-Content (Join-Path $projectRoot 'src\shrimpit\__init__.py') -Raw
    if ($source -notmatch '__version__ = "(\d+\.\d+\.\d+)"') { throw '__version__ must be in the X.Y.Z form.' }
    return $Matches[1]
}

function Initialize-BuildEnvironment {
    # Create the project's virtual environment when it is missing, as described in the README.
    if (-not (Test-Path $Python)) {
        if ($Python -ne $venvPython) { throw "Python not found: $Python" }
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($launcher) { & $launcher.Source -3 -m venv (Split-Path (Split-Path $venvPython)) }
        else { & python.exe -m venv (Split-Path (Split-Path $venvPython)) }
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) { throw 'Could not create .venv: install Python 3.11+.' }
    }
    & $Python -c "import struct, sys; sys.exit(sys.version_info < (3, 11) or struct.calcsize('P') != 8)"
    if ($LASTEXITCODE -ne 0) { throw 'A 64-bit Python 3.11 or later is required.' }

    # The build needs the runtime dependencies, PyInstaller, and Shrimp'It installed from this folder.
    # Single quotes only: Windows PowerShell drops double quotes from native arguments.
    $probe = @'
import importlib.util, pathlib, sys
missing = [name for name in ('PIL', 'PySide6', 'PyInstaller', 'shrimpit') if importlib.util.find_spec(name) is None]
if not missing:
    origin = pathlib.Path(importlib.util.find_spec('shrimpit').origin).resolve().parent
    if origin != pathlib.Path('src/shrimpit').resolve():
        missing.append('shrimpit (installed from another folder)')
print(', '.join(missing))
sys.exit(1 if missing else 0)
'@
    $missing = & $Python -c $probe
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing build dependencies (missing: $missing)"
        & $Python -m pip install -e ".[build]"
        if ($LASTEXITCODE -ne 0) { throw 'Could not install the build dependencies.' }
        $missing = & $Python -c $probe
        if ($LASTEXITCODE -ne 0) { throw "Build dependencies still missing: $missing" }
    }
}

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

function New-PortableArchive([string]$Destination) {
    # ShrimpIt.exe sits at the root of the archive: extract anywhere, then double-click it.
    # Python writes standard '/' separators, unlike .NET Framework's ZipFile in Windows PowerShell.
    Remove-Item $Destination -ErrorAction SilentlyContinue
    $archiveBase = $Destination -replace '\.zip$', ''
    & $Python -c "import shutil, sys; shutil.make_archive(sys.argv[1], 'zip', sys.argv[2])" $archiveBase $bundle
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the portable archive.' }

    # Check the archive as a user would get it: extracted to a folder whose name contains spaces.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($Destination)
    try {
        $names = $archive.Entries | ForEach-Object { $_.FullName }
        if ($names -notcontains $exeName) { throw "$exeName is missing from the root of the archive." }
        if ($names -match '\\') { throw 'The archive contains backslash-separated paths.' }
    } finally {
        $archive.Dispose()
    }
    $extracted = Join-Path $env:TEMP "ShrimpIt portable check $PID"
    Remove-Item $extracted -Recurse -Force -ErrorAction SilentlyContinue
    try {
        [IO.Compression.ZipFile]::ExtractToDirectory($Destination, $extracted)
        Test-FrozenBuild (Join-Path $extracted $exeName)
    } finally {
        Remove-Item $extracted -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Push-Location $projectRoot
try {
    $version = Get-AppVersion
    $baseName = "ShrimpIt-v$version-Windows"
    Write-Host "Shrimp'It $version"
    Initialize-BuildEnvironment
    # Fail early, before the long PyInstaller step, when the installer cannot be built.
    if (-not $SkipInstaller) { $iscc = Find-InnoSetup }

    & $Python -m PyInstaller --noconfirm --clean --log-level WARN --distpath $dist --workpath $work packaging\shrimpit.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

    New-Item -ItemType Directory -Force $release | Out-Null
    $zip = Join-Path $release "$baseName-Portable.zip"
    New-PortableArchive $zip
    $deliverables = @($zip)

    if (-not $SkipInstaller) {
        $setup = Join-Path $release "$baseName-Setup.exe"
        Remove-Item $setup -ErrorAction SilentlyContinue
        $icon = Join-Path $work 'shrimpit\shrimpit.ico'
        & $iscc /Q "/DAppVersion=$version" "/DOutputBaseName=$baseName-Setup" "/DSourceDir=$bundle" `
            "/DOutputDir=$release" "/DIconFile=$icon" packaging\shrimpit.iss
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $setup)) { throw 'Inno Setup compilation failed.' }
        $deliverables += $setup
    }

    foreach ($file in $deliverables) {
        $hash = (Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant()
        $size = [math]::Round((Get-Item $file).Length / 1MB, 1)
        Write-Host "$([IO.Path]::GetFileName($file))  $size Mo  SHA-256 $hash"
    }
    Write-Host "Deliverables written to $release"
} finally {
    Pop-Location
}
