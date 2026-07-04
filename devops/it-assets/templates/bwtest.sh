#!/bin/sh
# OpenClash bandwidth test — test proxy node bandwidth via OpenClash API
# Usage: bwtest [OPTION|NODE]
#   (no args)  Test the currently selected proxy node
#   NODE       Test a specific proxy node
#   --all      Test all proxy nodes
#   --help     Show this help with available nodes

API="http://127.0.0.1:9090"
SCR=$(awk '/^secret:/{print $2}' /etc/openclash/config.yaml 2>/dev/null)
H="Authorization: Bearer $SCR"
U="https://speed.cloudflare.com/__down?bytes=26214400"
FALLBACK="http://speedtest.tele2.net/10MB.zip"

if [ -z "$SCR" ]; then
  echo "ERROR: cannot read secret from /etc/openclash/config.yaml"
  exit 1
fi

# Fetch proxy-group data from API (single call, cached)
fetch_pgroup() {
  curl -s -H "$H" "$API/proxies/PROXY"
}

# Extract the "all" array as one-per-line, filter out pseudo-nodes
get_nodes() {
  fetch_pgroup | \
    sed 's/.*"all":\[\([^]]*\)\].*/\1/' | \
    sed 's/"//g' | tr ',' '\n' | grep -v '^AUTO$'
}

# Get current node name
get_current() {
  fetch_pgroup | sed 's/.*"now":"\([^"]*\)".*/\1/'
}

# Switch PROXY to given node; returns HTTP code
set_node() {
  curl -s -o /dev/null -w "%{http_code}" -X PUT "$API/proxies/PROXY" \
    -H "$H" -H "Content-Type: application/json" \
    -d "{\"name\":\"$1\"}"
}

# Restore original node if it changed
restore_orig() {
  orig="$1"
  now=$(get_current)
  if [ "$now" != "$orig" ]; then
    set_node "$orig" >/dev/null 2>&1
    echo "Restored to: $orig"
  fi
}

# Download a file via proxy and measure throughput
test_node() {
  n="$1"
  printf ">> %-40s " "$n"

  c=$(set_node "$n")
  if [ "$c" != "204" ] && [ "$c" != "200" ]; then
    echo "[fail HTTP $c]"
    return
  fi
  sleep 2

  s=$(date +%s)
  hc=$(curl -s --max-time 120 -x http://127.0.0.1:7890 --proxy-user Clash:3Ypy6ovV \
       -o /tmp/b.bin -w "%{http_code}" "$U")
  e=$(date +%s); d=$((e-s))

  if [ "$hc" = "200" ]; then
    sz=$(wc -c < /tmp/b.bin 2>/dev/null || echo 26214400)
    [ "$d" -le 0 ] && d=1
    mbps=$(awk -v sz=$sz -v d=$d 'BEGIN {printf "%.2f", sz * 8 / d / 1048576}')
    printf "%3ss  %sMbps\n" "$d" "$mbps"
    rm -f /tmp/b.bin
  else
    hc2=$(curl -s --max-time 120 -x http://127.0.0.1:7890 --proxy-user Clash:3Ypy6ovV \
          -o /tmp/b2.bin -w "%{http_code}" "$FALLBACK")
    e2=$(date +%s); d2=$((e2-s))
    if [ "$hc2" = "200" ]; then
      sz2=$(wc -c < /tmp/b2.bin 2>/dev/null || echo 10485760)
      [ "$d2" -le 0 ] && d2=1
      mbps2=$(awk -v sz=$sz2 -v d=$d2 'BEGIN {printf "%.2f", sz * 8 / d / 1048576}')
      printf "%3ss  %sMbps (10MB)\n" "$d2" "$mbps2"
      rm -f /tmp/b2.bin
    else
      echo "FAIL ($hc/$hc2)"
    fi
  fi
}

# ─── Argument handling ──────────────────────────────────
case "${1:-}" in
  --all)
    orig=$(get_current)
    echo "=== Node bandwidth test (all nodes) ==="
    echo "Time: $(date "+%Y-%m-%d %H:%M:%S")"
    echo ""
    for n in $(get_nodes); do
      test_node "$n"
    done
    echo ""
    echo "=== Done ==="
    restore_orig "$orig"
    ;;

  --help|-h)
    echo "Usage: bwtest [OPTION|NODE]"
    echo ""
    echo "Test proxy node bandwidth via OpenClash."
    echo ""
    echo "  (no args)    Test the currently selected proxy node"
    echo "  NODE         Test a specific proxy node"
    echo "  --all        Test all proxy nodes"
    echo "  --help       Show this help and list available nodes"
    echo ""
    echo "Available nodes:"
    current=$(get_current)
    curl -s -H "$H" "$API/proxies/PROXY" | \
      sed 's/.*"all":\[\([^]]*\)\].*/\1/' | \
      sed 's/"//g' | tr ',' '\n' | while read n; do
        mark=""
        [ "$n" = "$current" ] && mark="  (current)"
        [ "$n" = "AUTO" ] && mark="  (auto-select)"
        echo "    $n$mark"
      done
    ;;

  "")
    # Default: test current node
    orig=$(get_current)
    if [ -z "$orig" ]; then
      echo "ERROR: cannot determine current proxy node"
      exit 1
    fi
    echo "=== Bandwidth test: $orig ==="
    echo "Time: $(date "+%Y-%m-%d %H:%M:%S")"
    echo ""
    test_node "$orig"
    echo ""
    echo "=== Done ==="
    restore_orig "$orig"
    ;;

  *)
    # Test specific node — validate it exists
    n="$1"; found=0
    for node in $(get_nodes); do
      if [ "$node" = "$n" ]; then found=1; break; fi
    done
    if [ "$found" -eq 0 ]; then
      echo "ERROR: node '$n' not found."
      echo "Use 'bwtest --help' to see available nodes."
      exit 1
    fi
    orig=$(get_current)
    echo "=== Bandwidth test: $n ==="
    echo "Time: $(date "+%Y-%m-%d %H:%M:%S")"
    echo ""
    test_node "$n"
    echo ""
    echo "=== Done ==="
    restore_orig "$orig"
    ;;
esac
