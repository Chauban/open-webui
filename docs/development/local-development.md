# 本地开发

以下命令均从 Git 仓库根目录执行，即包含 `package.json` 和 `backend/` 的 `open-webui/`。本地开发使用前端 5050、后端 8080。

## 环境准备

使用 Node.js/npm 和 Python 3.12。前端依赖位于 `node_modules/`，后端虚拟环境必须位于 `backend/.venv/`。首次克隆时：

```powershell
npm ci
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

依赖、数据库和密钥不入库，换电脑后需在本地准备。迁移由 Alembic 管理，禁止用 ORM `create_all` 代替迁移。前端启动会执行 `pyodide:fetch`，首次下载需要网络。

## 启动入口

双击仓库根目录的两个脚本，各占一个终端窗口：

1. `start_backend.bat`：生成或加载 `backend/.webui_secret_key`，设置开发 CORS 白名单与默认中文，启动 uvicorn。
2. `start_frontend.bat`：执行 `npm run dev:5050`。

原有外层工作区的同名脚本调用仓库中的脚本，可继续双击使用。启动脚本的逻辑只在仓库中维护。

访问 `http://localhost:5050`，检查：

```powershell
curl.exe -i --connect-timeout 2 http://localhost:5050/
curl.exe -i --connect-timeout 2 http://localhost:8080/health
```

## 手动启动

后端终端：

```powershell
cd .\backend
if (-not (Test-Path .webui_secret_key)) {
    .venv\Scripts\python.exe -c "import base64,os;open('.webui_secret_key','w').write(base64.b64encode(os.urandom(48)).decode())"
}
$env:WEBUI_SECRET_KEY = (Get-Content .webui_secret_key -Raw).Trim()
$env:CORS_ALLOW_ORIGIN = 'http://localhost:5050;http://localhost:5051;http://localhost:5173;http://localhost:8080;http://127.0.0.1:5050;http://127.0.0.1:5051;http://127.0.0.1:5173;http://127.0.0.1:8080'
$env:DEFAULT_LOCALE = 'zh-CN'
.venv\Scripts\python.exe -m uvicorn open_webui.main:app --port 8080 --host 0.0.0.0 --reload
```

前端终端，从仓库根目录执行：

```powershell
npm run dev:5050
```

不要用 `npm run dev` 替代固定端口入口，不要在 Windows 上运行 `bash dev.sh`，不要裸启后端或添加 `--forwarded-allow-ips "*"`。

## 验证与测试

前端测试只检查主工作区，并在结束后退出：

```powershell
npm.cmd --% run test:frontend -- --run --exclude .claude/**
```

教学后端测试，先设置密钥但不输出密钥：

```powershell
$env:WEBUI_SECRET_KEY = (Get-Content backend\.webui_secret_key -Raw).Trim()
npm run test:education
```

其他命令见 [AGENTS.md](../../AGENTS.md)。修改迁移、列类型、约束或 SQL 时，除 SQLite 外还必须在专用 PostgreSQL 测试服务运行相关测试，严禁指向生产库。

## 排障

- 模型或 AI 对话异常先检查管理员功能开关、直连、模型可见性与角色权限。浏览器请求通常应走本地 `/api/...`；直接请求外部模型商可能是直连设置引起。
- Vite 默认代理到后端 8080，可用 `WEBUI_BACKEND_URL` 指定目标；先检查浏览器 Origin、代理目标与后端 CORS。
- Vite 在 5050 被占用时可能顺延端口，以终端打印的地址为准。使用其他端口前确认它在 CORS 白名单中；后端 8080 被占用时先确认占用进程，避免启动错项目。
- Socket.IO 使用自身的 WebSocket 重连，不人为降级到 polling。更改 CORS 后需重启后端。
- 默认 SQLite 为 `backend/data/webui.db`；登录密钥为 `backend/.webui_secret_key`，不要随意更换或提交。
- 普通功能开发使用以上本地入口。生产实例记录见 [部署文档](../../deploy/README.md)，部署工具在仓库 `deploy/`，只有明确的部署任务才读取并执行。
