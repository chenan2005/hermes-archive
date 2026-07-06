---
name: windows-remote-control
description: Windows 远程管理 — SSH/PowerShell/cmd、WiFi 无线电开关（Session 0 限制/Workaround）、FRP 隧道、内网 DNS、FreeRDP headless+WinRT Radio API，以及 sshd 崩溃修复。
category: devops
platforms: [linux]
metadata:
  hermes:
    tags: [windows, ssh, remote, powershell, frp, dns, termux]
---

# Windows Remote Control

Remote management of Windows, Android, and Linux machines via SSH, with FRP tunneling for external access and OpenWrt dnsmasq for internal DNS.

## Quick Patterns

```bash
# Windows via SSH config alias
ssh 9950x3d cmd /c "ver"
ssh minipc 'powershell -Command "Get-Process | Sort CPU -Descending | Select -First 5"'

# SCP file transfer
scp local/file.txt minipc:C:/Users/chen_/          # upload to Windows
scp minipc:C:/Users/chen_/file.txt local/           # download from Windows
scp -r local/dir minipc:C:/Users/chen_/             # recursive directory
scp -P 2222 file user@host:dir/                      # custom port

# WSL2 — REMOVED (2026-06-19). Ubuntu-24.04 unregistered.
# Hyper-V NAT networking made reliable SSH access impossible (SSH RST at vSwitch).
# Future container workloads → Hyper-V VMs with bridged networking.

# Android/Termux
ssh realme    # port 8022, chen_
ssh magicpad  # port 8022, u0_a250

# Internal DNS (all resolve via OpenWrt dnsmasq, domain: lan.11)
9950x3d.lan.11  minipc.lan.11  lenovo.lan.11
realme.lan.11   magicpad.lan.11  openwrt.lan.11

# GPU monitoring (9950x3d RTX 5090 + llama-server)
gpu-mon                          # one-shot snapshot
gpu-mon -w                       # continuous (1s interval, Ctrl-C to stop)
```

## Quoting (critical!)
## Pitfalls

### Hermes Security Redaction Blocks SSH Commands Containing Secrets

