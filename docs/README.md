# Right Write 项目文档

当前项目是基于 Open WebUI v0.11.2 的成长写作教学平台。项目代码和共享协作资料都在本 Git 仓库内维护。

## 开始开发

1. 阅读根目录 [AGENTS.md](../AGENTS.md)，了解工程规则和业务边界。
2. 按 [本地开发说明](development/local-development.md) 准备环境并启动。
3. 修改教学功能前阅读 [当前教学规则](product/education.md) 与 [架构说明](architecture/overview.md)。
4. 提交前按 [Git 协作规范](development/git-workflow.md) 检查修改和同步状态。

## 当前维护的文档

| 文档                                                                        | 用途                                     |
| --------------------------------------------------------------------------- | ---------------------------------------- |
| [本地开发](development/local-development.md)                                | Windows 环境、5050/8080 启动、密钥和排障 |
| [Git 协作](development/git-workflow.md)                                     | 分支、中文提交、同步范围检查             |
| [仓库结构与同步范围](development/repository-layout.md)                      | 文件位置、共享资料与本地资料边界         |
| [架构概览](architecture/overview.md)                                        | 前后端入口和教学业务分层                 |
| [教学模块规则](product/education.md)                                        | 身份、作业、修订初稿、批改和画像         |
| [画像投影](../backend/open_webui/services/education/PROFILE_PROJECTIONS.md) | 冻结证据、版本投影和显式重算             |
| [品牌资源边界](rightwrite-branding-boundary.md)                             | 品牌静态资源的维护规则                   |
| [压测工具](../scripts/loadtest/README.md)                                   | 模拟模型服务、k6 和诊断并发工具          |
| [安全说明](SECURITY.md)                                                     | 漏洞报告渠道                             |

## 部署与原始需求

- [部署实例记录](deployment/README.md)：现网与哈工深的原始部署流程，仅在部署任务中使用。
- [产品需求原始资料](product/sources/README.md)：哈工深课程研讨逐字稿，用于追溯需求来源。

## 历史资料

[docs/archive/](archive/README.md) 保留整理前的需求、计划与会话记录，每份文档都标注为历史资料。`docs/superpowers/` 中的既有设计和计划也用于追溯，不能直接视为当前待办。

产品规则变化时维护当前文档；新设计和计划应注明日期、状态和适用范围。不要维护两份互相重复的协作规范。

两份部署流程和需求研讨原文随仓库同步；外层工作区的部署工具、行政资料、真实学生材料、品牌源素材和个人工具配置仍单独管理，详见 [同步范围](development/repository-layout.md)。
