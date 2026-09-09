# Compatibility helper: create only a shortcut to an existing verified runtime.
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$RuntimeRoot = Join-Path $env:LOCALAPPDATA 'SampleBrain\runtime'
$RuntimeStartScript = Join-Path $RuntimeRoot 'tools\windows\start_runtime_workbench.cmd'
$CreateRuntimeShortcut = Join-Path $RepoRoot 'tools\windows\create_runtime_workbench_shortcut.ps1'

if (-not (Test-Path -LiteralPath $RuntimeStartScript)) {
    throw "Verified runtime not found: $RuntimeRoot. Run .\tools\windows\install_runtime_workbench.ps1 -CreateShortcut first."
}

if (-not (Test-Path -LiteralPath $CreateRuntimeShortcut)) {
    throw "Runtime shortcut helper not found: $CreateRuntimeShortcut"
}

& $CreateRuntimeShortcut -RuntimeRoot $RuntimeRoot
if (-not $?) {
    throw 'Could not create verified runtime shortcut.'
}

Write-Host 'The legacy shortcut helper now creates Sample Brain Runtime Workbench.'
