# #1321 - remove Scheduled Task for workflow observer.

$ErrorActionPreference = "Stop"
$TaskName = "SampleBrainWorkflowObserver"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
  Write-Host "Removed Scheduled Task '$TaskName'."
} else {
  Write-Host "No Scheduled Task '$TaskName' found."
}

$Root = Join-Path $env:LOCALAPPDATA "sample-brain\workflow-observer"
$status = Join-Path $Root "state\autostart.json"
if (Test-Path $status) {
  Remove-Item -Force $status
}
