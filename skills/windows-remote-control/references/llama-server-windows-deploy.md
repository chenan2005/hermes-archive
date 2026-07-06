# Deploying llama.cpp on Windows via SSH

Session-specific patterns for deploying llama-server on a Windows 11 machine (RTX 5090) from a Linux host.

## Key Differences from Linux Deployment

### Binary: `llama.exe server`, Not `llama-server.exe`

The prebuilt Windows zip contains a 9 KB `llama-server.exe` stub that loads `llama-server-impl.dll`. This stub has inconsistent behavior over SSH. **Always use `llama.exe server` (83 KB)** — it's the unified binary with proper subcommand support:

```powershell
# Correct
C:\llama\llama.exe server -m "<model>" -c 65536 -ngl 99 --host 0.0.0.0 --port 8080

# Avoid
C:\llama\llama-server.exe -m "<model>" ...  # 9KB stub, unreliable
```

### Download the Right Binary

Choose `llama-b9859-bin-win-cuda-<version>-x64.zip`. The version number includes CUDA major.minor:
- For RTX 5090 (CUDA 13): `llama-b9859-bin-win-cuda-13.3-x64.zip`
- The standalone binary package does NOT include CUDA runtime DLLs; they're bundled IN the zip.
- Also available: `cudart-llama-bin-win-cuda-13.3-x64.zip` (with redistributable CUDA runtime)

**Unzip on Windows:** Use `Expand-Archive` in PowerShell; Windows `tar` doesn't support .zip.

### Persistent Process (Surviving SSH Disconnect)

**⚠️ `Start-Process` from SSH Session 0 is unreliable.** On Windows 11 with OpenSSH 10.x, `Start-Process` launched from SSH often dies when the remote PowerShell session ends, even with `-PassThru` and `-NoNewWindow`. The process starts but silently exits seconds later. This is distinct from `start /B` failure — both are Session 0 lifetime issues.

**Reliable pattern: `schtasks` (one-time scheduled task)**
```bash
# Create a one-time task that boots at system start
ssh target 'schtasks /create /tn "llama-server" /tr "cmd /c C:\llama\start.bat" /sc once /st 23:58 /f'

# Trigger it immediately
ssh target 'schtasks /run /tn "llama-server"'

# Restart = kill + re-trigger
ssh target 'taskkill /f /im llama.exe & schtasks /run /tn "llama-server"'
```

This works because schtasks launches the process independently of the SSH session. The batch file (`C:\llama\start.bat`) isolates parameters from Windows shell quirks.

```powershell
$proc = Start-Process -FilePath C:\llama\llama.exe `
    -ArgumentList "server -m C:\llama\models\Qwen3.6-27B-Q4_K_M.gguf -c 65536 -ngl 99 --host 0.0.0.0 --port 8080 -t 16 --no-warmup" `
    -WindowStyle Hidden -PassThru
Write-Output $proc.Id
```

This creates a fully detached process independent of the SSH session.

**Deploy via SCP + remote execution:**
```bash
scp start_server.ps1 9950x3d:'C:/deploy/start.ps1'
ssh 9950x3d 'powershell -NoProfile -ExecutionPolicy Bypass -File C:\deploy\start.ps1'
```

### Windows Firewall

llama-server binds `--host 0.0.0.0:8080` correctly, but **Windows Firewall blocks external access by default**. Add an inbound rule:

```bash
ssh target 'netsh advfirewall firewall add rule name="LlamaServer" dir=in action=allow protocol=TCP localport=8080'
```

### KV Cache Quantization (-ctk/-ctv)

Windows prebuilt binaries may have **different supported types than Linux/macOS builds**. Check before deploying:

```bash
# List supported cache types — if wrong type is passed, an error shows all valid options:
C:\llama\llama.exe server -ctk invalid_type 2>&1 | findstr "allowed values"
```

