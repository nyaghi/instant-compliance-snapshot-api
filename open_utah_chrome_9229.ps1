param(
    [int]$Port = 9229,
    [string]$ChromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe",
    [string]$ProfileDirectory = "$env:LOCALAPPDATA\CharityClarity\UtahChrome9229"
)

$ErrorActionPreference = "Stop"
$registryUrl = "https://businessregistration.utah.gov/EntitySearch/OnlineEntitySearch"
$debugUrl = "http://127.0.0.1:$Port"

if (-not (Test-Path -LiteralPath $ChromePath -PathType Leaf)) {
    $fallbackChrome = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    if (Test-Path -LiteralPath $fallbackChrome -PathType Leaf) {
        $ChromePath = $fallbackChrome
    } else {
        throw "Google Chrome was not found. Install Chrome or pass -ChromePath."
    }
}

try {
    $existing = Invoke-RestMethod -Uri "$debugUrl/json/version" -TimeoutSec 2
    Write-Host "Utah Chrome is already available on port $Port."
    Write-Host "Browser: $($existing.Browser)"
    $encodedRegistryUrl = [Uri]::EscapeDataString($registryUrl)
    Invoke-RestMethod -Method Put -Uri "$debugUrl/json/new?$encodedRegistryUrl" -TimeoutSec 5 | Out-Null
    return
} catch {
    # The port is not open yet; launch the dedicated Utah Chrome profile.
}

New-Item -ItemType Directory -Path $ProfileDirectory -Force | Out-Null
Start-Process -FilePath $ChromePath -ArgumentList @(
    "--remote-debugging-address=127.0.0.1",
    "--remote-debugging-port=$Port",
    "--user-data-dir=$ProfileDirectory",
    "--no-first-run",
    "--new-window",
    $registryUrl
)

$version = $null
for ($attempt = 1; $attempt -le 20; $attempt++) {
    try {
        $version = Invoke-RestMethod -Uri "$debugUrl/json/version" -TimeoutSec 2
        break
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $version) {
    throw "Chrome opened, but debugging port $Port did not become available."
}

Write-Host "Utah Chrome is ready."
Write-Host "Browser: $($version.Browser)"
Write-Host "Debug URL: $debugUrl"
Write-Host "Leave this Chrome window open while the Utah checker runs."
