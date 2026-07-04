#!/bin/bash
# check-9900k.sh — 检查 9900K (192.168.37.200) 是否在线
# 用法: sh check-9900k.sh
IP="192.168.37.200"
echo "=== 9900K 在线检测 ==="
echo "目标: $IP (e0:d5:5e:d3:d7:4e)"
echo ""
result=$(ssh root@192.168.37.1 "
  ip neigh del $IP dev br-lan 2>/dev/null
  ping -c 1 -W 2 $IP >/dev/null 2>&1
  cat /proc/net/arp | grep $IP
" 2>&1)
state=$(echo "$result" | awk '{print $2}')
if [ "$state" = "0x2" ]; then
  echo "状态: 在线 ✅  (ARP 0x2 COMPLETE)"
  echo ""
  echo "--- 更多信息 ---"
  ssh -o ConnectTimeout=5 chenan@$IP "hostname" 2>/dev/null
elif [ "$state" = "0x1" ]; then
  echo "状态: 离线 ❌  (ARP 0x1 INCOMPLETE)"
else
  echo "状态: 离线 ❌  (ARP 无条目)"
fi
