> **历史资料，非当前规范。** 2026-10-09 整理入库，以下保留原始内容用于追溯，可能包含已下线功能、过期状态及旧路径。当前规则见 [教学模块](../product/education.md)、[开发说明](../development/local-development.md) 和 [AGENTS.md](../../AGENTS.md)。

# Open WebUI 项目介绍与架构文档

> 文档创建时间: 2026-02-27

---

## 一、项目概述

**Open WebUI** 是一个开源的、功能丰富的、用户友好的自托管 AI 平台，支持离线运行。它可以与多种 LLM（大语言模型）后端集成，包括：
- **Ollama**
- **OpenAI 兼容 API**
- **内置推理引擎**（支持 RAG 检索增强生成）

**项目 GitHub**: https://github.com/open-webui/open-webui

---

## 二、项目结构

```
right_chat/
├── open-webui/                    # 主项目目录
│   ├── backend/                   # 后端代码
│   │   └── open_webui/
│   │       ├── main.py           # FastAPI 应用入口
│   │       ├── config.py         # 配置管理
│   │       ├── env.py            # 环境变量处理
│   │       ├── routers/          # API 路由层
│   │       │   ├── auths.py      # 认证相关 API
│   │       │   ├── chats.py     # 聊天 API
│   │       │   ├── models.py    # 模型管理 API
│   │       │   ├── knowledge.py # 知识库 API
│   │       │   ├── retrieval.py # RAG 检索 API
│   │       │   ├── ollama.py    # Ollama 集成 API
│   │       │   ├── openai.py    # OpenAI 兼容 API
│   │       │   ├── users.py     # 用户管理 API
│   │       │   └── ...          # 其他路由
│   │       ├── models/           # 数据模型层
│   │       │   ├── users.py     # 用户模型
│   │       │   ├── chats.py     # 聊天模型
│   │       │   ├── files.py     # 文件模型
│   │       │   └── ...          # 其他模型
│   │       ├── internal/         # 内部模块
│   │       │   ├── db.py        # 数据库连接
│   │       │   └── migrations/  # 数据库迁移
│   │       ├── retrieval/        # RAG 检索功能
│   │       ├── socket/           # WebSocket 支持
│   │       ├── storage/          # 存储层
│   │       ├── tools/            # 工具集成
│   │       ├── utils/            # 工具函数
│   │       └── migrations/       # Alembic 数据库迁移
│   │
│   ├── src/                      # 前端代码
│   │   ├── lib/                  # 核心库
│   │   │   ├── apis/            # 前端 API 调用
│   │   │   ├── components/      # Svelte 组件
│   │   │   ├── stores/          # Svelte stores (状态管理)
│   │   │   ├── types/           # TypeScript 类型定义
│   │   │   ├── utils/           # 前端工具函数
│   │   │   └── i18n/            # 国际化
│   │   ├── routes/               # SvelteKit 路由页面
│   │   │   ├── (app)/           # 应用主页面
│   │   │   ├── auth/            # 认证页面
│   │   │   └── ...
│   │   ├── app.css              # 全局样式
│   │   ├── app.html             # HTML 模板
│   │   └── tailwind.css         # Tailwind CSS
│   │
│   ├── Dockerfile                # Docker 部署配置
│   ├── Makefile                 # 构建脚本
│   └── package.json 等          # 前端依赖配置
│
└── CLAUDE.md                     # Claude Code 指引文件
```

---

## 三、技术栈

### 后端

| 技术 | 用途 |
|------|------|
| **Python 3.11+** | 主要编程语言 |
| **FastAPI** | Web 框架 |
| **SQLAlchemy** | ORM 数据库操作 |
| **Alembic** | 数据库迁移工具 |
| **SQLite / PostgreSQL** | 数据库支持 |
| **Redis** | 缓存与会话管理 |
| **Pydantic** | 数据验证 |
| **aiohttp** | 异步 HTTP 客户端 |

### 前端

| 技术 | 用途 |
|------|------|
| **SvelteKit** | 前端框架 |
| **TypeScript** | 类型安全 |
| **Tailwind CSS** | 样式框架 |
| **Svelte Stores** | 状态管理 |

---

## 四、核心功能模块

### 1. 聊天系统
- **路由文件**: `routers/chats.py`
- **模型文件**: `models/chats.py`
- **功能**:
  - 多模型对话支持
  - 对话历史管理
  - 文件夹组织

### 2. 认证系统
- **路由文件**: `routers/auths.py`
- **模型文件**: `models/auths.py`
- **功能**:
  - 用户注册/登录
  - OAuth 集成
  - LDAP/AD 支持
  - SCIM 2.0 自动配置

### 3. 模型管理
- **路由文件**: `routers/models.py`
- **功能**:
  - Ollama 模型集成
  - OpenAI API 兼容
  - 自定义模型创建

