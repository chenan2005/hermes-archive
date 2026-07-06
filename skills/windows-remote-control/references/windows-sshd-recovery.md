# Windows OpenSSH Service Recovery

## Service Binary Missing (sshd.exe deleted)

When `Restart-Service sshd` succeeds (return code 0) but the service immediately
stops, and the event log shows no errors, the sshd.exe binary was likely deleted.

### Step 1: Check the service binary path

```powershell
# Find what the service thinks its binary is
Get-CimInstance Win32_Service -Filter "Name='sshd'" | Select-Object PathName
```

Common non-standard paths: `C:\Tools\OpenSSH\OpenSSH-Win64\sshd.exe`,
`C:\Program Files\OpenSSH\OpenSSH-Win64\sshd.exe`

### Step 2: Verify the binary exists

```powershell
# Search everywhere including WinSxS (Windows component store)
Get-ChildItem -Path "$env:SystemRoot" -Recurse -Filter "sshd.exe" -ErrorAction SilentlyContinue |
    Select-Object FullName, Length
```

### Step 3: Recovery options (choose one)

**Option A: Copy from WinSxS (quick emergency fix)**

```powershell
# Find the WinSxS copy (there may be multiple versions)
$src = Resolve-Path "C:\Windows\WinSxS\amd64_openssh-server-components-onecore_*_none_*\sshd.exe"
Copy-Item $src.Path "$env:SystemRoot\System32\OpenSSH\sshd.exe" -Force
```

Then fix the service path if it points elsewhere:
```powershell
sc.exe config sshd binPath= "C:\Windows\System32\OpenSSH\sshd.exe"
Start-Service sshd
```

**Option B: Install from GitHub MSI (recommended — proper, future-proof)**

