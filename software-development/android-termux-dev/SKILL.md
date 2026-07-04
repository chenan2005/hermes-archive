---
name: android-termux-dev
description: Android Termux 开发环境 — 安装配置、tmux、extra-keys 宏键盘、SSH、FRP 反向连接、APK 下载安装、手机脚本约定、C#/Python/Node.js 开发。
---

# Android Termux Development Environment

## When to use this skill

- User wants to write/run code on an Android phone or tablet
- Setting up a local terminal-based dev environment on Android
- Configuring tmux, neovim, or SSH on Android
- Running C#/.NET on Android via proot-distro
- Comparing Android local dev vs remote dev trade-offs

## Prerequisites

- Android 7.0+, ARM64 device
- F-Droid app installed OR ability to sideload APKs

## Step 1: Install Termux

**Download from GitHub Releases** (preferred over F-Droid):
```
https://github.com/termux/termux-app/releases/latest
```
Pick the `universal` APK (e.g., `termux-app_v*_universal.apk`).

Do NOT use Google Play version — it is outdated and package sources are broken.

F-Droid version works but is repackaged by third parties and occasionally lags behind GitHub releases.

## Step 2: Initial setup

```bash
pkg update && pkg upgrade
```

## Step 3: Core tools

```bash
# Terminal multiplexer
pkg install tmux

# Editor
pkg install neovim

# Languages
pkg install lua
pkg install python
pkg install nodejs

# Version control and tools
pkg install git
pkg install openssh
pkg install curl wget
pkg install ripgrep fd
```

## Step 4: C# / .NET (via proot-distro + Ubuntu)

Termux uses bionic libc, not glibc. .NET SDK has compatibility issues in native Termux (Roslyn compiler may crash with SIGSEGV). The stable approach is running Ubuntu inside a proot container:

```bash
pkg install proot-distro
proot-distro install ubuntu
proot-distro login ubuntu

# Inside Ubuntu:
apt update && apt install dotnet-sdk-9.0

# Exit back to Termux:
exit
```

Daily workflow: Termux → `proot-distro login ubuntu` → `dotnet run`.

## Step 5: SSH server (accept incoming connections)

```bash
pkg install openssh
sshd
# Set password on first run
```

Other devices on same WiFi can connect: `ssh <phone-ip> -p 8022`

**Note**: When you close Termux (swipe away from recents) and reopen it, `sshd` does NOT auto-start.
Run `sshd` again inside the new Termux session to re-enable remote connections.

## Step 6: tmux on small screens

For phone-sized screens, add to `~/.tmux.conf`:

```bash
set -g status-style fg=white,bg=black
set -g mode-keys vi
bind | split-window -h
bind - split-window -v
set -g mouse on

# ⚠️  Android Termux 必加：禁止备用屏幕切换
# Termux 切到后台再返回时，tmux 的 smcup/rmcup 转义序列可能被截断，
# 导致终端乱码。禁用备用屏幕可彻底解决。
set -g terminal-overrides "*:smcup@:rmcup@"
```

On 6-7" phone screens, single-pane tmux is fine. Split panes are too cramped. tmux's main value on phones is session persistence (survives Termux being backgrounded), not multi-pane layout.

## Step 7: Remote development complement

Termux can also serve as a thin client for remote development:

```bash
# SSH into remote dev machine
ssh user@remote-server

# On the remote machine, start tmux
tmux
```

The tmux session runs on the remote machine, not the phone. The phone is just a display terminal.

## Common confusion: Termux ≠ tmux

| | Termux | tmux |
|------|------|------|
| What | Android terminal emulator app | Terminal multiplexer (program) |
| Relationship | You install tmux INSIDE Termux | tmux runs WITHIN Termux's bash |
| Analogy | Termux ≈ Windows Command Prompt | tmux ≈ tabs/splits inside that window |

## Step 8: Sourcing and installing APKs

### Finding APK download URLs (when Google Play is unavailable)

Many APK mirror sites (APKMirror, APKPure, APKCombo) use aggressive Cloudflare blocking that makes automated downloads unreliable. **Aptoide's public API** bypasses this — it returns direct CDN links without any bot detection:

