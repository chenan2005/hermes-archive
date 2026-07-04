# Auxiliary Provider Configuration

When the **main provider** (e.g. DeepSeek) doesn't support a modality that
Hermes needs (vision, audio, long-context compression, web extraction),
the `auxiliary.*` config section lets you assign a **different provider**
for each subtask — without changing your main model.

## When You Need This

| Main provider | Lacks | Needs auxiliary |
|---------------|-------|-----------------|
| DeepSeek v4 Flash/Pro | Vision | Gemini / Claude / GPT-4o |
| DeepSeek v4 Flash/Pro | Compression (auto) | OpenRouter / Google / Anthropic |
| Local models (llama.cpp, Ollama) | Vision | Gemini / Claude |
| Any without web extract | Rich page fetch | Google / OpenRouter |

## Common Setup: Google Gemini as Vision Provider

Gemini is the most practical choice for auxiliary vision:
- Native multimodal (no base64 overhead)
- Free tier: 60 requests/min, generous daily quota
- Fast (sub-second first token for small images)
- No additional auth setup beyond an API key

### 1. Get a Gemini API Key

1. Go to https://aistudio.google.com/apikey
2. Sign in with your Google account
3. Click **"Create API Key"** (or "Get API Key")
4. If prompted, enable the Gemini API for your project
5. Copy the generated key

### 2. Write to Hermes `.env`

```bash
echo 'GOOGLE_API_KEY=<your-key-here>' >> ~/.hermes/.env
```

**Note:** The actual value must be a real API key string — if it ends up as
`***`, the write was redacted. Use terminal to append directly.

### 3. Configure Auxiliary Vision

```bash
hermes config set auxiliary.vision.provider google
hermes config set auxiliary.vision.model gemini-2.5-flash-preview
```

Alternative models (same procedure, different model name):
- `gemini-2.5-pro` — better quality, slower, more expensive
- `gemini-2.0-flash` — slightly older, still capable
- `gemini-2.5-flash-lite` — cheapest, good for simple classification

### 4. Restart Gateway

```bash
hermes gateway restart
```

### 5. Verify

Send a message with an image from a messaging platform, or test via CLI:
```bash
# Ask Hermes to read an image file
hermes chat -q "Describe the image at ~/test.png"
```

Check auxiliary logs for provider resolution:
```bash
grep "auxiliary.vision" ~/.hermes/logs/agent.log* | tail -5
```

## Config Reference

| Auxiliary Task         | Config Key                         | Recommended Provider      |
|------------------------|-------------------------------------|---------------------------|
| Vision analysis        | `auxiliary.vision.provider/model`  | Google Gemini             |
| Web page extraction    | `auxiliary.web_extract.provider`   | OpenRouter or auto        |
| Context compression    | `auxiliary.compression.provider`   | OpenRouter or auto        |
| Skill hub queries      | `auxiliary.skills_hub.provider`    | auto (usually fine)       |
| Approval (smart mode)  | `auxiliary.approval.provider`      | auto (usually fine)       |

Setting `provider: auto` tells Hermes to reuse the main provider — which
only works if the main provider actually supports that modality.

## Pitfalls

### Key not persisted

If you set `GOOGLE_API_KEY` via `hermes config set` or a tool call that
runs through secret redaction, the value may be written as `***` to `.env`.
Always append API keys via terminal directly:

```bash
echo 'GOOGLE_API_KEY=AIza...' >> ~/.hermes/.env
```

### Provider resolved but model wrong

```bash
hermes config set auxiliary.vision.model gemini-2.5-flash-preview
```
Without the model name, `auto` picks whatever Gemini defaults to — which
may not be the best for your use case. Always set both provider AND model.

### Gateway restart required

Auxiliary config changes are read at gateway startup. `hermes config set`
writes the config but doesn't reload the running process. Always follow
with `hermes gateway restart` (or restart the CLI session for CLI-only use).

## Comparison: Vision Provider Options

| Provider | Model | Speed | Cost | Setup Effort |
|----------|-------|-------|------|-------------|
| Google Gemini | gemini-2.5-flash-preview | Fast | Free tier ample | API key only |
| OpenRouter → Claude | anthropic/claude-sonnet-4 | Medium | Pay-per-token | OpenRouter API key |
| OpenRouter → Gemini | google/gemini-2.5-flash | Fast | Via OpenRouter billing | OpenRouter API key |
| Anthropic direct | claude-sonnet-4 | Medium | $3/M input | ANTHROPIC_API_KEY |
