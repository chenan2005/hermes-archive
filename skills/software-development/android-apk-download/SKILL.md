---
name: android-apk-download
description: Download Android APKs from alternative sources when Google Play is unavailable — Aptoide API, F-Droid, and direct CDN URLs.
tags: [android, apk, aptoide, sideload]
---

# Android APK Download (Alternative Sources)

Download APK files for Android devices when Google Play isn't available (e.g. Chinese devices without Play Store, or devices without Google services).

## Sources (ordered by reliability)

### 1. Aptoide API (best — no Cloudflare, direct download)

Use Aptoide's public API v7 to get app metadata and a direct APK download URL:

```bash
curl -s 'https://ws75.aptoide.com/api/7/app/getMeta?package_name=com.microsoft.rdc.android'
```

From the response, extract:
- `data.file.path` — direct APK download URL (e.g. `https://pool.apk.aptoide.com/...`)
- `data.file.md5sum` — MD5 to verify integrity
- `data.file.filesize` — size in bytes
- `data.file.vername` — version string
- `data.file.signature` — developer signature details

**Features**: No Cloudflare, direct CDN download, no auth required, returns TRUSTED malware rating.

### 2. Uptodown

Works in some regions but may have Cloudflare challenges or session-based download obfuscation. If the page loads in a browser, the button `data-url` attribute contains an obfuscated download path. The actual download is triggered via `onclick` → page event.

### 3. APKMirror / APKPure / APKCombo

Almost always behind Cloudflare. Not reliably accessible via automated tools.

## Transfer to device

### Via SCP (if FRP tunnel exists):

```bash
curl -sL -o /tmp/App.apk 'https://pool.apk.aptoide.com/...'
scp -P <remote_port> /tmp/App.apk user@frp-server:/data/data/com.termux/files/home/
```

### To shared Downloads folder (visible to file manager):

```bash
ssh -p <port> user@host "cp ~/App.apk /storage/emulated/0/Download/"
```

### Via termux-open (triggers package installer):

```bash
ssh -p <port> user@host "termux-open ~/App.apk"
```

## Verify integrity

Always verify MD5 from Aptoide API vs file on device:

```bash
md5sum /path/to/App.apk
```

## Triggers

- "帮我下载一个安卓 APK"
- "传一个 APK 到设备上"
- "有没有 xxx 的 APK"
- Any request to sideload an Android app

## Package names reference

| App | Package Name |
|-----|-------------|
| Microsoft Remote Desktop | com.microsoft.rdc.android |
| V2RayNG | com.v2ray.ang |
| Telegram | org.telegram.messenger |
| Termux | com.termux |
