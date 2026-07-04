#!/usr/bin/env python3
"""
sing-box-ctrl — 统一管理 sing-box 代理

跨平台（Linux / Windows），自动检测平台差异。

子命令:
  switch [节点名]   查看或切换出口节点
  start              启动 sing-box
  stop               停止 sing-box
  restart            重启 sing-box
  status             查看运行状态
  test [节点|--all]  测速（临时进程，不干扰当前代理）
  help               显示此帮助

跨平台设计:
  Linux:   systemctl --user 管理服务, 信号重载(SIGHUP)
  Windows: subprocess 启动, taskill 停止, 无 SIGHUP 改 stop+start
  路径:    Linux → ~/.config/sing-box/
           Windows → 脚本同级目录

关键发现（参见 network-pitfalls §windows-subprocess）:
  Windows 的 subprocess.Popen 默认在 Job Object 内,
  父进程退出后子进程也被杀。必须加 CREATE_BREAKAWAY_FROM_JOB。
"""

import json, os, shutil, signal, socket, statistics, subprocess, sys, tempfile, textwrap, time
from pathlib import Path

# ─── 平台检测 ────────────────────────
PLATFORM = sys.platform
IS_WINDOWS = PLATFORM == "win32"

# ─── 工具函数 ────────────────────────
def log(*a, **kw):
    print(*a, **kw)

def check_deps(name, flag="version"):
    r = subprocess.run([name, flag], capture_output=True, timeout=5)
    if r.returncode != 0:
        log(f"[FAIL] 未找到 {name}")
        sys.exit(1)

# ─── 平台抽象 ────────────────────────

class LinuxPlat:
    @staticmethod
    def bin():
        return "sing-box"

    @staticmethod
    def cfg_path():
        return Path.home() / ".config" / "sing-box" / "config.json"

    @staticmethod
    def is_running():
        r = subprocess.run(
            ["systemctl", "--user", "is-active", "sing-box.service"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0 and r.stdout.strip() == "active":
            r2 = subprocess.run(
                ["systemctl", "--user", "show", "--property", "MainPID",
                 "sing-box.service"],
                capture_output=True, text=True, timeout=5
            )
            pid = r2.stdout.strip().replace("MainPID=", "")
            if pid and pid != "0":
                return int(pid)
        return None

    @staticmethod
    def start():
        r = subprocess.run(["systemctl", "--user", "start", "sing-box.service"],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0

    @staticmethod
    def stop():
        r = subprocess.run(["systemctl", "--user", "stop", "sing-box.service"],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0

    @staticmethod
    def reload(pid):
        try:
            os.kill(pid, signal.SIGHUP)
            time.sleep(1)
            return True
        except ProcessLookupError:
            return False

    @staticmethod
    def port_free(p=10882):
        r = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True)
        return f":{p}" not in r.stdout

class WinPlat:
    _script_dir = Path(__file__).resolve().parent

    @staticmethod
    def bin():
        return str(WinPlat._script_dir / "sing-box.exe")

    @staticmethod
    def cfg_path():
        return WinPlat._script_dir / "config.json"

    @staticmethod
    def is_running():
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq sing-box.exe", "/FO", "CSV"],
            capture_output=True, text=True, timeout=5
        )
        if "sing-box.exe" in r.stdout:
            # parse PID from CSV line: "sing-box.exe","1234",...
            for line in r.stdout.strip().split("\n"):
                if "sing-box.exe" in line:
                    parts = line.split(",")
                    if len(parts) >= 2:
                        try:
                            pid = int(parts[1].strip('"'))
                            return pid
                        except ValueError:
                            pass
        return None

    @staticmethod
    def start():
        cfg = WinPlat.cfg_path()
        flags = subprocess.CREATE_NO_WINDOW
        if hasattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB"):
            flags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
        proc = subprocess.Popen(
            [WinPlat.bin(), "run", "-c", str(cfg)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags
        )
        time.sleep(2)
        return proc.poll() is None

    @staticmethod
    def stop():
        for pid in [WinPlat.is_running()] if WinPlat.is_running() else []:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=5)
        return True

    @staticmethod
    def reload(pid):
        WinPlat.stop()
        time.sleep(1)
        return WinPlat.start()

    @staticmethod
    def port_free(p=10882):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            s.close()
            return True
        except OSError:
            return False

PLAT = WinPlat() if IS_WINDOWS else LinuxPlat()

# ─── 配置操作 ────────────────────────

def load_config():
    p = PLAT.cfg_path()
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save_config(cfg):
    p = PLAT.cfg_path()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def list_nodes(cfg):
    return [o["tag"] for o in cfg["outbounds"]
            if o.get("tag") not in ("direct", "block") and o.get("tag")]

def current_node(cfg):
    return cfg.get("route", {}).get("final", "")

# ─── 延迟/带宽测试 ───────────────────

TEST_PORT =10882
NUL = "nul" if IS_WINDOWS else "/dev/null"
GOOGLE_URL= "https://www.google.com/generate_204"
GSTATIC_URL= "http://www.gstatic.com/generate_204"
CF_URL = "https://speed.cloudflare.com/__down?bytes=52428800"
_temp_dir = None
_temp_procs = []

def _cleanup(*_):
    for proc in _temp_procs:
        try:
            if proc.poll() is None:
                if IS_WINDOWS:
                    subprocess.run(["taskkill","/F","/T","/PID",str(proc.pid)],capture_output=True)
                else:
                    os.kill(proc.pid, signal.SIGKILL)
        except:
            pass
    if _temp_dir:
        shutil.rmtree(_temp_dir, ignore_errors=True)

signal.signal(signal.SIGINT, _cleanup)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _cleanup)

def curl_probe(*args, timeout=8, port=None):
    cmd = ["curl", "-sS", "--max-time", str(timeout)]
    if IS_WINDOWS:
        cmd.append("--ssl-no-revoke")
    if port:
        cmd += ["-x", f"socks5://127.0.0.1:{port}"]
    cmd += list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+5)
        return r.returncode, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return 28, ""
    except FileNotFoundError:
        return -1, "curl not found"

