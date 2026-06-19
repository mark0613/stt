# planning-with-files: resolve the current plan directory (PowerShell mirror).
#
# Resolution order:
#   1. Newest .\.planning\<dir>\ containing task_plan.md
#   2. Empty

param(
    [string]$PlanRoot = (Join-Path (Get-Location) ".planning")
)

function Test-PlanId {
    param([string]$Value)
    return ($Value -match '^[A-Za-z0-9_][A-Za-z0-9._-]*$')
}

if (Test-Path -LiteralPath $PlanRoot -PathType Container) {
    $latest = Get-ChildItem -LiteralPath $PlanRoot -Directory |
        Where-Object { -not $_.Name.StartsWith(".") } |
        Where-Object { Test-PlanId $_.Name } |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "task_plan.md") } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) {
        Write-Output $latest.FullName
    }
}

exit 0