Known supported types (b9859 Win CUDA 13.3): `f32, f16, bf16, q8_0, q4_0, q4_1, iq4_nl, q5_0, q5_1`
**`q6_k` is NOT supported** on this binary (build b9859). **However:** a later build or different CUDA variant (e.g., cu13 vs cudart) may include q6_k — a running server on the same machine (2026-07-04) was started with `-ctk q6_k -ctv q6_k` and ran without error on port 8080. If your binary accepts q6_k, the VRAM budget changes significantly: Q4_K_M (15.7GB) + q6_k KV 256K (~6GB) ≈ 25GB — much more comfortable than q5_1+f16 (~31GB). **Always verify** what your actual binary supports via `llama.exe server -ctk invalid_type 2>&1 | findstr "allowed values"` before committing to a cache type.

**Critical: Flash Attention is auto-disabled on Windows prebuilt binaries.** Quantized V cache (`-ctv` with any quant: q5_1, q8_0, iq4_nl, etc.) requires Flash Attention and will fail with:

```
E llama_init_from_model: failed to initialize the context: quantized V cache was requested, but this requires Flash Attention
W sched_reserve: Flash Attention was auto, set to disabled
```

**Workaround**: quantize K cache only, leave V at f16:
```powershell
# Recommended: save ~half KV VRAM, no Flash Attention needed
-ctk q5_1 -ctv f16
# Conservative: K at q8_0, V at f16 (less savings but simpler)
-ctk q8_0 -ctv f16
```

**VRAM impact at 262K context (Q4_K_M, RTX 5090, dual 4K):**
- q5_1 K + f16 V: 31.1 GB / 32 GB used — only 270 MB free, tight
- q8_0 K + f16 V: ~30-31 GB estimated — similar tightness
- F16 both (no -ctk/-ctv): does NOT fit (KV alone ~16.5 GB for K+V at 262K)

If 270 MB headroom is too tight, drop context to 200K (~3 GB free) or upgrade to 48 GB card.

**Performance penalty at 262K context**: generation speed drops ~15% from ~70 tok/s (65K F16) to ~60 tok/s (262K q5_1 K + f16 V) due to larger attention matrix.

### Model Loading Time

With `-ngl 99` (all layers on GPU), loading a 16.8 GB Q4_K_M model into RTX 5090 VRAM takes **30-60 seconds** via PCIe. The process appears to hang during this time — be patient.

VRAM budget example (65536 context, no KV cache quant):
- Model weights (Q4_K_M): ~15.7 GB
- KV cache + CUDA overhead: ~7-8 GB
- OS desktop (dual 4K): ~2.5 GB
- Total: ~23.5 GB / 32 GB — fits with headroom

### Process Detection over SSH

SSH to Windows with Chinese locale causes garbled `tasklist` output. Use `findstr /C:"llama.exe"` (not `/I`) for reliable detection:

```bash
# Reliable
ssh target 'tasklist /FI "IMAGENAME eq llama.exe" /NH | findstr /C:llama.exe'

# Unreliable (locale-dependent)
ssh target 'tasklist | findstr /I llama'
```

For all-process detection, use WMIC or PowerShell:
```powershell
Get-Process -Name *llama* -ErrorAction SilentlyContinue | Select-Object Id, ProcessName
```

## Qwen 3.6-Specific: Thinking Mode

Qwen 3.6 models output reasoning in a separate `reasoning_content` field. The final answer only appears in `content` when thinking is complete:

- **`finish_reason: "stop"`** → thinking complete, `content` has the answer
- **`finish_reason: "length"`** → truncated mid-thought, `content` may be empty
- **Generation speed**: ~77 tok/s on RTX 5090 (Q4_K_M, 65536 ctx)
- **Prompt processing**: ~100 tok/s (~280ms first-token latency)

For direct answers without thinking, add to system prompt: "Answer directly without thinking step by step."

## Service Management

```bash
# Check if running
ssh target 'tasklist /FI "IMAGENAME eq llama.exe" /NH | findstr /C:llama.exe'

# Get detailed info (memory, CPU time)
ssh target 'powershell -NoProfile -Command "Get-Process -Name *llama* -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,StartTime,@{N=\"WorkingSetMB\";E={[math]::Round($_.WorkingSet64/1MB,1)}},@{N=\"CPUTime\";E={$_.TotalProcessorTime}}"'

# Kill
ssh target 'taskkill /F /IM llama.exe'

# Start
scp start_script.ps1 target:C:/path/
ssh target 'powershell -NoProfile -ExecutionPolicy Bypass -File C:\\path\\start_script.ps1'
```

