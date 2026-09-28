# Download and extract required components for BambiBrowser
$ErrorActionPreference = 'Stop'

function Download-Extract {
    param(
        [string]$Url,
        [string]$DestDir
    )
    $zipPath = "$env:TEMP\component.zip"
    Write-Host "Downloading $Url ..."
    Invoke-WebRequest -Uri $Url -OutFile $zipPath -UseBasicParsing
    Write-Host "Extracting to $DestDir ..."
    if (-not (Test-Path $DestDir)) {
        New-Item -ItemType Directory -Path $DestDir | Out-Null
    }
    Expand-Archive -Path $zipPath -DestinationPath $DestDir -Force
    Remove-Item $zipPath
}

# Define target directories under the app directory
$appDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ahkDir = Join-Path $appDir "ahk"
$mpvDir = Join-Path $appDir "mpv"
$bundledMpv = Join-Path $mpvDir "mpv.exe"

# Download latest AutoHotkey installer (zip) from official site
# Note: The official AutoHotkey download redirects to latest version zip
$ahkUrl = "https://www.autohotkey.com/download/ahk.zip"
try {
    Download-Extract -Url $ahkUrl -DestDir $ahkDir
    Write-Host "AutoHotkey downloaded and extracted to $ahkDir"
} catch {
    Write-Warning "Failed to download or extract AutoHotkey: $_"
}

if (Test-Path $bundledMpv) {
    Write-Host "Bundled MPV found at $bundledMpv; skipping download."
} else {
    Write-Warning "Bundled MPV was not found at $bundledMpv. MPV must be supplied separately."
}

Write-Host "Component download script finished."