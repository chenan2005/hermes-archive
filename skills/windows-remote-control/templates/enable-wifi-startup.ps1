# ============================================================
# enable-wifi-startup.ps1
# Place in user's Startup folder or set as Run key to auto-connect
# WiFi on user login. Intended for out-of-band management when
# the primary network (wired) becomes unreachable.
#
# Deployment (via SSH from a Linux host):
#   scp enable-wifi-startup.ps1 minipc:'C:/Users/chen_/Desktop/'
#   ssh minipc powershell -NoProfile -EncodedCommand "<encoded>"
#   where <encoded> = base64(UTF-16LE):
#     New-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
#       -Name "EnableWiFi" `
#       -Value "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File
#               C:\Users\chen_\Desktop\enable-wifi-startup.ps1" `
#       -PropertyType String -Force
#
# If SCP is unavailable, pipe content:
#   cat enable-wifi-startup.ps1 | ssh minipc 'powershell -NoProfile -Command
#     "$c=[System.IO.StreamReader]::new([System.Console]::OpenStandardInput()).ReadToEnd();
#      Set-Content -Path $env:USERPROFILE\Desktop\enable-wifi-startup.ps1 -Value $c"'
# ============================================================

param(
    [string]$SSID = "ChinaNet-pfwQ-5G",
    [string]$ProfilePath = "$env:TEMP\wifi-profile.xml"
)

# Read password from a companion file (avoid hardcoding in deploy scripts)
$passFile = Join-Path $PSScriptRoot "wifi-password.txt"
if (Test-Path $passFile) {
    $Password = (Get-Content $passFile).Trim()
} else {
    Write-Warning "No wifi-password.txt found. Profile will not be created."
    $Password = $null
}

Write-Host "=== Out-of-Band WiFi Setup ===" -ForegroundColor Cyan

# Step 1: Enable the WLAN adapter (works from any session)
$adapter = Get-NetAdapter -Name "WLAN" -ErrorAction SilentlyContinue
if (-not $adapter) {
    Write-Error "WLAN adapter not found"
    exit 1
}
Enable-NetAdapter -Name "WLAN" -Confirm:$false
Write-Host "[1/4] WLAN adapter enabled" -ForegroundColor Green
Start-Sleep -Seconds 3

# Step 2: Create WiFi profile (skip if already exists)
$existing = netsh wlan show profiles | Select-String $SSID
if (-not $existing -and $Password) {
    Write-Host "[2/4] Creating WiFi profile for $SSID..." -ForegroundColor Yellow
    $xml = @"
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>$SSID</name>
    <SSIDConfig><SSID><name>$SSID</name></SSID></SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM><security>
        <authEncryption><authentication>WPA2PSK</authentication><encryption>AES</encryption><useOneX>false</useOneX></authEncryption>
        <sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>$Password</keyMaterial></sharedKey>
    </security></MSM>
</WLANProfile>
"@
    $xml | Out-File -FilePath $ProfilePath -Encoding UTF8
    netsh wlan add profile filename="$ProfilePath"
    Remove-Item $ProfilePath
    Write-Host "  Profile created" -ForegroundColor Green
} else {
    Write-Host "[2/4] Profile for $SSID already exists" -ForegroundColor Gray
}

# Step 3: Connect (may fail if software radio is off; user must toggle once manually)
Write-Host "[3/4] Connecting to $SSID..." -ForegroundColor Yellow
$connectResult = netsh wlan connect name="$SSID" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Connect command sent" -ForegroundColor Green
} else {
    Write-Warning "  Connect may have failed: $connectResult"
}
Start-Sleep -Seconds 8

# Step 4: Set high interface metric (prevent WiFi from being default route)
Write-Host "[4/4] Setting interface metric..." -ForegroundColor Yellow
Set-NetIPInterface -InterfaceAlias "WLAN" -InterfaceMetric 9999 -ErrorAction SilentlyContinue
Remove-NetRoute -InterfaceAlias "WLAN" -DestinationPrefix "0.0.0.0/0" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "  Metric set, default gateway removed" -ForegroundColor Green

# Summary
$ipInfo = ipconfig | Select-String "无线局域网适配器" -Context 0,8
Write-Host "`n=== WiFi Setup Complete ===" -ForegroundColor Cyan
Write-Host $ipInfo