## Startup Config Verification

Never assume the running server matches the startup script. Verify actual config via the /v1/models endpoint — this reveals the real runtime parameters:

```bash
# Check actual n_ctx vs n_ctx_train (model cap) — use single-quoted Python to avoid quote escaping
curl -s http://localhost:8080/v1/models | python3 -c 'import json,sys; m=json.load(sys.stdin)["data"][0]["meta"]; print(f"ctx: {m[\"n_ctx\"]}/{m[\"n_ctx_train\"]} params: {m[\"n_params\"]/1e9:.1f}B n_embd: {m[\"n_embd\"]}")'
```

Sample output from Qwen3.6-27B Q4_K_M:
```
n_ctx (actual):      65536
n_ctx_train (model): 262144
n_params:            26.9B
n_embd:              5120
n_vocab:             248320
Disk size:           16.8 GB
```

### Multiple Startup Script Config Drift

When multiple .ps1 and .bat files exist (iterative deployment), verify which script actually launched. The /v1/models endpoint is the only reliable way to know the running config.

| Drift | Symptom | Fix |
|-------|---------|-----|
| .ps1 uses llama-server.exe stub (9KB) | Unreliable, may fail silently | Use llama.exe server (83KB unified) |
| .ps1 omits -ctk/-ctv | KV cache defaults to F16, wasting ~2GB | Add -ctk q8_0 -ctv q8_0 |
| -c in .bat (262144) different from running .ps1 (65536) | /v1/models shows n_ctx=65536 vs n_ctx_train=262144 | Kill and restart with correct script |

Consolidate to one script:
```powershell
# start_qwen.ps1 - single source of truth
$exe = "C:\llama\llama.exe"
$args = "server -m C:\llama\models\Qwen3.6-27B-Q4_K_M.gguf -c 262144 -ctk q8_0 -ctv q8_0 -ngl 99 --host 0.0.0.0 --port 8080 -t 16 --no-warmup --log-file C:\llama\server_log.txt"
Start-Process -FilePath $exe -ArgumentList $args -WindowStyle Hidden -PassThru
```

Verify after restart: /v1/models n_ctx should match intended value.

## Preventing Infinite Generation (`--n-predict` Cap + Hermes Config)

When Hermes sub-agents use `reasoning_format: deepseek`, the model's think block can spiral into self-reinforcing loops, consuming the entire `max_tokens` budget (often 65536). The response hits `finish_reason='length'`, and Hermes misreports it as a network error ("Stream interrupted by network error").

**Three-layer defense:**

| Layer | Config | Purpose |
|---|---|---|
| llama-server | `--n-predict 32768` | Server-side hard cap |
| Hermes agent | `agent.reasoning_effort: none` | Disable deepseek think format |
| Hermes main model | `model.max_completion_tokens: 32768` | Main agent request cap |
| Hermes sub-agents | `delegation.max_completion_tokens: 32768` | Sub-agent request cap |

**Hermes profile config (`~/.hermes/profiles/<name>/config.yaml`):**
```yaml
model:
  max_completion_tokens: 32768
delegation:
  max_completion_tokens: 32768
agent:
  reasoning_effort: none    # disables reasoning_format: deepseek
```

This prevents 65K-token generations that waste GPU time and trigger false error detection. For code analysis, Qwen 3.6 naturally stops at `<|im_end|>` without the think-block guard when `reasoning_effort: none`.

### Pitfall: `--stop` is an API parameter, NOT a CLI argument

Trying `--stop "<|im_end|>"` on the llama-server command line produces:
```
error: invalid argument: --stop
```

The `stop` token is set per-request in the API payload (`"stop": ["<|im_end|>"]`), not as a server-level CLI flag. The server's CLI only accepts `--n-predict` for the global cap.

### Orphan Requests: Slots Survive Client Disconnect

llama-server continues processing submitted requests after the client disconnects. However, when the Hermes PROCESS fully exits (breaking all SSE connections), llama-server detects dead streams and stops. The key distinction: a background Hermes sub-agent keeping an SSE stream alive ≠ a fully exited process.

Check for orphans:

