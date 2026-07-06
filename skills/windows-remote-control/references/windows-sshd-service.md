# Windows OpenSSH Service Registration (GitHub Install)

When OpenSSH was installed from GitHub (not via Windows optionalfeatures),
the service registration is manual.

## Service Registration (sc.exe)

```powershell
sc.exe create sshd binPath= "\"C:\Program Files\OpenSSH\OpenSSH-Win64\sshd.exe\"" start= auto
sc.exe description sshd "OpenSSH SSH Server - provides secure remote login and file transfer"
sc.exe start sshd
sc.exe query sshd  # verify STATE: 4 RUNNING
```

The `DisplayName` cannot be set via `sc config` reliably — use registry directly:
```powershell
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\sshd" -Name DisplayName -Value "OpenSSH SSH Server"
```

## Remove and re-register

```powershell
sc.exe stop sshd 2>$null; sc.exe delete sshd 2>$null
sc.exe create sshd binPath= "\"C:\Program Files\OpenSSH\OpenSSH-Win64\sshd.exe\"" start= auto
```

## sshd_config Location

The service reads from `C:\ProgramData\ssh\sshd_config`, NOT the binary directory.
If missing, copy from the default template:

```powershell
copy "C:\Program Files\OpenSSH\OpenSSH-Win64\sshd_config_default" "C:\ProgramData\ssh\sshd_config"
```

## SCP/SFTP Subsystem Fix

The default config has `Subsystem sftp sftp-server.exe` (short name).
The service can't find it because PATH doesn't include the OpenSSH directory.
Use the full path:

```
Subsystem	sftp	C:\Program Files\OpenSSH\OpenSSH-Win64\sftp-server.exe
```

Then restart: `sc.exe stop sshd; sc.exe start sshd`

## Authorized Keys (Administrator)

On Windows, admin users use a special authorized_keys file:
`C:\ProgramData\ssh\administrators_authorized_keys`

Not `~/.ssh/authorized_keys`. This is the match rule in sshd_config:
```
Match Group administrators
       AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys
```

Deploy keys with:
```powershell
echo KEY_STRING >> C:\ProgramData\ssh\administrators_authorized_keys
```

To remove a specific key: `findstr /v "MARKER" <infile> > <tmpfile> && move /y <tmpfile> <infile>`

## Why Not nssm?

sshd.exe natively understands Windows service protocol — `sc.exe create` is enough.
nssm is only needed for programs that DON'T (like frpc.exe).

## Pitfall: InstallPending Collision

If `Add-WindowsCapability -Name OpenSSH.Server` was attempted (but timed out/killed),
DISM leaves the capability in `InstallPending` state. This creates a deadly collision:

1. Windows system maintenance detects `InstallPending`
2. It finds a manually-registered `sshd` service
3. **Deletes the manual service** (to "clean up")
4. Then fails to complete its own install
5. Result: after reboot, sshd service is gone

Check for this:
```powershell
Get-WindowsCapability -Online | Where-Object Name -like '*OpenSSH.Server*' | Select Name,State
```

If state is `InstallPending` or `UninstallPending`:
```powershell
Remove-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
# May need reboot to fully clear.
```

**After cleanup**, re-register the GitHub-installed sshd.
