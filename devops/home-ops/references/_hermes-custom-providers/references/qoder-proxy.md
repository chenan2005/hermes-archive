# qoder-proxy — Qoder as an OpenAI-Compatible Endpoint

Repository: https://github.com/foxy1402/qoder-proxy

A Docker container that wraps `qodercli` into an OpenAI-compatible `/v1/chat/completions` API. Lets any OpenAI-compatible client (Hermes, Open WebUI, LangChain) use Qoder's models.

**⚠️ Known limitation: process exits after each request.** The Node.js server in qoder-proxy exits cleanly (ExitCode=0) after every completed POST request. Docker's `--restart unless-stopped` restarts it, causing 15–20s downtime per request. Long-running requests from Hermes (~30s+ processing) hit `ConnectionResetError` / `RemoteProtocolError`. See **Python wrapper workaround** below for a stable alternative.

## Quick Start

```bash
QODER_TOKEN=$(cat ~/.qoder-token)
PROXY_KEY="<generate-a-random-hex-key>"

docker run -d \
  --name qoder-proxy \
  --restart unless-stopped \
  -p 3000:3000 \
  --memory=12g \
  -e QODER_PERSONAL_ACCESS_TOKEN=$QODER_TOKEN \
  -e PROXY_API_KEY=$PROXY_KEY \
  -e NODE_OPTIONS='--max-old-space-size=8192' \
  ghcr.io/foxy1402/qoder-proxy:latest
```

Generate the PAT at: https://qoder.com/account/integrations

## Memory Requirements

qodercli (Node.js) spawns per request and is VERY memory-hungry — especially with large prompts (Hermes sends ~5K tokens of system prompt + tools).

| Scenario | Docker --memory | NODE_OPTIONS |
|----------|----------------|--------------|
| Simple curl (1-2 msgs) | 2 GB | default |
| Hermes with tools | **12 GB** | `--max-old-space-size=8192` |
| Large codebase context | 16 GB | `--max-old-space-size=12288` |

Without enough heap, qodercli crashes with:
```
FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory
```

## Model Names

| Pass to Hermes | Qoder Tier | Notes |
|---------------|-----------|-------|
| `auto` | auto | Smart routing, best default |
| `lite` | lite | Fast/cheap |
| `ultimate` | ultimate | Best quality |
| `deepseek-v4` | dmodel | ⚠️ May fail (proxy mapping bug) |
| `kimi` | kmodel | Kimi-K2.6 |
| `qwen36plus` | qmodel | Qwen3.6-Plus |

Stick to `auto`, `lite`, `ultimate` — the named model aliases may break across qodercli updates.

## WASM Warnings

qodercli logs a non-fatal WASM error on startup:
```
failed to asynchronously prepare wasm: LinkError: WebAssembly.instantiate(): Import #6 module="env" function="_abort_js" error: function import requires a callable
```
This does NOT prevent the API from working. Ignore it unless paired with actual failures.

## Hermes Config

```yaml
custom_providers:
  - name: qoder-proxy
    base_url: http://localhost:3000/v1
    api_key: <PROXY_KEY>
    model: auto
    api_mode: chat_completions

model:
  default: auto
  provider: custom:qoder-proxy
```

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `401 Invalid API key` | PROXY_API_KEY env var in container matches config.yaml |
| Hermes uses wrong provider | Is `model.provider` set to `custom:qoder-proxy` (with `custom:` prefix)? |
| OOM / heap limit | Increase `--memory` and `NODE_OPTIONS=--max-old-space-size` |
| Empty response from model | Try non-streaming curl first; large prompt may need more heap |
| `403 Invalid model: auto` | qodercli version mismatch — check `docker exec qoder-proxy qodercli --version` |
| `Empty response from model` | Retry with `--safe-mode` or non-streaming curl to rule out streaming parse issues |

---

## Python Wrapper Workaround (Stable Alternative)

If qoder-proxy's crash-after-each-request behaviour breaks Hermes integration, replace the Node.js server with a minimal Python HTTP server.

### Architecture

```
Hermes → Python proxy (port 3000, stays alive)
                ↓
         docker exec qoder-proxy qodercli -p -f stream-json -m auto "prompt"
                ↓
         qoder-proxy container (port 3001, only provides qodercli binary)
```

The Python proxy:
- Uses stdlib `http.server` — no framework deps, single file
- Calls `docker exec qoder-proxy qodercli -p -f stream-json ...` per request
- **Stays alive between requests** — no crash/restart cycle
- Supports tool calling via text injection + JSON parsing

### Key Flags

