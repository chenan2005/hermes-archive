# Hindsight vs Prefix Caching

DeepSeek's automatic disk-based prefix cache matches on sequential token equality from the start of the request. Any variance in the prefix — including the injected memory block — breaks the cache.

## Cache Behavior by Hindsight Mode

| Injection Point | Without Hindsight | With Hindsight (per-turn recall) |
|---|---|---|
| Session turn 1 | ✅ System prompt cached | ❌ Memory content injected after system prompt, breaks from offset |
| Session turn N | ✅ System prompt + prior history cached | ❌ Memory content changes each turn (new recall results) |
| New session | ✅ Re-cache system prompt | ❌ Same — recall results differ per session |

## Why It Matters

- **No Hindsight:** ~80% of input tokens are cached per turn (system prompt + history prefix → 10% price)
- **With Hindsight (full recall):** Only system prompt itself (< 2000t) remains cached; the memory block and everything after is uncached → full price

## Mitigation Options (with tradeoffs)

| Approach | Cache Saved | Accuracy Loss | Complexity |
|----------|------------|---------------|------------|
| Per-session fixed memory (no per-turn recall) | ✅ Full prefix cached | ❌ High — no new context | None |
| Incremental memory (discussed but not implemented) | ✅ Most of prefix preserved | Low | High — dedup + context tracking needed |
| Reduce recall frequency (every 3-5 turns) | Partial (stable between recalls) | Low | Low — config change |
| Use OpenViking (L0 fixed → cached, L1/L2 on demand) | ✅ L0 cached always | Depends on tier | Low |
