# 部署工具与服务器配置

本目录从外层工作区迁入仓库，所有本地命令均从仓库根目录运行。仅在明确的部署任务中使用；日常功能开发使用根目录的两个 `start_*.bat`。

| 位置                                         | 用途                                                |
| -------------------------------------------- | --------------------------------------------------- |
| `deploy.sh`                                  | 本地入口：同步 Git、检查目标版本、触发服务器部署    |
| `remote.sh`                                  | 安装到服务器 `/opt/rightwrite/deploy.sh` 的部署脚本 |
| [server/](server/README.md)                  | 服务器脚本、systemd 单元和 Nginx 配置副本           |
| [部署实例记录](../docs/deployment/README.md) | 现网与哈工深部署流程                                |

## 本地入口

Windows 使用 **Git Bash**，不要使用系统的 WSL `bash.exe`。Linux/macOS 使用 Bash。从克隆仓库的根目录执行：

```bash
bash deploy/deploy.sh
bash deploy/deploy.sh --target hitsz
```

脚本先处理本地 `main` 与 `origin/main` 的同步，再检查服务器版本，随后可能备份、停止服务、运行迁移和构建。执行前必须确认本次任务授权部署到指定实例；`--no-deploy` 仍可能合并和推送 Git，不能用它作只读检查。

`--truncate` 涉及清表，只有当前任务明确授权且备份、迁移要求已核对后才能使用。脚本注释、旧文档和历史测试记录不能替代本次操作授权。

参数说明见 `deploy.sh` 开头注释。入口按脚本位置定位本仓库和同目录 `remote.sh`，不依赖外层 `right_chat/` 或其目录名称。

## 凭据与实例配置

SSH 别名 `rightwrite`、`rightwrite-hitsz` 由本机 `~/.ssh/config` 配置；私钥留在本机或密钥管理器。服务器的 `rightwrite.env`、`.cos.yaml`、数据库及备份不入库。

`server/` 保存的是实例文件副本，修改域名、证书路径、服务账户或服务器目录前需对照目标实例。文件入库不会自动安装到服务器；`deploy.sh` 自动更新的只有 `remote.sh`。
