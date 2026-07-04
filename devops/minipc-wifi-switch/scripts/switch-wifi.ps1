param(
    [Parameter(Mandatory=$true)]
    [string]$SSID,
    [string]$Password = '',
    [string]$AuthType = 'WPA2PSK'   # WPA2PSK or WPA3SAE
)

$iface = 'WLAN'
$vlessIP = '43.108.41.245'

# Known networks (if password not provided)
$known = @{
    'realme GT 7 FDC6'   = @{ Pass='iehx7624'; Auth='WPA3SAE' }
    'CMCC-C46N-5G'        = @{ Pass=''; Auth='WPA2PSK' }
    'ChinaNet-pfwQ-5G'    = @{ Pass=''; Auth='WPA2PSK' }
}

if (-not $Password -and $known.ContainsKey($SSID)) {
    $Password = $known[$SSID].Pass
    $AuthType = $known[$SSID].Auth
}

Write-Host "=== Switching WiFi to: $SSID ==="

# Delete old profile
netsh wlan delete profile name="$SSID" 2>$null

if ($Password) {
    $xml = @"
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>$SSID</name>
    <SSIDConfig><SSID><name>$SSID</name></SSID></SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>$AuthType</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>$Password</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>
"@
    $tmpFile = [System.IO.Path]::GetTempFileName() + '.xml'
    [System.IO.File]::WriteAllText($tmpFile, $xml, [System.Text.UTF8Encoding]::new($false))
    netsh wlan add profile filename="$tmpFile" interface="$iface"
    Remove-Item $tmpFile -Force
    Write-Host "Profile added (${AuthType})."
}

# Connect
netsh wlan connect name="$SSID" ssid="$SSID" interface="$iface"
Start-Sleep -Seconds 8

# Verify connection
$status = netsh wlan show interfaces | Select-String 'SSID\s+:|State\s+:'
$connected = $status -match $SSID
if ($connected) {
    Write-Host "Connected: $SSID"
} else {
    Write-Host "FAILED to connect"
    exit 1
}

# Get new gateway
$wlanIP = (Get-NetIPAddress -InterfaceAlias $iface -AddressFamily IPv4).IPAddress
$gw = (Get-NetRoute -InterfaceAlias $iface -DestinationPrefix '0.0.0.0/0').NextHop
Write-Host "WLAN IP: $wlanIP, Gateway: $gw"

# Update static route for VLESS
route delete $vlessIP 2>$null
route -p add $vlessIP mask 255.255.255.255 $gw metric 50
Write-Host "Static route: $vlessIP -> $gw (metric 50)"

# Verify Xray
$xray = Get-Process xray -ErrorAction SilentlyContinue
if ($xray) {
    Write-Host "Xray: PID $($xray.Id)"
} else {
    Write-Host "WARN: Xray not running"
}

Write-Host "=== Done ==="
