#!/bin/sh
# DHCP static lease manager for ImmortalWrt
# Usage: dhcp-manage.sh list | add <name> <mac> <ip> | del <name> | status
# Place in /root/.local/bin/

LEASE_FILE="/tmp/dhcp.leases"

list() {
    echo "NAME       STATIC       MAC                    STATUS"
    echo "---------- ------------ ---------------------  ------"
    i=0
    while true; do
        name=$(uci -q get dhcp.@host[$i].name 2>/dev/null) || break
        ip=$(uci -q get dhcp.@host[$i].ip)
        mac=$(uci -q get dhcp.@host[$i].mac | tr '[:upper:]' '[:lower:]')
        lease=$(grep -i "$mac" "$LEASE_FILE" 2>/dev/null | awk '{print $3}')
        [ -n "$lease" ] && status="✅ $lease" || status="⬜ offline"
        printf "%-10s %-12s %-21s %s\n" "$name" "$ip" "$mac" "$status"
        i=$((i + 1))
    done
}

del() {
    name="$1"
    i=0
    found=0
    while true; do
        n=$(uci -q get dhcp.@host[$i].name 2>/dev/null) || break
        if [ "$n" = "$name" ]; then
            mac=$(uci -q get dhcp.@host[$i].mac | tr '[:upper:]' '[:lower:]')
            uci delete dhcp.@host[$i]
            sed -i "/$mac/Id" "$LEASE_FILE" 2>/dev/null
            echo "Deleted $name ($mac)"
            found=1
            break
        fi
        i=$((i + 1))
    done
    [ $found -eq 0 ] && echo "Not found: $name" && return 1
    uci commit dhcp
    /etc/init.d/dnsmasq reload >/dev/null 2>&1
    return 0
}

add() {
    name="$1"; mac="$2"; ip="$3"
    [ -z "$name" ] && echo "Usage: dhcp-manage add <name> <mac> <ip>" && return 1
    [ -z "$mac" ] && echo "Usage: dhcp-manage add <name> <mac> <ip>" && return 1
    [ -z "$ip" ] && echo "Usage: dhcp-manage add <name> <mac> <ip>" && return 1

    # Check for duplicates
    uci show dhcp | grep -q "dhcp.@host.*.mac='$mac'" && echo "WARNING: MAC $mac already has a binding"
    uci show dhcp | grep -q "dhcp.@host.*.ip='$ip'" && echo "WARNING: IP $ip already has a binding"

    uci add dhcp host
    uci set dhcp.@host[-1].name="$name"
    uci set dhcp.@host[-1].mac="$mac"
    uci set dhcp.@host[-1].ip="$ip"
    uci commit dhcp
    /etc/init.d/dnsmasq reload >/dev/null 2>&1
    echo "Added $name: $mac → $ip"
}

force() {
    name="$1"
    [ -z "$name" ] && echo "Usage: dhcp-manage force <name>" && return 1

    mac=""
    i=0
    while true; do
        n=$(uci -q get dhcp.@host[$i].name 2>/dev/null) || break
        if [ "$n" = "$name" ]; then
            mac=$(uci -q get dhcp.@host[$i].mac | tr '[:upper:]' '[:lower:]')
            ip=$(uci -q get dhcp.@host[$i].ip)
            break
        fi
        i=$((i + 1))
    done
    [ -z "$mac" ] && echo "Not found: $name" && return 1

    echo "Force reassign $name ($mac → $ip)"
    echo "  1. Deleting all leases for $mac..."
    sed -i "/$mac/d" "$LEASE_FILE"
    echo "  2. Restarting dnsmasq..."
    /etc/init.d/dnsmasq restart >/dev/null 2>&1
    sleep 2
    echo "  Done. Tell device to forget WiFi and reconnect."
}

case "${1:-list}" in
    list)   list ;;
    add)    add "$2" "$3" "$4" ;;
    del)    del "$2" ;;
    force)  force "$2" ;;
    status) list ;;
    *)      echo "Usage: dhcp-manage {list|add <name> <mac> <ip>|del <name>|force <name>}" ;;
esac
