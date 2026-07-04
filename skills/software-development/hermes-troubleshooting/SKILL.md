---
name: hermes-troubleshooting
description: "Troubleshoot common Hermes setup issues — profile path mismatches, missing binaries, config drift, skills isolation, dependency resolution, and network blockers (CDP timeout, HuggingFace access)."
version: 1.1.0
author: agent
license: MIT
metadata:
  hermes:
    tags: [hermes, troubleshooting, setup, profiles, security, network]
---

# Hermes Troubleshooting

Common Hermes setup and runtime issues with proven fixes.

## Trigger Conditions

- Warnings about missing or unavailable tools/binaries
- Profile-specific path resolution failures
- Config version drift or outdated settings
- Auto-installed tools not found in profile context
- CDP browser navigation timeouts
- HuggingFace access failures
- Skills visible in one profile but not another

---

## Profile Binary Path Mismatch

### Symptom

```
⚠ tirith security scanner enabled but not available — command scanning will use pattern matching only
```

Or similar warnings about other auto-installed binaries (e.g., `cosign`, `faster-whisper`).

### Root Cause

Each profile has its own `HERMES_HOME` (e.g., `~/.hermes/profiles/<name>/`). Auto-installed binaries land in the **global** `$HERMES_HOME/bin/` (i.e., `~/.hermes/bin/`), but the profile looks in its **own** `bin/` subdirectory. The binary exists globally but not in the profile's scope.

### Diagnosis

```bash
# Check where the binary actually is
find ~/.hermes -name "tirith" 2>/dev/null

# Check profile's HERMES_HOME
echo $HERMES_HOME

# Check profile bin dir
ls ~/.hermes/profiles/<profile-name>/bin/

# Verify the binary works
/home/chenan/.hermes/bin/tirith --help
```

### Fix (Option A: symlink — recommended)

Replace the profile's `bin/` with a symlink to the global `bin/` so all profiles share binaries:

```bash
rm -rf ~/.hermes/profiles/<profile-name>/bin
ln -s ~/.hermes/bin ~/.hermes/profiles/<profile-name>/bin
```

This is the **preferred approach** — new binaries auto-install to `~/.hermes/bin/` and are immediately available to all profiles.

### Fix (Option B: copy — per-profile)

Copy the binary from the global location to the profile's bin directory:

```bash
cp ~/.hermes/bin/tirith ~/.hermes/profiles/<profile-name>/bin/tirith
```

### Prevention

After Hermes updates auto-install a new binary, symlinked profiles pick it up automatically. For copied profiles, repeat the copy or add `~/.hermes/bin` to your system `$PATH` so `shutil.which()` finds it globally.

---

## Profile Skills Isolation

### Symptom

A skill (e.g., `it-assets`) exists in the default profile but is not found in a named profile. `hermes skills list` or `skill_view(name='...')` returns "not found".

### Root Cause

Each profile has its own `skills/` directory under `~/.hermes/profiles/<name>/skills/`. The default profile's skills live in `~/.hermes/skills/`. Named profiles do **not** inherit skills from the default profile.

### Diagnosis

```bash
# Check default profile skills
ls ~/.hermes/skills/devops/it-assets

# Check named profile skills
ls ~/.hermes/profiles/<profile-name>/skills/
```

### Fix (symlink entire skills directory — recommended)

```bash
rm -rf ~/.hermes/profiles/<profile-name>/skills
ln -s ~/.hermes/skills ~/.hermes/profiles/<profile-name>/skills
```

After this, the named profile sees all default profile skills. Requires `/reset` to take effect.

### Note on Hindsight Memory

Hindsight memory (`memory.provider: hindsight`) uses an external API service (`localhost:8888`) and is **already global** — all profiles share the same memory bank. No symlink needed.

### Note on MEMORY.md / USER.md

These are **profile-local** and NOT shared across profiles. If you want shared memory, use hindsight or another external provider.

---

## Config Version Drift

### Symptom

```
⚠ Config version outdated (v30 → v31) (new settings available)
```

### Fix

```bash
hermes config migrate
```

Then restart the session for new defaults to apply.

---

## Command Approval Modes

Three modes available via `hermes config set approvals.mode <mode>`:

| Mode | Behavior |
|------|----------|
| `manual` | **Default** — all commands prompt for approval |
| `smart` | Auxiliary LLM auto-approves low-risk commands, prompts on high-risk (recommended) |
| `off` | Skip all approval prompts (equivalent to `--yolo`) |

```bash
hermes config set approvals.mode smart    # recommended middle ground
```

Per-invocation bypass: `hermes --yolo` or `export HERMES_YOLO_MODE=1`.

Note: YOLO / `approvals.mode: off` does NOT turn off secret redaction — they are independent.

---

## CDP Browser Navigation Timeout

### Symptom

```
navigate huggingface.co 31.7s [CDP command timed out: Page.navigate]
```

### Root Cause

This is a **network connectivity issue**, not a CDP capability limit. Verify with curl:

```bash
curl -sL -o /dev/null -w "%{http_code} %{time_total}s" "https://huggingface.co/"
# If this also times out → network blocked, not CDP
```

### Fix

Set up HuggingFace mirror (for China-based users):

```bash
# Add to ~/.bashrc or ~/.zshrc
export HF_ENDPOINT=https://hf-mirror.com
source ~/.bashrc
```

Then use `https://hf-mirror.com/` directly in browser or API calls. The mirror is maintained by Shanghai Jiao Tong University and is functionally identical to huggingface.co.

---

## General Diagnostic Commands

```bash
# Full health check
hermes doctor [--fix]

# View current config
hermes config

# Check for missing deps or env vars
hermes config check

# Inspect tool status
hermes tools list

# Check profile details
hermes profile show <name>
```

## Pitfalls

- **Changes don't take effect mid-session.** Config edits, tool changes, and new binaries require a fresh session (`/reset` or restart).
- **Profile isolation is strict.** Each profile has its own `config.yaml`, `.env`, `bin/`, `skills/`, `sessions/`. Tools installed globally are NOT shared unless the global `bin/` is on `$PATH`.
- **`HERMES_HOME` env var overrides profile detection.** If set manually, it bypasses the profile system entirely — every process inherits the same home.
- **`hf-mirror.com` is for China network environments.** If you have direct access to huggingface.co, no mirror is needed.

---

## Model Switch: "declared by multiple configured providers" Error

### Symptom

```
✗ 'qwen36-27b' is declared by multiple configured providers (custom:local, local).
   Re-run with --provider <slug> to choose which one to use.
```

Occurs when switching models via `hermes model` or `/model` command.

### Root Cause (Hermes Bug)

`config.yaml` `providers:` dict is internally converted to a `custom_providers` list by `get_compatible_custom_providers()`. Then `_configured_provider_matches()` scans **both**:
- `user_providers` → slug is the raw key, e.g., `local`
- `custom_providers` → slug is prefixed, e.g., `custom:local`

Both reference the same provider. If a model (e.g., `qwen36-27b`) is declared in that provider's `models:` section, it matches under **both slugs**, triggering the duplicate error.

Source: `hermes_cli/model_switch.py` ~L1048-1072 (`_configured_provider_matches` → duplicate detection)
Source: `hermes_cli/config.py` ~L4654 (`get_compatible_custom_providers` → converts `providers:` to list)

### Workaround

Explicitly specify the provider slug when switching:

```bash
/model qwen36-27b --provider local
# or
/model qwen36-27b --provider custom:local
```

### Note

This bug fires whenever a provider in `providers:` declares a model AND the model is typed without `--provider`. Single custom provider setups are most affected.