# OpenClash Init Script Pitfalls

## Self-Locking Cycle

When the Clash core fails to start, OpenClash's `/etc/init.d/openclash` calls `start_fail()`:

```sh
start_fail() {
   uci -q set openclash.config.enable=0   # ← THIS is the problem
   uci -q commit openclash
   stop
   exit 0
}
```

This creates a locked state:
1. Core fails → `start_fail()` → `uci set enable=0`
2. Next restart → init script checks `enable` → sees `0` → "Disabled, Need Start From Luci Page" → exits
3. No amount of restarting helps — must manually `uci set enable=1` AND fix the root cause

## Root Cause: Missing `proxy_mode` UCI Key

The most common reason for Core Start Failed after a clean config upload:

```bash
# Check if proxy_mode is set
uci get openclash.config.proxy_mode   # returns empty/nothing
```

If missing, the Ruby script `yml_change.sh` (Step 3) writes `mode: ''` into the active config, which mihomo rejects as "Parse config error: invalid mode".

**Fix:**
```bash
uci set openclash.config.proxy_mode='rule'
uci commit openclash
```

## Config File Duality

OpenClash uses TWO config files, not one:

| Path | Role | When Modified |
|------|------|---------------|
| `/etc/openclash/config/config.yaml` | **Source config** — user's uploaded/subscribed config | Manually by user, or by subscription update |
| `/etc/openclash/config.yaml` | **Active config** — modified copy for the core | Every restart (Step 3: yml_change.sh) |

The init script flow:
1. Copies `config/config.yaml` → `/tmp/yaml_config_tmp_...`
2. Modifies via Ruby scripts (adds auth, sets mode, adds rules)
3. Moves temp file → `/etc/openclash/config.yaml`
4. Runs core with `-f /etc/openclash/config.yaml`

**Key implication:** The source config always looks correct, but the active config gets corrupted. Always check `/etc/openclash/config.yaml`, not the source.

## Password Regeneration

Each time OpenClash processes the config (Step 3), it:
- Replaces `secret:` with the current UCI `dashboard_password`
- Generates a NEW `authentication:` entry with format `Clash:<random>`

So after every restart, the proxy auth password changes. To find the current password:

```bash
grep -A1 '^authentication:' /etc/openclash/config.yaml
```

The source config's `authentication:` section is effectively ignored — OpenClash overwrites it.

## Crashing the Boot — Nuclear Option

If the init script is corrupted (e.g., from a failed sed patch or incomplete reinstall), the cleanest fix is to reinstall the luci-app-openclash package:

```bash
# Complete purge
/etc/init.d/openclash stop 2>/dev/null
opkg remove luci-app-openclash --force-removal-of-dependent-packages
rm -rf /etc/openclash/core/* /etc/openclash/clash /tmp/openclash* /usr/share/openclash/* /etc/init.d/openclash

# Reinstall
cd /tmp
curl -sL "https://github.com/vernesong/OpenClash/releases/download/v0.47.096/luci-app-openclash_0.47.096_all.ipk" -o openclash.ipk
opkg install openclash.ipk

# Reconfigure UCI (critical: proxy_mode must be set!)
uci set openclash.config.enable='1'
uci set openclash.config.proxy_mode='rule'
uci set openclash.config.config_path='/etc/openclash/config/config.yaml'
uci set openclash.config.core_type='Meta'
uci commit openclash

# Reinstall core binary (see mihomo-musl-compatibility.md)
cp /wherever/mihomo /etc/openclash/core/clash_meta
chmod 755 /etc/openclash/core/clash_meta
ln -sf /etc/openclash/core/clash_meta /etc/openclash/clash

# Upload config to /etc/openclash/config/config.yaml, then restart
/etc/init.d/openclash restart
```

## Quick Start Bypass

If Step 3 keeps corrupting the config, bypass the init entirely:

```bash
killall clash openclash_watch 2>/dev/null
sleep 1
/etc/openclash/clash -d /etc/openclash -f /etc/openclash/config/config.yaml > /dev/null 2>&1 &
sleep 8
netstat -tlnp | grep -E '789|9090'
```

This starts the core directly without OpenClash's firewall rules, watchdog, or config modification. Good for testing. Not persistent across reboots.