```bash
curl -s http://192.168.71.41:8080/slots | python3 -c "
import json,sys
for s in json.load(sys.stdin):
    t=s.get('next_token',[{}])[0]
    if s.get('is_processing'):
        print(f\"ORPHAN slot={s['id']} task={s['id_task']} decoded={t.get('n_decoded','?')}\"
)"
```

**Cleanup:** Either wait for slots to finish, or restart the server. There is **no cancel API** — `POST /slots/{id}` with `{"action":"clear"}` requires `--slot-save-path` and only supports save/restore/erase, not cancel.

### Slot Management API Limitations

llama-server's `POST /slots/{id}` endpoint supports only `save`/`restore`/`erase` actions — **there is no cancel/stop action** even with `--slot-save-path`. The only way to cancel running tasks is to restart the server.

**kv_unified explained:** When the server logs `kv_unified = 'true'`, all slots share a single KV cache pool. With 262K context at q8_0, this means 4 slots use the same ~11GB KV cache instead of 4×11GB = 44GB. Extra slots cost zero VRAM — they only provide request queuing capacity.

### Batch File Special Character Escaping (`<|>`)

When writing tokens like `<|im_end|>` in `.bat` files, the `<`, `>`, and `|` characters are interpreted by `cmd.exe` as redirect/pipe operators. Escape with `^`:
```batch
set STP=^<^|im_end^|^>
:: STP now contains: <|im_end|>
```

### Batch File Update via SSH Stdin Pipe

Updating batch files on Windows over SSH is unreliable with inline PowerShell `-replace` (quoting hell). Use the stdin pipe pattern:

```bash
cat << 'EOF' | ssh target 'powershell -NoProfile -Command "[IO.File]::WriteAllText(\"C:\\llama\\start.bat\", [Console]::In.ReadToEnd())"'
@echo off
...batch content...
EOF
```

## Qwen 3.6 Thinking Mode

### Memory Shutdown Triggers Background LLM Activity

When a Hermes session with 100+ messages closes, `CLI cleanup calling memory shutdown` triggers Hindsight memory extraction on the full conversation history. If Hindsight is configured to use a local LLM (shared bank with `memory.provider: hindsight`), this generates a large prompt (100K+ tokens) with significant completion output. The GPU stays at high utilization for minutes after the user's interaction appears to be done.

**Symptom:** GPU at 96% utilization after Hermes exits, `curl /slots` shows a single slot with `n_prompt_tokens` > 100K and `n_decoded` > 10K.

**Fix:** Either wait (it will complete), or restart llama-server. Hindsight extraction model is configured via `HINDSIGHT_API_LLM_MODEL` env var (global, not per-profile). Setting it to an API-based model (e.g., `deepseek-v4-flash`) keeps extraction off the local GPU.

### Qwen 3.6 Outputs reasoning in `reasoning_content`. The answer appears in `content` only after thinking completes:

- `finish_reason: "stop"` → thinking done, content has the answer
- `finish_reason: "length"` → truncated mid-thought, content may be empty despite many tokens
- **High token overhead**: "what is 2+2?" consumes **60-100 reasoning tokens** before "4" — even with "Answer directly" system prompt
- **Token waste is real**: reasoning tokens consume VRAM, context budget, and generation time identically to output tokens. They are not free.
- **Perceived latency >> raw tok/s**: at 60 tok/s generation, 100 reasoning tokens = ~1.7s before any visible answer
- **Always set max_tokens high**: 300+ for simple queries, 500+ for complex ones to avoid `finish_reason: "length"` mid-thought

For direct answers, add to system prompt: "Answer directly without thinking step by step." (May still produce some reasoning tokens — Qwen3.6 RL-post-training strongly encourages CoT.)

### `reasoning_format: deepseek` and Infinite Think Loops

When Hermes sub-agents request `reasoning_format: deepseek`, llama-server wraps Qwen's output in `<think>...</think>` blocks. Under certain conditions (complex analysis with self-reinforcing chains), the model can spiral into a loop where each "think" step triggers further analysis, consuming the entire `max_tokens` budget (default 65536 in sub-agent configs) without producing a final answer.

**Symptoms:**
- Slot shows high `n_decoded` (hundreds or thousands of tokens) but `processing: true`
- Client reports `finish_reason='length'` — model was forcibly truncated
- Hermes sub-agent misreports as "Stream interrupted by network error"
- No useful output despite heavy GPU utilization

