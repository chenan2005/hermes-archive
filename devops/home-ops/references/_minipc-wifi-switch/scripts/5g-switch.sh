#!/bin/bash
# 5G Switch: Toggle minipc WiFi + OpenClash proxy node
# 
# Usage: ./5g-switch.sh connect|disconnect
# Requires: SSH to minipc and ImmortalWrt (192.168.71.9), 
#           scripts in ~/.hermes/skills/devops/minipc-wifi-switch/scripts/

set -e

SCRIPT_DIR="$HOME/.hermes/skills/devops/minipc-wifi-switch/scripts"
MINIPC="minipc"
OPENWRT="root@192.168.71.9"
SSID="realme GT 7 FDC6"
VLESS_IP="43.108.41.245"

connect_mode() {
    echo "=== 5G Switch: CONNECT ==="

    # Step 1: Scan for hotspot
    echo "[1/4] Scanning for $SSID ..."
    if ! ssh "$MINIPC" "powershell -Command \"netsh wlan show networks interface='WLAN' mode=bssid\"" 2>/dev/null | grep -q "$SSID"; then
        echo "ERROR: $SSID not found. Is hotspot on?"
        exit 1
    fi
    echo "  Hotspot found."

    # Step 2: Switch minipc WiFi using external script
    echo "[2/4] Switching minipc WiFi ..."
    local result
    result=$(cat "$SCRIPT_DIR/connect-realme.ps1" | ssh "$MINIPC" "powershell -ExecutionPolicy Bypass -Command -" 2>/dev/null)
    echo "$result"

    if echo "$result" | grep -q "FAIL"; then
        echo "ERROR: WiFi connection failed"
        exit 1
    fi

    # Extract gateway and update static route
    local gw
    gw=$(echo "$result" | grep "^GW=" | cut -d= -f2)
    if [ -n "$gw" ]; then
        echo "[*] Static route: $VLESS_IP -> $gw"
        ssh "$MINIPC" "route delete $VLESS_IP 2>nul & route -p add $VLESS_IP mask 255.255.255.255 $gw metric 50" 2>/dev/null
        echo "  Route updated."
    fi

    # Step 3: Check/start Xray
    echo "[3/4] Checking Xray ..."
    if ssh "$MINIPC" "tasklist 2>nul | findstr xray" 2>/dev/null | grep -q xray; then
        echo "  Xray running."
    else
        echo "  Xray not running, starting..."
        ssh "$MINIPC" "schtasks /run /tn Xray-SOCKS5" 2>/dev/null
        sleep 3
    fi

    # Step 4: Switch OpenClash
    echo "[4/4] Switching OpenClash -> minipc-socks ..."
    cat << 'OCCMD' | ssh "$OPENWRT" 'cat > /tmp/oc_switch.sh && sh /tmp/oc_switch.sh'
#!/bin/sh
S=$(awk '/^secret:/{print $2}' /etc/openclash/config.yaml)
curl -s -X PUT http://127.0.0.1:9090/proxies/PROXY \
  -H "Authorization: Bearer $S" \
  -H "Content-Type: application/json" \
  -d '{"name":"minipc-socks"}'
echo ""
NOW=$(curl -s http://127.0.0.1:9090/proxies/PROXY -H "Authorization: Bearer $S" | sed 's/.*"now":"\([^"]*\)".*/\1/')
echo "PROXY now: $NOW"
OCCMD

    echo ""
    echo "=== DONE: 5G mode active (minipc-socks) ==="
}

disconnect_mode() {
    echo "=== 5G Switch: DISCONNECT ==="

    # Step 1: Disconnect minipc WiFi
    echo "[1/2] Disconnecting minipc WiFi ..."
    ssh "$MINIPC" "powershell -Command \"netsh wlan disconnect interface='WLAN'\"" 2>/dev/null || {
        # Fallback
        ssh "$MINIPC" "netsh wlan disconnect" 2>/dev/null
    }
    echo "  WiFi disconnected."

    # Step 2: Switch OpenClash
    echo "[2/2] Switching OpenClash -> VMISS-HK ..."
    cat << 'OCCMD' | ssh "$OPENWRT" 'cat > /tmp/oc_rollback.sh && sh /tmp/oc_rollback.sh'
#!/bin/sh
S=$(awk '/^secret:/{print $2}' /etc/openclash/config.yaml)
curl -s -X PUT http://127.0.0.1:9090/proxies/PROXY \
  -H "Authorization: Bearer $S" \
  -H "Content-Type: application/json" \
  -d '{"name":"VMISS-HK"}'
echo ""
NOW=$(curl -s http://127.0.0.1:9090/proxies/PROXY -H "Authorization: Bearer $S" | sed 's/.*"now":"\([^"]*\)".*/\1/')
echo "PROXY now: $NOW"
OCCMD

    echo ""
    echo "=== DONE: normal mode (VMISS-HK) ==="
}

case "${1:-}" in
    connect)    connect_mode ;;
    disconnect) disconnect_mode ;;
    *)
        echo "Usage: $0 {connect|disconnect}"
        exit 1
        ;;
esac
