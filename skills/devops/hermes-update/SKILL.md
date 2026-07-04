---
name: hermes-update
description: 更新 Hermes Agent（git 安装 + local/customizations 分支场景）。用 stash+rebase 流程安全拉取上游代码，不丢失本地 patch。
---

# Hermes Update

## 适用场景

- 安装方式：**git clone**（`~/.hermes/hermes-agent/`）
- 本地有自定义 patch 在 `local/customizations` 分支上（数量不定，视当前活跃 patch 而定）
- `main` 跟踪 `origin/main`
- **不能用 `hermes update`**（它会 `git reset --hard origin/main` 静默丢弃本地 commit）

## 安全更新流程

```bash
# 0. 先 fetch 确认是否有新提交（避免白跑流程）
git fetch origin
behind=$(git rev-list --count main..origin/main)
if [ "$behind" -eq 0 ]; then
  echo "已是最新，无需更新。"
  exit 0
fi
echo "落后 $behind 个 commit，开始更新..."

# 1. 确保当前在 local/customizations 分支上
git checkout local/customizations

# 2. 有未提交改动先 stash
git status --short
git stash push -m "pre-update $(date +%F)"

# 3. 切到 main，从上游拉最新
git checkout main
git pull --ff-only origin main

# 4. 切回 customization，rebase 到最新 main
git checkout local/customizations
git rebase main

# 5. 恢复未提交改动
git stash pop

# 6. 抑制版本检查提示，重启 Hermes 生效
rm -f ~/.hermes/.update_check
echo "更新完成。退出 Hermes 重进即可使用新版本。"
```

> Rebase 有冲突时，解决后 `git rebase --continue`。rebase 的冲突处理比 stash pop 稳定。
> `.update_check` 是 Hermes 内部版本检查标记，删除后下次启动前不再提示。

## 验证结果

```bash
cd ~/.hermes/hermes-agent
git log --oneline -3                # 确认已包含上游最新 commit
git log --oneline main..HEAD        # 确认本地 patch 还在（数量 = 输出行数）
hermes --version                    # 确认新版本号
```

## 不慎用了 `hermes update` 的恢复

如果跑过 `hermes update` 导致本地 commit 丢失：

```bash
git reflog --date=iso | grep "commit:"
git checkout -b local/customizations main
git cherry-pick <hash-1> <hash-2> ...   # 按 reflog 顺序（旧→新）
```

Reflog 条目默认存活 30 天。之后走正常更新流程。

## 排坑

- **绝不用 `hermes update`** — 它静默丢本地 commit，且 stash 不可靠
- **更新前先 commit 到分支上**，不要依赖 stash 做备份
- **更新后需要完全退出 Hermes 重进**（`/reset` 不够，工具代码改动需新进程）
- **pip/uv 包安装用户不适用** — 本 skill 只适用于 `~/.hermes/hermes-agent/` git 安装
- **`git fetch origin` 超时 → 检查系统代理** — 如果 GitHub 需要走代理才能访问，先确保系统代理已开启：
  1. `sing-box-ctrl proxy on`（开启 GUI + CLI 代理）
  2. `source ~/.config/proxy-env`（让当前终端生效，或开新终端）
  3. 重新 `git fetch origin`
  
  验证代理生效：`echo $http_proxy` 应返回 `http://127.0.0.1:10881`。如果代理已开但当前终端未 source，env 变量不会自动进入子进程，git 仍会走直连导致超时。
