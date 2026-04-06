param(
    [string]$Repo = $(if ($env:DNS_SWITCHER_REPO) { $env:DNS_SWITCHER_REPO } else { "Glorp01/DNS-Switcher" }),
    [string]$InstallDir = "$env:LOCALAPPDATA\DNS Switcher"
)

$ErrorActionPreference = "Stop"
$assetName = "DNS-Switcher-windows-x64.zip"
$releaseUrl = "https://api.github.com/repos/$Repo/releases/latest"

Write-Host "Fetching latest release metadata from $Repo..."
$release = Invoke-RestMethod -Uri $releaseUrl
$asset = $release.assets | Where-Object { $_.name -eq $assetName } | Select-Object -First 1

if (-not $asset) {
    throw "Could not find release asset: $assetName"
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("dns-switcher-" + [guid]::NewGuid().ToString("n"))
$zipPath = Join-Path $tempRoot $assetName
$extractPath = Join-Path $tempRoot "extract"
$exePath = Join-Path $InstallDir "DNS Switcher.exe"

New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
New-Item -ItemType Directory -Path $extractPath -Force | Out-Null
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

Write-Host "Downloading $assetName..."
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath
Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force
Copy-Item -Path (Join-Path $extractPath "DNS Switcher.exe") -Destination $exePath -Force

Write-Host "Installed DNS Switcher to $exePath"
Start-Process -FilePath $exePath
