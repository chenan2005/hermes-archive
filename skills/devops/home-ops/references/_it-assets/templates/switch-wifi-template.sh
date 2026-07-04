#!/bin/bash
# ============================================================
# WiFi 切换脚本 — 本机切换至光猫 WiFi，FRP 隧道验证 + 自动回退
# 用法:
#   ./switch-wifi-template.sh                   dry-run 模式
#   ./switch-wifi-template.sh execute           真正执行
#
# 验证条件:  www.bernarty.xyz:30234 (FRP SSH 隧道端口) 可达
# 回退机制:  180s 看门狗，nohup + disown 确保 SSH 断连后仍生效
# ============================================================

TARGET_SSID="ChinaNet-pfwQ-5G"
TARGET_PASSWORD="36ugq6ra"
FRP_HOST="www.bernarty.xyz"
FRP_PORT=30234
WATCHDOG_TIMEOUT=180
STATE_FILE="/tmp/wifi-switch-state"
OK_FLAG="/tmp/wifi-frp-ok"
WATCHDOG_LOG="/tmp/wifi-watchdog.log"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERR]${NC}  $*"; }

# ---------- 前置确认 ----------
precheck() {
    info "前置检查: FRP 隧道当前是否可达..."
    if nc -zw 5 "$FRP_HOST" "$FRP_PORT" 2>/dev/null; then
        info "✅ FRP 隧道当前正常（$FRP_HOST:$FRP_PORT）"
    else
        warn "⚠️  FRP 隧道当前不可达，切换后可能无法回连"
        warn "   继续执行将依赖看门狗回退"
    fi
}

# ---------- 保存当前 WiFi 状态 ----------
save_current_state() {
    CURRENT_SSID=$(iwgetid -r 2>/dev/null)
    CURRENT_CONN=$(nmcli -t -f NAME connection show --active 2>/dev/null | grep -v '^$' | grep -v 'docker\|lo\|br-' | head -1)
    CURRENT_GW=$(ip route | grep "^default" | awk '{print $3}')
    CURRENT_IP=$(ip -4 addr show wlp1s0 2>/dev/null | grep inet | awk '{print $2}' | cut -d/ -f1)
    cat > "$STATE_FILE" <<- STATEEOF
CURRENT_SSID="${CURRENT_SSID}"
CURRENT_CONN="${CURRENT_CONN}"
CURRENT_GW="${CURRENT_GW}"
CURRENT_IP="${CURRENT_IP}"
STATEEOF
    info "当前 SSID : ${CURRENT_SSID:-未知}  连接: ${CURRENT_CONN:-未知}"
    info "当前网关  : ${CURRENT_GW:-未知}  IP: ${CURRENT_IP:-未知}"
}

# ---------- 创建目标 WiFi 连接配置 ----------
setup_target() {
    if nmcli connection show | grep -qF "$TARGET_SSID"; then
        info "目标 WiFi 已存在连接配置"
    else
        nmcli connection add type wifi con-name "$TARGET_SSID" ifname wlp1s0 ssid "$TARGET_SSID" \
            wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$TARGET_PASSWORD"
        info "目标 WiFi 连接配置已创建"
    fi
}

# ---------- 启动看门狗 ----------
start_watchdog() {
    rm -f "$OK_FLAG"
    info "启动后台看门狗（${WATCHDOG_TIMEOUT}秒）..."
    nohup bash -c "
        sleep $WATCHDOG_TIMEOUT
        if [ -f $OK_FLAG ]; then
            echo \"\$(date) 看门狗: 成功信号已收到，保持新 WiFi\" >> $WATCHDOG_LOG
            exit 0
        fi
        echo \"\$(date) 看门狗: 超时未收到成功信号，开始回退...\" >> $WATCHDOG_LOG
        source $STATE_FILE 2>/dev/null
        for i in 1 2 3; do
            timeout 30 nmcli connection up \"\${CURRENT_CONN}\" 2>/dev/null && {
                echo \"\$(date) 看门狗: 已切回原 WiFi (\${CURRENT_CONN})\" >> $WATCHDOG_LOG
                exit 0
            }
            sleep 3
        done
        echo \"\$(date) 看门狗: 回退全部失败，请手动处理\" >> $WATCHDOG_LOG
        exit 1
    " > "$WATCHDOG_LOG" 2>&1 &
    WATCHDOG_PID=$!
    disown "$WATCHDOG_PID" 2>/dev/null
    echo "$WATCHDOG_PID" > /tmp/wifi-watchdog.pid
    info "看门狗 PID: $WATCHDOG_PID"
}

# ---------- 执行切换 ----------
switch_wifi() {
    info "切换到 \"$TARGET_SSID\"..."
    timeout 30 nmcli connection up "$TARGET_SSID" || {
        # 切换失败，立即停止看门狗
        kill "$(cat /tmp/wifi-watchdog.pid 2>/dev/null)" 2>/dev/null
        err "切换失败"
        exit 1
    }
}

# ---------- 验证：FRP 隧道是否可达 ----------
verify() {
    info "等待网络稳定并检查 FRP 隧道..."
    local waited=0
    while [ "$waited" -lt 120 ]; do
        if nc -zw 5 "$FRP_HOST" "$FRP_PORT" 2>/dev/null; then
            info "✅ FRP 隧道可达（$FRP_HOST:$FRP_PORT），保持新连接"
            touch "$OK_FLAG"
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
        [ $((waited % 15)) -eq 0 ] && info "  等待 FRP 重连... ${waited}s"
    done
    warn "⚠️  FRP 隧道在 ${waited}s 内未恢复，触发回退"
    return 1
}

# ---------- 立即回退（非看门狗路径） ----------
fallback_now() {
    source "$STATE_FILE" 2>/dev/null
    info "立即回退到原 WiFi..."
    for i in 1 2 3; do
        timeout 30 nmcli connection up "${CURRENT_CONN}" 2>/dev/null && {
            info "✅ 已切回 ${CURRENT_CONN}"
            return 0
        }
        sleep 3
    done
    err "回退全部失败，看门狗仍在后台运行（${WATCHDOG_TIMEOUT}s 后会再试）"
    return 1
}

# ---------- Dry-run ----------
dry_run() {
    echo "=============================="
    echo " WiFi 切换计划"
    echo "=============================="
    echo "  从:     $(iwgetid -r 2>/dev/null || echo '未知')"
    echo "  到:     $TARGET_SSID"
    echo "  验证:   $FRP_HOST:$FRP_PORT (FRP SSH 隧道)"
    echo "  超时:   ${WATCHDOG_TIMEOUT}s 看门狗自动回退"
    echo ""
    echo "⚠️  切换后当前 SSH 会话会断连"
    echo "   确认回连: ssh chenan@$FRP_HOST -p $FRP_PORT"
    echo "=============================="
    echo "执行: $0 execute"
}

# ---------- Main ----------
main() {
    [ "$1" != "execute" ] && { dry_run; exit 0; }
    precheck
    save_current_state
    setup_target
    start_watchdog
    switch_wifi
    if verify; then
        info "✅ 切换成功，FRP 隧道已恢复"
        # 看门狗会在超时后检测到 OK_FLAG 并退出
        exit 0
    else
        kill "$(cat /tmp/wifi-watchdog.pid 2>/dev/null)" 2>/dev/null
        fallback_now
        exit 1
    fi
}

main "$@"
