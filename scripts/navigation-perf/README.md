# 学生作业导航验收

实现范围、目标、结果与发布边界只在 [原实施方案](../../docs/development/作业访问速度优化实施方案.md) 维护。

## 生产前端、合成接口

从仓库根目录执行：

```powershell
$env:NODE_OPTIONS = '--max-old-space-size=8192'
npm.cmd run build
backend/.venv/Scripts/python.exe scripts/navigation-perf/server.py
```

仅监听 `127.0.0.1:5099`，不访问数据库、真实账号或模型。`NAVIGATION_PERF_BUILD` 可指向另存的基线构建；未设置时使用当前 `build/`。服务端默认每个 API 增加 400 ms 延迟并启用 gzip。不要部署这个测试服务。

在独立 Tabbit 标签页打开本地址，设置该隔离 Origin 的 `localStorage.token = 'isolated-test'`、`localStorage.locale = 'zh-CN'` 后重新打开。测试前将标签页保持前台可见。使用 `/__fixture` 选择测试条件：

```powershell
Invoke-RestMethod http://127.0.0.1:5099/__fixture -Method Post -ContentType application/json -Body '{"aggregate":true}'
```

旧前端基线用 `aggregate:false`，新前端用 `aggregate:true`。控制项还包括 `tags_delay_ms`、`delays`（按 API 路径指定延迟）、`save_fail`、`hidden`、`denied`、`extra:["illustrated","returned"]`、`full_context`（每条 AI 历史消息携带合成全文快照）、模拟 `event`／`notification` 与 `reconnect`。

`measure.js` 在 Tabbit CLI 的 `nodejs` 环境运行，复用已取得的本地标签页；默认 ordinary、20 次，可在程序前设置 `globalThis.perfScenario`、`globalThis.perfPhase` 和 `globalThis.perfIterations`。实际点击监听器记录开始时间；检查稿件、正确可编辑性和最后一条历史消息后再记录绘制完成，不用自动化命令耗时。返回每次资源时间、gzip／解压大小和错误。资源结果须用 CLI 的 `resource` 读取完整 JSON；保存到方案的 assets 目录，不保存 Cookie 或认证头。

空稿、普通稿、长稿分别采集至少 20 次。页面保持前台，采样时不同时运行构建、测试或其他 CPU 密集任务。冷启动另记文档导航时间，不和应用内点击结果混算。合成内容的压缩率及 API 延迟不是生产性能证明。

`regressions.js` 检查乱序、慢标签、实时消息与保存失败，第一阶段返回 `needsNativeReload`。此时使用浏览器重新加载并确认原生“重新加载此网站？”提示，再以 `globalThis.regressionPhase='after-reload'` 运行第二阶段。Tabbit 的原生离开确认可能不受 Playwright `dialog` 控制，不能把自动化超时当成产品失败，也不能绕过备份核对。脚本只清理 `perf-student` 的合成备份。`cold.js` 使用临时测试链接的实际点击、跨文档时间戳和关闭浏览器缓存，单独记录三次整页冷启动。

## 真实后端、隔离数据库

```powershell
backend/.venv/Scripts/python.exe scripts/navigation-perf/backend_profile.py
```

脚本在导入应用前设置临时 `DATA_DIR`、临时 SQLite URL 和仅供测试的密钥，并移除进程内 `TEST_DATABASE_URL`；复用仓库 Alembic 测试 fixture 和模拟模型。对约 2000／20000／100000 字、10／50／200 条合成消息，各测 20 次 workspace GET 和 chat GET，记录总耗时、SQL 次数与耗时、JSON 和 gzip 大小。AI 消息带合成稿件快照；除初始化的一次模拟初读外，不触发模型。结果是 `backend-profile.json`。

该脚本是单请求诊断，不是压测。权限、保存、提交和冻结证据的回归仍须运行方案列出的 pytest 与前端测试。
