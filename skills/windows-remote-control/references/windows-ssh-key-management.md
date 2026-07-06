# Windows SSH Key Management

## Key Paths on Windows

Windows OpenSSH stores authorized keys differently for admin vs standard users:

| User type | authorized_keys path |
|-----------|---------------------|
| Administrator | `C:\ProgramData\ssh\administrators_authorized_keys` |
| Standard user | `%USERPROFILE%\.ssh\authorized_keys` |

Most Windows machines run the default user as administrator, so the key goes to `C:\ProgramData\ssh\administrators_authorized_keys`.

## Full Setup: Deploying a New Key (admin user)

For admin users, `echo >>` alone is **insufficient** — the file needs:
- **UTF-8 without BOM** (cmd `echo` outputs ANSI/GBK; `Set-Content -Encoding UTF8` outputs UTF-8 with BOM)
- **ACL restricted to SYSTEM + Administrators only** (inherited permissions cause StrictModes rejection)
- **sshd restart** to pick up the file

### Correct one-shot setup

```bash
# 1. FIRST verify the actual public key content:
cat ~/.ssh/id_ed25519.pub
#    ^-- Critical: don't assume which key you're using

# 2. Deploy — inline PowerShell (works over SSH):
ssh alias powershell -Command "\$p='C:\ProgramData\ssh\administrators_authorized_keys'; \$key='<paste exact pubkey from step 1>'; \$bytes=[System.Text.Encoding]::UTF8.GetBytes(\$key); [System.IO.File]::WriteAllBytes(\$p, \$bytes); \$acl=Get-Acl \$p; \$acl.SetAccessRuleProtection(\$true,\$false); \$acl.SetAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule('BUILTIN\Administrators','FullControl','Allow'))); \$acl.SetAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule('NT AUTHORITY\SYSTEM','FullControl','Allow'))); Set-Acl \$p \$acl; Restart-Service sshd"

# 3. Verify:
ssh -o PreferredAuthentications=publickey user@host cmd /c "echo OK"
```

### Alternative: deploy from existing password-based session

```bash
# If you only have password access, use sshpass + inline PowerShell:
sshpass -p '<password>' ssh user@host powershell -Command "\$p='C:\ProgramData\ssh\administrators_authorized_keys'; \$key='<pubkey>'; \$bytes=[System.Text.Encoding]::UTF8.GetBytes(\$key); [System.IO.File]::WriteAllBytes(\$p, \$bytes); ...ACL commands... ; Restart-Service sshd"
```

### Diagnostic: check file encoding and ACL

```bash
# Check for UTF-8 BOM (first 3 bytes = 239 187 191):
ssh alias powershell -Command "\$bytes=[System.IO.File]::ReadAllBytes('C:\ProgramData\ssh\administrators_authorized_keys'); Write-Host (\$bytes[0..5] -join ' ')"

# Check ACL:
ssh alias powershell -Command "(Get-Acl 'C:\ProgramData\ssh\administrators_authorized_keys').Access"

# Check sshd config for Match Group administrators:
ssh alias cmd /c "type C:\ProgramData\ssh\sshd_config"

# View sshd operational logs for rejection reason:
ssh alias powershell -Command "Get-WinEvent -LogName OpenSSH/Operational -MaxEvents 10"
```

## Removing an Old Key

```bash
# Filter out old key, write back:
ssh alias 'cmd /c "findstr /v \"old-key-identifier\" C:\ProgramData\ssh\administrators_authorized_keys > C:\ProgramData\ssh\administrators_authorized_keys.tmp && move /y C:\ProgramData\ssh\administrators_authorized_keys.tmp C:\ProgramData\ssh\administrators_authorized_keys"'
```

**Pitfall**: `move /y` on Windows may change file ACLs. After moving, verify the new key still works for authentication.

## Replacing Identity Keys on Windows

When consolidating to a single key pair (e.g., switching all machines to `~/.ssh/id_ed25519`):

1. Deploy new public key to `administrators_authorized_keys`
2. Upload new private+public key to `C:\Users\<user>\.ssh\id_ed25519*`
3. Update local `~/.ssh/config` to remove `IdentityFile` override (default key is now correct)
4. Remove old key from `administrators_authorized_keys`
5. Verify bidirectional connectivity

## PowerShell Traps

PowerShell over SSH for file operations is unreliable due to quoting:
- `Add-Content` fails silently
- `Set-Content` / `WriteAllText` may not write
- `-replace` with backtick escaping gets mangled

**Prefer `cmd /c` or `scp`** for file operations on remote Windows machines.
