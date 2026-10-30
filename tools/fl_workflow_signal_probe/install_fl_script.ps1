# #1320 - install FL MIDI probe script via normal Hardware folder path.
# Does NOT install virtual MIDI drivers. On enablement failure: MIDI_DRIVER_REQUIRED / HOLD.

$ErrorActionPreference = "Stop"

$ProbeSrc = Split-Path -Parent $MyInvocation.MyCommand.Path
$DeviceName = "SBWorkflowSignalProbe"
$DeviceSrc = Join-Path $ProbeSrc $DeviceName
$DeviceScript = Join-Path $DeviceSrc "device_SBWorkflowSignalProbe.py"
$HardwareRoot = Join-Path $env:USERPROFILE "Documents\Image-Line\FL Studio\Settings\Hardware"
$DestDir = Join-Path $HardwareRoot $DeviceName
$Spool = Join-Path $env:LOCALAPPDATA "sample-brain\workflow-observer-probe"

if (-not (Test-Path $DeviceScript)) {
  throw "Missing device script at tools/fl_workflow_signal_probe/$DeviceName/device_SBWorkflowSignalProbe.py"
}

New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
New-Item -ItemType Directory -Force -Path $Spool | Out-Null

Copy-Item -Force $DeviceScript (Join-Path $DestDir "device_SBWorkflowSignalProbe.py")
Copy-Item -Force (Join-Path $ProbeSrc "win_fl_input_probe.py") (Join-Path $Spool "win_fl_input_probe.py")
Copy-Item -Force (Join-Path $ProbeSrc "fuse_probe_matrix.py") (Join-Path $Spool "fuse_probe_matrix.py")
Copy-Item -Force (Join-Path $ProbeSrc "MATRIX_RUNBOOK.md") (Join-Path $Spool "MATRIX_RUNBOOK.md") -ErrorAction SilentlyContinue

$gate = [ordered]@{
  schema = "sb.fl_workflow_signal_probe.midi_gate.v1"
  status = "SCRIPT_INSTALLED_AWAITING_CONTROLLER_SELECT"
  dest_dir_exists = (Test-Path $DestDir)
  device_script_exists = (Test-Path (Join-Path $DestDir "device_SBWorkflowSignalProbe.py"))
  note = "Select Controller type 'SB Workflow Signal Probe' in FL MIDI Settings using an EXISTING port. Do not install virtual MIDI. If enablement fails: MIDI_DRIVER_REQUIRED / HOLD / Owner GO."
  spool = "<LOCALAPPDATA>/sample-brain/workflow-observer-probe"
}
$gate | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Spool "midi-gate-status.json")

Write-Host "Installed device script to Hardware\$DeviceName"
Write-Host "Spool helpers copied under LOCALAPPDATA sample-brain/workflow-observer-probe"
Write-Host "NEXT: Open FL Studio -> Options -> MIDI Settings -> set Controller type to 'SB Workflow Signal Probe' on an existing input."
Write-Host "Confirm OnInit via Script Output and fl-events.jsonl heartbeat."
Write-Host "If that fails: set MIDI_DRIVER_REQUIRED and HOLD - do NOT install a driver."
