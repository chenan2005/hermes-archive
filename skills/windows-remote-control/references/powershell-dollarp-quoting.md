# PowerShell `$_` Quoting with bash + SSH

**Problem:** When running PowerShell through SSH from bash, `$_` (PowerShell's automatic variable for the current pipeline object) gets interpreted by bash as `_` (last argument of previous command). This causes PowerShell command failures like `'Where-Object' is not recognized`.

## Examples That Break

```bash
# ❌ WRONG — `$_` gets eaten by bash
ssh minipc powershell "Get-NetIPInterface | Where-Object { $_.Status -eq 'Up' }"

# ❌ Also wrong — single quotes don't protect PowerShell's `$_`
ssh minipc powershell 'Get-NetIPInterface | Where-Object { $_.Status -eq "Up" }'
```

## The Pattern That Works

Use `.ps1` files (scp + execute) for ANY PowerShell command that references `$_`:

```bash
# ✅ CORRECT — write ps1 locally, scp, execute
cat > /tmp/check_nic.ps1 << 'PSEOF'
Get-NetIPInterface | Where-Object { $_.Status -eq 'Up' } | Format-Table
PSEOF
scp /tmp/check_nic.ps1 minipc:C:/Users/chen_/check_nic.ps1
ssh minipc "powershell -ExecutionPolicy Bypass -File C:\Users\chen_\check_nic.ps1"
```

**Reason:** PowerShell reads `$_` from a `.ps1` file without any bash preprocessing. The SSH command only contains the file path, never the `$_` token.

## Exception: Simple Commands

Commands that don't use `$_` can run inline:

```bash
# ✅ Works — no `$_`
ssh minipc powershell "Get-Service sshd | Start-Service"
```

## Detecting the Problem

The error is usually Chinese (on Chinese Windows): `'Where-Object' �����ڲ����ⲿ���Ҳ���ǿ����еĳ���` which translates to `'Where-Object' is not recognized as an internal or external command`. This happens because the PowerShell command was corrupted by bash/shell processing of `$_`.
