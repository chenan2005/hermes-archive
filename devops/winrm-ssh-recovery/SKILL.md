---
name: winrm-ssh-recovery
title: WinRM SSH Recovery for Windows
description: SSH 崩溃恢复（Defender 隔离 sshd-session.exe）— 通过 WinRM 重连、MD4 补丁、重新安装 OpenSSH、WiFi 无线电切换。
---

# WinRM SSH Recovery for Windows

Use when SSH to a Windows machine is down but WinRM (port 5985) is still accessible.

## Prerequisites

- Python 3 with `pywinrm` (`python3-winrm` package on Debian/Ubuntu: `sudo apt install python3-winrm`)
- A Windows account password (stored in `/tmp/tmp-passwd`, cleaned after use)
- Network access to the target on port 5985
## Python 3.12+ MD4 Workaround

Python 3.12 removed MD4 from hashlib. pywinrm needs MD4 for NTLM auth.

Save the following pure-Python MD4 as `/tmp/winrm_cmd2.py` (also available in this skill as `scripts/md4-patch.py`):

```python
# /tmp/winrm_cmd2.py — Pure-Python MD4 monkey-patch for Python 3.12+
import hashlib, struct

class _MD4:
    def __init__(self, data=b''):
        self._buf = bytearray(data)
    def update(self, data): self._buf.extend(data)
    def digest(self):
        buf = bytearray(self._buf) + b'\x80'
        while len(buf) % 64 != 56: buf.append(0)
        buf += struct.pack('<Q', len(self._buf) * 8)
        A, B, C, D = 0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476
        def F(x,y,z): return (x&y)|(~x&z)
        def G(x,y,z): return (x&y)|(x&z)|(y&z)
        def H(x,y,z): return x^y^z
        def lrot(x,n): return ((x<<n)|(x>>(32-n)))&0xFFFFFFFF
        for blk in range(0, len(buf), 64):
            X = list(struct.unpack('<16I', buf[blk:blk+64]))
            AA, BB, CC, DD = A, B, C, D
            for i, s in [(0,3),(1,7),(2,11),(3,19),(4,3),(5,7),(6,11),(7,19),
                         (8,3),(9,7),(10,11),(11,19),(12,3),(13,7),(14,11),(15,19)]:
                if i%4==0: A=lrot((A+F(B,C,D)+X[i])&0xFFFFFFFF,s)
                elif i%4==1: D=lrot((D+F(A,B,C)+X[i])&0xFFFFFFFF,s)
                elif i%4==2: C=lrot((C+F(D,A,B)+X[i])&0xFFFFFFFF,s)
                else: B=lrot((B+F(C,D,A)+X[i])&0xFFFFFFFF,s)
            for n in range(16):
                i, s = [0,4,8,12,1,5,9,13,2,6,10,14,3,7,11,15][n], [3,5,9,13][n%4]
                if n%4==0: A=lrot((A+G(B,C,D)+X[i]+0x5A827999)&0xFFFFFFFF,s)
                elif n%4==1: D=lrot((D+G(A,B,C)+X[i]+0x5A827999)&0xFFFFFFFF,s)
                elif n%4==2: C=lrot((C+G(D,A,B)+X[i]+0x5A827999)&0xFFFFFFFF,s)
                else: B=lrot((B+G(C,D,A)+X[i]+0x5A827999)&0xFFFFFFFF,s)
            for n in range(16):
                i, s = [0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15][n], [3,9,11,15][n%4]
                if n%4==0: A=lrot((A+H(B,C,D)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
                elif n%4==1: D=lrot((D+H(A,B,C)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
                elif n%4==2: C=lrot((C+H(D,A,B)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
                else: B=lrot((B+H(C,D,A)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
            A = (AA+A)&0xFFFFFFFF; B = (BB+B)&0xFFFFFFFF
            C = (CC+C)&0xFFFFFFFF; D = (DD+D)&0xFFFFFFFF
        return struct.pack('<4I',A,B,C,D)
    def copy(self): return _MD4(bytes(self._buf))

# Monkey-patch: preserve original, replace md4
_orig_new = hashlib.new
def _patched_new(name, data=b''):
    if name == 'md4':
        h = _MD4()
        if data: h.update(data)
        return h
    return _orig_new(name, data)
hashlib.new = _patched_new
```

### Usage: connect and run a command via SSH

Store the patch in `/tmp/winrm_cmd2.py`, then when connecting:

```python
exec(open('/tmp/winrm_cmd2.py').read())
import winrm
pwd = open('/tmp/tmp-passwd').read().strip()
s = winrm.Session('192.168.71.21', auth=('chen_', pwd), transport='ntlm')
r = s.run_ps('Write-Host WINRM_OK')
print(r.std_out.decode('utf-8', errors='replace'))
```

## Common Recovery Tasks

### Restart sshd service

```
Restart-Service sshd -Force
Start-Sleep 3
Get-Service sshd | Format-Table Status,Name,StartType
```

### Reinstall OpenSSH when files are missing

If `sshd-session.exe` (required by SSH 10.x) or other binaries are deleted:

```powershell
$url = "https://github.com/PowerShell/Win32-OpenSSH/releases/download/10.0.0.0p2-Preview/OpenSSH-Win64-v10.0.0.0.msi"
$msi = "C:\Users\chen_\OpenSSH-Win64.msi"
Invoke-WebRequest -Uri $url -OutFile $msi -UseBasicParsing
Start-Process msiexec -ArgumentList "/i `"$msi`" /quiet /norestart" -Wait -NoNewWindow
Remove-Item $msi -Force
Restart-Service sshd -Force
```

### Toggle WiFi radio (WinRT API)

```powershell
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
$result = Await ($wifi.SetStateAsync([Windows.Devices.Radios.RadioState]::On)) ([Windows.Devices.Radios.RadioAccessStatus])
Write-Output "Result: $result"
```

## Pitfalls

- **Python 3.12 has no MD4** — must monkey-patch. OpenSSL 3.0+ also disabled MD4.
- **SSH Session 0 vs WinRM Session 1** — WinRM runs in Session 1 (interactive), Radio API only works there.
- **Clean up passwords** — `rm /tmp/tmp-passwd` immediately after use.
- **sshd-session.exe** — OpenSSH 10.x+ uses a split architecture. If this file is deleted, sshd crashes immediately with ExitCode 1067.
- **Do NOT use `Register-ScheduledTask -LogonType Interactive` from SSH** — Windows Defender ASR detects this as lateral movement (Session 0 → Session 1 injection) and quarantines `sshd-session.exe`. This is what causes the crash. Always use WinRM for operations needing Session 1 access.
