# toggle-wifi-radio.ps1 — WinRT Radio API for WiFi Soft Switch

## Purpose

Toggle the WiFi radio (软开关 — `软件 开/关`) on Windows 11 24H2+ where `netsh wlan set interface radioState` has been removed. **Must run in Session 1 (interactive user desktop).** SSH Session 0 cannot access the WinRT Radio API.

## The Script

Save as `C:\Users\<user>\toggle-wifi-radio.ps1`:

```powershell
<#
.SYNOPSIS
    Use WinRT Radio API to toggle WiFi radio (soft switch).
    Must run in Session 1 (interactive user session), not SSH Session 0.
#>

Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

Function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

# Load the Radio WinRT type
[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null

# Request access and get radios
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$wifi = $radios | ? { $_.Kind -eq 'WiFi' }

if (-not $wifi) {
    Write-Output "ERROR: No WiFi radio device found."
    exit 1
}

Write-Output "Current WiFi radio state: $($wifi.State)"

$targetState = [Windows.Devices.Radios.RadioState]::On
$result = Await ($wifi.SetStateAsync($targetState)) ([Windows.Devices.Radios.RadioAccessStatus])
Write-Output "Set WiFi state to On → result: $result"

# Re-read to confirm
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$wifi = $radios | ? { $_.Kind -eq 'WiFi' }
Write-Output "WiFi radio state after operation: $($wifi.State)"
```

## How to Trigger via Headless RDP

When SSH is dead but RDP is alive:

```bash
# 1. Deploy script (use SCP if SSH works, or RDP app-cmd to write it)
scp toggle-wifi-radio.ps1 target:'C:\Users\chen_\toggle-wifi-radio.ps1'

# 2. Headless RDP to execute it
Xvfb :99 -screen 0 1024x768x16 &
export DISPLAY=:99

xfreerdp /v:<host>:<port> /u:<user> /p:"$(cat /tmp/tmp-passwd)" \
  /cert-ignore /sec:nla /network:auto /bpp:16 \
  /app:"powershell.exe" /app-icon \
  /app-cmd:"-NoProfile -ExecutionPolicy Bypass -File C:\Users\chen_\toggle-wifi-radio.ps1"
```

## Port Check — Confirm Target Alive

Before attempting RDP, scan for open ports to confirm the machine is alive (SSH may be stuck but other services work):

```bash
for port in 22 3389 5985 445 135; do
  nc -zv -w 3 <target> $port 2>&1
done
```

- Port 22 open but `kex_exchange_identification: Connection reset by peer` → sshd daemon hung, not dead
- Port 3389 open → RDP available, can use headless xfreerdp for recovery
- Ports 5985 (WinRM), 445 (SMB), 135 (RPC) all open → machine is healthy, only sshd needs restart

## Detection via SSH (read-only, Session 0)

```bash
ssh target 'netsh wlan show interfaces'
# Look for:
#   无线电状态: 硬件 开 / 软件 关  → radio off (soft switch), need Session 1
#   无线电状态: 硬件 开 / 软件 开  → radio on (normal)
#   状态: 已断开连接               → radio on but not associated
#   状态: 已连接                   → connected to an AP
```

## Related

See SKILL.md section **"FreeRDP Headless: Control WiFi Radio from Session 1"** for the full approach including setup instructions and the recovery ladder.
