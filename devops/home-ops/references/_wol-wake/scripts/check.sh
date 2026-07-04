#!/bin/bash
# check.sh — 通用 ARP 探测脚本
# 用法: sh check.sh <IP> [路由器IP] [接口名]
# 默认: 71.41 → 路由器 192.168.71.11 / eth0
#       37.200 → 路由器 192.168.37.1 / br-lan

IP="${1:-192.168.71.41}"

case "$IP" in
  192.168.71.*)
    ROUTER="${2:-root@192.168.71.9}"
    DEV="${3:-eth1}"
    ;;
  192.168.37.*)
    ROUTER="${2:-root@192.168.37.1}"
    DEV="${3:-br-lan}"
    ;;
  *)
    ROUTER="$2"
    DEV="$3"
    ;;
esac

echo "=== 在线检测 ==="
echo "目标: $IP"
echo "路由器: $ROUTER 接口: $DEV"
echo ""

result=$(ssh "$ROUTER" "
  ip neigh del $IP dev $DEV 2>/dev/null
  ping -c 1 -W 2 $IP >/dev/null 2>&1
  cat /proc/net/arp | grep -E '[[:space:]]'"$IP"'[[:space:]]'
" 2>&1)

state=$(echo "$result" | awk '{print $2}')
if [ "$state" = "0x2" ]; then
  mac=$(echo "$result" | awk '{print $4}')
  echo "状态: 在线 ✅  (ARP 0x2, MAC: $mac)"
elif [ "$state" = "0x1" ]; then
  echo "状态: 离线 ❌  (ARP 0x1 INCOMPLETE)"
else
  echo "状态: 离线 ❌  (无 ARP 条目)"
fi
