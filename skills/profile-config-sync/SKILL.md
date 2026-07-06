---
name: profile-config-sync
description: Sync missing structural config keys from the default profile to a named profile. Use after creating a new profile or after `hermes update` to keep profiles consistent.
category: devops
platforms: [linux]
---

# Profile Config Sync

New profiles created with `hermes profile create` start with a minimal config.yaml.  
Use this script to sync structural config keys (agent behavior, tools, UX) from the default profile.

## Usage

```bash
python3 ~/.hermes/scripts/sync-profile-config.py <profile-name>
```

Example:
```bash
python3 ~/.hermes/scripts/sync-profile-config.py hermes-remote-<hostname>
```

## What it syncs

- Agent behavior: `agent`, `compression`, `context`, `memory`, `security`, `tool_loop_guardrails`
- Tool configuration: `toolsets`, `platform_toolsets`, `tools`, `code_execution`, `browser`
- Auxiliary models: `auxiliary` (vision, compression, etc.)
- Display/UX: `display`, `dashboard`, `voice`, `stt`, `tts`
- Delegation & sub-agents: `delegation`, `kanban`
- Cron & sessions: `cron`, `session_reset`, `sessions`
- And other structural settings

## What it skips

- Platform credentials: `platforms`, `weixin`, `telegram`, `discord`, etc.
- These contain tokens/secrets and should be configured per-platform

## When to run

- After `hermes profile create` (new profile) — also see `windows-remote-control` skill reference: `references/so-embedding-pattern.md` for SOUL.md technique
- After `hermes update` (new config keys might be added)
- When tools count differs between profiles
- When you see "⚠ N commits behind" or OpenClaw residue warnings on a fresh profile

## Full new-profile recipe

New profiles need more than just config sync. The complete checklist:

```bash
NAME=hermes-remote-<hostname>
# 1. Create
hermes profile create $NAME
# 2. API keys + model
grep -E 'DEEPSEEK_API_KEY|GOOGLE_API_KEY' ~/.hermes/.env > ~/.hermes/profiles/$NAME/.env
hermes config set model.default deepseek-v4-pro --profile $NAME
hermes config set model.provider deepseek --profile $NAME
hermes config set terminal.backend local --profile $NAME
# 3. SSH config alias (add to ~/.ssh/config)
# 4. Structural config sync
python3 ~/.hermes/scripts/sync-profile-config.py $NAME
# 5. Write SOUL.md with command patterns
# 6. Verify
hermes -p $NAME -q "echo test" --yolo
```

## Background: what `hermes update` does NOT sync

`hermes update` syncs to all profiles:
- ✅ Source code (shared git repo at `~/.hermes/hermes-agent/`)
- ✅ Bundled skills (`seed_profile_skills()` loops over all profiles)
- ❌ **config.yaml** — config migration only runs against the *active* profile
- ❌ `_config_version` — per-profile, must be synced manually

This is intentional: profile configs contain platform secrets (tokens) that must not leak between profiles. But structural keys (tool config, behavior settings) should stay aligned — that's what this script does.

**Note:** the sync script currently skips `_config_version` (keys starting with `_` are filtered). After running the sync, manually set it:
```bash
hermes config set _config_version 30 --profile <name>
```
(Check the current value with `hermes config check` on the default profile.)

## Common missing-key symptoms

| Missing key | Symptom |
|---|---|
| `_config_version` | "⚠ N commits behind — run hermes update" banner |
| `onboarding.profile_build` | OpenClaw residue cleanup warning on every start |
| `platform_toolsets.cli` | Tool count lower than default (e.g. 26 vs 29) |
| `toolsets` | Skills/tools fall back to wrong defaults |

## Pitfall: `hermes config set` stores complex values as strings

`hermes config set` writes JSON-encoded strings for list/dict values instead of native YAML:

```bash
# WRONG — stored as '["hermes-cli"]' (string, not list)
hermes config set toolsets '["hermes-cli"]' --profile <name>

# RIGHT — use the sync script, or edit config.yaml directly
python3 ~/.hermes/scripts/sync-profile-config.py <name>
```

Always verify with `hermes config check --profile <name>` after manual `config set` calls involving lists or dicts. If the value appears quoted in the YAML, fix it with a Python one-liner or re-run the sync script.

## Pitfall: interrupted `hermes update` blocks subsequent operations

If `hermes update` is killed mid-install (Ctrl-C, timeout, etc.), it leaves a breadcrumb that causes future `hermes` invocations to re-attempt the install before doing anything else:

```
⚠ A previous `hermes update` was interrupted mid-install — finishing dependency installation now...
```

This blocks `hermes config set`, `hermes chat`, and other commands. Fix:

```bash
# The marker file is in the shared source tree, not per-profile:
rm -f ~/.hermes/hermes-agent/.update-incomplete
# Also clean any stale per-profile markers:
find ~/.hermes/profiles -name '.update-incomplete' -delete 2>/dev/null
```

If `hermes` still hangs on startup after clearing the marker,
the venv deps need a manual reinstall (pypi.org may be slow/blocked):
```bash
cd ~/.hermes/hermes-agent
sudo venv/bin/python3 -m pip install -e '.[all]' -i https://mirrors.aliyun.com/pypi/simple/
```
