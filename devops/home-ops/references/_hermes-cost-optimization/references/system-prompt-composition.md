# System Prompt & Tool Schema Composition Reference

Measured on Hermes git-installed (commit ~2026-06), 130 skills, 42 tools, deepseek-v4-flash.

## System Prompt (sent as `system` message)

| Tier | Size | Contents |
|------|------|----------|
| **stable** | ~24.5 KB / ~6,100 tok | SOUL.md + guidance + platform hint + environment + **skills index** + profile hint |
| **context** | 0 (typical) | AGENTS.md (only if cwd is inside a git repo with one) |
| **volatile** | ~6.5 KB / ~1,600 tok | Memory + User profile + timestamp/model |
| **Total** | **~31.5 KB / ~7,900 tok** | Sent on every turn, cached as KV prefix |

### Major Blocks Inside Stable

| Block | Size | Notes |
|-------|------|-------|
| Skills index (130 skills) | ~14.1 KB | Largest single block; middle entries most susceptible to LITM |
| SOUL.md | ~2.3 KB | User identity + style |
| Guidance constants | ~5.5 KB | 6-8 blocks: task completion, parallel calls, tool-specific guidance, enforcement |
| Environment/platform | ~1.5 KB | OS, cwd, Python probe, CLI hint |
| Profile hint | ~0.3 KB | Active Hermes profile name |

## Tool Schemas (sent as `tools` API parameter)

- **Total**: ~64.7 KB JSON / ~16,000 tok
- **Count**: 42 tools
- **Not part of system prompt string** — sent as a separate API parameter

### Largest Tools

| Tool | Size | Why |
|------|------|-----|
| cronjob | 7.9 KB | Many optional params (schedule, skills, model, deliver, script...) |
| delegate_task | 7.8 KB | tasks array + parallel spawn params |
| session_search | 5.8 KB | 4 calling shapes, long description |
| terminal | 5.5 KB | background + pty + watch_patterns |
| skill_manage | 4.1 KB | create/patch/edit/delete each has distinct params |
| memory | 2.8 KB | batch operations array + formatting |
| execute_code | 2.7 KB | code + timeout + explicit tool imports |

Top 7 tools account for ~36 KB (56% of total). Browser tools (10 tools) account for ~4.1 KB, Feishu tools (5 tools) ~2.6 KB.

## Why Tool Schemas Don't Cause "Lost in the Middle"

Tool schemas sit at a **fixed position** in the context (immediately after system prompt, before any conversation history). The model accesses them lazily — it only reads the schema of a tool it's actively considering calling. 16K of JSON with template structure is much lower attention cost than 16K of natural language prose, because the model has been trained to pattern-match against tool schemas rather than read them sequentially.

The bigger attention concern is the **skills index inside the system prompt**: 130 natural-language descriptions, with middle entries in the index susceptible to "Lost in the Middle" as conversation history grows.

## Fixed Per-Turn Overhead

```
system prompt     = ~7,900 tok
tool schemas      = ~16,000 tok  
total fixed cost  = ~24,000 tok
```

On a 1M context model, the fixed prefix is ~2.4% of the window — negligible. On a 128K model (gpt-4o), it's ~19% — significant.

## Key Insight

**Conversation history length, not system prompt size, is the primary cause of attention degradation.** Each turn adds ~500-2,000 tokens. After 100 turns (~50K-200K tokens), the middle of conversation history hits "Lost in the Middle" regardless of how lean the system prompt is.
