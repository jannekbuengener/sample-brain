# Create or overwrite a desktop shortcut for Sample Brain Local Workbench.
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$StartScript = Join-Path $RepoRoot 'tools\windows\start_workbench.cmd'

if (-not (Test-Path -LiteralPath $StartScript)) {
    throw "Start script not found: $StartScript"
}

$DesktopPath = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $DesktopPath 'Sample Brain Workbench.lnk'

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $StartScript
$Shortcut.WorkingDirectory = $RepoRoot
$Shortcut.Description = 'Start Sample Brain Local Workbench'
$Shortcut.Save()

Write-Host "Desktop shortcut created: $ShortcutPath"
Write-Host "Target: $StartScript"
Write-Host "Working directory: $RepoRoot"
