#Requires -Version 5.1
<#
.SYNOPSIS
  Build the #729 Windows Screen-1 portable tester ZIP.

.DESCRIPTION
  Preferred: pyside6-deploy dry-run -> Nuitka standalone.
  Documented Nuitka/librosa blocker -> PyInstaller onedir fallback.

  Hard requirements:
  - Exact Python 3.12.10
  - Exact PySide6 6.11.2 (pilot pin)
  - Release/x64 samplebrain_audio.dll (or -BuildNative)
  - No OneFile / MSI / installer

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\tools\windows\build_distributable.ps1 -BuildNative
#>
param(
    [switch]$BuildNative,
    [switch]$DryRunOnly,
    [string]$Python = "",
    [string]$OutRoot = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location -LiteralPath $RepoRoot

function Get-PackagingPython {
    param([string]$Preferred)
    if ($Preferred -and (Test-Path -LiteralPath $Preferred)) { return (Resolve-Path $Preferred).Path }
    $venvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPy) { return $venvPy }
    throw "Packaging Python not found. Create .venv with Python 3.12.10 and install deps."
}

$Py = Get-PackagingPython -Preferred $Python
$PyVer = & $Py -c "import sys; print('{0}.{1}.{2}'.format(*sys.version_info[:3]))"
if ($PyVer -ne "3.12.10") {
    throw "Pilot packaging requires exact Python 3.12.10; found $PyVer."
}

$SourceSha = (& git -C $RepoRoot rev-parse HEAD).Trim()
$BuildId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ") + "-" + $SourceSha.Substring(0, 12)
$DistRoot = if ($OutRoot) { $OutRoot } else { Join-Path $RepoRoot "dist\packaging" }
$StageDir = Join-Path $DistRoot "stage-$BuildId"
$ArtifactName = "SampleBrain-Screen1-Pilot-$BuildId-win64.zip"
$ArtifactPath = Join-Path $DistRoot $ArtifactName
$DumpbinEvidenceName = "dumpbin-samplebrain_audio-$BuildId.txt"
$BlockerEvidenceName = "nuitka-blocker-$BuildId.txt"

New-Item -ItemType Directory -Force -Path $DistRoot | Out-Null
if (Test-Path -LiteralPath $StageDir) { Remove-Item -LiteralPath $StageDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

# Ensure packaging pins (includes PySide6==6.11.2 for the release path)
& $Py -m pip install -r (Join-Path $RepoRoot "tools\windows\requirements-packaging.txt") | Out-Host

$PySideVer = & $Py -c "import PySide6; print(PySide6.__version__)"
if ($PySideVer -ne "6.11.2") {
    throw "Pilot packaging requires exact PySide6 6.11.2; found $PySideVer."
}

if ($BuildNative) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path -LiteralPath $vswhere)) { throw "vswhere.exe not found; cannot build native audio." }
    $vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vs) { throw "Visual Studio C++ tools not found." }
    $buildDir = Join-Path $RepoRoot "native\audio\build"
    New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
    $cmd = @"
call `"$vs\VC\Auxiliary\Build\vcvarsall.bat`" x64
cd /d `"$buildDir`"
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
ctest -C Release --output-on-failure
"@
    cmd /c $cmd
    if ($LASTEXITCODE -ne 0) { throw "Native audio build/tests failed." }
}

$Dll = Join-Path $RepoRoot "native\audio\build\bin\Release\samplebrain_audio.dll"
if (-not (Test-Path -LiteralPath $Dll)) {
    throw "REQUIRED samplebrain_audio.dll missing (expected native/audio/build/bin/Release/). Packaging acceptance FAIL."
}

# dumpbin dependents (build-machine evidence outside the shipped ZIP)
$vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$DumpbinLog = Join-Path $DistRoot $DumpbinEvidenceName
cmd /c "`"$vs\VC\Auxiliary\Build\vcvarsall.bat`" x64 >nul & dumpbin /DEPENDENTS `"$Dll`" > `"$DumpbinLog`""
if ($LASTEXITCODE -ne 0) { throw "dumpbin /DEPENDENTS failed." }

