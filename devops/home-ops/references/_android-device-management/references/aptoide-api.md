# Aptoide API v7 — APK Metadata Lookup

Base URL: `https://ws75.aptoide.com/api/7/app/getMeta?package_name=<pkg>`

## Response shape (relevant fields)

```json
{
  "info": { "status": "OK" },
  "data": {
    "name": "app display name",
    "package": "com.example.app",
    "size": 19104536,
    "file": {
      "vername": "8.1.82.445",
      "vercode": 95,
      "md5sum": "9ee8c12cad139ea3579352285390af22",
      "filesize": 19104536,
      "path": "https://pool.apk.aptoide.com/...apk",
      "path_alt": "https://pool.apk.aptoide.com/...apk",
      "signature": {
        "sha1": "00:05:DF:...",
        "owner": "CN=Microsoft Corporation Third Party Marketplace..."
      },
      "malware": { "rank": "TRUSTED" }
    }
  }
}
```

## Common apps

| App | Package | Latest found |
|-----|---------|-------------|
| Microsoft Remote Desktop | `com.microsoft.rdc.android` | 8.1.82.445 (2022) |
| V2RayNG | `com.v2ray.ang` | 2.0.6 (2026-05) |

## Notes

- CDN domain: `pool.apk.aptoide.com` — accessible from China without VPN (tested from Alibaba Seoul and Tencent Cloud).
- Always verify `file.signature.owner` matches the official developer.
- `file.malware.rank` is reliably "TRUSTED" for well-known apps.
