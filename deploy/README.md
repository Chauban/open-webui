# 部署工具与服务器配置

本目录从外层工作区迁入仓库，所有本地命令均从仓库根目录运行。仅在明确的部署任务中使用；日常功能开发使用根目录的两个 `start_*.bat`。

| 位置                            | 用途                                                |
| ------------------------------- | --------------------------------------------------- |
| `deploy.sh`                     | 本地入口：同步 Git、检查目标版本、触发服务器部署    |
| `remote.sh`                     | 安装到服务器 `/opt/rightwrite/deploy.sh` 的部署脚本 |
| [server/](server/README.md)     | 服务器脚本、systemd 单元和 Nginx 配置副本           |
| [实例记录](#实例记录与相关资料) | 现网与哈工深部署流程                                |

## 本地入口

Windows 使用 **Git Bash**，不要使用系统的 WSL `bash.exe`。Linux/macOS 使用 Bash。从克隆仓库的根目录执行：

```bash
bash deploy/deploy.sh
bash deploy/deploy.sh --target hitsz
```

脚本先处理本地 `main` 与 `origin/main` 的同步，再检查服务器版本，随后可能备份、停止服务、运行迁移和构建。执行前必须确认本次任务授权部署到指定实例；`--no-deploy` 仍可能合并和推送 Git，不能用它作只读检查。

`--truncate` 涉及清表，只有当前任务明确授权且备份、迁移要求已核对后才能使用。脚本注释、旧文档和历史测试记录不能替代本次操作授权。

参数说明见 `deploy.sh` 开头注释。入口按脚本位置定位本仓库和同目录 `remote.sh`，不依赖外层 `right-write/` 或其目录名称。

## 凭据与实例配置

SSH 别名 `rightwrite`、`rightwrite-hitsz` 由本机 `~/.ssh/config` 配置；私钥留在本机或密钥管理器。服务器的 `rightwrite.env`、`.cos.yaml`、数据库及备份不入库。

`server/` 保存的是实例文件副本，修改域名、证书路径、服务账户或服务器目录前需对照目标实例。文件入库不会自动安装到服务器；`deploy.sh` 自动更新的只有 `remote.sh`。

## 实例记录与相关资料

[现网部署流程](../docs/deployment/部署流程.md) 和 [哈工深部署流程](../docs/deployment/哈工深部署流程.md) 保存实际部署过程。记录应随环境变化维护，其中的价格、组件版本、已部署提交及验收结果属于注明日期时的事实，不代表读取时的实时状态。

- [本地开发](../docs/development/local-development.md)：日常开发的启动与排障。
- [修订初稿历史方案](../docs/archive/哈工深修订初稿方案.md)：实例记录中的课程背景。
- [当前 PRD](../docs/product/PRD.md) 与 [架构规则](../docs/product/education.md)：当前产品和实现边界。
- [压测工具](../scripts/loadtest/README.md) 与 [历史压测记录](../docs/archive/压测记录.md)：运行方法及旧实测数据。

服务器命令从对应服务器目录执行；本地 `deploy/deploy.sh` 从仓库根目录运行。本机 `.ssh`、实际密钥和外层 `哈工深批注/` 材料仍单独管理。

旧实例记录中的 `本地开发启动流程.md`、`哈工深修订初稿方案.md` 和 `loadtest/README.md` 分别对应以上开发说明、历史方案和当前压测工具说明。文档中的历史清表步骤不代表新的操作授权。

## 课程课件发布

课件功能复用网站账号，支持一个由管理员维护的 HTML 课件及同目录 MP4 视频。不增加数据库或迁移。

1. 将经过验证的 HTML 命名为 `index.html`，与它引用的五个压缩 MP4 一起放入实例私有目录，例如 `/opt/rightwrite/courseware/agent-2026`。保留视频原文件名；不要上传 `qa/`、日志、压缩报告或其他课程源文件。
2. 目录归属 `rightwrite:rightwrite`，目录 750、文件 640。不要将课件放入 `app/static/`、构建产物或任何 Nginx 公共静态目录。
3. 在南科大 `/opt/rightwrite/rightwrite.env` 增加 `COURSEWARE_DIR=/opt/rightwrite/courseware/agent-2026`，部署包含课件路由和页面的版本并重启服务。哈工深不设置此变量；代码共用而课件目录、入口和权限校验由实例控制。
4. 用学生、教师与管理员账号检查侧边栏「课程课件」、`/courseware` 的页面与返回主页、视频起播与拖动。使用未登录窗口检查 HTML 和视频直链均返回 401；已登录的 Range 请求应返回 206。
5. 更新课件时先上传至新的版本目录并验证所有资源，再切换环境变量并重启；保留上一目录便于回退。撤回时移除 `COURSEWARE_DIR` 并重启。不要在学生正在播放时覆盖原视频。

后端 `/api/v1/courseware/` 检查可用性；`/api/v1/courseware/content/{filename}` 仅服务 `index.html` 和同目录 MP4，所有请求要求已激活账号。响应禁止公共缓存，文件响应支持 Range。课件 HTML 是管理员发布的可信脚本，与网站同源；不要发布不可信来源的 HTML。

2026-11-07 本地课件接入从南科大线上基线 `bf064fed4` 在独立分支实现，未包含主工作区未提交的教学改造；此记录不表示已经部署到生产。

本地验证：11 项课件后端测试与 8 项侧边栏/页面测试通过，生产构建通过（本机需 `NODE_OPTIONS=--max-old-space-size=8192`）。全量前端回归为 146 通过、3 项既有 PDF 路径测试失败，另有 2 个既有编辑器 jsdom 错误；随后新增的 3 项课件页面测试单独通过。全量类型检查仍有既有错误，新增课件组件/页面没有类型错误；不将此描述为全项目检查通过。真实浏览器和线上验收仍需在部署环节完成。