# Patch a staged copy of pysidedeploy.spec only (never mutate the tracked file).
$TrackedSpec = Join-Path $RepoRoot "tools\windows\pysidedeploy.spec"
$StagedSpec = Join-Path $StageDir "pysidedeploy.spec"
Copy-Item -LiteralPath $TrackedSpec -Destination $StagedSpec -Force
$SpecText = Get-Content -LiteralPath $StagedSpec -Raw
$SpecText = [regex]::Replace($SpecText, "(?m)^project_dir\s*=\s*.*$", "project_dir = $RepoRoot")
$SpecText = [regex]::Replace($SpecText, "(?m)^python_path\s*=\s*.*$", "python_path = $Py")
if ($SpecText -notmatch "(?m)^packages\s*=") {
    $SpecText = $SpecText -replace "(?m)(^\[python\]\r?\n)", "`$1packages = Nuitka==4.1.1`r`n"
} else {
    $SpecText = [regex]::Replace($SpecText, "(?m)^packages\s*=\s*.*$", "packages = Nuitka==4.1.1")
}
$SpecText = [regex]::Replace($SpecText, "(?m)^exec_directory\s*=\s*.*$", "exec_directory = $StageDir")
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($StagedSpec, $SpecText, $utf8NoBom)

$Deploy = Join-Path (Split-Path $Py -Parent) "pyside6-deploy.exe"
if (-not (Test-Path -LiteralPath $Deploy)) {
    $Deploy = & $Py -c "import shutil; print(shutil.which('pyside6-deploy') or '')"
}
if (-not $Deploy -or -not (Test-Path -LiteralPath $Deploy)) {
    throw "pyside6-deploy not found in packaging venv."
}

$Entry = Join-Path $RepoRoot "tools\windows\sample_brain_gui_entry.py"
$DryLog = Join-Path $DistRoot "pyside6-deploy-dry-run-$BuildId.txt"
Write-Host "=== pyside6-deploy --dry-run (Nuitka invocation evidence) ==="
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Deploy --config-file $StagedSpec --mode standalone --force --name SampleBrain --dry-run $Entry 2>&1 |
    Tee-Object -FilePath $DryLog
$deployExit = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($deployExit -ne 0) { throw "pyside6-deploy --dry-run failed with exit $deployExit." }

if ($DryRunOnly) {
    Write-Host "Dry-run only; stopping before standalone build."
    exit 0
}

# Documented Nuitka blocker (librosa/lazy_loader _StubVisitor) across 2.7/2.8/4.1.1.
# Authorized #729 fallback: PyInstaller onedir.
$BlockerNote = Join-Path $DistRoot $BlockerEvidenceName
@"
NUITKA_BLOCKED=1
reason=Nuitka implicit-imports FATAL on module librosa: lazy_loader has no attribute _StubVisitor
reproduced_with=Nuitka 2.7.12, 2.8.10, 4.1.1
python=3.12.10
pyside6=6.11.2
fallback=PyInstaller onedir (tools/windows/sample_brain_screen1.spec)
"@ | Set-Content -LiteralPath $BlockerNote -Encoding ASCII

Write-Host "=== PyInstaller onedir fallback build ==="
$PyInstallerOut = Join-Path $StageDir "pyinstaller-out"
New-Item -ItemType Directory -Force -Path $PyInstallerOut | Out-Null
$SpecFile = Join-Path $RepoRoot "tools\windows\sample_brain_screen1.spec"
& $Py -m PyInstaller --noconfirm --clean --distpath $PyInstallerOut --workpath (Join-Path $StageDir "pyi-work") $SpecFile
if ($LASTEXITCODE -ne 0) { throw "PyInstaller onedir build failed." }

$Standalone = Join-Path $PyInstallerOut "SampleBrain"
if (-not (Test-Path -LiteralPath $Standalone)) {
    throw "Standalone SampleBrain output not found under staged pyinstaller-out."
}

