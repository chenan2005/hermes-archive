---
name: model-vram-budget
description: Estimate whether a model fits on a given GPU. Architecture-aware VRAM budgeting for local inference — weights + KV cache + overhead, handling hybrid/linear-attention models (Gated DeltaNet, Mamba, etc.) correctly.
version: 1.0.0
author: hermes-agent
tags: [VRAM, KV-cache, GPU, budget, hybrid-attention, local-inference]
---

# Model VRAM Budgeting

Use this skill when the user asks whether a model fits on their GPU, how much context they can run at a given quant, or how different quants compare on their specific hardware.

## The Trap

**Do not assume pure attention for all models.** Modern architectures (Qwen3.6, Jamba, Samba, RecurrentGemma) use hybrid linear-attention + standard-attention layers where only a fraction of layers contribute to KV cache. Assuming pure attention for these models produces estimates that are off by 4-10x, which leads to recommending the wrong model.

Always check the architecture before estimating.

## VRAM Budget Formula

```
Total VRAM = model_weights + KV_cache + scratch/overhead
```

| Component | How to Get |
|---|---|
| model_weights | GGUF file size from tree API, or FP16 size / quant factor |
| KV_cache | See below -- architecture dependent |
| scratch + overhead | Typically 1-3 GB for CUDA context + allocator fragmentation |

## KV Cache Estimation by Architecture Type

### 1. Pure Attention (LLaMA 3, Mistral, Gemma 2, Phi-3)

KV cache scales with: num_attention_layers * hidden_dim * 2 (K+V) * seq_len * bytes_per_value

For Q8 (1 byte): roughly layers * hidden_dim * 2 * seq_len bytes
For FP16 (2 bytes): double the above.

### 2. GQA / MQA (Grouped Query Attention)

KV cache is divided by num_attention_heads / num_kv_heads. Most modern models use GQA with 4-8 KV heads, making KV cache 4-8x smaller than full MHA.

### 3. Hybrid DeltaNet + Attention (3:1 ratio)

Qwen3.6-27B, Qwen3.6-35B-A3B and similar models interleave Gated DeltaNet (linear attention, no KV cache) with Gated Attention (standard KV cache) at a ratio (commonly 3:1).

Only the standard-attention layers contribute to KV cache -- linear-attention layers use a fixed-size state.

For Qwen3.6-27B (64 layers, 3:1 ratio -> ~16 attention layers):

| Context | KV Cache (Q8) | Source |
|---|---|---|
| 32K | ~3 GB | HN zargon |
| 128K | ~5 GB | estimated |
| 262K | ~8.7 GB | HN zargon |

### 4. Mamba / State Space Models

No KV cache needed -- fixed-size state per layer. Only weights matter for VRAM.

## How to Check Architecture

1. Search for architecture description: e.g. "Qwen3.6-27B gated deltanet"
2. Check config.json: look for num_attention_heads, num_kv_heads, and any linear_attention_layers or attention_layers arrays
3. Search community benchmarks: "RTX 5090 <model> context VRAM" on HN/Reddit
4. Check the model card / blog -- usually mentions if it's hybrid or linear attention

## Reference Data Points

### Qwen3.6-27B on Consumer GPUs

| GPU | Quant | Max Context | VRAM Used | Speed | Source |
|---|---|---|---|---|---|
| RTX 5090 32GB | Q4_K_M (15.7 GB) | 262K (est fits) | ~27 GB | 55+ tok/s | estimated |
| RTX 5090 32GB | Q6_K (21.0 GB) | 123K | ~28 GB | 50 tok/s | HN gfosco |
| RTX 3090 24GB | INT4 AutoRound + MTP (vLLM) | 125K | 21.3 GB | 85 tok/s | Medium Wasif Basharat |

### General Guidance

- 24 GB cards (3090, 4090): Q4_K_M of 27B models -- fits with ~32-125K context
- 32 GB cards (5090): Q4_K_M of 27B -- fits with up to 262K for hybrid architectures
- 48+ GB cards (A6000, PRO 6000): Q8_0 of 27B or Q4 of 70B

## Reference Files

- **[references/windows-desktop-vram-overhead.md](references/windows-desktop-vram-overhead.md)** — Windows 桌面环境（DWM、多显示器、浏览器、IDE）的 VRAM 开销估算，含 Qwen3.6-27B 在 RTX 5090 上的具体配置对照表。

## Pitfalls

- Don't use generic formula for hybrid architectures -- you'll under-estimate context by 3-5x
- KV cache quantization matters: Q8 (1 byte) vs FP16 (2 bytes) vs TurboQuant (3-bit) changes cache size significantly
- Vision encoder models add ~1-2 GB for mmproj + encoder
- CUDA graph capture adds ~500 MB-1 GB overhead for graph memory pools
