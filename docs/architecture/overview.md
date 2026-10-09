# Right Write 架构概览

> 核对日期：2026-10-09。基于本 Fork v0.11.2 的当前目录与实现。

Right Write 是成长写作教学平台，前端使用 Svelte 5、SvelteKit 2、TypeScript 和 Tailwind CSS 4，后端使用 FastAPI、SQLAlchemy 和 Alembic。

## 代码入口

| 位置                                      | 职责                       |
| ----------------------------------------- | -------------------------- |
| `src/routes/`                             | 页面与布局                 |
| `src/lib/components/`                     | 共享组件与教学 UI          |
| `src/lib/apis/`                           | 前端 HTTP 客户端和类型     |
| `src/lib/stores/`                         | 全局状态和实例功能开关     |
| `backend/open_webui/main.py`              | 应用、路由挂载和中间件     |
| `backend/open_webui/routers/`             | HTTP、身份权限和事务入口   |
| `backend/open_webui/models/`              | 严格模型、数据库约束和仓储 |
| `backend/open_webui/services/education/`  | 教学业务逻辑               |
| `backend/open_webui/migrations/versions/` | Alembic 数据结构迁移       |
| `backend/open_webui/socket/main.py`       | Socket.IO 服务             |

## 请求与数据流

前端 API 客户端通过同源 `/api/...` 请求后端；开发时 Vite 默认代理到 8080。路由检查身份和资源权限，调用服务及仓储，并在事务入口控制提交。Socket.IO 负责实时通知和流式消息。

教学流程包括班级与作业、写作会话、初稿基线、正文版本和来源、对话辅导、提交快照、教师批改及成长画像。身份使用教学用户组，平台管理员角色与教学身份分开。

画像事实证据冻结保存，算法结果和聚合结果使用版本化投影。普通画像 GET 读取投影，不能扫描原始历史并偷偷重算。细节见 [画像投影说明](../../backend/open_webui/services/education/PROFILE_PROJECTIONS.md)。

具体服务划分、学生与教师页面入口、任务模式和权限边界统一在 [教学模块规则](../product/education.md) 维护，避免在多份文档重复定义。

后端品牌静态资源在 `backend/open_webui/static/`，是项目资源，不是可随意清理的构建垃圾。[品牌边界](../rightwrite-branding-boundary.md) 说明了维护范围。
