<#
.SYNOPSIS
    WinRT Radio API — toggle WiFi soft switch (软件开/关)
    Must run in Session 1 (interactive desktop, RDP). SSH Session 0 can't access Radio API.
.DESCRIPTION
    Requires elevated PowerShell and an interactive user session (RDP or local login).
    Deploy via scp + execute via xfreerdp headless.
.PARAMETER Action
    "On" (default) or "Off" — target radio state.
.EXAMPLE
    # Deploy
    scp toggle-wifi-radio.ps1 target:'C:\Users\chen_\toggle-wifi-radio.ps1'

    # Execute via headless RDP
    Xvfb :99 -screen 0 1024x768x16 &
    export DISPLAY=:99
    xfreerdp /v:host:port /u:user /p:"$(cat /tmp/tmp-passwd)" \
      /cert-ignore /sec:nla /network:auto /bpp:16 \
      /app:"powershell.exe" /app-icon \
      /app-cmd:"-NoProfile -ExecutionPolicy Bypass -File C:\Users\chen_\toggle-wifi-radio.ps1"
#>

param([string]$Action = "On")

Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

Function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null

$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$wifi = $radios | ? { $_.Kind -eq 'WiFi' }

if (-not $wifi) {
    Write-Output "ERROR: No WiFi radio device found."
    exit 1
}

Write-Output "Current WiFi radio state: $($wifi.State)"

$target = if ($Action -eq 'On') { [Windows.Devices.Radios.RadioState]::On } else { [Windows.Devices.Radios.RadioState]::Off }
$result = Await ($wifi.SetStateAsync($target)) ([Windows.Devices.Radios.RadioAccessStatus])
Write-Output "Set WiFi state to $Action → result: $result"

$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$wifi = $radios | ? { $_.Kind -eq 'WiFi' }
Write-Output "WiFi radio state after operation: $($wifi.State)"