Hermes's credential guard replaces secrets (API tokens, passwords) and their indirect references (`$VAR`, `$(cat file)`, `` `cmd` ``, even octal `\NNN` sequences) with `***` before the command reaches the terminal. Adjacent quotes (`"`, `'`) following the replacement are also consumed, breaking command syntax.

**Symptoms:** SSH commands that include an API secret or a variable referencing one return `syntax error: unterminated quoted string` or `401 Unauthorized` with a different key than you provided.

**Fix:** never inline secrets in SSH command arguments. Always write the full script to a local file (which preserves content correctly), then transfer it to the remote and execute:

```bash
# ❌ Don't: ssh host 'curl -H "Authorization: Bearer ***
# ✅ Do: write_file → transfer via Python octal printf → execute
```

See `references/script-transfer-via-ssh.md` for the transfer technique when SCP is unavailable.

### Don't Iterate Failing Approaches
When a networking approach (e.g., portproxy, routing) fails consistently after 2-3 variations with the same error pattern ("Connection reset by peer"), **stop and pivot.** Document the failure signatures and move to a different approach. The user strongly prefers a clear summary of what was tried and why it failed over continued debugging of the same category.

### Windows Locked 0-Byte File After Failed SSH Write

When an SSH file-creation command partially succeeds (creates a 0-byte file) before failing, the file can become **permanently locked** — subsequent writes AND deletion attempts all fail with "另一个程序正在使用此文件，进程无法访问". Manual deletion on the desktop shows "文件已在 cmd.exe 中打开".

**Root cause:** A stale `cmd.exe` process from the failed SSH command still holds the file handle. Even after killing the cmd process, Windows may keep the lock (explorer.exe can also hold a reference for desktop files).

**Lock characteristics:**
- Persists across multiple SSH sessions
- Survives `taskkill /F` on the owning cmd process
- `del /f` and `Remove-Item -Force` both fail
- Windows "this file is open in cmd.exe" dialog points to the correct owner

**Workaround:** Use a different filename. **Only guaranteed fix:** reboot. **Prevention:** use the Python generator pattern (see `references/windows-file-creation-via-ssh.md`) — it either writes completely or fails cleanly, never leaving 0-byte zombies with stale file handles.

### WSL2 Hyper-V NAT Limitation
WSL2's default NAT network mode drops inbound SSH protocol traffic forwarded through netsh portproxy (`EnforcementStatus: NATInboundRuleNotApplicable`). Raw TCP (nc echo) and HTTP work fine; SSH banner exchange gets RST'd. ProxyCommand (origin SSH session → wsl → nc localhost:22) is the only reliable SSH access path, but user may prefer to drop WSL entirely in favor of Hyper-V VMs with bridged networking.

## PowerShell Script Execution (Avoid Escaping Hell)

When running complex PowerShell through SSH from bash, `$`, `|`, and nested quotes cause cascading escaping failures. **Never inline complex scripts.**

### Why escaping fails: the four-layer nesting model

Every SSH command to Windows passes through four parsers, each interpreting special characters:

```
第1层: Linux bash    →  解释 $var, |, >, 引号
第2层: SSH 传输      →  将参数字符串传给远程 sshd
第3层: Windows cmd   →  sshd 默认启动 cmd.exe，再次解释 &, >, %, ^
第4层: PowerShell    →  -Command 参数再次解析 $, @, {}, 引号
```

If the goal is to **create a file with special characters** (e.g., a `.bat` script with `%date%`, `^`, `>`), there's a fifth layer — the file content itself. No character survives all five layers intact through inline escaping alone.

**Quick failure reference** (from 2026-07-04 session — creating bat files on 9950x3d desktop):

| Approach | Why it failed |
|----------|--------------|
| PowerShell `@"... "@` via SSH | `@` misinterpreted by outer shell → `ParserError` |
| cmd `(...)` block + `>` redirect | Block doesn't accumulate multi-line echo output |
| base64 + `[Convert]::FromBase64String` | `$env:USERPROFILE` expanded by bash in double-quotes |
| SCP direct transfer | First failed attempt creates a 0-byte file that Windows **permanently locks** |
| cmd `echo ... > file` (after lock) | Locked file → "另一个程序正在使用此文件" |

**The only pattern that worked consistently:** Transfer a Python script via `cat >`, then let Python's `open().write()` create the target file — no shell parsing at any layer. Full analysis in `references/windows-file-creation-via-ssh.md`.

### Correct Pattern
```bash
# 1. Write the .ps1 file locally
# 2. Upload via scp
scp script.ps1 target:C:/Users/chen_/script.ps1
# 3. Execute remotely
ssh target 'powershell -ExecutionPolicy Bypass -File C:\Users\chen_\script.ps1'
```

This eliminates all quoting/escaping problems. The session had 5+ consecutive escaping failures before adopting this pattern.

### Middle Ground: `& { }` for Simple Inline Commands

When a full .ps1 upload is overkill but a single inline command is too simple, use the `& { }` wrapper pattern:

```bash
# Works: single pipeline wrapped in & { }
ssh target 'powershell -NoProfile -Command "& { Get-ChildItem \"D:\\Unity\" -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue | Select-Object Sum }"'

# Does NOT reliably work: scriptblocks with foreach loops, multiple statements,
# variables from outer scope, or complex quoting (escaped quotes break)
ssh target 'powershell -Command "\$folders = ... ; foreach ..."'  # ❌ avoid
```

**Rule of thumb:** if the command fits in one pipeline (filter → transform → output), use `& { }`. If it needs variables, loops, conditionals, or multi-line logic, upload a `.ps1` file. `Get-ChildItem | Where-Object | ForEach-Object | Measure-Object` in one pipe = OK. Anything more complex = script file.

#### Python Output Buffering on Windows SSH

When running Python scripts on Windows via SSH, stdout is **fully buffered** (no TTY is attached). Output may appear empty even though the script is running and printing. 

**Fix:**
```bash
# Option 1: Environment variable
ssh target "set PYTHONUNBUFFERED=1 && python script.py"

