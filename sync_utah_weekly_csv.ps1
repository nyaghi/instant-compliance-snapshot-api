param(
    [string]$WeeklyCheckerDirectory = "$env:USERPROFILE\Desktop\UTAH\UT_Weekly_Status_Checker",
    [string]$PythonExecutable = "",
    [string]$ChromeDebugUrl = "http://127.0.0.1:9229",
    [switch]$OnlyRecheckRequired,
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
    if (-not $PythonExecutable) {
        $pythonCandidates = @(
            "$env:LOCALAPPDATA\Python\bin\python.exe"
        )
        $pythonPrograms = Get-ChildItem -Path "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe" `
            -ErrorAction SilentlyContinue | Sort-Object FullName -Descending
        $pythonCandidates += @($pythonPrograms.FullName)
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($pythonCommand -and $pythonCommand.Source -notlike "*\Microsoft\WindowsApps\*") {
            $pythonCandidates += $pythonCommand.Source
        }
        $PythonExecutable = $pythonCandidates | Where-Object {
            $_ -and (Test-Path -LiteralPath $_ -PathType Leaf)
        } | Select-Object -First 1
    }
    if (-not $PythonExecutable -or -not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
        throw "A working Python executable was not found. Install Python or pass -PythonExecutable with its full path."
    }

    $weeklyArguments = @($weeklyScript)
    if ($ChromeDebugUrl) {
        $weeklyArguments += @("--chrome-debug-url", $ChromeDebugUrl)
    }
    if ($OnlyRecheckRequired) {
        $weeklyArguments += "--only-recheck-required"
    }
    & $PythonExecutable @weeklyArguments
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
