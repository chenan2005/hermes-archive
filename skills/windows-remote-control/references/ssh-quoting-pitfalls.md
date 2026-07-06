# PowerShell over SSH — quoting traps

When running PowerShell commands via SSH from a Linux/bash shell, special characters get intercepted by the LOCAL shell before reaching PowerShell.

## The single-quote wrapper pattern

```bash
# WRONG — $ and | consumed by local bash:
ssh host powershell -Command "Get-Process | Sort CPU -Descending"

# RIGHT — single-quote the entire SSH command:
ssh host 'powershell -Command "Get-Process | Sort CPU -Descending | Select -First 5"'
```

## Why this happens

When bash parses a double-quoted string, it expands `$var` and treats `|` as pipe. The SSH command never sees these characters. Single-quoting the outer layer preserves everything verbatim.

## Multi-line PowerShell

```bash
ssh host 'powershell -Command "
  Get-Service | Where-Object {\$_.Status -eq \"Running\"} | Format-Table
"'
```

The `\$` inside single quotes prevents bash expansion, and `\"` escapes the inner double quotes for PowerShell.

## Service management patterns

```bash
# Query Windows service (cmd, no quoting issues)
ssh host cmd /c "sc query frpc-service | findstr STATE"

# Restart stuck service
ssh host 'cmd /c "taskkill /f /im frpc.exe 2>nul & timeout /t 2 >nul & sc start frpc-service"'

# Find service binary path
ssh host 'cmd /c "reg query HKLM\SYSTEM\CurrentControlSet\Services\frpc-service\Parameters"'
```

# File operations over SSH

```bash
# Upload: scp (works with SSH config alias)
scp local_file.txt host:C:/path/to/dest/

# Download
scp host:C:/path/to/file.txt ./

# Read remote file
ssh host cmd /c "type C:\\path\\to\\file"

# Write remote file (small content)
ssh host 'powershell -Command "Set-Content -Path C:\\path\\to\\file -Value \\\"content\\\"\"'
```

## The SCP+PS1 pattern — zero-escape complex scripts

When a PowerShell script has `$_`, `|`, `$var`, nested quotes, or multiple commands, inline quoting becomes fragile. Write a `.ps1` file locally, upload via SCP, and execute remotely:

```bash
# 1. Write script locally (no escaping needed)
cat > /tmp/fix.ps1 << 'EOF'
Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | ForEach-Object {
    Write-Host "Adapter: $($_.Name)"
    Write-Host "  MAC: $($_.MacAddress)"
}
EOF

# 2. Upload
scp /tmp/fix.ps1 host:C:/Users/chen_/fix.ps1

# 3. Execute
ssh host 'powershell -ExecutionPolicy Bypass -File C:\Users\chen_\fix.ps1'
```

This pattern avoids ALL escaping issues. Use it whenever the command has `$_`, pipes, or more than ~3 levels of nested quotes.
