# 3-Node Cluster: KVM + Seoul Direct + VMISS-HK

## Nodes

| Name | Type | Server | Port | UUID | Path | TLS | skip-cert |
|------|------|--------|------|------|------|-----|-----------|
| 233boy-KVM | VMess+WS | kvm.bernarty.xyz | 30717 | f2586607-5bbd-4947-a1cb-db23f48aaf0c | /f2586607-... | ✅ | ❌ |
| Seoul-Cloudflare | VMess+WS | seoul.bernarty.xyz | 443 | ac6aa939-156c-452f-a7da-4ddd79b7d5c9 | /ws-seoul | ✅ | ✅ |
| VMISS-HK | VMess+WS | vmiss.bernarty.xyz | 443 | ac6aa939-156c-452f-a7da-4ddd79b7d5c9 | /ws-vmiss | ✅ | ❌ |

## 2026-06-21 Seoul 迁移

- Seoul 节点从 Cloudflare 快速隧道迁移到固定 DNS 直连
- DNSPod 新增 A 记录 seoul.bernarty.xyz -> 43.108.41.245
- 加入 skip-cert-verify: true（Seoul xray TLS 证书为自签）
- cloudflared 保留在 Seoul VPS 但不作为 OpenClash 节点

## Google Auth Traffic Splitting

19 个 Google 认证域名路由到 Google-Auth 代理组:
- 路由规则: accounts.google.*, oauth2.googleapis.com, ssl.gstatic.com, play.google.com 等
- 代理组选序: Seoul-Cloudflare → VMISS-HK → 233boy-KVM
- 原因: KVM IP 被 Google 封禁，认证请求必须走 Seoul 或 VMISS

## Real-world Latency (2026-06-21)

| 场景 | 233boy-KVM | Seoul-Cloudflare | VMISS-HK |
|------|-----------|-----------------|---------|
| CF generate_204 | 204 0.72s | 204 0.98s | 204 0.59s |
| YouTube | 200 2.32s | — (隧道已弃用) | 200 1.37s |
| 节点直连 | 301 2.53s | 404 0.23s | 404 0.87s |
