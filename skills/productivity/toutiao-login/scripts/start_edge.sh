#!/bin/bash
# 启动 Edge 并输出 CDP WebSocket URL
# 用法: bash start_edge.sh [URL]

URL="${1:-https://www.toutiao.com/}"

# 清理旧进程
pkill -f "microsoft-edge.*9222" 2>/dev/null
sleep 1

# 启动 Edge
DISPLAY=:0 microsoft-edge \
  --remote-debugging-port=9222 \
  --remote-allow-origins=* \
  --no-first-run \
  --no-default-browser-check \
  --window-size=1400,900 \
  --window-position=100,50 \
  "$URL" &

# 等待 CDP 端口就绪
for i in $(seq 1 30); do
  if curl -s http://127.0.0.1:9222/json/version > /dev/null 2>&1; then
    break
  fi
  sleep 1
done

# 获取 page ID
PAGE_ID=$(curl -s http://127.0.0.1:9222/json | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
echo "ws://127.0.0.1:9222/devtools/page/$PAGE_ID"
