# 压测工具

仅在明确的压测任务中使用。以下命令均从仓库根目录执行。默认目标是本地后端 `http://localhost:8080`；需要测试其他环境时显式指定目标。

| 文件                 | 用途                                                 |
| -------------------- | ---------------------------------------------------- |
| `mock_llm.py`        | 标准库实现的 OpenAI 兼容模拟端点，按固定节奏输出 SSE |
| `loadtest.js`        | k6 的聊天、Socket.IO 长连接和页面接口并发负载        |
| `diagnosis_burst.py` | 调用现有诊断提示词并检验真实模型响应能否解析         |

## 模拟模型服务

在单独的终端前台运行：

```powershell
backend\.venv\Scripts\python.exe scripts\loadtest\mock_llm.py
```

只监听 `127.0.0.1:9099`，模型 id 默认为 `loadtest-mock`。参数通过环境变量设置：

| 变量            | 默认值             |
| --------------- | ------------------ |
| `MOCK_PORT`     | `9099`             |
| `MOCK_MODEL_ID` | `loadtest-mock`    |
| `MOCK_TOKENS`   | `400`              |
| `MOCK_TPS`      | `25`               |
| `MOCK_TTFT_MS`  | `600`              |
| `MOCK_API_KEY`  | 空，默认不校验认证 |

在被测后端管理员面板新增 `http://127.0.0.1:9099/v1` 连接，按 `MOCK_API_KEY` 配置认证，并把模型访问权限授予测试账号。连接地址是后端可访问的地址；远程测试时模拟服务也应运行在后端可访问的环境。

## k6 并发负载

安装 k6，使用独立测试账号。在本机设置环境变量，不把密码写入脚本、文档或提交：

```powershell
$env:BASE_URL = 'http://localhost:8080'
$env:EMAILS = 'test1@example.com,test2@example.com'
$env:PASSWORD = '<测试账号密码>'
$env:MODEL = 'loadtest-mock'
$env:CHAT_VUS = '5'
$env:SOCKET_VUS = '20'
$env:BROWSE_RPS = '3'
$env:DURATION = '2m'
k6 run scripts\loadtest\loadtest.js
```

脚本会登录、创建对话并写入消息，不应将它当成只读健康检查。默认并发值为聊天 10、Socket.IO 40、页面接口每秒 3 次，时长 3 分钟。

当前带 `chat_id` 的聊天请求由后端处理模型流、落库并经 Socket.IO 推送，HTTP 成功响应可能为 `null`。脚本用 HTTP 200 和耗时大于 3 秒判断模拟模型请求通过；这是压测脚本的判据，不是完整的产品正确性验证。`chat_stream_duration` 测量整次请求耗时，不能当成首 token 延迟。

## 真实模型诊断并发

此工具调用真实模型，会消耗模型额度。先启动本地后端，确认管理员账号和模型权限，再按需要选择并发量和模型：

```powershell
$env:WEBUI_SECRET_KEY = (Get-Content backend\.webui_secret_key -Raw).Trim()
$env:RW_ADMIN_EMAIL = '<测试管理员邮箱>'
$env:RW_ADMIN_PASSWORD = '<测试管理员密码>'
backend\.venv\Scripts\python.exe scripts\loadtest\diagnosis_burst.py --n 5 --model '<可访问的模型ID>' --base http://localhost:8080
```

该脚本使用固定文献综述样稿和评分维度，通过现有后端服务生成诊断提示词。统计响应成功数、可解析数及耗时；它不验证学生身份、初稿确认或完整提交流程。

## 结束测试

用 Ctrl+C 停止模拟服务，删除临时模型连接和访问授权，按被测环境的数据管理要求处理测试对话。不要把通用工具的清理说明理解为删除生产数据的授权。

旧实例测试条件和结果见 [历史压测记录](../../docs/archive/压测记录.md)，服务器运维记录见 [部署文档](../../docs/deployment/README.md)。
