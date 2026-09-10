# Explicitly install or update an isolated, pinned Runtime worktree.
param(
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'SampleBrain\runtime'),
    [string]$Channel = 'main',
    [switch]$ReplaceExisting,
    [switch]$CreateShortcut
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$Commit = (& git -C $RepoRoot rev-parse "origin/$Channel").Trim()
if ($Commit -notmatch '^[0-9a-f]{40}$') { throw "Could not resolve origin/$Channel to a full commit SHA." }

if ((Test-Path -LiteralPath $RuntimeRoot) -and -not $ReplaceExisting) {
    Write-Host "Runtime already exists and was left unchanged: $RuntimeRoot"
    exit 0
}

$Parent = Split-Path -Parent $RuntimeRoot
if (-not (Test-Path -LiteralPath $Parent)) {
    New-Item -ItemType Directory -Force -Path $Parent | Out-Null
}
$StagingRoot = "$RuntimeRoot.staging-$PID"
$BackupRoot = "$RuntimeRoot.previous-$PID"

try {
    & git -C $RepoRoot worktree add --detach $StagingRoot $Commit
    if ($LASTEXITCODE -ne 0) { throw 'Could not create staging runtime worktree.' }
    & py -3.12 -m venv (Join-Path $StagingRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create runtime virtual environment.' }
    $Python = Join-Path $StagingRoot '.venv\Scripts\python.exe'
    & $Python -m pip install -r (Join-Path $StagingRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not install runtime requirements.' }
    & $Python -m pip install -e $StagingRoot
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the runtime package.' }
    Push-Location -LiteralPath $StagingRoot
    try {
        & $Python -m src.runtime_provenance --write-manifest --runtime-root $StagingRoot --channel $Channel --commit $Commit
        if ($LASTEXITCODE -ne 0) { throw 'Could not write runtime manifest.' }
        & $Python -m src.runtime_provenance --check --runtime-root $StagingRoot
        if ($LASTEXITCODE -ne 0) { throw 'Staging runtime provenance validation failed.' }
    }
    finally {
        Pop-Location
    }

    if (Test-Path -LiteralPath $RuntimeRoot) {
        & git -C $RepoRoot worktree move $RuntimeRoot $BackupRoot
        if ($LASTEXITCODE -ne 0) { throw 'Could not preserve previous runtime worktree.' }
    }
    & git -C $RepoRoot worktree move $StagingRoot $RuntimeRoot
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path -LiteralPath $BackupRoot) { & git -C $RepoRoot worktree move $BackupRoot $RuntimeRoot }
        throw 'Could not activate staged runtime worktree.'
    }
    if ($CreateShortcut) {
        & (Join-Path $RuntimeRoot 'tools\windows\create_runtime_workbench_shortcut.ps1') -RuntimeRoot $RuntimeRoot
    }
    Write-Host "Verified runtime installed: $RuntimeRoot @ $Commit"
}
catch {
    throw
}