```bash
# Get APK metadata + download URL for any package
curl -s "https://ws75.aptoide.com/api/7/app/getMeta?package_name=<package-name>" \
  | python3 -c "import sys,json; d=json.load(sys.stdin)['data']; print('Version:', d['file']['vername']); print('Size:', d['file']['filesize']); print('URL:', d['file']['path']); print('Malware:', d['file']['malware']['rank']); print('Signer:', d['file']['signature']['owner'])"
```

For Microsoft Remote Desktop specifically: `package_name=com.microsoft.rdc.android`. Response includes:
- Direct `.apk` URL at `pool.apk.aptoide.com/...`
- Version, size, file hash (`md5sum`, not SHA256)
- Malware scan status (`TRUSTED` = clean)
- Developer signing certificate info

The returned APK is signed by the original developer (Microsoft, Google, etc.), not modified — the `malware.rank: TRUSTED` field plus the certificate `signature.owner` confirm this. Always verify these before transferring.

### Transferring APKs via SSH/FRP

**⚠️ FIRST: check `it-assets` skill** for the correct FRP port mapping. Each device has its own FRP tunnel port (e.g. phone=30205, tablet=30177). Using the wrong port sends the file to the wrong device.

For Android devices behind NAT (no inbound SSH), use FRP tunnels to transfer APKs and trigger installation:

```bash
# Transfer APK (prefer FDroid variant for Chinese ROMs)
cat /tmp/app.apk | ssh -p <FRP_PORT> <user>@<frp-server> \
  "cat > /data/data/com.termux/files/home/app.apk"

# OR via SCP (more reliable for larger files):
scp -P <FRP_PORT> /tmp/app.apk <user>@<frp-server>:/data/data/com.termux/files/home/

# Verify integrity
ssh -p <FRP_PORT> <user>@<frp-server> "md5sum app.apk && ls -la app.apk"

# Trigger Android package installer
ssh -p <FRP_PORT> <user>@<frp-server> "termux-open app.apk"
```

SSH timeout for transfers: set to 120s for APKs up to 30MB through FRP tunnels. Always verify `ls -la` on the destination before telling the user to install.

### Self-service cue: when to give commands instead of doing it yourself

This user prefers being handed exact commands when agent-side automation fails:
- If downloading an APK remotely times out or hits bot protection → give a one-line `curl` command to run in Termux, don't keep trying alternative sources.
- If an FRP tunnel is down → give the startup command + the auth token, don't try creative routing through other devices.
- Always state what output to expect (`login to server success` / file size / etc.) so they know it worked.

Signal phrase: user says "直接给我", "你直接说怎么操作", "算了" — switch from agent-does-it to agent-gives-commands mode.

### APK signing and Chinese ROMs

| Variant | Signer | Compatibility |
|---------|--------|---------------|
| **FDroid** (e.g. `v2rayNG_*-fdroid_arm64-v8a.apk`) | F-Droid official key | ✅ Works on all devices |
| **Non-FDroid** (e.g. `v2rayNG_*_arm64-v8a.apk`) | Developer self-signed cert | ⚠️ May show "安装包已损坏" on realme/Xiaomi/Huawei |

If both FDroid and non-FDroid versions show "安装包已损坏", the issue is the Android system's package verification (手机管家/安全中心 on Chinese ROMs). Solutions:
1. Give Termux explicit permission: 设置 → 安全 → 安装未知应用 → Termux → 允许
2. Use a file manager app to browse to and install the APK instead of termux-open
3. Try an older version of the app targeting a lower SDK

### Install methods from Termux

| Method | Command | Notes |
|--------|---------|-------|
| Package installer UI | `termux-open /path/to/app.apk` | Shows UI for user to tap "Install" — preferred |
| CLI silent | `pm install /data/local/tmp/app.apk` | Requires root; files must be under `/data/local/tmp/` |
| ADB | `adb install /path/to/app.apk` | Requires ADB over network or USB |

`pm install` cannot read files in Termux's home (`/data/data/com.termux/files/home/`) due to SELinux policy. Use `termux-open` instead.

### APK size and transfer time

28MB APK through a 15Mbps FRP tunnel takes ~15-30s. Set SSH timeouts to 60-120s for transfers and verify `wc -c` on the destination before telling the user to install.

## Step 9: Keyboard management on tablets