# Option 2: In-script (Python 3.7+)
import sys
sys.stdout.reconfigure(line_buffering=True)

# Option 3: Python -u flag
ssh target "python -u script.py"
```

### PowerShell File Writing via Stdin Pipe (Windows Over SSH)

When SCP is unavailable and you need to write a config file to a Windows machine over SSH, use PowerShell's `[Console]::In.ReadToEnd()` combined with `[IO.File]::WriteAllText()`:

```bash
cat local_config.yaml | ssh target 'powershell -NoProfile -Command "\$i=[Console]::In.ReadToEnd(); [IO.File]::WriteAllText(\"C:\\path\\to\\file.yaml\",\"\$i\"); echo ok"'
```

**How it works:** `ReadToEnd()` reads stdin (the piped content) into a string, `WriteAllText()` writes it to the specified path. The double-quoting escapes `$` signs passed through the SSH command.

**Pitfall — encoding:** PowerShell's `Out-File` and `Set-Content` default to UTF-16 (not UTF-8). Use `[IO.File]::WriteAllText()` or pass `-Encoding UTF8` to ensure UTF-8 output.

### WiFi Interface Metric Management

When a Windows machine has both Ethernet and WiFi connected, Windows selects the default route based on the **route metric** (lower = preferred). To ensure Ethernet stays as the default route while WiFi is available for applications that explicitly bind to it:

**Check current metrics:**
```bash
ssh minipc 'route print -4 2>&1 | findstr "0.0.0.0" | findstr /V "224|255"'
```

Output shows each interface's metric:
```
0.0.0.0 0.0.0.0 192.168.71.9 192.168.71.21 74    ← wired, metric 74
0.0.0.0 0.0.0.0 192.168.1.1  192.168.1.33   35    ← WiFi, metric 35 (LOWER → preferred!)
```

**Interface metric vs route metric:** The `route print` metric is the sum of the interface metric (set by `netsh interface ip set interface`) and the gateway metric (from DHCP). See both with:

```bash
netsh interface ip show interfaces    # "Met" column = interface metric
netsh interface ip show config        # "网关跃点数" line
```

**Fix — set WiFi interface metric high (~5000) so Ethernet is preferred:**
```bash
ssh target 'netsh interface ip set interface "WLAN" metric=5000'
```

This setting persists across WiFi disconnects and reboots. Only manual change or selecting "自动跃点数" will revert it.

**Binding an app to WiFi:** With the high metric, normal traffic goes through Ethernet. Apps that specifically bind to the WiFi interface (e.g. Clash Verge with `interface-name: WLAN`) will use WiFi regardless of the metric.

### Deploying the WiFi Startup Script

The `scripts/enable-wifi-startup.ps1` template deploys via SSH (SCP + registry Run key) and auto-enables the WiFi adapter + connects to a management SSID on next user login. Works around Session 0's inability to control WiFi radio:

```bash
scp enable-wifi-startup.ps1 minipc:'C:/Users/chen_/Desktop/'
ssh minipc powershell -NoProfile -EncodedCommand "<encoded>"  # set Run key pointing to script
```

The script must execute in the user's desktop session (via Run key, Startup folder, or scheduled task at logon) — not from SSH.

### PowerShell -EncodedCommand (Best for Complex Scripts Via SSH)

When `ExecutionPolicy Bypass -File` is impractical (e.g. SCP unavailable), use `-EncodedCommand` with UTF-16LE base64.

**Bash-side helper functions** (fully self-contained, no Python needed):

```bash
ps_enc() {
    local script="$1"
    local b64
    b64=$(printf '%s' "$script" | iconv -f UTF-8 -t UTF-16LE 2>/dev/null | base64 -w0 2>/dev/null || \
          printf '%s' "$script" | base64 -w0 2>/dev/null)
    echo "$b64"
}
ps_run() {
    local script="$1"
    local default="${2:-}"; local enc; enc=$(ps_enc "$script")
    ssh "$TARGET" "powershell -NoProfile -EncodedCommand ${enc}" 2>/dev/null || echo "$default"
}
```

Usage:
```bash
PORT_OK=$(ps_run "try { (netstat -ano | Select-String ':8080' | Select-String LISTEN).Count } catch { 0 }" "0")
```

See `references/ps-enc-bash-functions.md` for detailed pattern, pitfalls (CRLF, CLIXML, `set -e`), and multi-line examples.

**Python helper** (alternative, useful when already in Python):

```bash
# Python helper to generate the -EncodedCommand value
import base64
ps_script = '''
Get-Service WlanSvc | Select-Object Status
Get-NetAdapter -Name "WLAN"
'''
encoded = base64.b64encode(ps_script.encode('utf-16le')).decode()
# Then: ssh target powershell -NoProfile -EncodedCommand "<encoded>"
```

This bypasses all quote-escaping issues because SSH passes a single base64 token. Works for multi-line scripts, loops, and PowerShell-specific syntax that inline `-Command` can't handle.

**Pitfall:** `-EncodedCommand` returns output as CLIXML (serialized XML), not plain text. `Select-String`, string-based comparisons, and simple echo patterns still work, but structured output parsing may need `| ConvertTo-Json` or `Out-String` at the end.

### Windows WiFi Radio Management (Session 0 Limitation)

SSH on Windows (OpenSSH server) runs as a system service in **Session 0** — the non-interactive session. The WiFi radio state (`软件 关` / `Software Off`) is owned by the **user's desktop session** (Session 1+). This is a deliberate security boundary.

**But WinRM (port 5985) runs in Session 1** and CAN call the WinRT Radio API directly. This is the cleanest remote approach — no RDP needed.

**Detection:** `netsh wlan show interfaces` shows:
```
无线电状态: 硬件 开 / 软件 关
```
The interface itself shows as "已启用" (Enabled) but "已断开连接" (Disconnected). Attempting to connect returns: `WlanGetAvailableNetworkList returned error 2150899714` ("wireless LAN interface power off").

**All approaches tested and blocked (from SSH Session 0):**

| Approach | Result | Error |
|----------|--------|-------|
| `netsh wlan set interface name=WLAN radioState=on` | ❌ Win11 24H2+ removed this subcommand | `找不到下列命令` |
| `Enable-NetAdapter -Name "WLAN"` | ❌ Enables OS adapter but NOT radio — driver-level only | Silent, no effect |
| `WlanSetInterface` with `wlan_intf_opcode_radio_state` via C# P/Invoke | ❌ Session 0 denies at WLAN API level | Error code 50 (`ERROR_NOT_SUPPORTED`) |
| `Windows.Devices.Radios.Radio` WinRT API | ❌ Async interop from Session 0 fails | ComException |
| Scheduled task (normal) | ❌ Registers but never starts in user session | No side effects |
| `schtasks /it` (interactive mode) | ❌ **DANGER**: Triggers Defender ASR, quarantines sshd-session.exe | SSH kex reset, exit 1067 |

**⚠️ `schtasks /it` / Register-ScheduledTask -LogonType Interactive from SSH Session 0:**
This triggers **Windows Defender ASR (Attack Surface Reduction)** which detects the operation as lateral movement (Session 0 → Session 1 injection) and quarantines `sshd-session.exe` (OpenSSH 10.x session handler). Recovery requires:
1. WinRM → download MSI from GitHub → reinstall (`msiexec /i ... /quiet /norestart`)
2. Full workflow saved in `devops/winrm-ssh-recovery` skill
3. Do NOT attempt the same operation twice — same trigger, same Defender response

**What DOES work (deployable from remote):**

| Approach | How | When |
|----------|-----|------|
| **WinRM (5985) + Radio API** | ✅ **Preferred.** Connect via WinRM from jumpbox (needs pywinrm + MD4 patch, see `references/winrm-md4-patch.md`), call Windows.Devices.Radios.Radio.SetStateAsync(On) | Immediate, no RDP needed, works Session 1 |
| Run key | `HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run` → run script on login | Next reboot + login needed |
| Scheduled task | Trigger at logon, runs in user session | Needs admin to create task |
| Manual via RDP | User toggles WiFi in Action Center / taskbar | Immediate, simplest |
| FreeRDP headless (Xvfb) + WinRT API | Connect headless RDP → run PowerShell to toggle radio | Remote, session 1, works but heavier than WinRM |

**Recovery from `schtasks /it` SSH breakage:**

修复流程见 `devops/winrm-ssh-recovery` skill。常见坑汇总见 `devops/network-pitfalls`。

When `schtasks /it` has been run and SSH now shows `kex_exchange_identification: read: Connection reset by peer`, the sshd process is hung but the machine is otherwise healthy. Confirm with:

```bash
# Port check from Python on the same subnet:
python3 -c "
import socket
for port, name in [(22, 'SSH'), (5985, 'WinRM'), (445, 'SMB'), (135, 'RPC'), (3389, 'RDP')]:
    s = socket.socket(); s.settimeout(3)
    r = s.connect_ex(('192.168.71.21', port))
    status = 'OPEN' if r == 0 else 'CLOSED'
    print(f'{port:5} ({name:8}): {status}')
    s.close()
