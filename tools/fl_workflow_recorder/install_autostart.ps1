# #1321 - zero-touch recorder start at user logon.
# Prefer Scheduled Task; fall back to HKCU Run + Startup shortcut (no admin).

$ErrorActionPreference = "Stop"

$TaskName = "SampleBrainWorkflowObserver"
$PkgRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoHint = Split-Path -Parent (Split-Path -Parent $PkgRoot)
$Root = Join-Path $env:LOCALAPPDATA "sample-brain\workflow-observer"
New-Item -ItemType Directory -Force -Path (Join-Path $Root "state") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null

$Python = $null
if ($env:SAMPLE_BRAIN_RECORDER_PYTHON -and (Test-Path $env:SAMPLE_BRAIN_RECORDER_PYTHON)) {
  $Python = $env:SAMPLE_BRAIN_RECORDER_PYTHON
}
if (-not $Python) {
  $probe = $PkgRoot
  while ($probe) {
    foreach ($rel in @(".venv\Scripts\pythonw.exe", ".venv\Scripts\python.exe")) {
      $cand = Join-Path $probe $rel
      if (Test-Path $cand) { $Python = $cand; break }
    }
    if ($Python) { break }
    $parent = Split-Path $probe -Parent
    if (-not $parent -or $parent -eq $probe) { break }
    $probe = $parent
  }
}
if (-not $Python) {
  $cmd = Get-Command pythonw -ErrorAction SilentlyContinue
  if ($cmd) { $Python = $cmd.Source }
}
if (-not $Python) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { $Python = $cmd.Source }
}
if (-not $Python) {
  $cmd = Get-Command py -ErrorAction SilentlyContinue
  if ($cmd) { $Python = $cmd.Source }
}
if (-not $Python) { throw "No python interpreter found for autostart (set SAMPLE_BRAIN_RECORDER_PYTHON)" }

$ModuleDir = $PkgRoot
$ArgList = if ((Split-Path -Leaf $Python) -eq "py.exe") {
  "-3.12 -m fl_workflow_recorder run"
} else {
  "-m fl_workflow_recorder run"
}

$mechanism = $null
$detail = $null

# 1) Scheduled Task (best restart-on-failure)
try {
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
  $userId = if ($env:USERDOMAIN) { "$env:USERDOMAIN\$env:USERNAME" } else { $env:USERNAME }
  $Principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
  Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
  $mechanism = "scheduled_task"
  $detail = $TaskName
} catch {
  # 2) HKCU Run key (no admin; starts at logon; no visible window when using pythonw)
  $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
  $cmdLine = "`"$Python`" $ArgList"
  # WorkingDirectory is not supported by Run key; use a tiny wrapper cmd/vbs instead.
  $wrapper = Join-Path $Root "state\start_recorder.cmd"
  @"
@echo off
cd /d "$ModuleDir"
start "" /B "$Python" $ArgList
"@ | Set-Content -Encoding ascii $wrapper
  Set-ItemProperty -Path $runKey -Name $TaskName -Value "`"$wrapper`""
  $mechanism = "hkcu_run"
  $detail = $wrapper
  # Only one fallback mechanism — do not also create a Startup shortcut
  # (would double-launch; recorder singleton would reject the second, but avoid it).
}

@{
  schema = "sb.fl_workflow_recorder.autostart.v1"
  task_name = $TaskName
  python = "$Python"
  working_directory = "$ModuleDir"
  mechanism = $mechanism
  detail = "$detail"
  status = "REGISTERED"
} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Root "state\autostart.json")

Write-Host "Autostart registered via $mechanism"
Write-Host "Disable: .\uninstall_autostart.ps1"
