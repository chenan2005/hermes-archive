# Remote Hermes Session Reading

When you need to read past Hermes session data from a remote machine
(e.g., to understand why a service broke after a previous session):

## Pattern: scp a Python script, execute remotely

1. Write a Python script locally that queries SQLite:
```python
import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
db = r"C:\Users\chen_\AppData\Local\hermes\state.db"  # Windows path
conn = sqlite3.connect(db)
rows = conn.execute(
    "SELECT role, substr(content,1,400) FROM messages WHERE session_id=? ORDER BY id",
    ("20260618_213710_dcedd2",)  # session ID from `hermes sessions list`
)
for r in rows:
    print(f"[{r[0]}] {r[1]}")
    print("---")
```

2. Upload and execute:
```bash
scp /tmp/q.py HOST:C:/Users/chen_/q.py
ssh HOST 'cmd /c "python C:\Users\chen_\q.py"'
```

## Pitfalls

- Session IDs contain underscores — must use parameterized queries (`?`), not string interpolation
- Windows console encoding (GBK) may crash Python's print. Fix with `sys.stdout` wrapper above
- The `$env:LOCALAPPDATA` expansion fails through SSH. Use absolute paths
- If SCP is broken, fix sshd_config sftp subsystem path first (see v2ray-recovery.md)
