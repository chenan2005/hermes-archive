# VMISS Hong Kong BGP Variants

Source: DigVPS review + VMISS product page (verified 2026-06)

## Tier comparison

| Tier | Label | Return routing | Peak stability | Price (Basic) | Best for |
|------|-------|---------------|----------------|---------------|----------|
| **DC1** (Cloudie) | CN - HongKong - BGP | Telecom **CN2**/CMI, Mobile CMI/CMI, Unicom 4837/4837 | ✅ Good | CAD $5/mo (~¥26) | **Default recommendation** |
| **DC2** | CN - HongKong - BGP #DC2 | Telecom **CN2**/CMI, Mobile CMI/CMI, Unicom 4837/CMI | ⚠️ Good speed (860Mbps single-thread tested) but 95s connection breaks | CAD $5/mo | Backup/secondary, speed when it works |
| **DC3** | CN - HongKong - BGP #DC3 | Telecom **CN2**/CTG, Mobile 4837/CMI, Unicom 4837/10099 | ✅ All models exceed rated 100Mbps | CAD $5/mo | **Runner-up**, slightly different routing mix |
| **INTL** | CN - HongKong - INTL | Telecom 163/163, Mobile CMI/CMI, Unicom 4837/4837 | ❌ No China optimization | CAD $30/yr (~¥13/mo) | **NOT for China users** — use as landing only |

## Key observations

- **DC1 and DC3** both have Telecom CN2/CTG return — this is the premium China Telecom route. Either is suitable.
- **DC2** has excellent burst speed but reported instability (connection drops after ~95s). Not recommended for primary use.
- **INTL** is cheap for a reason — it routes through Telecom 163 (the congested standard path). This is equivalent to Alibaba's "非中国优化". Do NOT buy for China-facing use.
- All three BGP tiers (DC1/DC2/DC3) should use the **same PassWall node config** — VMess+WS+TLS with the server's IP/domain, port 443, valid Let's Encrypt cert. The routing difference is on the provider side (peering/transit), not the protocol.

## Buying decision flow

```
Need HK VPS for China proxy?
  ├── Budget ≤¥30/mo → VMISS Basic (DC1 or DC3)
  ├── Budget ¥50-100/mo → Alibaba Cloud HK (BGP, not 非中国优化)
  └── Budget >¥100/mo → GigsGigsCloud / DMIT (CN2 GIA guaranteed)
```

## Performance comparison

| Test | VMISS BGP DC1 | Seoul (Alibaba CN→KR) |
|------|:----------:|:--------------------:|
| Outbound (VPS→Tokyo) | 45 Mbps | 620 Mbps |
| Return (VPS→CN) | 36-52 Mbps | 0.75 Mbps |
| Peak-hour drop | Minimal | 100% (unusable) |
| Price | ¥26/mo | ¥56/mo |

China→Hong Kong has fundamentally better cross-border bandwidth than China→Korea, regardless of routing tier. Even basic HK BGP outperforms Seoul with CN2.