When using Termux on a tablet with a physical or Bluetooth keyboard, the soft keyboard may hide and refuse to re-appear when tapping the input area. This is a common issue on Android tablets.

### Solution 1: Notification bar (fastest)

Swipe down the notification shade → find the Termux persistent notification → expand it → tap **"Show keyboard"**.

### Solution 2: Extra keys row with KEYBOARD button (recommended)

Add the `KEYBOARD` key to your extra-keys in `~/.termux/termux.properties`:

```properties
extra-keys = [['ESC','TAB','LEFT','DOWN','UP','RIGHT','KEYBOARD']]
```

`KEYBOARD` is a toggle — tap to show/hide the soft keyboard.
After editing, run: `termux-reload-settings`.

### Solution 3: Volume key shortcut

While Termux is focused, press **Volume Down + Q** to toggle the extra keys row visibility (not the keyboard itself, but gives you access to the KEYBOARD button if configured).

### Solution 4: Overlay permission (Chinese ROMs)

On realme/OPPO/Xiaomi ROMs, Termux may not have **"display over other apps"** (显示悬浮窗) permission. This can block the notification-based keyboard callback. Check:

Settings → App management → Termux → Display over other apps → Allow.

## Step 10: Extra-keys macros for tmux on tablets

Termux extra-keys support **macros** — space-separated key sequences that can include modifier toggles (`CTRL`, `ALT`, `SHIFT`, `FN`). This is ideal for adding tmux shortcuts as one-tap buttons on tablets.

### Macro syntax

Define a macro using the JSON dict format in the extra-keys array:

```properties
{macro: "CTRL b c", display: "新建"}
```

Processing rules (from `TerminalExtraKeys.java`):
1. `CTRL`, `ALT`, `SHIFT`, `FN` set the modifier flag for the **next** key only
2. The next non-modifier token is sent with those modifiers active
3. Flags are cleared after each non-modifier token
4. Unrecognized tokens are sent as literal Unicode code points

So `CTRL b %` → send `Ctrl+b` → clear → send `%` character.

### ⚠️ CRITICAL PITFALL: SHIFT silently dropped on literal characters

`SHIFT` and `FN` modifiers are **transparently lost** when applied to literal characters (tokens not in the keycode map). From the Termux source:

```java
// non-keycode path: inputCodePoint receives ONLY ctrlDown + altDown
key.codePoints().forEach(codePoint ->
    mTerminalView.inputCodePoint(source, codePoint, ctrlDown, altDown));
// ^^^ shiftDown NOT passed
```

So `SHIFT 5` sends plain `5`, NOT `%`. And `SHIFT APOSTROPHE` sends `'`, NOT `"`.

**Correct approach**: use the target character directly as a literal token.

| Wrong       | Right     | Reason                     |
|-------------|-----------|----------------------------|
| `SHIFT 5`   | `%`       | Send `%` char directly     |
| `SHIFT APOSTROPHE` | `QUOTE`   | `QUOTE` alias → `"` char   |
| `SHIFT 7`   | `&`       | Send `&` char directly     |
| `SHIFT BACKSLASH`  | `~`       | Send `~` char directly     |

`SHIFT` works correctly ONLY with named keycodes (`LEFT`, `RIGHT`, `HOME`, `UP`, `END`, `PGUP`, etc.) because those go through the `KeyEvent` path which passes the full metaState.

### Practical config

A 2-row layout tailored for tablet tmux use — see the full reference:

**📎 `references/termux-tmux-macros.md`** — complete config + macro reference table + popup examples + loading/troubleshooting.

