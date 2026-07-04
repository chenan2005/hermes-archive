#!/bin/bash
# check-9950x3d.sh — 检查 9950x3d (192.168.71.41) 是否在线
# 用法: sh check-9950x3d.sh
IP="192.168.71.41"
echo "=== 9950x3d 在线检测 ==="
echo "目标: $IP (34:5a:60:b5:8d:13)"
echo ""
result=$(ssh root@192.168.71.9 "
  ip neigh del $IP dev eth0 2>/dev/null
  ping -c 1 -W 2 $IP >/dev/null 2>&1
  cat /proc/net/arp | grep $IP
" 2>&1)
state=$(echo "$result" | awk '{print $2}')
if [ "$state" = "0x2" ]; then
  echo "状态: 在线 ✅  (ARP 0x2 COMPLETE)"
  echo ""
  echo "--- 更多信息 ---"
  ssh -o ConnectTimeout=5 chen_@$IP "powershell -NoProfile -Command \"
    Write-Host \\\"主机名: \\\"(hostname)
    Write-Host \\\"开机时间: \\\"(Get-CimInstance Win32_OperatingSystem).LastBootUpTime
  \\"" 2>/dev/null
elif [ "$state" = "0x1" ]; then
  echo "状态: 离线 ❌  (ARP 0x1 INCOMPLETE)"
else
  echo "状态: 离线 ❌  (ARP 无条目)"
fi
