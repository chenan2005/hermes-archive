# SCP File Transfer Patterns

Quick reference for common scp operations.

## Basic

```bash
# Upload: local → remote
scp local/file.ext user@host:remote/dir/

# Download: remote → local
scp user@host:remote/file.ext local/dir/

# Rename while transferring
scp local/file.ext user@host:remote/dir/new-name.ext
```

## Options

| Flag | Purpose |
|------|---------|
| `-r` | Recursive (directories) |
| `-P N` | Specify port (must be uppercase **P**) |
| `-C` | Enable compression |
| `-v` | Verbose (debug connection issues) |

## Common Destinations

```bash
# Windows (OpenSSH server)
scp file.txt minipc:C:/Users/chen_/
scp minipc:C:/Users/chen_/file.txt ./

# Linux servers
scp file.txt ubuntu@bernarty.xyz:~/
scp file.txt root@openwrt:/etc/config/

# Android/Termux
scp -P 8022 file.txt realme:~/storage/downloads/
```