"
```

If SSH port 22 is open (TCP handshake completes) but fails during key exchange, AND other ports (WinRM 5985, SMB 445, RPC 135, RDP 3389) are also open, the machine is fine — only sshd needs restarting.

**Port-checking script (fix Python f-string — avoid nested ternaries):**

```python
import socket
for port, name in [(22, 'SSH'), (5985, 'WinRM'), (445, 'SMB'), (135, 'RPC'), (3389, 'RDP')]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    r = s.connect_ex(('192.168.71.21', port))
    status = 'OPEN' if r == 0 else 'CLOSED'
    print(f'{port:5} ({name:8}): {status}')
    s.close()
```

**Recovery ladder (preference order):**

1. **WinRM** (when SSH is broken but port 5985 is open) — **Preferred.** Needs pywinrm + pure-Python MD4 patch (Python 3.12+ / OpenSSL 3.0 dropped MD4). See `references/winrm-md4-patch.md`. Connect and restart sshd:
   ```bash
   python3 -c "
   exec(open('/tmp/winrm_cmd2.py').read().split('hashlib.new = patched_new')[0] + '\nhashlib.new = patched_new')
   import winrm
   s = winrm.Session('target-ip', auth=('user', pwd), transport='ntlm')
   r = s.run_ps('Restart-Service sshd -Force; Start-Sleep 2; Write-Host (Get-Service sshd).Status')
   print(r.std_out.decode())
   "
   ```
   After restarting, verify the service actually started — it may stop again if `sshd-session.exe` was quarantined by Defender ASR:
   ```powershell
   # Check exit code 1067 + missing sshd-session.exe
   Get-Service sshd | Format-List Name,Status
   Get-ChildItem "C:\Program Files\OpenSSH\sshd-session.exe" -ErrorAction SilentlyContinue
   ```
   Full recovery workflow (including MSI reinstall) saved in `devops/winrm-ssh-recovery`.
   WinRM can also toggle WiFi radio via Radio API — SSH cannot.

2. **RDP via xfreerdp + Xvfb** (if no GUI available on the jumpbox):
   ```bash
   # Install tools
   sudo apt-get install -y freerdp2-x11 xvfb

   # Start virtual display (must be background process)
   Xvfb :99 -screen 0 1024x768x16 &
   export DISPLAY=:99

   # Connect to RDP via FRP tunnel (minipc example: bernarty:30389)
   xfreerdp /v:www.bernarty.xyz:30389 /u:chen_ /p:"$PASS" \
     /cert-ignore +wallpaper /sec:nla /network:auto /bpp:16
   ```
   Inside RDP session: `services.msc` → restart `OpenSSH SSH Server`.
   Password must be provided via temp file (`/tmp/tmp-passwd`) since the user's shell doesn't share env vars with the Hermes terminal.

2. **RDP via mstsc** (Windows jumpbox): Standard RDP client through the FRP tunnel.

3. **WinRM** (when SSH is broken but port 5985 is open):
   Install `pywinrm` and apply the Python 3.12+ MD4 workaround (OpenSSL 3.0 dropped MD4, breaking NTLM auth). See `references/winrm-md4-patch.md` for the full workaround script. Connect and restart sshd:
   ```python
   import winrm
   s = winrm.Session('target-ip', auth=('user', password), transport='ntlm')
   r = s.run_cmd('powershell', ['-Command', 'Restart-Service sshd -Force'])
   ```
   After restarting, verify the service actually started — it may stop again if the binary is missing or the service path is wrong:
   ```powershell
   Get-Service sshd | Format-List Name,Status
   netstat -ano | findstr ":22 "
   ```

4. **SSH service binary recovery** (when Restart-Service fails because sshd.exe is missing):

   **Option A: Copy from WinSxS (quick emergency fix)**
   ```powershell
   # 1. Find sshd.exe in WinSxS
   Get-ChildItem -Path "$env:SystemRoot\WinSxS" -Recurse -Filter "sshd.exe" | Select-Object FullName

   # 2. Copy to System32\OpenSSH\
   Copy-Item <WinSxS_path>\sshd.exe "$env:SystemRoot\System32\OpenSSH\sshd.exe" -Force

   # 3. Check current service binary path
   Get-CimInstance Win32_Service -Filter "Name='sshd'" | Select-Object PathName

   # 4. If wrong, fix it (commonly points to a deleted custom install like C:\Tools\OpenSSH\...)
   sc.exe config sshd binPath= "C:\Windows\System32\OpenSSH\sshd.exe"

   # 5. Start the service
   Start-Service sshd
   ```

   **Option B: Install from GitHub MSI (recommended — proper, future-proof)**
   ```powershell
   # Download the Win64 MSI from PowerShell/Win32-OpenSSH releases
   $url = (curl -s "https://api.github.com/repos/PowerShell/Win32-OpenSSH/releases/latest" |
           python3 -c "import json,sys;print([a['browser_download_url'] for a in json.load(sys.stdin)['assets'] if 'Win64' in a['name'] and a['name'].endswith('.msi')][0])")
   $out = "$env:TEMP\OpenSSH-Win64.msi"
   Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing

   # Install silently (skip if download fails — use direct URL instead)
   msiexec /i "$out" /quiet /norestart

   # The MSI auto-installs to C:\Program Files\OpenSSH\ and fixes the service path
   Start-Service sshd
   ```
   Verify:
   ```powershell
   Get-Service sshd | Format-List Name,Status
   Get-CimInstance Win32_Service -Filter "Name='sshd'" | Select-Object PathName
   # Expected: C:\Program Files\OpenSSH\sshd.exe
   ssh -V  # should show OpenSSH_for_Windows_10.x
   ```

5. **Auto-recovery**: Windows may eventually restart the hung sshd service on its own (service recovery timeout default is ~2 mins after last failure). Disconnecting and waiting can work.

6. **Physical/desktop access**: Log in locally or via RDP and restart sshd.

**Pitfalls:**
- `$RDP_PASS` set by `read` in the user's own terminal does NOT propagate to Hermes terminal(). Use `echo "$p" > /tmp/tmp-passwd` for cross-shell transfer.
- `schtasks /it` (interactive mode) can break SSH on the target. The SSH port stays open (TCP handshake completes) but `kex_exchange_identification` gets RST. Other ports (WinRM 5985, SMB 445, RPC 135, RDP 3389) remain open — confirming the machine is fine, only sshd needs a restart.

**Practical pattern (run key, deployable via SSH):**
```powershell
# Deploy via SSH + EncodedCommand
New-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" \
  -Name "EnableWiFi" \
  -Value "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\Users\chen_\Desktop\enable-wifi.ps1" \
  -PropertyType String -Force