**Fix:** For code analysis tasks that don't benefit from chain-of-thought reasoning:
- Disable `reasoning_format` in the Hermes provider config
- Reduce `max_tokens` from 65536 to 8192–16384

### Orphan Requests: Slots Survive Client Disconnect

llama-server continues processing submitted requests after the client disconnects. However, when the Hermes PROCESS fully exits (breaking all SSE connections), llama-server detects dead streams and stops. The key distinction: a background Hermes sub-agent keeping an SSE stream alive ≠ a fully exited process.

Check for orphans:

```bash
curl -s http://192.168.71.41:8080/slots | python3 -c "
import json,sys
for s in json.load(sys.stdin):
    t=s.get('next_token',[{}])[0]
    if s.get('is_processing'):
        print(f\"ORPHAN slot={s['id']} task={s['id_task']} decoded={t.get('n_decoded','?')}\")
"
```

**Cleanup:** Either wait for slots to finish, or restart the server. The lightweight slot-clear API (`POST /slots/{id}` with `{"action":"clear"}`) requires `--slot-save-path` at server start; without it, it returns 501.

### Measured Throughput (RTX 5090, Q4_K_M)

| Metric | 65K ctx (F16 KV) | 262K ctx (q5_1 K + f16 V) |
|--------|:-:|:-:|
| Gen speed (sustained) | **67-76 tok/s** | **~60 tok/s** |
| Prompt speed (cold) | ~100-200 tok/s | — |
| Prompt speed (warm) | 330-370 tok/s | ~94 tok/s |
| VRAM used | 23.2 GB (8.1 GB free) | 31.1 GB (0.27 GB free ⚠️) |
| Temp under load | 75°C / 545W | 75°C / 545W |
| GPU util during gen | 98% | 98% |

262K context on RTX 5090 32GB leaves only 270 MB VRAM free — functional for dedicated inference but no headroom for simultaneous GPU workloads.

## Final Working Startup Config (Qwen3.6-27B Q4_K_M, RTX 5090, 2026-07)

```batch
@echo off
set MODEL=C:\llama\models\Qwen3.6-27B-Q4_K_M.gguf
set SLOTS=C:\llama\slots
if not exist "%SLOTS%" mkdir "%SLOTS%"
echo Starting llama-server...
C:\llama\llama-server.exe ^
  -m "%MODEL%" ^
  -c 262144 ^
  -ctk q8_0 -ctv q8_0 ^
  -ngl 99 ^
  --host 0.0.0.0 --port 8080 ^
  -t 16 -b 512 ^
  --n-predict 32768 ^
  --slot-save-path "%SLOTS%" ^
  --metrics
```

Key params: `--n-predict 32768` (prevents 65K-token think loops), `--slot-save-path` (enables save/restore/erase), `--metrics` (enables /metrics endpoint for token tracking). Remove `> log.txt 2>&1` to see model loading progress in real time.

## Monitoring GPU Status

`nvidia-smi --query-gpu` on RTX 5090 (GeForce) does NOT expose `temperature.memory` — returns `N/A`. VRAM junction temperature requires HWiNFO64 (Windows) or NVML overrides (Linux). Core temp, utilization, power, and VRAM usage are available:

```bash
nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,clocks.sm --format=csv,noheader
```

A monitoring script `gpu-mon` at `~/.local/bin/gpu-mon` on the Linux host queries 9950x3d over SSH for one-shot or continuous monitoring (`gpu-mon -w`).

## Connection Testing

```bash
# From server itself (localhost)
curl -s http://localhost:8080/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"hi"}],"max_tokens":5}' -w "\nHTTP:%{http_code}"

# From LAN
curl -s http://192.168.x.x:8080/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"hi"}],"max_tokens":5}'
```

## Hermes Provider Config

```yaml
# ~/.hermes/profiles/<name>/config.yaml
providers:
  local-qwen:
    base_url: http://192.168.71.41:8080/v1
    api_key: not-needed
    api_mode: chat_completions
    models:
      qwen3.6-27b:
        context_length: 262144

model:
  default: qwen3.6-27b
  provider: local-qwen
  context_length: 262144
```
