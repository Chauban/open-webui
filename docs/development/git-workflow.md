# Git 协作规范

所有 Git 命令在本仓库中执行；外层 `right_chat/` 不是 Git 仓库。

- `origin`：`https://github.com/Chauban/open-webui.git`，本项目 Fork。
- `upstream`：`https://github.com/open-webui/open-webui.git`，官方仓库。
- 常规工作分支为 `main`；核查项目同步状态应比较 `origin`。

## 提交

提交格式为 `<type>: <subject>`，主题使用中文和祈使语气，不超过 50 个字符。类型包括 `feat`、`fix`、`refactor`、`style`、`docs`、`chore`、`perf` 和 `remove`。

```text
docs: 整理项目协作规范与开发文档
```

提交前检查 `git status`、`git diff` 和暂存内容，按功能选择文件；相关修改放在同一提交，不相关修改拆分。运行与修改有关的检查，行为变更需新增或调整有意义的测试。

不要使用 `git commit --amend` 或强制推送。密钥、环境变量、数据库、依赖、虚拟环境、个人配置和运行日志不入库；共享配置必须使用环境变量或无敏感信息的模板。

## 核查 GitHub 同步

先刷新远端引用，再核对实时状态：

```powershell
git fetch origin --prune
git status --short --branch --untracked-files=all
git rev-list --left-right --count HEAD...origin/main
git ls-remote origin refs/heads/main
git worktree list
git branch -vv
git log --oneline --branches --not --remotes=origin
git stash list
```

还要逐一检查其他 worktree 中的修改和未跟踪文件。旧分支落后于 `main` 不等于代码遗漏，应确认其提交是否已包含在 `main` 中；不要自动删除分支、工作区或 stash。

“代码已同步”只描述本仓库，不能表示外层工作区的行政资料、课程材料及本地状态已备份。

## 官方更新

仅按任务需要获取并选择性引入 `upstream` 更新，先核对本 Fork 的定制功能和测试，不自动把追踪官方更新扩展成全量合并或生产部署。

PR 按 `.github/pull_request_template.md` 编写，说明问题、修改后的行为、验证证据和需要维护的文档。漏洞通过 GitHub Security 报告渠道处理。
