# Bash-Side PowerShell EncodedCommand Helper

Pure-bash functions to encode and run PowerShell scripts over SSH without any quoting/escaping issues.

## The Core Functions

```bash
# Encode a PowerShell script as UTF-16LE Base64 (for -EncodedCommand)
ps_enc() {
    local script="$1"
    local b64
    b64=$(printf '%s' "$script" | iconv -f UTF-8 -t UTF-16LE 2>/dev/null | base64 -w0 2>/dev/null || \
          printf '%s' "$script" | base64 -w0 2>/dev/null)
    echo "$b64"
}

# Run a PS command over SSH, return stdout (or default on failure)
ps_run() {
    local script="$1"
    local default="${2:-}"
    local enc
    enc=$(ps_enc "$script")
    ssh "${TARGET}" "powershell -NoProfile -EncodedCommand ${enc}" 2>/dev/null || echo "$default"
}
```

## Usage Example

```bash
# Simple PowerShell: check port
PORT_OK=$(ps_run "try { (netstat -ano | Select-String \":8080\" | Select-String LISTEN).Count } catch { 0 }" "0")

# Multi-line: start a background process
PS_START=$(ps_enc "
    \$log = \"C:\\llama\\start_log.txt\";
    Add-Content \$log \"\$(Get-Date) === started ===\";
    Start-Process -FilePath \"C:\\llama\\llama.exe\" -ArgumentList @(
        '-m', 'C:\\llama\\models\\Qwen3.6-27B-Q4_K_M.gguf',
        '-c', '262144'
    ) -WindowStyle Hidden
")
ssh "${TARGET}" "powershell -NoProfile -EncodedCommand ${PS_START}" > /dev/null 2>&1
```

## Why This Wins

| Approach | Issue |
|----------|-------|
| `ssh host "powershell -Command \"...\""` | Double/triple nested quotes break on `$`, `|`, `"` |
| `ssh host 'powershell -File script.ps1'` | Needs SCP+upload first |
| **`-EncodedCommand` (base64)** | **Single token, zero escaping. Works for any PS script.** |

`iconv -f UTF-8 -t UTF-16LE` ensures proper encoding for PowerShell's Unicode base64 expectations. On systems without `iconv`, fallback to plain `base64` still works for ASCII-only scripts.

## Pitfalls

- **Return value is CLIXML** when `-OutputFormat xml` is default. Simple strings, `Write-Host`, and `Select-String` work fine. Structured data needs `| ConvertTo-Json` at script end.
- **No PS1 file fallback** — for complex workflows (file transfers, multi-script orchestration), still prefer SCP + `-File` approach.
- **`set -euo pipefail`** will crash if the SSH command fails. Always `|| echo "$default"` or wrap in a function like `ps_run` that catches failure.
- **Windows CRLF** — PowerShell stdout often includes `\r` characters. Pipe through `| tr -d '\r'` when consuming output in bash.
