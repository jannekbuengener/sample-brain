# #1321 - register user Scheduled Task for zero-touch recorder start at logon.
# No Windows Service. Hidden window. Restart on failure (bounded).

$ErrorActionPreference = "Stop"

$TaskName = "SampleBrainWorkflowObserver"
$PkgRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoHint = Split-Path -Parent (Split-Path -Parent $PkgRoot)

# Prefer repo venv python if present beside install source; else py -3.12 / python.
$Python = $null
$VenvPy = Join-Path $RepoHint ".venv\Scripts\pythonw.exe"
if (Test-Path $VenvPy) {
  $Python = $VenvPy
} else {
  $VenvPy2 = Join-Path $RepoHint ".venv\Scripts\python.exe"
  if (Test-Path $VenvPy2) { $Python = $VenvPy2 }
}
if (-not $Python) {
  $cmd = Get-Command py -ErrorAction SilentlyContinue
  if ($cmd) { $Python = "py" } else { $Python = "python" }
}

$ModuleDir = $PkgRoot
$ArgList = if ($Python -eq "py") {
  "-3.12 -m fl_workflow_recorder run"
} else {
  "-m fl_workflow_recorder run"
}

# Working directory must be package root so -m fl_workflow_recorder resolves.
$Action = New-ScheduledTaskAction -Execute $Python -Argument $ArgList -WorkingDirectory $ModuleDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null

$Root = Join-Path $env:LOCALAPPDATA "sample-brain\workflow-observer"
New-Item -ItemType Directory -Force -Path (Join-Path $Root "state") | Out-Null
@{
  schema = "sb.fl_workflow_recorder.autostart.v1"
  task_name = $TaskName
  python = "$Python"
  working_directory = "$ModuleDir"
  status = "REGISTERED"
} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Root "state\autostart.json")

Write-Host "Scheduled Task '$TaskName' registered (AtLogOn, restart-on-failure x3)."
Write-Host "Start now: Start-ScheduledTask -TaskName $TaskName"
Write-Host "Disable: .\uninstall_autostart.ps1"
