# Windows SSH 管理员用户免密登录配置

## 背景

Windows OpenSSH 对管理员组用户（Administrators）的处理方式与普通用户不同。
如果目标用户属于 Administrators 组，SSH 服务会**忽略** `%USERPROFILE%\.ssh\authorized_keys`，
改为读取 `C:\ProgramData\ssh\administrators_authorized_keys`。

## 配置步骤

### 1. 确认用户角色

```powershell
net localgroup Administrators
```

如果用户名出现在列表中，走管理员路径。

### 2. 获取本机公钥

```bash
cat ~/.ssh/id_ed25519.pub
# 统一使用: ssh-ed25519 ... chenan@chenan-Lenovo-XiaoXinPro-13API-2019
```

### 3. 首次配置（密码登录）

```bash
# 3a. 用 sshpass 写入公钥（UTF-8 无 BOM）
sshpass -p '<password>' ssh <user>@<ip> powershell -Command \
  "\$p='C:\ProgramData\ssh\administrators_authorized_keys'; \$key='<pubkey content>'; \$bytes=[System.Text.Encoding]::UTF8.GetBytes(\$key); [System.IO.File]::WriteAllBytes(\$p, \$bytes)"

# 3b. 设置 ACL（仅 SYSTEM + Administrators）
sshpass -p '<password>' ssh <user>@<ip> powershell -Command \
  "\$p='C:\ProgramData\ssh\administrators_authorized_keys'; \$acl=Get-Acl \$p; \$acl.SetAccessRuleProtection(\$true,\$false); \$acl.SetAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule('BUILTIN\Administrators','FullControl','Allow'))); \$acl.SetAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule('NT AUTHORITY\SYSTEM','FullControl','Allow'))); Set-Acl \$p \$acl"

# 3c. 重启 sshd 服务
sshpass -p '<password>' ssh <user>@<ip> powershell -Command "Restart-Service sshd"
```

### 4. 验证

```bash
ssh -o PreferredAuthentications=publickey <user>@<ip> "hostname"
```

### 5. 清理

```bash
rm /tmp/tmp-passwd   # 删除临时密码文件
```

## 已知陷阱

| 问题 | 原因 | 解决 |
|------|------|------|
| 公钥认证失败 | authorized_keys 含 UTF-8 BOM | 用 `[System.IO.File]::WriteAllBytes` 写入，不用 `Set-Content` |
| ACL 不对 | 普通用户路径（%USERPROFILE%）对管理员无效 | 必须用 `C:\ProgramData\ssh\administrators_authorized_keys` |
| sshd 未重载 | 配置文件变更需重启服务 | `Restart-Service sshd` |
| PowerShell 命令传参错误 | cmd 模式下的管道/引号问题 | 用 `-EncodedCommand` 或避免管道操作 |
