# #1321 - remove FL Hardware device script. Does not delete local SQLite/spool.

$ErrorActionPreference = "Stop"

$DeviceName = "SBWorkflowObserver"
$LegacyName = "SBWorkflowSignalProbe"
$HardwareRoot = Join-Path $env:USERPROFILE "Documents\Image-Line\FL Studio\Settings\Hardware"
$DestDir = Join-Path $HardwareRoot $DeviceName
$LegacyDir = Join-Path $HardwareRoot $LegacyName
$LegacyScript = Join-Path $LegacyDir "device_SBWorkflowSignalProbe.py"

if (Test-Path $DestDir) {
  Remove-Item -Recurse -Force $DestDir
  Write-Host "Removed Hardware\$DeviceName"
} else {
  Write-Host "Device folder not present."
}

# Undo install.ps1 legacy bridge so FL stops writing durable recorder events.
if (Test-Path $LegacyScript) {
  $text = Get-Content -Raw -Path $LegacyScript -ErrorAction SilentlyContinue
  if ($text -and $text -match "workflow-observer") {
    Remove-Item -Force $LegacyScript
    Write-Host "Removed durable bridge script from Hardware\$LegacyName"
    # If folder is now empty aside from leftovers, leave directory (user may keep probe assets).
  }
}

Write-Host "Local DB/spool under %LOCALAPPDATA%\sample-brain\workflow-observer left intact (delete manually if desired)."
Write-Host "Also run uninstall_autostart.ps1 to disable login start."
