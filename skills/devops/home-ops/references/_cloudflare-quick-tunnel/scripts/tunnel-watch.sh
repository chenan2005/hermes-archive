#!/bin/sh
# Seoul Cloudflare tunnel self-heal script for OpenWrt
# Detects tunnel URL changes and auto-updates OpenClash config
#
# Install:
#   cp tunnel-watch.sh /usr/bin/seoul-tunnel-watch
#   chmod +x /usr/bin/seoul-tunnel-watch
#   echo '*/30 * * * * /usr/bin/seoul-tunnel-watch' >> /etc/crontabs/root
#   /etc/init.d/cron restart
#
# Prerequisites:
#   - SSH key auth from OpenWrt to Seoul VPS (~/.ssh/id_ed25519)
#   - cloudflared on Seoul with logging to /var/log/cloudflared.log

PROXY_URL="http://Clash:3Ypy6ovV@127.0.0.1:7890"
TEST_URL="https://cp.cloudflare.com/generate_204"
CFG="/etc/openclash/config/config.yaml"
CFGMAIN="/etc/openclash/config.yaml"
SEOL="ssh -i /root/.ssh/id_ed25519 -o StrictHostKeyChecking=accept-new admin@alibaba.bernarty.xyz"
LOG="/var/log/seoul-tunnel.log"

log() { echo "$(date "+%Y-%m-%d %H:%M:%S") $*" >> "$LOG"; }

# Step 1: Test Seoul-Cloudflare connectivity through proxy
RESULT=$(curl -s --connect-timeout 15 -x "$PROXY_URL" "$TEST_URL" -o /dev/null -w "%{http_code}" 2>/dev/null)

if [ "$RESULT" = "204" ] || [ "$RESULT" = "200" ]; then
    exit 0  # Tunnel is fine, stay quiet
fi

log "Seoul-Cloudflare failed (HTTP $RESULT), checking tunnel URL..."

# Step 2: Get current tunnel URL from Seoul VPS log
NEW_URL=$($SEOL "sudo cat /var/log/cloudflared.log 2>/dev/null | grep https:// | grep trycloudflare | tail -1 | grep -o \"https://[a-z0-9-]*\\.trycloudflare\\.com\"" 2>/dev/null)

if [ -z "$NEW_URL" ]; then
    log "ERROR: could not get new URL from Seoul VPS"
    exit 1
fi

# Step 3: Get old URL from config
OLD_URL=$(grep -o "https://[a-z0-9-]*\\.trycloudflare\\.com" "$CFG" 2>/dev/null | head -1)

if [ -z "$OLD_URL" ]; then
    log "No tunnel URL found in config (not using tunnel setup?)"
    exit 0
fi

if [ "$OLD_URL" = "$NEW_URL" ]; then
    log "URL unchanged but still failing - manual check needed"
    exit 1
fi

# Step 4: Replace URL in both config files
sed -i "s|$OLD_URL|$NEW_URL|g" "$CFG"
cp "$CFG" "$CFGMAIN"
log "Updated tunnel URL: $OLD_URL -> $NEW_URL"

# Step 5: Restart clash core
killall clash 2>/dev/null; sleep 2
/etc/openclash/clash -d /etc/openclash -f "$CFG" > /dev/null 2>&1 &
log "Clash core restarted with new tunnel URL"