Download the latest MSI from
[PowerShell/Win32-OpenSSH releases](https://github.com/PowerShell/Win32-OpenSSH/releases/latest).
The Win64 MSI is named `OpenSSH-Win64-v<version>.msi`.

```bash
# Find the actual download URL via GitHub API
curl -s "https://api.github.com/repos/PowerShell/Win32-OpenSSH/releases/latest" |
    python3 -c "import json,sys; [print(a['browser_download_url']) for a in json.load(sys.stdin)['assets'] if 'Win64' in a['name'] and a['name'].endswith('.msi')]"
```

Transfer to the target and install silently:
```powershell
# Via SCP/SSH
scp OpenSSH-Win64-v10.0.0.0.msi chen_@host:'C:/Users/chen_/Desktop/'

# Install on the target
msiexec /i "C:\Users\chen_\Desktop\OpenSSH-Win64-v10.0.0.0.msi" /quiet /norestart
```

The MSI automatically:
- Installs to `C:\Program Files\OpenSSH\`
- Registers the sshd service with the correct path
- Sets StartType to Automatic
- Includes all dependencies (libcrypto, moduli, sshd-auth, sshd-session, etc.)

After install, verify:
```powershell
Get-Service sshd | Format-List Name,Status,StartType
Get-CimInstance Win32_Service -Filter "Name='sshd'" | Select-Object PathName
# Should show: C:\Program Files\OpenSSH\sshd.exe
netstat -ano | findstr ":22 "
```

**Option C: Manual ZIP install (legacy)**

Only use if the MSI is unavailable. The process from
[Install-Win32-OpenSSH-Wiki](https://github.com/PowerShell/Win32-OpenSSH/wiki/Install-Win32-OpenSSH):

1. Download `OpenSSH-Win64.zip` from releases
2. Extract to `C:\Program Files\OpenSSH`
3. Run `powershell -ExecutionPolicy Bypass -File install-sshd.ps1`
4. `Start-Service sshd`

### Step 4: Clean up stale DISM state

If `Add-WindowsCapability` was previously called and left the feature in
`InstallPending` state, it may conflict with the GitHub install on reboot:

```powershell
Get-WindowsCapability -Online -Name "OpenSSH.Server*" | Format-List Name,State
# If State = InstallPending, clean it up:
Remove-WindowsCapability -Online -Name "OpenSSH.Server~~~~0.0.1.0"
```

## Service Won't Start for Other Reasons

### Check host keys exist

```powershell
Get-ChildItem "$env:ProgramData\ssh\ssh_host_*"
```

### Run sshd in debug mode to see exact error

```powershell
# Run manually in foreground (Ctrl+C to stop)
& "C:\Program Files\OpenSSH\sshd.exe" -d
```

### Check the OpenSSH Operational event log

```powershell
Get-WinEvent -LogName OpenSSH/Operational -MaxEvents 20 -ErrorAction SilentlyContinue
```

### Port 22 still in use by old process

If netstat shows an ESTABLISHED or CLOSE_WAIT connection from a previous
session, the port isn't fully freed. Wait for the TCP timeout or reboot.

## Service Lost After Reboot — DISM InstallPending Collision

If sshd was working, then vanished after a Windows reboot, the likely cause is
a collision between two install methods:
1. `Add-WindowsCapability -Name OpenSSH.Server` was called but timed out →
   DISM state stuck at `InstallPending`, partial files in
   `C:\Windows\System32\OpenSSH\`
2. User gave up and manually installed from GitHub
3. Windows maintenance detected `InstallPending`, cleaned up the manually
   registered service, then failed its own install
4. On reboot, the `UninstallPending` cleanup completed → deleted
   `System32\OpenSSH\` files → service binary gone

Check for this with:
```powershell
Get-WindowsCapability -Online | Where-Object Name -like '*SSH*' |
    Format-List Name,State
```

Clean up the stale state:
```powershell
Remove-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
```

Then re-register the GitHub binary with `sc.exe create` pointing to
`C:\Program Files\OpenSSH\sshd.exe` (NOT System32).

## SSH Port Open But Connection Reset During Key Exchange

### Symptom

```
kex_exchange_identification: read: Connection reset by peer
```

TCP port 22 accepts connections (plain-text tools like `nc` connect fine),
but the SSH handshake fails. Often caused by:
- sshd service crashed after a `schtasks /it` command locked the desktop
- sshd hitting MaxStartups or resource limits

### Diagnosis (from another machine on the same subnet)

```python
import socket
for port, name in [(22, 'SSH'), (5985, 'WinRM'), (445, 'SMB'),
                   (135, 'RPC'), (3389, 'RDP')]:
    s = socket.socket(); s.settimeout(3)
    r = s.connect_ex(('target-ip', port))
    print(f'{port:5} ({name:8}): {\"OPEN\" if r == 0 else \"CLOSED\"}')
    s.close()
```

If SSH port is OPEN (TCP connects) but other ports (WinRM 5985, SMB 445,
RDP 3389) are also open → machine is healthy, only sshd needs restarting.

### Recovery Ladder

1. **WinRM** (recommended when port 5985 is open) — See
   `references/winrm-md4-patch.md` for the Python 3.12+ workaround.
   Connect and restart sshd:
   ```powershell
   Restart-Service sshd -Force
   Start-Sleep 2
   Get-Service sshd | Format-List Name,Status
   netstat -ano | findstr ":22 "
   ```

2. **RDP via xfreerdp + Xvfb** (freeRDP from Linux jumpbox) — Install
   `freerdp2-x11` and `xvfb`. Start a virtual display, then connect:
   ```bash
   Xvfb :99 -screen 0 1024x768x16 &
   export DISPLAY=:99
   xfreerdp /v:host:port /u:user /p:"$PASS" /cert-ignore +wallpaper
   ```
   Inside the RDP session restart the `OpenSSH SSH Server` service.

3. **Wait for auto-recovery** — Windows may eventually restart the hung sshd
   on its own (service recovery timeout ~2 mins).

### Pitfall: `schtasks /it` Destroys SSH

When `schtasks /create /tn ... /it` (interactive mode) is run on a remote
Windows machine via SSH, it can lock the desktop session and break sshd.
The SSH port stays open (TCP handshake completes) but
`kex_exchange_identification` gets RST. Recovery requires restarting sshd
via one of the methods above.

## Register the service

First try the built-in installer:

```powershell
& "C:\Program Files\OpenSSH\OpenSSH-Win64\sshd.exe" install
```

The `&` is required in PowerShell to invoke a quoted path as a command.

**Fallback**: GitHub standalone builds sometimes reject `install` with
`Extra argument install`. Use `sc.exe` directly:

```powershell
sc.exe create sshd binPath= "C:\Program Files\OpenSSH\OpenSSH-Win64\sshd.exe" start= auto
```

Note: there is a space after `=` in `sc.exe` syntax — `binPath= ` not `binPath=`.

**Fixing an existing service's binary path** (when the path is wrong):

```powershell
sc.exe config sshd binPath= "C:\Program Files\OpenSSH\sshd.exe"
```

## Start and enable

```powershell
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
Get-Service sshd | Format-List Name,Status,StartType
```

## Debug mode (foreground, see live logs)

```powershell
& "C:\Program Files\OpenSSH\sshd.exe" -d
```

Useful when the service won't start — shows exactly what's failing. Ctrl+C to
stop, then fix the issue and register as service.

## SCP works, SSH works, but scp from remote says "Connection closed"

Root cause: `C:\ProgramData\ssh\sshd_config` has a relative path for the
sftp subsystem. Fix — use absolute path:

```
Subsystem	sftp	C:\Program Files\OpenSSH\sftp-server.exe
```

Then restart: `sc.exe stop sshd; sc.exe start sshd`

Diagnosis: `ssh` works but `scp` or `sftp` hangs/refuses. Run
`findstr sftp C:\ProgramData\ssh\sshd_config` to check the subsystem path,
then verify the binary exists at that path.

## Check authorized_keys location

Windows OpenSSH admin users read from:
```
C:\ProgramData\ssh\administrators_authorized_keys
```
NOT `C:\Users\<user>\.ssh\authorized_keys` (which is for non-admin users).

```bash
ssh windows-host cmd /c "type C:\ProgramData\ssh\administrators_authorized_keys"
```

## Key deployment (when SSH access is lost but other paths exist)

If the machine is still reachable via RDP, SMB, or physical access but SSH keys
were corrupted, deploy the public key:

```powershell
Add-Content -Path C:\ProgramData\ssh\administrators_authorized_keys -Value "ssh-ed25519 AAAAC3..."
```

From Linux over SSH (using an alternate key that still works):
```bash
ssh host 'powershell -Command "Add-Content -Path C:\ProgramData\ssh\administrators_authorized_keys -Value \"ssh-ed25519 AAAAC3...\""'
```

But `cmd /c echo >>` is more reliable when PowerShell quoting is a problem:
```bash
ssh host "cmd /c \"echo ssh-ed25519 AAAAC3... >> C:\ProgramData\ssh\administrators_authorized_keys\""
```
