# Windows Service Discovery — FRP Client

How to find and inspect frpc running as a Windows service,
including nssm-wrapped services where the service binary is nssm.exe,
not frpc.exe directly.

## Find the service

```bash
# List all frp-related services
ssh <alias> cmd /c "sc query state= all | findstr /i frp"
```

## Get service details (path, config)

```bash
# sc qc shows binary path and args
ssh <alias> cmd /c "sc qc <service-name>"
```

If the binary is `nssm.exe` (Non-Sucking Service Manager), nssm wraps the real
frpc.exe. Find the actual config via registry:

```bash
# Read nssm's stored application parameters
ssh <alias> 'cmd /c "reg query HKLM\SYSTEM\CurrentControlSet\Services\<service-name>\Parameters"'
```

This reveals:
- `Application` — actual frpc.exe path
- `AppParameters` — CLI args (e.g. `-c frpc.ini`)
- `AppDirectory` — working directory (where frpc.ini lives)

## Read the config

```bash
ssh <alias> cmd /c "type <AppDirectory>\frpc.ini"
```

## Verify from server side

```bash
ssh bernarty 'sudo ss -tlnp | grep frps'
```

Shows all active FRP proxy ports and confirms which clients are connected.

## Common dead-giveaway signs

- frpc.exe exists but no service registered → FRP was uninstalled, binaries left behind
- Service exists but `sc query` shows STOPPED → service disabled, config still readable
- Config has many `; commented` proxies → historical projects, safe to clean
- No frpc process in `tasklist` → not running (but service may be set to manual start)

## Restarting a stuck frpc service

When `sc stop frpc-service` hangs in `STOP_PENDING` state:

```bash
# Force-kill both frpc and its nssm wrapper, then restart
ssh <alias> 'cmd /c "taskkill /f /im frpc.exe 2>nul & taskkill /f /im nssm.exe 2>nul & timeout /t 3 /nobreak >nul & sc start frpc-service"'
```

The `sc stop` command can leave the service in a non-stoppable state — only `taskkill /f` on both processes unlocks it.

## FRP Token Authentication

Old FRP versions (≤0.51.2) use INI format with `token = <value>` in `[common]`.
Newer versions (≥0.69) use TOML format with `auth.token = "<value>"`.

**Server (frps.ini):**
```ini
[common]
bind_port = 10086
token = <random-hex>
```

**Client INI format (Windows old frpc):**
```ini
[common]
server_addr = <ip>
server_port = 10086
token = <random-hex>
```

**Client TOML format (Linux new frpc):**
```toml
serverAddr = "www.bernarty.xyz"
serverPort = 10086
auth.token = "<random-hex>"
```

Mismatched format → `token in login doesn't match token from configuration` in frps log.
Check which format a running frps expects by looking at its startup command:
- `./frps -p 10086` → no config file, needs INI
- `./frps -c frps.toml` → TOML format
- `./frps -c frps.ini` → INI format

## Note

Avoid `dir /s /b` and `for /r` (recursive directory listing) on Windows drives over SSH —
both follow junction/symlink loops under `C:\Documents and Settings\` and will
time out producing gigabytes of cyclic output.

`wmic` is deprecated on Windows 11 24H2+ and may be missing. Use `Get-CimInstance` in
PowerShell instead for WMI queries, or `sc`/`reg` in cmd for service/registry lookups.
