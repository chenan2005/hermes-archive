# Qoder CLI Installation on Linux

Official install script. Verified on Linux Mint 22 (x86_64).

## Install

```bash
# Download script first (avoid curl|bash pipe)
curl -fsSL -o /tmp/qoder_install.sh https://qoder.com/install

# Inspect, then run
bash /tmp/qoder_install.sh
```

Installs to `~/.qoder/bin/qodercli/` with entry point at `~/.local/bin/qodercli`.

## Authentication

```bash
export QODER_PERSONAL_ACCESS_TOKEN="pt-xxxx..."
qodercli --version  # verify: 1.0.24+
```

Token file can be stored at `~/.qoder-token` for scripts.

## Offline/Non-interactive Mode

```bash
qodercli -p "prompt text" -m auto                       # plain text output
qodercli -p "prompt text" -f stream-json -m auto         # streaming JSON output
```

Flags: `-p` prompt, `-m` model tier (auto/lite/ultimate), `-f` output format.
