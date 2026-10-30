# #1321 - install FL Workflow Observer (device script + local dirs).
# Does NOT install virtual MIDI drivers. Does NOT alter other MIDI devices.

$ErrorActionPreference = "Stop"

$PkgRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DeviceName = "SBWorkflowObserver"
$DeviceSrc = Join-Path $PkgRoot $DeviceName
$DeviceScript = Join-Path $DeviceSrc "device_SBWorkflowObserver.py"
$HardwareRoot = Join-Path $env:USERPROFILE "Documents\Image-Line\FL Studio\Settings\Hardware"
$DestDir = Join-Path $HardwareRoot $DeviceName
$Root = Join-Path $env:LOCALAPPDATA "sample-brain\workflow-observer"

if (-not (Test-Path $DeviceScript)) {
  throw "Missing device script at tools/fl_workflow_recorder/$DeviceName/device_SBWorkflowObserver.py"
}

New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "spool") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "state") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null

Copy-Item -Force $DeviceScript (Join-Path $DestDir "device_SBWorkflowObserver.py")

# Venue migration: keep #1320 Hardware folder working so existing MIDI Controller
# type "SB Workflow Signal Probe" continues without a rebind. Same recorder script,
# durable spool under workflow-observer/.
$LegacyName = "SBWorkflowSignalProbe"
$LegacyDir = Join-Path $HardwareRoot $LegacyName
New-Item -ItemType Directory -Force -Path $LegacyDir | Out-Null
Copy-Item -Force $DeviceScript (Join-Path $LegacyDir "device_SBWorkflowSignalProbe.py")

$gate = [ordered]@{
  schema = "sb.fl_workflow_recorder.install.v1"
  status = "SCRIPT_INSTALLED"
  dest_dir_exists = (Test-Path $DestDir)
  device_script_exists = (Test-Path (Join-Path $DestDir "device_SBWorkflowObserver.py"))
  legacy_probe_bridge_installed = (Test-Path (Join-Path $LegacyDir "device_SBWorkflowSignalProbe.py"))
  note = "Prefer Controller type 'SB Workflow Observer' on MIDI IN 'Sample Brain Observer' with OUT paired (port 240). Existing 'SB Workflow Signal Probe' binding also loads the durable recorder spool. Do not install virtual MIDI drivers here."
  root = "<LOCALAPPDATA>/sample-brain/workflow-observer"
}
$gate | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Root "state\install-status.json")

Write-Host "Installed device script to Hardware\$DeviceName"
Write-Host "Also bridged durable script into Hardware\$LegacyName (keeps #1320 MIDI binding working)"
Write-Host "Observer root: %LOCALAPPDATA%\sample-brain\workflow-observer"
Write-Host "MIDI: Sample Brain Observer IN/OUT pair (port 240)."
Write-Host "Then run install_autostart.ps1 for zero-touch login start."
