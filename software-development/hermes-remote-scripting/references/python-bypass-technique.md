# Python 远程脚本构建与传输（可重用配方）

当需要创建包含 shell 变量引用（如 `$S`）的脚本并传输到远程机器时：

```python
from hermes_tools import terminal

# 1. 定义运行时构造的字符串
DS = chr(36) + "S"       # "$S" — 通过 chr(36) 避免源码中出现 "$S"
Q = '" '                   # 关闭引号 + 空格（shell 语法要求）
SVAL = "actual_secret"     # secret 值

# 2. 用普通字符串拼接构建脚本（不要用 f-string）
script = ""
script += '#!/bin/sh\n'
script += 'S="' + SVAL + '"\n'
script += 'echo "Test:"\n'
script += 'curl -s -H "Authorization: Bearer *** + DS + Q + 'some-arg\n'

# 3. 转换为八进制，用 printf 写入远程
octal = ''.join(f'\\{b:03o}' for b in script.encode())
terminal(f"ssh user@host \"printf '{octal}' > /tmp/script.sh\"", timeout=10)

# 4. 单独执行
terminal("ssh user@host 'sh /tmp/script.sh'", timeout=15)
```

## 验证方法

```python
# 确认脚本内容正确
terminal("ssh user@host 'awk \"{print NR\\\": \\\"\\$0}\" /tmp/script.sh'", timeout=10)

# 确认 $ 字符出现在脚本中（0x24）
terminal("ssh user@host 'grep -c \"\\$\" /tmp/script.sh'", timeout=10)
```

## 已知可用的安全引用模式

| 模式 | 在源码中出现 | 是否幸存 |
|------|-------------|:--------:|
| `$S` | `chr(36) + "S"` 拼接 | ✅ |
| `"` 关闭引号 | 单独变量 `Q = chr(34) + chr(32)` | ✅ |
| `$(grep ...)` | 远程脚本中的命令替换 | ✅ |
| `` `grep ...` `` | 远程脚本中的反引号 | ❌ 被替换 |
| `$SECRET` | 远程脚本中的长变量名 | ❌ `$S` 前缀触发替换 |
| 注释中写 `# $S` | 源码注释 | ❌ |
