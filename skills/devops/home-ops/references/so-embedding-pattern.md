# SOUL.md Embedding Pattern for Hermes Profiles

## Problem

New Hermes profiles created with `hermes profile create` don't auto-load skills. The agent needs to call `skill_view()` explicitly, which it may not do unless prompted. Using `-s <skill>` every time is annoying.

## Solution: Embed essentials directly in SOUL.md

SOUL.md is injected into the system prompt at session start. Put the critical operational patterns directly in SOUL.md — no `skill_view()` call needed.

### Example: Windows remote control profile

```markdown
# SOUL.md for hermes-remote-<hostname>

You control a remote Windows machine at <IP>.

To execute commands, use SSH via the pre-configured alias:
    ssh hermes-remote-<hostname> <command>

## Command Patterns

### cmd.exe
    ssh hermes-remote-<hostname> cmd /c "ver"

### PowerShell (CRITICAL: single-quote wrapper!)
    ssh hermes-remote-<hostname> 'powershell -Command "Get-Process | Sort CPU -Descending"'

## File Transfer
    scp local_file hermes-remote-<hostname>:C:/Users/<user>/Desktop/
```

### Key principle

Keep SOUL.md short but CONCRETE. Don't say "load the skill for details" — put the most-used patterns right in the system prompt. The agent reads this every turn.

## When to use SOUL.md vs skills

| SOUL.md | Skills |
|---------|--------|
| Core operational patterns | Detailed reference, edge cases |
| Always available (zero cost) | Load on demand |
| ~1KB max, just the essentials | Can be longer with references/ |
| Profile-specific | Cross-profile reusable |
