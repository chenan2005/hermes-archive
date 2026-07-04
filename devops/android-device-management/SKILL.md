---
name: android-device-management
description: Manage Android devices via SSH/FRP — source APKs (Aptoide), transfer via FRP tunnel, install, configure Termux auto-start (sshd, frpc), and manage proxies.
tags: [android, apk, termux, frp, ssh, aptoide, v2ray]
---

# Android Device Management

Deploy APKs and manage Android devices (phone/tablet) without Google Play — source from Aptoide, push via FRP tunnel, install, and configure Termux services.

## Triggers

- "帮我把 xx.apk 装到手机上/平板上"
- "下个安卓 apk 发过来"
- "帮我配置 sshd / frpc 自启"
- "把节点配置发到手机/平板"
- "有没有其他代理软件推荐"

## Step 1: Source the APK

Use Aptoide's public API v7 to find the app and get a direct download link:

```bash
curl -s 'https://ws75.aptoide.com/api/7/app/getMeta?package_name=<package.name>' | jq '.data.file.path'
```

The response includes:
- `data.file.path` — direct APK download URL (CDN)
- `data.file.md5sum` — checksum for verification
- `data.file.filesize` — size in bytes
- `data.file.vername` — version name
- `data.file.signature.owner` — signer identity (verify it matches the official developer)

**Known package names:**
| App | Package | Notes |
|-----|---------|-------|
| Microsoft Remote Desktop (old) | `com.microsoft.rdc.android` | Remote Desktop 8 |
| Windows App (new) | `com.microsoft.rdc.androidx` | Renamed, ~90MB, v11+ |
| V2RayNG | `com.v2ray.ang` | |
| NekoBox | `moe.nb.nekobox` | |

**Security check**: Verify the signature `owner` matches the official developer (e.g. "O=v2ray" for V2RayNG, "O=Microsoft Corporation" for Remote Desktop). Malware rating from Aptoide's `file.malware.rank` is usually "TRUSTED" for these.

**Alternative recommendation list** (when user asks for proxy app alternatives):

| App | Pros | Cons |
|-----|------|------|
| **V2RayNG** | Classic, stable, all protocols | UI dated |
| **NekoBox** | V2RayNG fork, sing-box core, more protocols | More complex |
| **Sing-box** | Unified core, efficient, future-proof | Manual config |
| **Clash Meta for Android** | Best UI, familiar if using OpenClash | Less protocol support |
| **Hiddify** | Auto speed test, easy import | China connectivity occasionally |

## Step 2: Download to laptop

```bash
curl -sL -o /tmp/<app>.apk '<direct_url>' -w 'HTTP %{http_code}, Size: %{size_download} bytes'
```

## Step 3: Verify checksum

```bash
md5sum /tmp/<app>.apk
# Compare with data.file.md5sum from API response
```

## Step 4: Transfer via FRP tunnel

Check `devops/it-assets` skill for correct FRP port mapping per device:
- Phone (真我 GT7):    `bernarty:30205 → localhost:8022`  user: `chen_`
- Tablet (荣耀 MagicPad): `bernarty:30177 → localhost:8022`  user: `u0_a250`

```bash
# Test tunnel
ssh -o ConnectTimeout=5 -p <FRP_PORT> <user>@www.bernarty.xyz "echo connected"

# SCP transfer (best for files < 30MB)
scp -P <FRP_PORT> /tmp/<app>.apk <user>@www.bernarty.xyz:~/<app>.apk

# Pipe method (more reliable for large files, 30MB+)
# SCP can timeout on large files via FRP tunnels with limited bandwidth
cat /tmp/<app>.apk | ssh -p <FRP_PORT> <user>@www.bernarty.xyz \
  "cat > ~/<app>.apk"
```

**Pitfall**: Killing frpc while connected via the FRP tunnel drops the SSH session immediately. Always use the tablet's own connection when restarting its frpc.

## Step 5: Copy to shared Downloads

```bash
cp ~/<app>.apk /storage/emulated/0/Download/
```

This makes it visible to the Android file manager. The user taps it manually to install.

**User preference**: Do NOT use `termux-open` — it sometimes reports "安装包损坏" even on valid APKs. Manual install via file manager is more reliable.

## Step 6: Termux auto-start (sshd + frpc)

Add to `~/.bashrc`:

```bash
# sshd 自启动 + wakelock
if ! pgrep -x sshd > /dev/null 2>&1; then
    sshd
    termux-wake-lock sshd 2>/dev/null
fi

# frpc 自启动
if ! pgrep -f "frpc -c" > /dev/null 2>&1; then
    nohup ~/frp/frpc -c ~/frp/frpc.ini > ~/frp/frpc.log 2>&1 &
fi
```

For frpc, use the server IP directly (not domain) to avoid Go's DNS resolution issues on Android. If a domain is needed, wrap with proot: `proot -b ~/my-etc:/etc ~/frp/frpc -c ~/frp/frpc.ini`.

## Step 7: Push node configs (proxy subscriptions)

When user asks to send proxy configs (e.g. OpenClash nodes from router) to an Android device:

1. Read config from the router (e.g. `/etc/openclash/config.yaml`)
2. Convert nodes to V2RayNG-compatible share links:
   - **VMess nodes**: Build JSON, base64 encode → `vmess://<base64>`
   - **VLESS nodes**: Build vless:// URI directly
3. Write to a `.txt` file with labels
4. SCP to `/storage/emulated/0/Download/`

## Pitfalls

- **FRP port confusion**: `30205` = phone, `30177` = tablet. Always verify in `it-assets` before connecting.
- **Kill frpc from FRP tunnel**: Will disconnect yourself. If restart needed, ask user to open Termux and run the restart command.
- **termux-open reliability**: Some APKs fail with "安装包损坏" even when MD5 matches. Use manual file manager install instead.
- **FRP proxy name uniqueness**: Each device's frpc must use a unique `[proxy-name]` in its config. Phone=`ssh-android`, Tablet=`ssh-magicpad` (or `ssh-tablet`). Duplicates cause `proxy [name] already exists` on the server.