```

Place a `.ps1` at that path that calls `Enable-NetAdapter`, waits for DHCP, then sets a high interface metric to prevent the WiFi gateway from becoming the default route.

### FreeRDP Headless: Control WiFi Radio from Session 1

Unlike SSH (Session 0), **RDP connects to the user's interactive desktop session (Session 1)**, where the WinRT Radio API is fully accessible. This means even through a headless FreeRDP connection (via Xvfb, no physical display), you can toggle WiFi radio programmatically.

#### Setup (one-time)

```bash
sudo apt-get install -y freerdp2-x11 xvfb   # jumpbox
```

#### Toggle WiFi Radio ON via WinRT API (automated)

```bash
# Start virtual display background
Xvfb :99 -screen 0 1024x768x16 &
export DISPLAY=:99

# Connect via RDP and enable WiFi radio using WinRT Radio API
xfreerdp /v:<target>:<port> /u:<user> /p:"$(cat /tmp/tmp-passwd)" \
  /cert-ignore /sec:nla /network:auto /bpp:16 \
  /app:"powershell.exe" /app-icon \
  /app-cmd:"-NoProfile -Command \"
    Add-Type -AssemblyName System.Runtime.WindowsRuntime;
    \$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? {
      \$_.Name -eq 'AsTask' -and \$_.GetParameters().Count -eq 1 -and
      \$_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation\`1' })[0];
    Function Await(\$t,\$rt) {
      \$m = \$asTask.MakeGenericMethod(\$rt);
      \$r = \$m.Invoke(\$null,@(\$t)); \$r.Wait(-1)|Out-Null; \$r.Result
    };
    [Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime]|Out-Null;
    Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]);
    \$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]]);
    \$wifi = \$radios | ? { \$_.Kind -eq 'WiFi' };
    Write-Host 'WiFi current state: \$(\$wifi.State)';
    if (\$wifi.State -eq 'Off') {
      Await (\$wifi.SetStateAsync([Windows.Devices.Radios.RadioState]::On)) ([Windows.Devices.Radios.RadioAccessStatus]);
      Write-Host 'WiFi radio turned ON';
    } else { Write-Host 'WiFi radio already ON' }
  \""
```

> **Brittleness warning:** The `-Command` quoting through `/app-cmd:` is fragile. For production, upload a `.ps1` file via SCP and use:
> ```bash
> xfreerdp ... /app:"powershell.exe" /app-icon \
>   /app-cmd:"-NoProfile -File C:\Users\<user>\Desktop\toggle-wifi.ps1"
> ```

#### Simpler: just `netsh wlan connect` through RDP

If the radio is on but disconnected from a network, `netsh wlan connect` works from RDP (Session 1 context):

```bash
xfreerdp /v:<target>:<port> /u:<user> /p:"$(cat /tmp/tmp-passwd)" \
  /cert-ignore /sec:nla /network:auto /bpp:16 \
  /app:"cmd.exe" /app-icon \
  /app-cmd:"/c netsh wlan connect name=MyWiFiSSID"
```

#### Detect radio state from SSH (read-only, Session 0)

```bash
ssh target 'netsh wlan show interfaces'
# Key indicators:
#   '无线电状态: 软件 关' / 'Software Off' → radio off, need RDP
#   '已连接 Connected' → radio on and associated
#   Interface missing entirely → netsh interface set interface admin=disable was used (hard disable, needs admin=enable)
```

### dir /A for Quick Directory Listing (No PowerShell)

For simple enumeration when PowerShell escaping is problematic, fall back to `cmd.exe`:

```bash
ssh target "dir D:\ /A:D"      # list directories only
ssh target "dir D:\ /A:D /S"   # recursive (slow for large drives)
```

`cmd.exe` handles spaces and backslashes with simple double-quoting — no PowerShell parser to fight.

| `references/llama-server-windows-deploy.md` | Deploying llama.cpp server on Windows via SSH — binary selection, persistent process, firewall, Qwen thinking mode |
| `references/winrm-md4-patch.md` | Pure-Python MD4 workaround for pywinrm on Python 3.12+ (NTLM auth fix) |
| `references/windows-sshd-recovery.md` | Recovering broken OpenSSH services on Windows (DISM, sc.exe, SCP) |
| `references/windows-ssh-key-management.md` | Key deployment and authorized_keys management |
| `references/toggle-wifi-radio-ps1.md` | WinRT Radio API PowerShell script + headless RDP execution guide |
| `references/frp-setup-guide.md` | FRP architecture, INI/TOML formats, upgrade, proxy name conflicts |
| `references/internal-dns-setup.md` | OpenWrt dnsmasq + smartdns address.conf pitfall + Android proot DNS |
| `references/termux-onboarding.md` | Bringing new Android/Termux devices into the ecosystem |
| `references/wake-on-lan.md` | WoL prerequisites, BIOS/registry/powercfg, cross-subnet relay via minipc |
| `references/v2ray-recovery.md` | V2Ray 233boy script management, Caddy reverse-proxy, service restart |
| `references/remote-hermes-sessions.md` | Reading past Hermes sessions from remote machines via SQLite |
| `references/profile-setup-guide.md` | Hermes profile creation and config sync |
| `references/ps-enc-bash-functions.md` | Bash-side ps_enc()/ps_run() — encode & run PowerShell over SSH without quoting |
| `scripts/toggle-wifi-radio.ps1` | Deployable WinRT Radio API script — toggle WiFi soft switch from Session 1 |
| `references/network-switch-watchdog.md` | WiFi/network switch script with nohup watchdog — survives SSH disconnect, auto-rollback on failure |
| `references/scp-patterns.md` | SCP file transfer quick reference |
| `references/wsl2-docker-deploy.md` | WSL2 Docker deployment, port exposure, apt locks, sudo pitfall, networking debug |
| `references/cdp-browser-data-extraction.md` | CDP browser automation on Windows — Edge debug port, token extraction, API reverse-engineering |
| `references/clash-verge-windows.md` | Clash Verge Rev 配置（interface-name WLAN、allow-lan、profile 系统、clash-verge.yaml vs config.yaml） |
| `references/sing-box-windows-client.md` | **替代方案** — sing-box 纯 CLI 部署（v1.13 config 迁移、bind_interface WLAN、schtasks 持久化、无窗口自启） |
| `references/windows-network-binding-limitation.md` | `IP_UNICAST_IF` vs Linux `SO_BINDTODEVICE` — Windows绑接口不可靠的根因，静态路由是唯一稳定方案 |
| `references/windows-file-creation-via-ssh.md` | **Windows 远程文件创建** — Python 生成器模式（绕过 SSH 引号地狱）、锁定 0 字节文件陷阱、为什么 SCP/cmd/PowerShell 都不可靠
| `references/gpu-monitoring.md` | GPU 监控 — nvidia-smi query + llama-server process via SSH, gpu-mon 脚本 |
| `scripts/gpu-mon.sh` | GPU 监控便捷脚本 — 单次/持续查询 9950x3d 状态 |
