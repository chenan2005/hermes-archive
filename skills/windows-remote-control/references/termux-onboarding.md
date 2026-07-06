# Android/Termux Device Onboarding

Standard workflow to bring a new Android device into the SSH + FRP + DNS ecosystem.

## Prerequisites

- Termux installed on the device
- Local machine has `sshpass` (`sudo apt install sshpass`)
- OpenWrt dnsmasq running for DNS

## Step 1: Install and start SSH on device

On the Android device, in Termux:
```bash
pkg install openssh -y
passwd                    # set a temporary password
sshd                      # start SSH server (default port 8022)
```

## Step 2: Test connection from local

```bash
sshpass -p '<temp_password>' ssh -o StrictHostKeyChecking=accept-new -p 8022 <user>@192.168.37.<IP> 'echo ONLINE && uname -m'
```

## Step 3: Deploy permanent SSH key

```bash
sshpass -p '<temp_password>' ssh -p 8022 <user>@192.168.37.<IP> 'cat >> ~/.ssh/authorized_keys << EOF
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJx8zg0qFHgJzuRanXtBRz6MF55Ph45Cy2Z2G6AEKwI+ chenan@chenan-Lenovo-XiaoXinPro-13API-2019
EOF'
```

## Step 4: Verify key auth + disable password

```bash
# Test key login
ssh -p 8022 <user>@192.168.37.<IP> 'echo KEY_OK'

# Disable password auth
ssh -p 8022 <user>@192.168.37.<IP> 'sed -i "s/^#*PasswordAuthentication.*/PasswordAuthentication no/" /data/data/com.termux/files/usr/etc/ssh/sshd_config && pkill sshd && sshd'
```

## Step 5: Add DNS + SSH alias

```bash
# OpenWrt DNS
ssh openwrt "echo '192.168.37.<IP> <hostname> <hostname>.lan.11' >> /etc/hosts && /etc/init.d/dnsmasq restart"

# Local SSH config
cat >> ~/.ssh/config << EOF
Host <hostname>
    HostName <hostname>.lan.11
    Port 8022
    User <user>
    StrictHostKeyChecking accept-new
    ConnectTimeout 5
EOF
```

## Step 6: Auto-start with bashrc + wake-lock

```bash
ssh <hostname> 'cat >> ~/.bashrc << "EOF"

# sshd 自启动 + wakelock
if ! pgrep -x sshd > /dev/null 2>&1; then
    sshd
    termux-wake-lock sshd 2>/dev/null
fi
EOF'
```

> `termux-wake-lock` prevents Android from deep-sleeping the network connection.
> If `termux-wake-lock` is not available, install `termux-api` package.

## Step 7 (optional): FRP with proot DNS fix

See `internal-dns-setup.md` for the proot DNS workaround for Go programs.

## Device Registry

| Hostname | SSH alias | IP | Port | User |
|----------|-----------|----|------|------|
| realme | `ssh realme` | 192.168.37.205 | 8022 | chen_ |
| magicpad | `ssh magicpad` | 192.168.37.177 | 8022 | u0_a250 |
