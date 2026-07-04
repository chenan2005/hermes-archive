---
name: hermes-cost-optimization
description: "Install and configure token monitoring (Tokscale), terminal output compression (RTK), and context compression threshold tuning for Hermes Agent — track and reduce API costs by matching compression to model attention degradation."
---

# Hermes Cost Optimization

Three complementary strategies to track and reduce Hermes Agent API token costs:

- **Tokscale** — local token usage monitor, reads Hermes state.db directly
- **RTK** (Rust Token Killer) — CLI output compressor
- **Context compression tuning** — adjust auto-compression threshold to match model context window vs. practical attention degradation

## Tokscale — Token Monitoring

### Install
```bash
npm install -g tokscale
# or run directly without install:
npx tokscale@latest
```

### Usage
```bash
tokscale                              # Interactive TUI
tokscale --client hermes --light      # Hermes-only, table view
tokscale --client hermes --today      # Today's usage
tokscale --client hermes --week       # Last 7 days
tokscale pricing "deepseek-v4-flash"  # Look up model pricing
```

**How it works:** Tokscale automatically detects Hermes state.db at `$HERMES_HOME/state.db` or `~/.hermes/state.db`. No config needed.

**Pricing:** Real-time via LiteLLM pricing database, 1-hour disk cache.

## RTK — Terminal Output Compression

### Install
```bash
# Download install script (pipe-to-sh is blocked by Hermes security filters):
curl -fsSL -o /tmp/rtk-install.sh https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh
# Review script, then:
sh /tmp/rtk-install.sh
```

### Configure for Hermes
```bash
rtk init --agent hermes
```

This installs a Python plugin at `~/.hermes/plugins/rtk-rewrite/` and registers it in `~/.hermes/config.yaml`. **Restart Hermes** to activate.

### Verification
```bash
rtk --version     # Should show v0.28+ (or current)
rtk gain          # Token savings stats (after some usage)
```

### How RTK Saves Tokens
RTK sits between the shell and Hermes, rewriting commands like `git status`, `ls`, `cat`, `cargo test` to output only the essential info:

| Operation | Standard | RTK | Savings |
|-----------|----------|-----|---------|
| git status | 3,000 | 600 | -80% |
| cat/read | 40,000 | 12,000 | -70% |
| cargo/npm test | 25,000 | 2,500 | -90% |
| ls/tree | 2,000 | 400 | -80% |

## Pitfalls

- **RTK curl | sh blocked**: Hermes security filters block pipe-to-interpreter patterns. Always download first with `-o /tmp/rtk-install.sh`, review, then execute.
- **RTK needs Hermes restart**: Plugin won't activate until the session restarts.
- **Tokscale no output**: If `tokscale --client hermes` shows empty data, check `~/.hermes/state.db` exists and has session records (needs at least a few conversations of usage).
- **Model not in pricing**: Tokscale falls back to OpenRouter pricing or custom overrides at `~/.config/tokscale/custom-pricing.json`. For DeepSeek models, LiteLLM coverage is good.
- **Name collision on crates.io**: Another project named "rtk" (Rust Type Kit) exists. If `rtk gain` fails, you have the wrong package. Use `cargo install --git https://github.com/rtk-ai/rtk` instead.

## Context Compression Tuning — Model-Aware Threshold

Hermes auto-compresses conversation history when cumulative tokens reach `threshold × context_length`. The default `threshold: 0.85` is a safe-for-all-models value, but it wastes tokens on large-context models because **instruction-following degrades well before 85%**.

### The Problem

A model's context window is NOT the same as its usable attention budget:

| Model | Context | Default 85% threshold | Compression fires at | Skill/instruction recall starts to fade at |
|---|---|---|---|---|
| deepseek-v4-flash | 1,000,000 | 850,000 tokens | Way too late | ~200K tokens |
| claude-sonnet-4 | 200,000 | 170,000 tokens | Marginal | ~100K tokens |
| gpt-4o | 128,000 | 108,800 tokens | OK | ~80K tokens |

