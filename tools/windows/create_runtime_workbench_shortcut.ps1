# Create a separate producer shortcut. Legacy developer shortcuts remain untouched.
param(
    [Parameter(Mandatory = $true)]
    [string]$RuntimeRoot
)

$ErrorActionPreference = 'Stop'
$RuntimeRoot = (Resolve-Path -LiteralPath $RuntimeRoot).Path
$StartScript = Join-Path $RuntimeRoot 'tools\windows\start_runtime_workbench.cmd'
if (-not (Test-Path -LiteralPath $StartScript)) {
    throw "Runtime launcher not found: $StartScript"
}

$DesktopPath = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $DesktopPath 'Sample Brain Runtime Workbench.lnk'
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $StartScript
$Shortcut.WorkingDirectory = $RuntimeRoot
$Shortcut.Description = 'Start Sample Brain verified runtime'
$Shortcut.Save()

Write-Host "Runtime shortcut created: $ShortcutPath"