def latency_probe(port=None, timeout=8, count=10):
    samples = []
    if port is None:
        for _ in range(count):
            rc, out = curl_probe("-o", NUL, "-w","%{time_starttransfer}",
                                 GSTATIC_URL, timeout=5)
            if rc==0 and out:
                try: samples.append(float(out))
                except ValueError: pass
    else:
        for _ in range(3):
            rc, out = curl_probe("-o", NUL, "-w","%{time_starttransfer}",
                                 GOOGLE_URL, timeout=timeout, port=port)
            if rc==0 and out:
                try: samples.append(float(out))
                except ValueError: pass
        ok = len(samples)>0
        url = GOOGLE_URL if ok else GSTATIC_URL
        for _ in range(count-len(samples)):
            rc, out = curl_probe("-o", NUL, "-w","%{time_starttransfer}",
                                 url, timeout=timeout, port=port)
            if rc==0 and out:
                try: samples.append(float(out))
                except ValueError: pass
    return samples

def lat_stats(s):
    if len(s)<2: return 0.,0.
    ss = sorted(s)
    if len(ss)>=4: ss=ss[1:-1]
    m = statistics.mean(ss)
    return m*1000, sum(abs(x-m) for x in ss)/len(ss)*1000

def bandwidth_test(port, url, max_time=60):
    cmd = ["curl","-sS","--max-time",str(max_time)]
    if IS_WINDOWS: cmd.append("--ssl-no-revoke")
    cmd += ["-w","%{http_code} %{speed_download}", "-o", NUL]
    if port: cmd+=["-x",f"socks5://127.0.0.1:{port}"]
    cmd.append(url)
    try:
        start = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=max_time+10)
        el = time.time()-start
        if r.returncode==0 and r.stdout.strip():
            p = r.stdout.strip().split()
            h = int(p[0]) if p[0].isdigit() else 0
            sp= float(p[1]) if len(p)>1 else 0.
            return h, sp, el
        return 0,0.,el
    except subprocess.TimeoutExpired:
        return 0,0.,max_time+10

def make_temp_cfg(tag):
    cfg = load_config()
    target = None
    for o in cfg["outbounds"]:
        if o.get("tag")==tag:
            target = dict(o); break
    if not target:
        log(f"[FAIL] 节点 '{tag}' 未找到"); sys.exit(1)
    return {
        "log":{"level":"error"},
        "inbounds":[{"type":"socks","tag":"si","listen":"127.0.0.1","listen_port":TEST_PORT}],
        "outbounds":[target,{"type":"direct","tag":"direct"}],
        "route":{"final":tag}
    }

def test_one(tag):
    global _temp_dir, _temp_procs
    cfg = load_config()
    if tag not in list_nodes(cfg):
        log(f"[FAIL] 节点 '{tag}' 不在配置中"); return
    _temp_dir = tempfile.mkdtemp(prefix="sb-")
    with open(Path(_temp_dir)/"config.json", "w") as f:
        json.dump(make_temp_cfg(tag), f, indent=2)
    bin = PLAT.bin()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if hasattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB"):
        flags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
    proc = subprocess.Popen(
        [bin,"run","-c",str(Path(_temp_dir)/"config.json"),"-D",_temp_dir],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags
    )
    _temp_procs.append(proc); time.sleep(2)
    if proc.poll() is not None:
        log(f"  [FAIL] 临时 sing-box 启动失败"); return
    ls = latency_probe(port=TEST_PORT)
    lat, jit = lat_stats(ls) if ls else (0,0)
    _, sp, _ = bandwidth_test(port=TEST_PORT, url=CF_URL)
    mbps = sp*8/1_000_000 if sp>0 else 0
    log(f"  {tag:<25s} {lat:7.0f} {jit:7.1f} {mbps:8.1f} Mbps")

