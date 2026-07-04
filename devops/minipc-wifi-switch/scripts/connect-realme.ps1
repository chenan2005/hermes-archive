$ssid = 'realme GT 7 FDC6'
$iface = 'WLAN'

# Delete old profile
netsh wlan delete profile name="$ssid" 2>$null

# Create XML profile
$xml = @"
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>$ssid</name>
    <SSIDConfig>
        <SSID>
            <name>$ssid</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA3SAE</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>iehx7624</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>
"@

$tmp = [System.IO.Path]::GetTempFileName() + '.xml'
[System.IO.File]::WriteAllText($tmp, $xml, [System.Text.UTF8Encoding]::new($false))

netsh wlan add profile filename="$tmp" interface="$iface"
Remove-Item $tmp -Force

netsh wlan connect name="$ssid" ssid="$ssid" interface="$iface"
Start-Sleep -Seconds 8

$status = netsh wlan show interfaces | Select-String 'SSID'
if ($status -match $ssid) { 
    Write-Host "OK:$ssid" 
} else { 
    Write-Host "FAIL:$ssid" 
}

$gw = (Get-NetRoute -InterfaceAlias $iface -DestinationPrefix '0.0.0.0/0').NextHop
Write-Host "GW=$gw"