$FinalApp = Join-Path $StageDir "SampleBrain"
if ($Standalone -ne $FinalApp) {
    if (Test-Path -LiteralPath $FinalApp) { Remove-Item -LiteralPath $FinalApp -Recurse -Force }
    Move-Item -LiteralPath $Standalone -Destination $FinalApp
}

$Exe = Join-Path $FinalApp "SampleBrain.exe"
if (-not (Test-Path -LiteralPath $Exe)) { throw "SampleBrain.exe missing in staged SampleBrain folder." }

# Ensure native DLL next to exe (packaging REQUIRED)
$DllDest = Join-Path $FinalApp "samplebrain_audio.dll"
Copy-Item -LiteralPath $Dll -Destination $DllDest -Force

# qwindows.dll presence gate
$QWindows = Get-ChildItem -LiteralPath $FinalApp -Recurse -Filter "qwindows.dll" -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $QWindows) { throw "qwindows.dll missing from standalone artifact - Qt platforms plugin FAIL." }

# Tester note + BUILDINFO (relative evidence IDs only; no machine-local absolute paths)
Copy-Item -LiteralPath (Join-Path $RepoRoot "tools\windows\TESTER_NOTE.md") `
    -Destination (Join-Path $FinalApp "TESTER_NOTE.txt") -Force

$QtVer = & $Py -c "from PySide6.QtCore import qVersion; print(qVersion())"
$NuitkaVer = ((& $Py -m nuitka --version 2>&1) | Select-Object -First 1).ToString().Trim()
$PyInstallerVer = & $Py -c "import PyInstaller; print(PyInstaller.__version__)"

$BuildInfoPath = Join-Path $FinalApp "BUILDINFO.txt"
& $Py (Join-Path $RepoRoot "tools\windows\write_buildinfo.py") `
    --out $BuildInfoPath `
    --build-id $BuildId `
    --source-sha $SourceSha `
    --python $PyVer `
    --pyside6 $PySideVer `
    --qt $QtVer `
    --pyinstaller $PyInstallerVer `
    --nuitka $NuitkaVer `
    --artifact-zip $ArtifactName
if ($LASTEXITCODE -ne 0) { throw "BUILDINFO render/hygiene check failed." }
# Hygiene: refuse common leak patterns in tree names
$Forbidden = @(".venv", ".git", "catalog.db", "__pycache__", "profiles.local.yaml")
$Leaks = Get-ChildItem -LiteralPath $FinalApp -Recurse -Force |
    Where-Object { $Forbidden -contains $_.Name }
if ($Leaks) {
    throw ("Artifact hygiene FAIL: forbidden names present in staged SampleBrain tree.")
}

# Hygiene: refuse absolute path leaks inside shipped text files
foreach ($shipped in @("BUILDINFO.txt", "TESTER_NOTE.txt")) {
    $shippedPath = Join-Path $FinalApp $shipped
    & $Py -c "from pathlib import Path; from src.workbench_distributable_buildinfo import validate_buildinfo_hygiene; validate_buildinfo_hygiene(Path(r'$shippedPath').read_text(encoding='utf-8'))"
    if ($LASTEXITCODE -ne 0) { throw "Artifact hygiene FAIL: absolute path leak in $shipped" }
}

if (Test-Path -LiteralPath $ArtifactPath) { Remove-Item -LiteralPath $ArtifactPath -Force }
Compress-Archive -Path $FinalApp -DestinationPath $ArtifactPath -Force
$Hash = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
$Sidecar = "$ArtifactPath.sha256"
Set-Content -LiteralPath $Sidecar -Value "$Hash  $ArtifactName" -Encoding ASCII
$ExternalInfo = Join-Path $DistRoot "BUILDINFO-$BuildId.txt"
Copy-Item -LiteralPath $BuildInfoPath -Destination $ExternalInfo -Force
Add-Content -LiteralPath $ExternalInfo -Value "artifact_sha256=$Hash" -Encoding UTF8

Write-Host "ARTIFACT=$ArtifactPath"
Write-Host "SHA256=$Hash"
Write-Host "BUILD_ID=$BuildId"
Write-Host "SOURCE_SHA=$SourceSha"
