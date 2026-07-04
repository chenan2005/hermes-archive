# TODO Reminder System

## Architecture

Each category has:
1. A `[标签]` prefix in the SKILL.md items
2. A cron job running a wrapper script that calls `check-todos.py <category>`
3. All scripts run with `no_agent=true` — **zero LLM tokens, pure shell**

## Adding a New Category

1. Add a `## <类别名>` header to SKILL.md with items tagged `- [ ] [标签]`
2. Create wrapper script `check-todos-<slug>.py`:
   ```python
   #!/usr/bin/env python3
   import subprocess, sys
   subprocess.run([sys.executable, "/home/chenan/.hermes/scripts/check-todos.py", "标签"])
   ```
3. Create cron job with `no_agent=true`, schedule, and script filename

## Silent-on-empty Pattern

- `check-todos.py` exits with code 0 and prints nothing when no pending items exist
- Cron jobs set `no_agent=true`: empty stdout = no delivery to user
- This avoids spamming the user with "you have 0 items" messages

## Current Cron Jobs

| Job | Schedule | Script |
|-----|----------|--------|
| 回家待办提醒 | `30 23 * * *` | check-todos-home.py |
| 周末待办提醒 | `0 10 * * 0` | check-todos-weekend.py |

## Scripts

All in `~/.hermes/scripts/`:
- `check-todos.py` — core logic, takes category arg, counts `- [ ] [标签]` lines
- `check-todos-home.py` — wrapper for 回家
- `check-todos-weekend.py` — wrapper for 周末