### 4. 知识库与 RAG
- **路由文件**: `routers/knowledge.py`, `routers/retrieval.py`
- **功能**:
  - 文档上传与解析
  - 向量数据库集成 (ChromaDB, Qdrant, Milvus 等)
  - 检索增强生成

### 5. 工具系统
- **路由文件**: `routers/tools.py`
- **目录**: `tools/`
- **功能**:
  - Python 函数调用
  - 自定义工具扩展
  - Pipelines 插件框架

### 6. 用户管理
- **路由文件**: `routers/users.py`
- **模型文件**: `models/users.py`
- **功能**:
  - 角色权限控制 (RBAC)
  - 用户组管理
  - 多租户支持

---

## 五、部署方式

### 1. Docker 部署 (推荐)

```bash
# 基础部署 (Ollama 在本机)
docker run -d -p 3000:8080 \
  --add-host=host.docker.internal:host-gateway \
  -v open-webui:/app/backend/data \
  --name open-webui \
  --restart always \
  ghcr.io/open-webui/open-webui:main

# Ollama 在远程服务器
docker run -d -p 3000:8080 \
  -e OLLAMA_BASE_URL=https://example.com \
  -v open-webui:/app/backend/data \
  --name open-webui \
  --restart always \
  ghcr.io/open-webui/open-webui:main

# 仅使用 OpenAI API
docker run -d -p 3000:8080 \
  -e OPENAI_API_KEY=your_secret_key \
  -v open-webui:/app/backend/data \
  --name open-webui \
  --restart always \
  ghcr.io/open-webui/open-webui:main

# GPU 加速版本
docker run -d -p 3000:8080 \
  --gpus all \
  --add-host=host.docker.internal:host-gateway \
  -v open-webui:/app/backend/data \
  --name open-webui \
  --restart always \
  ghcr.io/open-webui/open-webui:cuda
```

### 2. Python pip 安装

```bash
pip install open-webui
open-webui serve
```

访问地址: http://localhost:8080

---

## 六、数据库架构

- **ORM**: SQLAlchemy
- **默认数据库**: SQLite
- **可选数据库**: PostgreSQL
- **迁移工具**: Alembic
- **迁移文件位置**:
  - `backend/open_webui/internal/migrations/`
  - `backend/open_webui/migrations/versions/`

---

## 七、关键配置文件

| 文件 | 说明 |
|------|------|
| `config.py` | 核心配置，包含所有可配置项 |
| `env.py` | 环境变量解析 |
| `.env.example` | 环境变量示例 |
| `Dockerfile` | Docker 构建配置 |
| `alembic.ini` | 数据库迁移配置 |

---

## 八、扩展性

### Pipelines 插件框架
- 允许添加自定义 Python 逻辑
- 示例: 函数调用、用户限流、使用监控、消息过滤等

### 工具系统
- 支持自定义 Python 函数
- 通过 BYOF (Bring Your Own Function) 集成 LLM

### 向量数据库支持
- ChromaDB
- PGVector
- Qdrant
- Milvus
- Elasticsearch
- OpenSearch
- Pinecone
- S3Vector
- Oracle 23ai

### 存储后端支持
- 本地存储
- S3
- Google Cloud Storage
- Azure Blob Storage

---

## 九、开发指南

### 新增 API 端点
在 `backend/open_webui/routers/` 中添加路由文件

### 新增数据模型
在 `backend/open_webui/models/` 中添加模型

### 前端组件开发
在 `src/lib/components/` 中添加 Svelte 组件

### 前端页面开发
在 `src/routes/` 中添加页面

### 数据库变更
创建 Alembic 迁移文件

### 本地开发
参考官方文档: https://docs.openwebui.com/getting-started/development

---

## 十、常用环境变量

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `OLLAMA_BASE_URL` | Ollama 服务地址 | `http://localhost:11434` |
| `OPENAI_API_KEY` | OpenAI API 密钥 | - |
| `OPENAI_API_BASE_URL` | OpenAI API 基础 URL | `https://api.openai.com/v1` |
| `DATA_DIR` | 数据存储目录 | `./data` |
| `DATABASE_URL` | 数据库连接 URL | SQLite |
| `REDIS_URL` | Redis 连接 URL | - |
| `WEBUI_NAME` | 应用名称 | `Open WebUI` |
| `WEBUI_AUTH` | 是否启用认证 | `True` |

---

## 十一、相关链接

- **官方文档**: https://docs.openwebui.com
- **GitHub 仓库**: https://github.com/open-webui/open-webui
- **Discord 社区**: https://discord.gg/5rJgQTnV4s
- **Pipelines 插件框架**: https://github.com/open-webui/pipelines

---

*此文档由 Claude Code 生成，用于项目团队参考*
