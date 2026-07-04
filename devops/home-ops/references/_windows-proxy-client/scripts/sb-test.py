#!/usr/bin/env python3
"""Proxy bandwidth test tool for sing-box on Windows.

Usage:
  sb-test.py                        Test current node
  sb-test.py <node_tag>             Test specific node
  sb-test.py --all                  Test all nodes + direct
  sb-test.py --direct               Direct test only
  sb-test.py --help                 Show help

Mechanism:
  Starts a temporary sing-box on port 10882 (doesn't interfere with the
  running proxy on 10880), runs latency probe (10 curl samples via SOCKS5),
  then bandwidth test (Cloudflare 50MB download). Kills temp instance after.

Key findings (see network-pitfalls skill speedtest-socks5):
  - speedtest.exe does NOT support SOCKS5 proxy
  - Use curl -x socks5://127.0.0.1:<port> for correct proxy measurements
"""

import json, os, shutil, signal, socket, statistics, subprocess, sys, tempfile, time
from pathlib import Path

TEST_PORT = 10882
CF_URL = "https://speed.cloudflare.com/__down?bytes=52428800"
GOOGLE_PROBE = "https://www.google.com/generate_204"
GSTATIC_PROBE = "http://www.gstatic.com/generate_204"
NUL = "nul"

SCRIPT_DIR = Path(__file__).resolve().parent
PID_FILE = Path(tempfile.gettempdir()) / "sb-test.pid"

_temp_dir = None
_temp_procs = []

def log(*a, **kw):
    print(*a, **kw)

def _cleanup_temp(*_):
    for proc in _temp_procs:
        try:
            if proc.poll() is None:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True)
        except:
            pass
    if PID_FILE.exists():
        PID_FILE.unlink()
    if _temp_dir:
        shutil.rmtree(_temp_dir, ignore_errors=True)

signal.signal(signal.SIGINT, _cleanup_temp)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _cleanup_temp)

def load_config():
    cfg = SCRIPT_DIR / "config.json"
    with open(cfg, encoding="utf-8") as f:
        return json.load(f)

def list_nodes(cfg):
    return [o["tag"] for o in cfg["outbounds"]
            if o.get("tag") not in ("direct", "block") and o.get("tag")]

def current_node(cfg):
    final = cfg.get("route", {}).get("final", "")
    return final

def port_free(p=TEST_PORT):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        s.close()
        return True
    except OSError:
        return False

def curl_probe(*args, timeout=8, proxy=None):
    cmd = ["curl", "-sS", "--max-time", str(timeout), "--ssl-no-revoke"]
    if proxy:
        cmd += ["-x", f"socks5://127.0.0.1:{proxy}"]
    cmd += list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        return r.returncode, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return 28, ""
    except FileNotFoundError:
        return -1, "curl not found"

def latency_probe(proxy_port=None, timeout=8, count=10):
    samples = []
    if proxy_port is None:
        for _ in range(count):
            rc, out = curl_probe(
                "-o", NUL, "-w", "%{time_starttransfer}",
                GSTATIC_PROBE, timeout=5
            )
            if rc == 0 and out:
                try:
                    samples.append(float(out))
                except ValueError:
                    pass
    else:
        for _ in range(3):
            rc, out = curl_probe(
                "-o", NUL, "-w", "%{time_starttransfer}",
                GOOGLE_PROBE, timeout=timeout, proxy=proxy_port
            )
            if rc == 0 and out:
                try:
                    samples.append(float(out))
                except ValueError:
                    pass
        use_google = len(samples) > 0
        for _ in range(count - len(samples)):
            url = GOOGLE_PROBE if use_google else GSTATIC_PROBE
            rc, out = curl_probe(
                "-o", NUL, "-w", "%{time_starttransfer}",
                url, timeout=timeout, proxy=proxy_port
            )
            if rc == 0 and out:
                try:
                    samples.append(float(out))
                except ValueError:
                    pass
    return samples

def lat_stats(samples):
    if len(samples) < 2:
        return (0.0, 0.0)
    s = sorted(samples)
    if len(s) >= 4:
        s = s[1:-1]
    m = statistics.mean(s)
    mad = sum(abs(x - m) for x in s) / len(s)
    return (m * 1000, mad * 1000)

