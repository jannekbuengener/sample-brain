# #1321 - remove login autostart for workflow observer.

$ErrorActionPreference = "Continue"
$TaskName = "SampleBrainWorkflowObserver"
$Root = Join-Path $env:LOCALAPPDATA "sample-brain\workflow-observer"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
  Write-Host "Removed Scheduled Task '$TaskName'."
}

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (Get-ItemProperty -Path $runKey -Name $TaskName -ErrorAction SilentlyContinue) {
  Remove-ItemProperty -Path $runKey -Name $TaskName -ErrorAction SilentlyContinue
  Write-Host "Removed HKCU Run entry '$TaskName'."
}

$startup = [Environment]::GetFolderPath("Startup")
$lnkPath = Join-Path $startup "$TaskName.lnk"
if (Test-Path $lnkPath) {
  Remove-Item -Force $lnkPath
  Write-Host "Removed Startup shortcut."
}

$wrapper = Join-Path $Root "state\start_recorder.cmd"
if (Test-Path $wrapper) { Remove-Item -Force $wrapper }

$status = Join-Path $Root "state\autostart.json"
if (Test-Path $status) { Remove-Item -Force $status }

Write-Host "Autostart cleanup done."
