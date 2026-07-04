Linux Mint 22, sudo NOPASSWD。设备/网络→home-ops skill。WOL走ImmortalWrt。本机71.24（光猫WiFi）。
§
OpenClash redir-host模式(mihomo挂不影响国内)。
§
本机DNS:71.1+223.5.5.5(AliDNS直连不代理)，不加IPv6。nmcli操作，network-profile切direct(71.1)/proxy(71.9)。minipc有线71.9(metric 25)，WiFi(metric 5000)。9950x3d纯走71.9(sing-box已删)。静态路由37.0/24 via 71.9。
§
9950x3d Win11: RTX5090 32GB。Python3.14(用python不是python3)，终端GBK。Edge:C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe。CDP需schtasks(SSH→Session 0)。Qwen3.6-27B: Q4_K_M, 262K ctx, q8_0 KV, ~75tok/s, VRAM 27.8/32GB。Windows llama.cpp无FA。
§
sing-box: ~/.config/sing-box/config.json, systemctl --user。修改前unset所有proxy。.bashrc proxy函数切换+auto source ~/.config/proxy-env。
§
查待办→直接skill_view('todo-list')，不查todo()/cron/记忆。
§
cron互管用no_agent=true+脚本调Hermes API，不经过LLM。