def test_direct():
    ls = latency_probe(port=None); lat,jit = lat_stats(ls) if ls else (0,0)
    _, sp, _ = bandwidth_test(port=None, url="https://dl.google.com/tag/s/appguid%3D%7B8A69D345-D564-463C-AFF1-A69D9E530F96%7D%26iid%3D%7B00000000-0000-0000-0000-000000000000%7D%26lang%3Den%26browser%3D3%26usagestats%3D1%26appname%3DGoogle%2520Chrome%26needsadmin%3Dprefers%26ap%3Dx64-stable-statsdef_1/dl/chrome/install/googlechromestandaloneenterprise64.msi", max_time=15) if not IS_WINDOWS else (0, 0., 0.)
    if sp==0:
        _, sp, _ = bandwidth_test(port=None, url="https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb", max_time=15) if not IS_WINDOWS else bandwidth_test(port=None, url="https://dldir1.qq.com/weixin/Windows/WeChatSetup.exe", max_time=15)
    mbps = sp*8/1_000_000 if sp>0 else 0
    log(f"  {'direct':<25s} {lat:7.0f} {jit:7.1f} {mbps:8.1f} Mbps")

# ─── 子命令 ────────────────────────

def cmd_switch(args):
    cfg = load_config(); nodes = list_nodes(cfg); cur = current_node(cfg)
    if not args:
        log(f"当前节点: {cur}")
        pid = PLAT.is_running()
        log(f"sing-box: {'运行中 (PID '+str(pid)+')' if pid else '已停止'}\n")
        log("可用节点:")
        for n in nodes:
            log(f"  {'->' if n==cur else '  '} {n}")
        return
    target = args[0]
    if target not in nodes:
        log(f"[FAIL] 节点 '{target}' 不在配置中: {', '.join(nodes)}"); return
    cfg["route"]["final"] = target
    save_config(cfg)
    pid = PLAT.is_running()
    if pid:
        if PLAT.reload(pid):
            time.sleep(1)
            log(f"[OK] 已切换 -> {target}")
        else:
            log(f"[WARN] 配置已更新但重载失败")
    else:
        log(f"[OK] 配置已更新 (未运行)")

def cmd_start():
    if PLAT.is_running():
        log("[WARN] sing-box 已在运行"); return
    if PLAT.start():
        pid = PLAT.is_running()
        log(f"[OK] sing-box 已启动" + (f" (PID {pid})" if pid else ""))
    else:
        log("[FAIL] 启动失败")

def cmd_stop():
    if not PLAT.is_running():
        log("[WARN] sing-box 未运行"); return
    if PLAT.stop():
        log("[OK] sing-box 已停止")
    else:
        log("[FAIL] 停止失败")

def cmd_restart():
    cmd_stop(); time.sleep(1); cmd_start()

def cmd_status():
    cfg = load_config(); nodes = list_nodes(cfg); cur = current_node(cfg)
    pid = PLAT.is_running()
    log(f"状态: {'运行中 (PID '+str(pid)+')' if pid else '已停止'}")
    log(f"节点: {cur}")
    log("")
    for n in nodes:
        log(f"  {'->' if n==cur else '  '} {n}")
    # show proxy ports from config
    for ib in cfg.get("inbounds", []):
        ip = ib.get("listen",""); pt = ib.get("listen_port","")
        tp = ib.get("type","").upper()
        if pt: log(f"  {tp:7s} {ip}:{pt}")

def cmd_test(args):
    cfg = load_config(); nodes = list_nodes(cfg); cur = current_node(cfg)
    if not args:
        test_one(cur); _cleanup(); return
    if args[0]=="--all":
        for n in nodes: test_one(n)
        test_direct(); _cleanup(); return
    if args[0]=="--direct":
        test_direct(); _cleanup(); return
    tag = args[0]
    if tag not in nodes:
        log(f"[FAIL] 节点 '{tag}' 未找到: {', '.join(nodes)}"); return
    test_one(tag); _cleanup()

def show_help():
    print(textwrap.dedent("""\
    sing-box-ctrl -- 跨平台 sing-box 管理

    子命令:
      switch [节点]  切换出口节点
      start          启动
      stop           停止
      restart        重启
      status         状态
      test [--all|--direct|<节点>]  测速
      help           帮助
    """))
    try:
        cfg = load_config(); nodes=list_nodes(cfg); cur=current_node(cfg)
        pid=PLAT.is_running()
        log(f"节点: {', '.join(nodes)}")
        log(f"当前: {cur}")
        log(f"状态: {'运行中' if pid else '已停止'}")
    except:
        log("(config.json 不可用)")

def main():
    sub = sys.argv[1] if len(sys.argv)>1 else "help"
    args = sys.argv[2:]
    cmds = {
        "switch": lambda: cmd_switch(args),
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "status": cmd_status,
        "test": lambda: cmd_test(args),
        "help": show_help,
    }
    if sub in cmds:
        cmds[sub]()
    else:
        log(f"[FAIL] 未知命令: {sub}. 可用: {', '.join(cmds)}")

if __name__ == "__main__":
    main()
