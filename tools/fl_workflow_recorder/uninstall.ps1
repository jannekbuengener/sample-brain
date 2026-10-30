# #1321 - remove FL Hardware device script. Does not delete local SQLite/spool.

$ErrorActionPreference = "Stop"

$DeviceName = "SBWorkflowObserver"
$HardwareRoot = Join-Path $env:USERPROFILE "Documents\Image-Line\FL Studio\Settings\Hardware"
$DestDir = Join-Path $HardwareRoot $DeviceName

if (Test-Path $DestDir) {
  Remove-Item -Recurse -Force $DestDir
  Write-Host "Removed Hardware\$DeviceName"
} else {
  Write-Host "Device folder not present."
}

Write-Host "Local DB/spool under %LOCALAPPDATA%\sample-brain\workflow-observer left intact (delete manually if desired)."
Write-Host "Also run uninstall_autostart.ps1 to disable login start."
