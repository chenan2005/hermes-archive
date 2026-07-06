# ============================================================
# enable-wifi-startup.ps1
# Deploy via SSH to auto-enable WiFi radio + connect to management SSID
# on user login. Only works from DESKTOP session (not SSH Session 0).
#
# Deploy:
#   scp enable-wifi-startup.ps1 minipc:'C:/Users/chen_/Desktop/'
#   ssh minipc powershell -NoProfile -Command "... registry Run key ..."
#
# Or place in Startup folder:
#   C:\Users\chen_\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\
# ============================================================

param(
    [string]$SSID = "ChinaNet-pfwQ-5G",
    [string]$Password = "",
    [string]$InterfaceName = "WLAN"
)

# ---- Step 1: Enable OS-level adapter ----
Write-Host "[1/4] Enabling WLAN adapter..."
$adapter = Get-NetAdapter -Name $InterfaceName -ErrorAction SilentlyContinue
if (-not $adapter) {
    Write-Host "ERROR: WLAN adapter not found"
    exit 1
}
Enable-NetAdapter -Name $InterfaceName -Confirm:$false
Start-Sleep -Seconds 3

# ---- Step 2: Show radio state ----
$radioLine = netsh wlan show interfaces | Select-String "\u7535"
Write-Host "Radio: $radioLine"

# ---- Step 3: Add WiFi profile if not exists ----
$profileExists = netsh wlan show profiles | Select-String $SSID
if (-not $profileExists -and $Password) {
    Write-Host "[2/4] Adding WiFi profile for $SSID..."
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
    $tmp = "$env:TEMP\wifi-profile.xml"
    $xml | Out-File -FilePath $tmp -Encoding UTF8
    netsh wlan add profile filename="$tmp"
    Remove-Item $tmp
}

# ---- Step 4: Connect ----
Write-Host "[3/4] Connecting to $SSID..."
netsh wlan connect name="$SSID"
Start-Sleep -Seconds 10

# ---- Step 5: Set high metric to prevent default route hijack ----
Write-Host "[4/4] Setting interface metric..."
Set-NetIPInterface -InterfaceAlias $InterfaceName -InterfaceMetric 9999 -ErrorAction SilentlyContinue

$wifiGw = Get-NetRoute -InterfaceAlias $InterfaceName -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue
if ($wifiGw) {
    Remove-NetRoute -InterfaceAlias $InterfaceName -DestinationPrefix "0.0.0.0/0" -Confirm:$false
    Write-Host "Removed WiFi default gateway (wired still preferred)"
}

# ---- Status ----
Write-Host ""
Write-Host "IP info:"
ipconfig | Select-String "\u65e0\u7ebf\u7f51" -Context 0,8
Write-Host "WiFi setup complete."
