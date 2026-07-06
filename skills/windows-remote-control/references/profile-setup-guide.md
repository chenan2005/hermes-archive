# Hermes Profile Setup for Remote Windows Control

How to create a Hermes profile that controls a remote Windows machine via SSH.

## Architecture

Do NOT use Hermes SSH backend (`terminal.backend: ssh`) for Windows — it hardcodes `bash -c`. Instead:

- `terminal.backend: local` — commands run locally
- Windows commands via explicit SSH: `ssh <alias> powershell -Command "..."` or `ssh <alias> cmd /c "..."`
- SOUL.md embeds the command patterns so the agent knows them without `-s` flag

## Full Setup Recipe

```bash
NAME=hermes-remote-<hostname>
ALIAS=<ssh-alias>
IP=<ip-address>

# 1. Create profile
hermes profile create $NAME

# 2. API keys + model
grep -E 'DEEPSEEK_API_KEY|GOOGLE_API_KEY' ~/.hermes/.env > ~/.hermes/profiles/$NAME/.env
hermes config set model.default deepseek-v4-pro --profile $NAME
hermes config set model.provider deepseek --profile $NAME
hermes config set model.base_url https://api.deepseek.com --profile $NAME
hermes config set terminal.backend local --profile $NAME

# 3. SSH config alias (skip IdentityFile if using default ~/.ssh/id_ed25519)
cat >> ~/.ssh/config << EOF

Host $ALIAS
    HostName $IP
    User chen_
    StrictHostKeyChecking accept-new
    ConnectTimeout 10
EOF

# 4. Sync structural config from default profile
python3 ~/.hermes/scripts/sync-profile-config.py $NAME

# 4b. Set config version (sync script skips _-prefixed keys)
hermes config set _config_version 30 --profile $NAME

# 5. Write SOUL.md with embedded command patterns
# (see template in windows-remote-control SKILL.md)

# 6. Verify
hermes -p $NAME -q "ssh $ALIAS cmd /c 'echo ONLINE && hostname'" --yolo
```

## Why not --clone-config?

`hermes profile create --clone-config` copies config.yaml including platform tokens (WeChat, Feishu, etc.) and display preferences from the default profile. For a Windows-control profile, it's cleaner to start minimal and use `sync-profile-config.py` which only copies structural keys, skipping platform secrets.

## SSH Key Management

- Default key: `~/.ssh/id_ed25519` (used for all machines)
- Windows admin authorized_keys: `C:\ProgramData\ssh\administrators_authorized_keys`
- See `references/windows-ssh-key-management.md` for deployment/rotation workflow

## Pitfalls

1. **Bare profiles lack `_config_version`** → "N commits behind" banner. Fixed by `sync-profile-config.py`.
2. **Bare profiles lack `onboarding.profile_build`** → OpenClaw migration banner on startup. Set `onboarding.profile_build: ask` and `onboarding.seen.openclaw_residue_cleanup: true`.
3. **`hermes update` doesn't sync config to profiles** → only code + skills. Run sync script after updates.
4. **PowerShell escaping over SSH** → backticks and `$` break. Use `cmd /c` for remote file writes.
5. **`hermes config set` stores lists as strings** → verify with `hermes config check`.
6. **`hermes profile rename` doesn't update SSH config** → update `~/.ssh/config` manually.
7. **`hermes update` interrupted (China network)** → pypi.org times out. Fix:
   ```bash
   rm -f ~/.hermes/hermes-agent/.update-incomplete
   sudo ~/.hermes/hermes-agent/venv/bin/python3 -m pip install -e '.[all]' \
     -i https://mirrors.aliyun.com/pypi/simple/
   ```
