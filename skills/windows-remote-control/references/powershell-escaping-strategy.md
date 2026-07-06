# PowerShell Escaping Strategy

## Core rule

**NEVER inline complex PowerShell through SSH from bash.** The `$`, `|`, `"`,
and backtick escaping across bash→SSH→cmd→PowerShell layers is
exponentially error-prone and nearly impossible to debug.

## Correct pattern: scp + ps1

```bash
# 1. Write script locally
cat > /tmp/script.ps1 << 'EOF'
Get-NetAdapter | Where-Object Status -eq Up | Select Name, MacAddress
EOF

# 2. Upload
scp /tmp/script.ps1 HOST:C:/Users/chen_/script.ps1

# 3. Execute
ssh HOST 'powershell -ExecutionPolicy Bypass -File C:\Users\chen_\script.ps1'
```

Zero escaping risk. Works every time.

## When you MUST inline (simple commands only)

```bash
# cmd.exe -- safe, no special chars to escape:
ssh HOST cmd /c "dir C:\Users\chen_"

# Simple PowerShell -- use single-quote wrapper for SSH:
ssh HOST 'powershell -Command "Get-Service sshd | Select Status"'
```

If it involves `$_`, `|`, `Format-Table`, or more than one `{}` block:
**switch to scp + ps1 immediately.**