def bandwidth_test(proxy_port, url, max_time=60):
    cmd = ["curl", "-sS", "--max-time", str(max_time), "--ssl-no-revoke",
           "-w", "%{http_code} %{speed_download}",
           "-o", NUL]
    if proxy_port:
        cmd += ["-x", f"socks5://127.0.0.1:{proxy_port}"]
    cmd.append(url)
    try:
        start = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=max_time + 10)
        elapsed = time.time() - start
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split()
            http_code = int(parts[0]) if parts[0].isdigit() else 0
            speed = float(parts[1]) if len(parts) > 1 else 0.0
            return http_code, speed, elapsed
        return 0, 0.0, elapsed
    except subprocess.TimeoutExpired:
        return 0, 0.0, max_time + 10

def make_temp_cfg(node_tag):
    cfg = load_config()
    target = None
    for o in cfg["outbounds"]:
        if o.get("tag") == node_tag:
            target = dict(o)
            break
    if not target:
        log(f"[FAIL] 节点 '{node_tag}' 未找到")
        sys.exit(1)
    temp = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "socks",
            "tag": "socks-in",
            "listen": "127.0.0.1",
            "listen_port": TEST_PORT
        }],
        "outbounds": [target, {"type": "direct", "tag": "direct"}],
        "route": {"final": node_tag}
    }
    return temp

def test_one(node_tag):
    log(f"\n  测试节点: {node_tag}")
    if node_tag not in list_nodes(load_config()):
        log(f"  节点 '{node_tag}' 不在配置中")
        return
    global _temp_dir
    _temp_dir = tempfile.mkdtemp(prefix="sb-test-")
    temp_cfg = make_temp_cfg(node_tag)
    cfg_path = Path(_temp_dir) / "config.json"
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(temp_cfg, f, indent=2)

    log("  启动临时 sing-box...")
    flags = subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB"):
        flags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
    proc = subprocess.Popen(
        [str(SCRIPT_DIR / "sing-box.exe"), "run", "-c", str(cfg_path), "-D", _temp_dir],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags
    )
    _temp_procs.append(proc)
    time.sleep(2)

    if proc.poll() is not None:
        log("  [FAIL] 临时 sing-box 启动失败")
        return

    log("  延迟采样...")
    lat_samples = latency_probe(proxy_port=TEST_PORT)
    lat, jit = lat_stats(lat_samples) if lat_samples else (0, 0)

    log("  带宽测试 (Cloudflare 50MB)...")
    http_code, speed, _ = bandwidth_test(proxy_port=TEST_PORT, url=CF_URL)
    if speed > 0:
        mbps = speed * 8 / 1_000_000
    else:
        mbps = 0

    log(f"  [{node_tag}] 延迟={lat:.0f}ms 抖动={jit:.1f}ms 带宽={mbps:.1f}Mbps")

def test_direct():
    log("\n  直连测试:")
    log("    延迟采样...")
    lat_samples = latency_probe(proxy_port=None)
    lat, jit = lat_stats(lat_samples) if lat_samples else (0, 0)
    log("    带宽测试 (Google CDN)...")
    url = "https://dl.google.com/tag/s/appguid%3D%7B8A69D345-D564-463C-AFF1-A69D9E530F96%7D%26iid%3D%7B00000000-0000-0000-0000-000000000000%7D%26lang%3Den%26browser%3D3%26usagestats%3D1%26appname%3DGoogle%2520Chrome%26needsadmin%3Dprefers%26ap%3Dx64-stable-statsdef_1/dl/chrome/install/googlechromestandaloneenterprise64.msi"
    http_code, speed, _ = bandwidth_test(proxy_port=None, url=url, max_time=15)
    if speed > 0:
        mbps = speed * 8 / 1_000_000
    else:
        log("    Google CDN 不可用，回退腾讯 CDN...")
        url2 = "https://dldir1.qq.com/weixin/Windows/WeChatSetup.exe"
        _, speed, _ = bandwidth_test(proxy_port=None, url=url2, max_time=15)
        mbps = speed * 8 / 1_000_000 if speed > 0 else 0
    log(f"  [direct] 延迟={lat:.0f}ms 抖动={jit:.1f}ms 带宽={mbps:.1f}Mbps")

def cmd_test(args):
    if not args or args[0] in ("--help", "-h"):
        print(__doc__)
        return
    if args[0] == "--direct":
        test_direct()
        return

    cfg = load_config()
    nodes = list_nodes(cfg)

    if args[0] == "--all":
        for n in nodes:
            test_one(n)
        test_direct()
    else:
        node_tag = args[0]
        if node_tag not in nodes:
            log(f"[FAIL] 节点 '{node_tag}' 未找到。可用: {', '.join(nodes)}")
            return
        test_one(node_tag)
    _cleanup_temp()

def main():
    if not sys.argv[1:]:
        cmd_test(["--help"])
        return
    cmd_test(sys.argv[1:])

if __name__ == "__main__":
    main()