**Two hardware-optimized variants** documented in the reference:
- **MagicPad (12.3" tablet)**: Text labels, PGUP/PGDN, @ at row-2-end
- **realme GT7 (6.8" phone)**: Symbol style (`extra-keys-style = all`), BKSP/ENTER instead of PGUP/PGDN, @ after CTRL, CTRL+copy popup, no custom display labels
- See the "Converting between phone and tablet" section in the reference for migration steps.

**Connection recovery** documented in the reference:
- When both LAN SSH and FRP paths to an Android Termux device are down, physical access is required to restart sshd/frpc
- OpenClash fake-IP (198.18.0.x) can hijack bernarty.xyz DNS — use direct IP 122.51.232.209 as workaround

### Auto-confirm pattern

For tmux commands that prompt `(y/n)`, appending `y` to the macro (`CTRL b x y`) is **theoretically expected** to auto-accept, but **user testing showed it does NOT work in practice** — the `y` character may arrive before tmux sets up the prompt reader, or tmux's prompt reads input through a different path than `inputCodePoint`. Use the non-auto-confirm form (`CTRL b x`) and tap `y` manually when the prompt appears, or define a custom tmux binding that skips confirmation entirely (see `references/termux-tmux-macros.md`).

Quick-start 8-button tmux row:

```properties
extra-keys = [[
    {macro: "CTRL b c", display: "++"},
    {macro: "CTRL b n", display: "→"},
    {macro: "CTRL b p", display: "←"},
    {macro: "CTRL b %", display: "⊞"},
    {macro: "CTRL b QUOTE", display: "⊟"},
    {macro: "CTRL b d", display: "⊘"},
    {macro: "CTRL b [", display: "↕"},
    "KEYBOARD"
]]
```

**Key mappings**: `%` = horizontal split (use `%` directly, NOT `SHIFT 5`), `"` = vertical split (use `QUOTE` alias, NOT `SHIFT APOSTROPHE`).

### Loading

```bash
termux-reload-settings
```
Or: Termux side drawer → Reload Settings.

`termux-reload-settings` works via SSH on Android 14+ (tested on Realme GT7). It sends an IPC broadcast to the Termux app process and completes successfully in ~1s. If it hangs (>10s), run directly on the device.

## Android hotspot and VPN behavior

When an Android phone runs a VPN app (like v2rayNG) with **per-app proxy** (分应用代理), only selected apps on that phone have traffic routed through the VPN. Devices connected to the phone's **hotspot** bypass the VPN entirely — the hotspot's NAT forwarding goes through the system routing stack, not the VPN interface.

To proxy hotspot traffic: use **full VPN mode** (全局代理) instead of per-app proxy, though this still may not intercept hotspot traffic on all Android versions. For reliable proxy coverage for hotspot clients, consider a router-level solution (OpenWrt PassWall) instead.

## Real device experience reference

Tested on Realme GT7 (Dimensity 9400+, 12GB RAM, 6.8" screen):
- `pkg install` works reliably
- `proot-distro` + Ubuntu + .NET SDK 9.0 builds small C# projects without issues
- Bluetooth keyboard + phone for terminal work is functional for emergencies
- Single-pane tmux is comfortable; split panes strain readability on phone screens
- Extra-keys macros work well on 6.8" screens — 8-button row is comfortable, 16-button 2-row is usable but crowded; consider two rows of 5-6 each on phones
- KEYBOARD button essential for tablets — the soft keyboard may not re-trigger from screen taps after it's dismissed by a hardware keyboard
- Chinese realme ROM (realme UI 6.0) needs overlay permission for full notification bar keyboard callback

## Extra-keys macros: SHIFT limitation

When defining macros with `{macro: "CTRL b SHIFT 5", display: "横分"}`, the **SHIFT modifier is NOT passed to `inputCodePoint`** for non-keycode characters. So `SHIFT 5` sends literal `5`, not `%`.

**Fix:** Use the target character directly instead of SHIFT+key:
- `%` instead of `SHIFT 5` (horizontal split)
- `QUOTE` (alias for `"`) or `"` instead of `SHIFT APOSTROPHE` (vertical split)
- `&` instead of `SHIFT 7` (kill-window)

The built-in display map handles special key names (LEFT→←, RIGHT→→, UP→↑, DOWN→↓) automatically. Direction keys don't need a custom `display`.

**JSON dict format for macros:**
```properties
extra-keys = [[
    {key: ESC, display: "ESC/d", popup: {macro: "CTRL b d", display: "分离"}},
    {key: "/", display: "/竖分", popup: {macro: "CTRL b QUOTE", display: "竖分"}},
    ...
]]
```
Macros use space-separated tokens: `CTRL`/`ALT`/`SHIFT`/`FN` set a modifier for the **next** token, then auto-reset.

## Reverse SSH: Termux → Laptop via FRP

Configure an Android Termux device to connect back to the laptop (the "hub" machine) through an FRP tunnel. This is the **reverse** of the usual inbound-SSH pattern — the mobile device initiates the connection, which works even when the mobile device is on a different network or behind NAT.

### Use case

- Start a tmux session on the laptop **from** the phone/tablet
- Resume existing tmux sessions remotely
- Access the laptop's full environment from a mobile terminal

### Prerequisites

- Laptop already has FRP client running on port 22 (e.g. `bernarty:30234 → laptop:22`)
- Mobile Termux has FRP client running (required for the laptop→device direction; the reverse direction uses the laptop's FRP tunnel)

### Step 1: SSH config on the mobile device

Create `~/.ssh/config` on the mobile Termux:

```
Host laptop
    HostName <frp-server-domain>
    Port <laptop-frp-port>
    User <laptop-username>
    StrictHostKeyChecking accept-new
    ConnectTimeout 10
```

Example:
```
Host laptop
    HostName www.bernarty.xyz
    Port 30234
    User chenan
    StrictHostKeyChecking accept-new
    ConnectTimeout 10
```

### Step 2: Generate and exchange SSH keys

On the mobile Termux:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Then add the public key to the laptop's `~/.ssh/authorized_keys`. Add a comment line identifying the device.

### Step 3: Verify the connection

```bash
ssh laptop "hostname && whoami"
```

Should return the laptop's hostname and your laptop username without a password prompt.

### Step 4: Tmux shortcut functions

Add to the mobile device's `~/.bashrc`:

```bash
# FRP tunnel shortcuts to laptop (本机)
rta() { ssh laptop -t "tmux attach -t ${1:-main}" 2>/dev/null || ssh laptop -t "tmux new -s ${1:-main}"; }
rtc() { ssh laptop -t "tmux new -s ${1:-main}"; }
```

| Command | Behavior |
|---------|----------|
| `rta` | Re-attach to existing tmux session named `main` on laptop |
| `rta work` | Re-attach to session `work` |
| `rtc` | Create a new session named `main` |
| `rtc dev` | Create a new session named `dev` |

The `-t` flag on ssh forces PTY allocation, which is required for tmux to work.

### Step 4a (advanced): LAN + FRP dual-path shortcuts

When the Termux device has a local LAN connection to the laptop (same WiFi subnet) *and* an FRP tunnel for when it's remote, set up dual-path commands:

1. Add a `laptop-lan` SSH host to `~/.ssh/config` for the LAN path:
```
Host laptop-lan
    HostName <laptop-lan-ip>
    Port 22
    User <laptop-username>
    StrictHostKeyChecking accept-new
    ConnectTimeout 5
```

2. Replace/upgrade the basic functions with dual-path variants in `~/.bashrc`:
```bash
# Tmux shortcuts to laptop
# LAN (local network, fast)
rta() { ssh laptop-lan -t "tmux attach -t ${1:-main}" 2>/dev/null || ssh laptop-lan -t "tmux new -s ${1:-main}"; }
rtc() { ssh laptop-lan -t "tmux new -s ${1:-main}"; }
# FRP tunnel (remote)
rtat() { ssh laptop -t "tmux attach -t ${1:-main}" 2>/dev/null || ssh laptop -t "tmux new -s ${1:-main}"; }
rtct() { ssh laptop -t "tmux new -s ${1:-main}"; }
```

| Command | Path | Use case |
|---------|------|----------|
| `rta` / `rtc` | LAN (laptop-lan) | Same WiFi, fast, no tunnel overhead |
| `rtat` / `rtct` | FRP tunnel (laptop) | Remote / mobile data |

3. **Optional: startup banner** — add at the very end of `~/.bashrc` so the user sees available commands when Termux starts:
```bash
echo ""
echo "========================================"
echo "  rta  <会话>  — 局域网连本机 tmux"
echo "  rtc  <会话>  — 局域网本机新建 tmux"
echo "  rtat <会话>  — FRP 隧道连本机 tmux"
echo "  rtct <会话>  — FRP 隧道本机新建 tmux"
echo "  默认会话名: main"
echo "========================================"
```

### ⚠️ Quoting pitfall: `${1:-main}` in SSH commands

When writing the above functions into `~/.bashrc` **via SSH** (e.g. `ssh device "cat >> ~/.bashrc ..."`), the outer quoting matters:

- **Single quotes** for the SSH command string: `ssh device 'cat >> ~/.bashrc << '\''EOF'\'' ... EOF'` — `${1:-main}` is preserved correctly because single quotes prevent local shell expansion.
- **Double quotes** for the SSH command string: `ssh device "cat >> ~/.bashrc ..."` — `${1:-main}` is **expanded by the local shell** before being sent. Must escape: `\${1:-main}`.

Rule of thumb: when piping a heredoc through SSH, use single quotes for the outermost SSH command to avoid escaping headaches.

### Verification

From the mobile device:

```bash
# Test LAN path
ssh laptop-lan "hostname && whoami"
# Test FRP path
ssh laptop "hostname && whoami"
# Test tmux functions
source ~/.bashrc && ssh laptop -t "tmux new -s test -d && tmux has-session -t test && echo OK"
type rta rtc rtat rtct
# Clean up:
ssh laptop -t "tmux kill-session -t test"
```

### Troubleshooting

- **Permission denied**: The mobile device's public key is not in the laptop's `authorized_keys`. Generate and add it.
- **No route to host (LAN)**: The device is not on the same WiFi subnet, or the laptop's firewall (UFW/iptables) blocks the subnet. Check with `ping <laptop-ip>`.
- **No route to host (FRP)**: The FRP server is unreachable or the FRP tunnel is down. Check `frpc` status on both sides.
- **open terminal failed: not a terminal**: SSH lacks a PTY. Make sure `-t` flag is used in the ssh command (the `rta`/`rtc` functions include it).
- **bashrc not sourcing**: Verify no `.bash_profile` or `.profile` overrides the bashrc sourcing path. On Termux, interactive bash shells source `~/.bashrc` directly.
- **SSH functions defined but `type` says 'not found'**: In SSH non-interactive mode, `.bashrc` is not sourced automatically. Run `source ~/.bashrc` first, or test interactively on the device.

### Sing-box SOCKS5 proxy (for 5G accelerated proxy)

Run a local SOCKS5 proxy on the phone that routes through VLESS+Reality, useful when home broadband to Seoul is slow but phone 5G has a fast path.

**⚠️ CRITICAL LIMITATION — Requires root or system (ADB) user**

sing-box on Android Termux requires **netlink socket** access to initialize the network manager, which Android blocks for non-root processes:

```
FATAL[0000] initialize network manager: create network monitor:
  netlink socket in Android is banned by Google,
  use the root or system (ADB) user to run sing-box,
  or switch to the sing-box Android graphical interface client
```

This means `pkg install sing-box` followed by `sing-box run` will **fail immediately** on a stock non-rooted device. The only workarounds are:

1. **Root the device** — not practical for most users
2. **Run via ADB** — requires USB connection and `adb shell` (not convenient)
3. **Use the official Android GUI client** — **sing-box for Android (SFA)**, available on [GitHub Releases](https://github.com/SagerNet/sing-box/releases) or F-Droid
4. **Use v2rayNG instead** — supports VLESS+Reality, no root needed, works well (tested on MagicPad v2rayNG)

```bash
# Install via F-Droid APK (download + termux-open to install)
curl -sL -o /tmp/sfa.apk "https://github.com/SagerNet/sing-box/releases/download/v1.13.14/SFA-1.13.14-arm64-v8a.apk"
termux-open /tmp/sfa.apk
```

For actual 5G-accelerated proxy testing, **v2rayNG is the recommended choice on non-rooted Android** — tested vs sing-box on the same Alibaba-Seoul-VLESS-Reality node and performs well.

**Install (Termux, will only work for config check — not runtime):**
```bash
pkg install sing-box
```

**Config** (`~/.config/sing-box/config.json`):
```json
{
  "log": { "level": "info", "timestamp": true },
  "inbounds": [{
    "type": "socks",
    "tag": "socks-in",
    "listen": "0.0.0.0",
    "listen_port": 1080
  }],
  "outbounds": [
    {
      "type": "vless",
      "tag": "proxy-out",
      "server": "43.108.41.245",
      "server_port": 40002,
      "uuid": "a5fa1889-1316-4115-a866-96c8f30523ef",
      "tls": {
        "enabled": true,
        "server_name": "www.bing.com",
        "utls": { "enabled": true, "fingerprint": "chrome" },
        "reality": {
          "enabled": true,
          "public_key": "0o3XsyApUXA0_1Ns2GZPbzLCbUW8zpAarRxCbb0gr1g",
          "short_id": "a1b2c3d4"
        }
      }
    },
    { "type": "direct", "tag": "direct" }
  ],
  "route": { "final": "proxy-out" }
}
```

**Start:**
```bash
nohup sing-box run -c ~/.config/sing-box/config.json \
  > ~/.config/sing-box/run.log 2>&1 &
```

**Verify:** `curl -s --socks5 127.0.0.1:1080 https://www.google.com`

**Connect from laptop:** `ssh -D 1080 -f -N realme-frp` then use `127.0.0.1:1080` as SOCKS5 proxy. Traffic flows: laptop → FRP → phone → sing-box → VLESS+Reality → 5G.

**Limitation:** When phone is on WiFi, both FRP and sing-box traffic go through WiFi. To use 5G, turn off WiFi on the phone — sing-box's base connection auto-switches to 5G without config changes. FRP tunnel also switches to 5G as long as it stays connected.

## 手机本地脚本约定

Android Termux 上打字不便（无实体键盘/屏幕小），本机 Shell 脚本遵循以下约定以最小化输入量：

- **放 `~/.local/bin/`**，确保在 Termux 默认 PATH 中（自动在 PATH 里）
- **短名 + 无后缀**，例如 `h`、`wake`、`r`，不加 `.sh`
- 脚本无需 chmod，`~/.local/bin/` 下文件自动可执行
- 这个目录也在设备的 FRP/SSH 配置脚本的 PATH 中

> 这些脚本是设备本地的快捷工具，非本机 Hermes 管理的一部分。it-assets 的「子技能索引」会引用本章节。

## Pitfalls

- **Google Play Termux is stale**: Always use GitHub or F-Droid.
- **tmux 后台返回乱码（Android）**: Termux 被挂起/切后台再返回时，备用屏幕（alternate screen）的转义序列可能被截断，导致终端显示乱码。在 `~/.tmux.conf` 加 `set -g terminal-overrides "*:smcup@:rmcup@"` 禁用备用屏幕可彻底解决。
- **Don't expect multi-pane tmux on phones**: The screen is too small. Use for session persistence only.
- **Native .NET in Termux is unstable**: Always use proot-distro + Ubuntu for C# work.
- **Not a full desktop replacement**: Good for algorithm verification, script testing, and remote terminal. Not for IDE workloads, Docker, or GPU-dependent tasks.
- **Go programs can't resolve DNS**: Go binaries read `/etc/resolv.conf` which doesn't exist on Android (read-only `/etc`). Go falls back to `127.0.0.1:53` which has no DNS service, causing `dial tcp: lookup ... on [::1]:53: read: connection refused`. Fix with proot to create a fake filesystem view:\n  ```bash\n  mkdir -p ~/my-etc\n  echo \"nameserver 8.8.8.8\" > ~/my-etc/resolv.conf\n  proot -b ~/my-etc:/etc ./your-go-binary\n  ```\n  This applies to frpc, Hugo, and any other Go-compiled tool on Termux. Use directory-level binding (`~/my-etc:/etc`) rather than file-level so hosts/SSL certs can be added later. See `frp-setup` skill, `references/android-termux-frp.md` for the full workflow including runit service setup, .bashrc auto-start, and stuck-reconnection recovery.\n- **SHIFT in macros silently dropped on literal chars**: `SHIFT 5` sends `5`, not `%`; `SHIFT APOSTROPHE` sends `'`, not `"`. Use the target character directly: `%` for `%`, `QUOTE` alias for `"`, `&` for `&`. Only named keycodes (LEFT, RIGHT, HOME, etc.) respect SHIFT because they use the KeyEvent path.\n- **Multi-line .properties values need backslash continuations**: Each line except the last in a multi-line property must end with ` \\` (backslash, space? no — just a bare backslash at the very end of the line, no trailing whitespace). Without these, `java.util.Properties.load()` treats each extra line as a new property key.
- **sing-box needs root on stock Android**: `sing-box run` fails with `netlink socket in Android is banned by Google` on non-rooted devices. Use v2rayNG or SFA (sing-box for Android GUI) instead.