With a 1M model at default 85%, you'll burn **200K-600K tokens** of degraded-quality conversation before compression finally fires. Each of those turns pays full price for context that the model can't effectively use.

### Fixed Context Overhead

Every turn includes a fixed prefix that never compresses:

```
system prompt (SOUL.md + guidance + skills index)      ~6,100 tok
memory + user profile                                    ~1,600 tok
tool schemas (42 tools average)                          ~16,000 tok
Fixed total per turn                                     ~24,000 tok
```

The skills index grows with installed skills (~14 KB for 130 skills). Tool schemas are sent as API `tools` parameter, not part of the system prompt string, but still consume KV cache budget.

### Recommended Thresholds

Set `compression.threshold` in config.yaml based on the model's ACTUAL attention degradation point, not its advertised window:

```bash
# deepseek-v4-flash (1M): degrade starts ~200K → compress at 20%
hermes config set compression.threshold 0.20

# deepseek-v4-pro (1M): same family, same setting
hermes config set compression.threshold 0.20

# claude-sonnet-4 (200K): degrade starts ~100K → compress at 50%
hermes config set compression.threshold 0.50

# gpt-4o (128K): degrade starts ~80K → compress at 60%
hermes config set compression.threshold 0.60
```

An aggressive `threshold: 0.15` (150K for 1M models) keeps quality high but compresses more frequently. A conservative `0.25` reduces compression frequency at the cost of some late-session drift.

### Local Models: Different Calculus

Local models with smaller context windows (128K-262K) need different thresholds:

| Model type | Context | Recommended threshold | Trigger point |
|------------|---------|----------------------|---------------|
| API (1M window) | 1,000,000 | 0.15-0.25 | 150K-250K |
| Local (262K) | 262,144 | **0.60** | ~157K |
| Local (128K) | 128,000 | 0.70 | ~90K |

The compression ratio is tighter for local models because the context window is smaller — there's less room to "waste" between trigger and full context. A threshold of 0.60 means compression fires at ~157K tokens, leaving ~105K tokens of usable space for the conversation turn-to-turn.

**Why not 0.15 like API models?** A 262K window at 0.15 (39K trigger) would compress too frequently — every few turns — defeating the point of having a large local context. The 0.60 threshold is a balance: compress only when the conversation actually fills most of the working space, not preemptively.

### Target Ratio

`target_ratio: 0.10` (compress to 10% of threshold) is the default. For large-context models, consider raising it:

```bash
# Default: 850K → 85K (for 1M at 85%). Aggressive compression summary.
hermes config set compression.target_ratio 0.10

# Gentler: 200K → 40K (for 1M at 20%). Better summary quality, higher budget.
hermes config set compression.target_ratio 0.20
```

Higher `target_ratio` = better summary quality but less freed context. For 1M models, even a gentle ratio leaves plenty of room.

### Protect Settings

```bash
hermes config set compression.protect_last_n 20   # keep last 20 messages intact (default)
hermes config set compression.protect_first_n 3   # keep first 3 exchanges (default)
```

These ensure recent context and the initial problematic exchange survive compression intact.

### View Current Settings

```bash
hermes config | grep -A 8 "Context Compression"
```

### How Compression Works (for diagnostics)

1. Tool results are pruned first (cheap, no LLM call)
2. Head messages (system prompt + first exchange) are protected
3. Tail messages (most recent ~20K tokens) are protected
4. Middle turns are lossily summarized by an LLM call
5. On subsequent compactions, the previous summary is iteratively updated

The compression LLM call costs tokens (typically ~2-5K). On a 1M model, this is negligible compared to the wasted tokens from late compression.

## References

- Tokscale: github.com/junhoyeo/tokscale (4k stars, MIT)
- RTK: github.com/rtk-ai/rtk (66k stars, Apache 2.0)
- Hermes config: ~/.hermes/config.yaml (RTK plugin auto-added)
- Tokscale data: `~/.config/tokscale/settings.json`
- **System prompt & tool schema composition**: `references/system-prompt-composition.md` (measured breakdown of fixed per-turn overhead)
