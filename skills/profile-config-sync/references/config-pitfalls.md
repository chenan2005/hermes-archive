# Hermes Config Pitfalls

## `hermes config set` stores arrays as strings

```bash
# WRONG — stores literal '["browser","web"]' string, not a YAML list
hermes config set platform_toolsets.cli '["browser","web"]'

# RIGHT — use Python to write proper YAML
python3 -c "
import yaml
with open('config.yaml') as f:
    cfg = yaml.safe_load(f)
cfg['platform_toolsets'] = {'cli': ['browser', 'web']}
with open('config.yaml', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False)
"
```

## New profile essentials

A fresh `hermes profile create` produces a bare config. Missing keys cause:
- `_config_version` → "⚠ N commits behind" banner
- `onboarding.profile_build` → OpenClaw residue warning
- `platform_toolsets.cli` → different tool count vs default
- `toolsets` → different tool count

Fix: run `python3 ~/.hermes/scripts/sync-profile-config.py <name>` after creation.
