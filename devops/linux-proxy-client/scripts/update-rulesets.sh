#!/bin/bash
# update-rulesets.sh — 更新 sing-box 的 geoip/geosite 规则集
# 建议 cron: 0 3 1 * * ~/.config/sing-box/scripts/update-rulesets.sh

set -e
DIR="${HOME}/.config/sing-box/ruleset"
mkdir -p "$DIR"
cd "$DIR"

echo "[$(date)] Updating rule-sets..."

# 1. China IP (17mon)
echo "  Downloading china_ip_list.txt..."
curl -sL --max-time 60 -o china_ip_list.txt \
  "https://raw.githubusercontent.com/17mon/china_ip_list/master/china_ip_list.txt"

# 2. China domains (v2fly)
echo "  Downloading cn_domains.txt..."
curl -sL --max-time 60 -o cn_domains.txt \
  "https://raw.githubusercontent.com/v2fly/domain-list-community/release/cn.txt"

# 3. Compile geoip-cn
echo "  Compiling geoip-cn..."
python3 -c "
import json
with open('china_ip_list.txt') as f:
    ips = [l.strip() for l in f if l.strip()]
src = {'version': 1, 'rules': [{'ip_cidr': ips}]}
json.dump(src, open('geoip-cn.json', 'w'), separators=(',', ':'))
"
sing-box rule-set compile geoip-cn.json

# 4. Compile geosite-cn (WARNING: must use domain + domain_suffix)
echo "  Compiling geosite-cn..."
python3 -c "
import json
with open('cn_domains.txt') as f:
    domains = [l.strip().replace('domain:', '') for l in f
               if l.strip() and not l.startswith('#')]
src = {'version': 1, 'rules': [
    {'domain': domains},
    {'domain_suffix': ['.' + d for d in domains]}
]}
json.dump(src, open('geosite-cn.json', 'w'), separators=(',', ':'))
"
sing-box rule-set compile geosite-cn.json

# 5. Cleanup source files
rm -f china_ip_list.txt cn_domains.txt geoip-cn.json geosite-cn.json
echo "[$(date)] Done. geoip-cn.srs + geosite-cn.srs updated."

# 6. Reload sing-box if running
SB_PID=$(pgrep -x "sing-box" 2>/dev/null || true)
if [ -n "$SB_PID" ]; then
  kill -HUP "$SB_PID"
  echo "  sing-box reloaded (PID $SB_PID)"
fi
