param(
    [Parameter(Mandatory = $true)][string]$Action,
    [Parameter(Mandatory = $true)][Int64]$Hwnd,
    [string]$Name = ""
)

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$ErrorActionPreference = "Stop"

$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd)
if (-not $root) {
    throw "ElementFromHandle failed for hwnd=$Hwnd"
}

function Find-ByName([string]$TargetName) {
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty,
        $TargetName
    )
    return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
}

switch ($Action) {
    "exists" {
        $el = Find-ByName $Name
        if ($el) { Write-Output "true" } else { Write-Output "false" }
    }
    "invoke" {
        $el = Find-ByName $Name
        if (-not $el) { throw "element not found: $Name" }
        $pattern = $null
        if ($el.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
            $pattern.Invoke()
            Write-Output "ok"
        }
        else {
            throw "InvokePattern missing for: $Name"
        }
    }
    "names" {
        $names = New-Object System.Collections.Generic.List[string]
        foreach ($controlType in @(
                [System.Windows.Automation.ControlType]::Button,
                [System.Windows.Automation.ControlType]::CheckBox,
                [System.Windows.Automation.ControlType]::Text
            )) {
            $cond = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                $controlType
            )
            $nodes = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
            foreach ($node in $nodes) {
                $n = $node.Current.Name
                if ($n) { [void]$names.Add($n) }
            }
        }
        ($names | Select-Object -Unique) -join "`n"
    }
    default {
        throw "unknown action $Action"
    }
}
