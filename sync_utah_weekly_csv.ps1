param(
    [string]$WeeklyCheckerDirectory = "C:\Users\Dell\Desktop\UTAH\UT_Weekly_Status_Checker",
    [switch]$RunWeeklyChecker
)

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$requiredBranch = "expansion-10-state-lab"
$currentBranch = (& git -C $repositoryRoot branch --show-current).Trim()

if ($LASTEXITCODE -ne 0) {
    throw "Unable to read the current Git branch."
}
if ($currentBranch -ne $requiredBranch) {
    throw "Refusing to continue. Expected branch '$requiredBranch', found '$currentBranch'."
}

$weeklyDirectory = (Resolve-Path -LiteralPath $WeeklyCheckerDirectory).Path
$weeklyScript = Join-Path $weeklyDirectory "run_utah_status_list_weekly.py"
$sourceCsv = Join-Path $weeklyDirectory "UTAH_STATUS_LIST_copy_paste_batches.csv"
$destinationDirectory = Join-Path $repositoryRoot "state_data\utah"
$destinationCsv = Join-Path $destinationDirectory "UTAH_STATUS_LIST_copy_paste_batches.csv"

if ($RunWeeklyChecker) {
    if (-not (Test-Path -LiteralPath $weeklyScript -PathType Leaf)) {
        throw "Weekly Utah checker not found: $weeklyScript"
    }
    & python $weeklyScript
    if ($LASTEXITCODE -ne 0) {
        throw "The weekly Utah checker failed. The repository CSV was not refreshed."
    }
}

if (-not (Test-Path -LiteralPath $sourceCsv -PathType Leaf)) {
    throw "Weekly Utah output CSV not found: $sourceCsv"
}

New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
$temporaryCsv = "$destinationCsv.tmp"
Copy-Item -LiteralPath $sourceCsv -Destination $temporaryCsv -Force
Move-Item -LiteralPath $temporaryCsv -Destination $destinationCsv -Force

$sourceHash = (Get-FileHash -LiteralPath $sourceCsv -Algorithm SHA256).Hash
$destinationHash = (Get-FileHash -LiteralPath $destinationCsv -Algorithm SHA256).Hash
if ($sourceHash -ne $destinationHash) {
    throw "CSV verification failed after copying."
}

Write-Host "Utah staging CSV refreshed locally."
Write-Host "Branch: $currentBranch"
Write-Host "File: $destinationCsv"
Write-Host "No commit, push, branch switch, or deployment was performed."