`-p` — non-interactive mode (without it qodercli opens a pager).
`-f stream-json` — structured JSON output lines with tool call info. Without it, output is plain text and tool calls are lost.

```bash
docker exec qoder-proxy qodercli -p "Say OK" -f stream-json -m auto
# → {"message":{"role":"assistant","content":[{"type":"text","text":"OK"}]}}
```

### Tool Calling via Text Injection

qodercli does NOT support native OpenAI tool definitions. Instead, the proxy:
1. Injects tool descriptions as plain text into the system prompt
2. Instructs the model to output `{"tool_call":{"name":"...","arguments":{...}}}` as raw JSON
3. Parses the response (regex: raw JSON / fenced code block / depth-based scan)
4. Converts parsed calls to OpenAI `tool_calls` format

**Important:** The model makes tool calls ONLY when it truly can't answer from knowledge (e.g. `/etc/hostname`, unknown file contents). For obvious answers (e.g. "list /app directory" where the model knows the container structure), it gives a text response instead. This is correct model behaviour — the tool call is used when external data is needed.

### Pitfalls

| Issue | Fix |
|-------|-----|
| `env={}` in subprocess.run | Remove `env=` param — subprocess needs PATH, HOME etc. for `docker exec` |
| `--entrypoint python3` fails | Container image has NO python3. Proxy must run OUTSIDE container |
| File paths with "token"/"key" get redacted | Upload file first, then `sed` via SSH on the target machine to fix corruption |
| Port 3000 conflict on restart | `pkill -f qoder_proxy_v3` before starting a new instance |

### Hermes Profile (Isolation)

Always create a separate Hermes profile for custom providers to avoid breaking the default:

```bash
hermes profile create qoder
```

Config in `~/.hermes/profiles/qoder/config.yaml`:

```yaml
model:
  default: auto
  provider: qoder-proxy
providers:
  qoder-proxy:
    base_url: http://minipc.lan.11:3000/v1
    api_key: "<proxy-key>"
    models:
      auto: { context_length: 1000000 }
      lite: { context_length: 1000000 }
agent:
  max_turns: 90
  gateway_timeout: 180         # higher timeout for slow first-token generation
  api_max_retries: 2
```

Use with: `hermes chat -p qoder` or the profile-specific wrapper `qoder chat`.

**Provider format note:** The new `providers:` dict format (not legacy `custom_providers:` list) uses bare provider names — no `custom:` prefix in `model.provider`.

### WSL2 Memory Configuration

WSL2 default memory limit is 50% of system RAM. On a 48GB machine this gives ~23GB, which may be insufficient for memory-hungry model runners. Override with `.wslconfig`:

```ini
# %USERPROFILE%\.wslconfig
[wsl2]
memory=36GB
processors=8
swap=8GB
```

Apply: `wsl --shutdown` then restart WSL. Verify: `free -h` inside WSL shows the new limit.

### WSL2 Deployment (minipc example)

```bash
# Start qoder-proxy container (provides qodercli binary)
docker rm -f qoder-proxy
docker run -d --name qoder-proxy --restart unless-stopped -p 3001:3000 \
  --memory=32g --env-file /mnt/c/Users/chen_/qoder.env \
  ghcr.io/foxy1402/qoder-proxy:latest

# Start Python proxy (always runs OUTSIDE the container)
# Script: C:\Users\chen_\qoder_proxy_v3.py (288 lines, tool-call aware)
python3 /mnt/c/Users/chen_/qoder_proxy_v3.py &

# Verify: health + tool call test
curl http://localhost:3000/health
# Test tool call: should return {"tool_calls":[{...}]} for read-only requests
```

### Model Tier Speed Comparison

Benchmark (simple "1+1=?" query, non-streaming):

| Tier | Time | Notes |
|------|------|-------|
| `auto` | 9.4s | Smart select — may pick slower but better model |
| `lite` | **7.5s** | Fastest tier |
| `dfmodel` | 7.7s | DeepSeek-V4-Flash, also fast |

Switch model: `qoder config set model.default lite` or edit the profile's `config.yaml`.

### WSL2 Port Forwarding (LAN Access)

Docker port binds are localhost-only. To expose to LAN:

```powershell
# After WSL restart, the IP changes. Check & re-add:
$wslIp = wsl -d Ubuntu-24.04 -- bash -c "hostname -I | cut -d' ' -f1"
netsh interface portproxy delete v4tov4 listenport=3000
netsh interface portproxy add v4tov4 listenport=3000 listenaddress=0.0.0.0 \
  connectport=3000 connectaddress=$wslIp

# Persistent firewall rule (one-time)
New-NetFirewallRule -DisplayName "Qoder 3000" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow
```
