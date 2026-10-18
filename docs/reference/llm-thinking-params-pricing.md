# 国内大模型「思考/推理」API 参数与价格参考（RightWrite）

- 整理日期：2026-10-18（北京时间）。只用了各家官方文档，每节都附了 URL。
- 用途：给 RightWrite（Open WebUI 分支）的「统一思考档位」（off / low / medium / high / model-default）做各厂商的参数映射；后续 CC 实测思考参数时也拿它当基准。
- 约定：价格单位是 **元 / 百万 tokens（CNY）**，取中国内地（北京）区域的在线推理标准价。不是从官方页面原文拿到的数字都标了 **⚠️未核实**。官方页面大多没写更新日期，凡是没写的，都按「抓取于 2026-10-18」处理。
- 各家模型迭代很快（本文写作时已有 Kimi K3、DeepSeek V4.1 Flash、GLM-5.3、Doubao Seed 2.1、Qwen3.8）。**上线前一定要按本文的「待实测清单」用真实 Key 再验证一遍。**

---

## 0. 总览对比表

| 厂商 | 模型 ID（推荐/已接入） | 思考控制字段 | 默认 | 是否可关 | 是否分档 | 输入 / 缓存命中 / 输出（元/M） |
|---|---|---|---|---|---|---|
| DeepSeek | `deepseek-flash`（V4.1-Flash-1017） | `thinking:{type:enabled\|disabled}` + `reasoning_effort: low\|high\|max` | 开，effort=high | ✅ | ✅（low/high/max，medium→high） | 高峰 2 / 0.04 / 8；空闲 1 / 0.02 / 4 |
| DeepSeek | `deepseek-v4-pro`（V4-Pro-0813） | 同上 | 开，high | ✅ | ✅ | 高峰 9 / 0.30 / 27；空闲 4.5 / 0.15 / 13.5 |
| Kimi | `kimi-k2.6` | `thinking:{type:enabled\|disabled, keep:null\|"all"}` | 开 | ✅ | ❌（只能开/关） | 6.5 / 1.10 / 27 |
| Kimi | `kimi-k3` | 顶层 `reasoning_effort: low\|high\|max`（不能传 `thinking`） | 始终思考，max | ❌ | ✅（3 档） | 20 / 2 / 100（另有缓存写入费） |
| Kimi | `kimi-k2.7-code`(-highspeed) | 不传；只接受 `{type:enabled,keep:all}` | 始终思考 | ❌ | ❌ | 6.5 / 1.30 / 27（highspeed 13 / 2.6 / 54） |
| 智谱 | `glm-5.3` / `glm-5.3-flash` / `glm-5.3-flashx` | `thinking:{type:enabled}`（传 disabled 报错）+ `reasoning_effort: low\|high\|max` | 始终思考，max | ❌ | ✅（3 档） | 5.3：8 / 2 / 28；Flash：0.8 / 0.23 / 2.8；FlashX：2 / 0.57 / 7 |
| 智谱 | `glm-5.2` | `thinking.type enabled\|disabled` + `reasoning_effort`（none/minimal=关；low/medium→high；xhigh→max） | 开，max | ✅ | 部分（实际只有关/high/max） | 8 / 2 / 28 |
| 智谱 | `glm-5.1` / `glm-5` / `glm-4.7` / `glm-4.6` / `glm-4.5*` | `thinking.type enabled\|disabled` | 开（多数模型自己决定是否思考） | ✅ | ❌ | 见 §3 价格表（按输入长度分段） |
| 智谱（视觉） | `glm-4.6v` / `glm-5v-turbo` / `glm-5.3-flash` | 同上 | 开 | 4.6V/5V 可关；5.3-Flash 不可关 | 5.3-Flash 可分档 | 4.6V：1 / 0.2 / 3（≤32K） |
| 豆包（方舟） | `doubao-seed-2-1-pro-260915` / `-lite-` / `-turbo-` / `doubao-seed-evolving` | `thinking:{type:enabled\|disabled}` + `reasoning_effort: minimal\|low\|medium\|high` | 开，high | ✅ | ✅（minimal=关，3 档） | 2.1-pro 6 / 1.2 / 30；2.1-lite 0.8 / 0.16 / 2.7；2.1-turbo 3 / 0.6 / 15 |
| 豆包（方舟） | `doubao-seed-2-0-*`（lite/mini/pro） | 同上 | 开，medium | ✅ | ✅ | 2.0-lite 0.6 / 0.12 / 3.6（≤32K） |
| 千问（百炼） | `qwen3.8-max` / `qwen3.8-flash` / `qwen3.7-plus` / `qwen3.7-flash` | `enable_thinking: true\|false` + `thinking_budget: <int tokens>` | 开 | ✅（混合思考模型） | 用 token 预算（不是档位） | 3.8-max 12 / — / 36；3.8-flash 0.8 / — / 2.7；3.7-flash 0.2 / — / 0.8（≤32K） |
| 千问（百炼） | `qwen-plus` / `qwen-flash`（Qwen3 一代） | 同上 | **关** | ✅ | 预算 | qwen-plus 0.8 / — / 非思考 2、思考 8；qwen-flash 0.15 / — / 1.5 |

> 「缓存命中」那一列写 — 的，表示百炼价格页上这些模型只写了「上下文缓存享有折扣」，没有单独列出命中单价。价格页只举了一个例子：显式缓存创建按标准输入价的 125% 计，命中按 10% 计。⚠️ 隐式缓存的比例和各模型的具体命中价都没有核实。

---

## 1. DeepSeek

官方文档：
- 模型与价格（中文，人民币）：https://api-docs.deepseek.com/zh-cn/quick_start/pricing （页面没写日期）
- 思考模式：https://api-docs.deepseek.com/guides/thinking_mode
- 图像理解：https://api-docs.deepseek.com/zh-cn/guides/vision
- 限速：https://api-docs.deepseek.com/zh-cn/quick_start/rate_limit

### 1.1 Base URL
- OpenAI 兼容：`https://api.deepseek.com`（也可以写 `https://api.deepseek.com/v1`，属 OpenAI SDK 惯例）。
- Anthropic 兼容：`https://api.deepseek.com/anthropic`
- 只有一个全球端点，官方没有单独的国际站域名。

### 1.2 模型
- `deepseek-flash` → DeepSeek-V4.1-Flash-1017。上下文 1M，最大输出 384K，**支持图像输入**。
  - 旧名 `deepseek-v4-flash`、`deepseek-v4-flash-vision-exp` 仍然能调，但实际由 V4.1-Flash 提供服务，按 Flash 价计费。
- `deepseek-v4-pro` → DeepSeek-V4-Pro-0813。**不支持**图像。
- 老名字 `deepseek-chat` / `deepseek-reasoner` 已经不在当前官方价格页上了。⚠️ 现在调用会怎样（是否还兼容）没有核实。后台如果还配着这两个名字，建议改成 `deepseek-flash`。

### 1.3 思考控制（OpenAI 格式）
| 作用 | 字段 |
|---|---|
| 开关 | `{"thinking": {"type": "enabled" \| "disabled"}}`（OpenAI SDK 要放进 `extra_body`；直接发 HTTP 时放顶层） |
| 力度 | 顶层 `"reasoning_effort": "low" \| "high" \| "max"` |
| Responses API | `{"reasoning": {"effort": "none\|low\|high\|max"}}`，`none` 表示关闭 |

- 默认：**开启思考，effort = high**。
- effort 的映射（官方表）：minimal→low，low→low，**medium→high**，high→high，xhigh→high，max→max，ultra→max。
- 思考模式下 `temperature` / `presence_penalty` / `frequency_penalty` 不生效，但传了也不报错。`deepseek-flash` 的 `top_p` 只在思考模式下生效（范围 0.95–1.0）。

OFF：
```json
{"model":"deepseek-flash","messages":[{"role":"user","content":"你好"}],
 "thinking":{"type":"disabled"}}
```
ON（低档）：
```json
{"model":"deepseek-flash","messages":[{"role":"user","content":"你好"}],
 "thinking":{"type":"enabled"},"reasoning_effort":"low"}
```

### 1.4 思考内容返回与计费
- 思考内容在 `choices[0].message.reasoning_content` 里（流式在 `delta.reasoning_content`），和 `content` 同级。
- 多轮对话：如果请求**没带** `tools`，历史 `reasoning_content` 传回去也会被忽略；如果**带了** `tools`，必须把历史 `reasoning_content` 全部传回，否则返回 400。
- 计费：官方写的是「按输入、输出 token 总数计费」。思考 token 是模型输出，按输出价计（官方页面没有单独写一句「思考按输出计」，但定价上只有输出这一档）。

### 1.5 视觉（仅 `deepseek-flash`）
- 标准 OpenAI `content` 数组，`{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}`，也支持公网 URL 和 Files API 的 `file_id`。
- 支持 JPEG / PNG / GIF / WebP。请求体 ≤ 48 MiB，单张 ≤ 32 MiB，单边 ≤ 8192 px。可选 `detail: low|high|original|auto`。
- 每张图会先缩放到约 1300×1300 的总像素，**每张最多 1024 tokens**。RightWrite 现在上传前缩到 1600px，跟这个尺度是匹配的。
- 图片只能放在 `user` 消息里。

### 1.6 价格（元 / M tokens）
| 模型 | 时段 | 输入（缓存命中） | 输入（未命中） | 输出 |
|---|---|---|---|---|
| deepseek-flash | 空闲 | 0.02 | 1 | 4 |
| deepseek-flash | 高峰 | 0.04 | 2 | 8 |
| deepseek-v4-pro | 空闲 | 0.15 | 4.5 | 13.5 |
| deepseek-v4-pro | 高峰 | 0.30 | 9.0 | 27.0 |

- 高峰时段：**北京时间周一到周五 9:00–12:00、14:00–18:00**（不含法定节假日）。其他时间都算空闲，空闲价是高峰价的一半。注意：**这正好和学生上课、写作业的时间重叠**。
- 思考和非思考价格一样，不按上下文长度分档。

### 1.7 限速
- 按账号算并发：`deepseek-flash` 2500，`deepseek-v4-pro` 500。超出返回 HTTP 429。可以传 `user_id`（放在 `extra_body`）做用户隔离。
- 请求还没开始推理时，服务器会持续发空行或 `: keep-alive` 保活；10 分钟内仍未开始推理就断开连接。

---

## 2. Moonshot Kimi

官方文档：
- API 概述（Base URL）：https://platform.kimi.com/docs/api/overview
- 模型参数参考：https://platform.kimi.com/docs/api/models-overview
- 思考模型：https://platform.kimi.com/docs/guide/use-thinking-models
- 推理强度：https://platform.kimi.ai/docs/guide/use-reasoning-effort
- 视觉：https://platform.kimi.com/docs/guide/use-kimi-vision-model
- 价格：https://platform.kimi.com/docs/pricing/chat
- 限速：https://platform.kimi.com/docs/pricing/limits

### 2.1 Base URL
- 中国站：`https://api.moonshot.cn/v1`（Anthropic 兼容：`https://api.moonshot.cn/anthropic`）
- 国际站：`https://api.moonshot.ai/v1`（platform.kimi.ai 文档的示例用的是这个）。⚠️ 国际站的价格没有核实。

### 2.2 模型与思考控制
| 模型 | 字段 | 默认 | 能否关闭 |
|---|---|---|---|
| `kimi-k2.6` | `thinking: {"type":"enabled"\|"disabled"}`，可选 `"keep":"all"`（保留历史思考） | enabled | ✅ |
| `kimi-k2.7-code` / `kimi-k2.7-code-highspeed` | 不用传；显式传只能是 `{"type":"enabled","keep":"all"}`，传 disabled 会报错 | 始终思考 | ❌ |
| `kimi-k3` | **不能传 `thinking`**，改用顶层 `reasoning_effort: "low"\|"high"\|"max"` | 始终思考，`max` | ❌ |

- ⚠️ **重要的坑**：Kimi 的 `temperature`、`top_p`、`n`、`presence_penalty`、`frequency_penalty` 都是**固定值，传其他值会报错**（K2.6：思考时 temperature=1.0，不思考时 0.6；K3 / K2.7 固定 1.0）。如果 RightWrite 或 Open WebUI 的模型参数里给 Kimi 配了 temperature，请求会失败，必须保证不发这些字段。
- K3 中途换 effort 会让前缀缓存失效。官方建议一次会话里固定一个档位。
- K2.6 / K3 多轮对话时，要把完整的 assistant message（包括 `reasoning_content`）原样传回去。

OFF（只有 k2.6 能关）：
```json
{"model":"kimi-k2.6","messages":[{"role":"user","content":"你好"}],
 "thinking":{"type":"disabled"}}
```
ON：
```json
{"model":"kimi-k2.6","messages":[{"role":"user","content":"你好"}],
 "thinking":{"type":"enabled"}}
```
K3 低档：
```json
{"model":"kimi-k3","messages":[{"role":"user","content":"你好"}],"reasoning_effort":"low"}
```

### 2.3 思考内容返回与计费
- `choices[0].message.reasoning_content`（只在开启思考时返回）。
- 思考 token 计入 `max_tokens`，官方建议 `max_tokens >= 16000`。
- 官方 FAQ 写明：`reasoning_content` 会计入输入/输出 token 消耗。开启 Preserved Thinking 后，历史思考内容会作为输入持续计费。

### 2.4 视觉
- `kimi-k3`、`kimi-k2.6`、`kimi-k2.7-code`(-highspeed) 都支持图片（也支持视频）。
- 格式：OpenAI `image_url`。**只支持 base64 data URL 或文件上传后的 `ms://<file-id>`，不支持公网图片 URL。**
- 支持 jpeg / png / gif / webp / bmp / heic / heif（GIF、WebP 动图会按视频解码计费）。图片数量不限，但请求体不能超过 100MB。`content` 必须是 JSON 数组，不能是序列化后的字符串。

### 2.5 价格（元 / M tokens，中国站）
| 模型 | 缓存命中 | 输入（未命中） | 输出 | 其他 |
|---|---|---|---|---|
| kimi-k3 | 2.00 | 20.00 | 100.00 | 缓存写入 TTL5min 20、TTL1h 40；1M 上下文 |
| kimi-k2.7-code | 1.30 | 6.50 | 27.00 | 256K |
| kimi-k2.7-code-highspeed | 2.60 | 13.00 | 54.00 | 256K |
| kimi-k2.6 | 1.10 | 6.50 | 27.00 | 256K |

- 思考和非思考价格一样，不按上下文长度分档。

### 2.6 限速（按累计充值分级）
| 等级 | 累计充值 | 并发 | RPM | TPM |
|---|---|---|---|---|
| Tier0 | ¥0 | 1 | 3 | 500K（TPD 1.5M） |
| Tier1 | ¥50 | 15 | 100 | 2M |
| Tier2 | ¥100 | 40 | 100 | 3M |
| Tier3 | ¥500 | 50 | 200 | 3M |
| Tier4 | ¥5,000 | 60 | 200 | 4M |
| Tier5 | ¥20,000 | 100 | 300 | 5M |

> ⚠️ RightWrite 识图会 8 路同时请求。如果 Kimi 账号还在 Tier0（并发 1、RPM 3），一定会被 429 限流。用 Kimi 识图的话，账号至少要到 Tier1。代金券不计入累计充值。

---

## 3. 智谱 GLM（bigmodel.cn / Z.ai）

官方文档：
- 深度思考：https://docs.bigmodel.cn/cn/guide/capabilities/thinking （国际版：https://docs.z.ai/guides/capabilities/thinking）
- GLM-5.3：https://docs.bigmodel.cn/cn/guide/models/text/glm-5.3
- GLM-5.3-Flash/FlashX（原生多模态）：https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5.3-flash
- 对话补全 API：https://docs.bigmodel.cn/api-reference/模型-api/对话补全
- 价格：https://docs.bigmodel.cn/cn/guide/start/pricing
- 限速：https://docs.bigmodel.cn/cn/api/rate-limit

### 3.1 Base URL
- 中国站：`https://open.bigmodel.cn/api/paas/v4`（chat 接口为 `/chat/completions`）
- 国际站（Z.ai）：`https://api.z.ai/api/paas/v4`。⚠️ 国际站按美元计价，本文没有收录。

### 3.2 思考控制
- `thinking.type`：`enabled`（默认）| `disabled`。GLM-4.5 及以上支持。
  - 选 `enabled` 时，「是否真的思考」分两类：
    - **模型自己判断**：GLM-5.2、5.1、5、5-Turbo、5V-Turbo、4.6、4.6V、4.5
    - **强制思考**：GLM-5.3、5.3-Flash、4.7、4.5V
  - **GLM-5.3 / 5.3-Flash / 5.3-FlashX 不支持关闭**，传 `disabled` 会报错。
- `reasoning_effort`（只有 GLM-5.2 及以上支持，开启思考时才生效，默认 `max`）：
  - GLM-5.3 系列：只接受 `low` / `high` / `max`，其他值报错。
  - GLM-5.2：接受 max、xhigh、high、medium、low、minimal、none。其中 **none/minimal 等于放弃思考**，low/medium 映射成 high，xhigh 映射成 max。
- `thinking.clear_thinking: false` 用于保留历史思考（Preserved Thinking），GLM-5.3-Flash 推荐这样设。

OFF（GLM-5.2 及以下）：
```json
{"model":"glm-5.2","messages":[{"role":"user","content":"你好"}],
 "thinking":{"type":"disabled"}}
```
ON：
```json
{"model":"glm-5.2","messages":[{"role":"user","content":"你好"}],
 "thinking":{"type":"enabled"},"reasoning_effort":"high"}
```
GLM-5.3 系列最低档（只能用这个代替「关」）：
```json
{"model":"glm-5.3-flash","messages":[{"role":"user","content":"你好"}],
 "thinking":{"type":"enabled"},"reasoning_effort":"low"}
```

### 3.3 思考内容返回与计费
- `choices[0].message.reasoning_content`（流式在 `delta.reasoning_content`）。
- 官方只写了「思考过程会消耗额外的 Token」。⚠️ 没找到「思考按输出价计费」的明文，按行业惯例和价格表结构推断是按输出计。

### 3.4 视觉
- `glm-5.3-flash` / `glm-5.3-flashx`：原生多模态，支持图片、视频、文件。`content[]` 里放 `{"type":"image_url","image_url":{"url": "<URL 或 base64 data URL>"}}`，多张图就放多个。
- 视觉模型：`glm-5v-turbo`、`glm-4.6v`、`glm-4.6v-flashx`、`glm-4.6v-flash`（免费）、`glm-4.5v`；另有专门做 OCR 的 `glm-ocr`（0.2/0.2，32K）。
- `glm-5.3`（非 Flash）**只支持文本**。

### 3.5 价格（元 / M tokens，中国站，缓存存储目前限时免费）
| 模型 | 条件 | 输入 | 缓存命中 | 输出 |
|---|---|---|---|---|
| GLM-5.3 | 1M | 8 | 2 | 28 |
| GLM-5.3-Flash | 1M | 0.8 | 0.23 | 2.8 |
| GLM-5.3-FlashX | 1M | 2 | 0.57 | 7 |
| GLM-5.2 | 1M | 8 | 2 | 28 |
| GLM-5.1 | 输入 <32K / ≥32K | 6 / 8 | 1.3 / 2 | 24 / 28 |
| GLM-5-Turbo | <32K / ≥32K | 5 / 7 | 1.2 / 1.8 | 22 / 26 |
| GLM-5 | <32K / ≥32K | 4 / 6 | 1 / 1.5 | 18 / 22 |
| GLM-4.7 | 输入<32K 且输出<0.2K / 输入<32K 且输出≥0.2K / 输入 32–200K | 2 / 3 / 4 | 0.4 / 0.6 / 0.8 | 8 / 14 / 16 |
| GLM-4.5-Air | 同上三档（最后一档 32–128K） | 0.8 / 0.8 / 1.2 | 0.16 / 0.16 / 0.24 | 2 / 6 / 8 |
| GLM-4.7-FlashX | 200K | 0.5 | 0.1 | 3 |
| GLM-4.7-Flash | 200K | 免费 | 免费 | 免费 |
| GLM-5V-Turbo | <32K / ≥32K | 5 / 7 | 1.2 / 1.8 | 22 / 26 |
| GLM-4.6V | <32K / 32–128K | 1 / 2 | 0.2 / 0.4 | 3 / 6 |
| GLM-4.6V-FlashX | <32K / 32–128K | 0.15 / 0.3 | 0.03 | 1.5 / 3 |
| GLM-4.6V-Flash | — | 免费 | 免费 | 免费 |
| GLM-4.5V | <32K / 32–64K | 2 / 4 | 0.4 / 0.8 | 6 / 12 |
| GLM-OCR | 32K | 0.2 | 不支持 | 0.2 |

- 思考和非思考价格一样。Batch API 打 5 折。
- ⚠️ GLM-5.3-Flash 官方介绍页写着「定价为 GLM-5.3 的 1/10，**限时折扣内为 1/20**」，但价格表列的是 0.8 / 2.8（也就是 1/10）。折扣期内实际扣费是不是更低，需要看账单确认。
- ⚠️ 老型号 GLM-4.5 / GLM-4.6 的价格没出现在当前价格页上，没有核实。

### 3.6 限速
- 按「用户权益等级 × 模型」限制**并发数**，具体额度要在控制台 https://bigmodel.cn/usercenter/proj-mgmt/rate-limits 查看，文档没有固定数字。
- 错误码 `1302` 是账户超过限速，`1305` 是平台过载。两种都适合用 RightWrite 现在的退避重试处理。

---

## 4. 字节豆包（火山方舟 Ark）

官方文档：
- 深度思考（Chat API）：https://ark.volcengine.com/region:cn-beijing/docs/deep-thinking
- 深度思考（Responses API）：https://ark.volcengine.com/region:cn-beijing/docs/responses-api-deep-thinking
- 模型参数支持表：https://ark.volcengine.com/region:cn-beijing/docs/model-parameter-support
- 模型列表（含 RPM/TPM）：https://ark.volcengine.com/region:cn-beijing/docs/model-list
- 图片理解：https://ark.volcengine.com/region:cn-beijing/docs/image-understanding
- 价格：https://ark.volcengine.com/region:cn-beijing/docs/model-pricing

### 4.1 Base URL
- 北京：`https://ark.cn-beijing.volces.com/api/v3`（OpenAI SDK 直接可用，chat 接口为 `/chat/completions`）
- ⚠️ 国际版（BytePlus ModelArk）的域名和价格没有核实。
- `model` 字段填**带日期的模型 ID**（例如 `doubao-seed-2-1-pro-260915`）或推理接入点 ID（`ep-...`）。模型要先在控制台开通。

### 4.2 思考控制（Chat API）
- `thinking: {"type": "enabled" | "disabled" | "auto"}`。文档里列了 auto，但当前所有 doubao-seed 模型在官方支持表里**只写了 enabled（默认）/ disabled**，没有 auto。⚠️ auto 实际会不会报错没有核实。
- `reasoning_effort`（Chat API）/ `reasoning.effort`（Responses API）：七个值 none / minimal / low / medium / high / xhigh / max 都能接受，各模型会映射：
  - **doubao-seed-2.1 系列 / evolving**：默认 `high`；`minimal`=关闭思考，`none`→minimal，xhigh/max→high。
  - **doubao-seed-2.0 系列 / character**：默认 `medium`；映射规则同上。
  - 方舟上托管的 `glm-5-3-flash-260828`：不能关，none/minimal/low→low，medium/high→high，xhigh/max→max。
  - 方舟上的 `deepseek-v4-1-flash-260910`：`none`=关闭，minimal→low，medium/xhigh→high。
- 组合规则：`thinking.type=disabled` 时，`reasoning_effort` 只能填 `minimal`，填别的会报错。
- 官方提醒：深度思考耗时长，非流式调用建议把超时设到 1800 秒以上，或者直接用流式。

OFF：
```json
{"model":"doubao-seed-2-1-pro-260915","messages":[{"role":"user","content":"你好"}],
 "thinking":{"type":"disabled"}}
```
ON（低档）：
```json
{"model":"doubao-seed-2-1-pro-260915","messages":[{"role":"user","content":"你好"}],
 "thinking":{"type":"enabled"},"reasoning_effort":"low"}
```

### 4.3 思考内容返回与计费
- `choices[0].message.reasoning_content`。
- seed-2.1 系列、evolving、seed-2.0-lite-260428 **默认开启 thinking summary**：`reasoning_content` 里是**思考摘要**，原始思考加密后放在 `encrypted_content`。多轮工具调用时要原样传回 `encrypted_content`。
- 官方写明：`usage.completion_tokens_details.reasoning_tokens` 统计的是**原始思考**的 token，**计费也按原始思考 token 算**（按输出价）。所以界面上看到的摘要很短，账单可能明显更多。

### 4.4 视觉
- 模型列表里，doubao-seed-2.1 / 2.0 系列（pro/lite/mini/turbo/evolving）都标了「多模态理解」，也就是都支持图片。
- 格式：OpenAI `{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}`，也支持公网 URL 和 Files API 的 `file_id`。
- base64 单张小于 10 MB，请求体不超过 64 MB；支持 PNG / JPEG / WEBP 等。

### 4.5 价格（元 / M tokens，在线推理常规档，北京）
| 模型 | 输入长度条件 | 输入 | 缓存命中 | 输出 |
|---|---|---|---|---|
| doubao-seed-evolving | [0, 1024K] | 6.00 | 1.20 | 30.00 |
| doubao-seed-2.1-pro | [0, 1024K] | 6.00 | 1.20 | 30.00 |
| doubao-seed-2.1-lite | [0, 1024K] | 0.80 | 0.16 | 2.70 |
| doubao-seed-2.1-turbo | [0, 256K] | 3.00 | 0.60 | 15.00 |
| doubao-seed-2.0-pro | [0,32K] / (32,128K] / (128,256K] | 3.2 / 4.8 / 9.6 | 0.64 / 0.96 / 1.92 | 16 / 24 / 48 |
| doubao-seed-2.0-lite | 同上 | 0.6 / 0.9 / 1.8 | 0.12 / 0.18 / 0.36 | 3.6 / 5.4 / 10.8 |
| doubao-seed-2.0-mini | 同上 | 0.2 / 0.4 / 0.8 | 0.04 / 0.08 / 0.16 | 2.0 / 4.0 / 8.0 |

- 缓存存储另收 0.017 元 / M tokens / 小时。思考和非思考同价。
- 另有「低延迟」档（`service_tier=fast`，更贵）和「低优 flex」档（约 5 折）。批量推理价格更低。详见价格页。

### 4.6 限速（模型列表标注的「最大」值）
- doubao-seed-2.1-pro / turbo / evolving：RPM 500，TPM 1M
- doubao-seed-2.1-lite、2.0-lite / mini：RPM 30000，TPM 5M
- 账号实际配额以控制台为准。

---

## 5. 阿里千问（百炼 Model Studio / DashScope）

官方文档：
- 深度思考：https://help.aliyun.com/zh/model-studio/deep-thinking
- Base URL 总览（页面写着「更新时间 Oct 11, 2026」）：https://www.alibabacloud.com/help/zh/model-studio/base-url
- 地域与域名：https://help.aliyun.com/zh/model-studio/regions
- 模型调用价格：https://help.aliyun.com/zh/model-studio/model-pricing
- 视觉理解：https://help.aliyun.com/zh/model-studio/vision
- 错误码：https://help.aliyun.com/zh/model-studio/error-code

### 5.1 Base URL（OpenAI 兼容）
| 地域 | 业务空间专属域名（推荐） | DashScope 共享域名（旧） |
|---|---|---|
| 北京 | `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 新加坡（国际） | `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |
| 中国香港 | `https://{WorkspaceId}.cn-hongkong.maas.aliyuncs.com/compatible-mode/v1` | `https://cn-hongkong.dashscope.aliyuncs.com/compatible-mode/v1` |

- **API Key 按地域绑定**，跨地域调用会返回 401 `invalid_api_key`。
- 官方说明：DashScope 共享域名「自 2026 年 9 月 30 日起不再支持新特性」，请求超时 600 秒；专属域名超时 3600 秒。**新接入建议直接用专属域名**。

### 5.2 思考控制
- `enable_thinking: true | false`（不是 OpenAI 标准参数：Python SDK 放在 `extra_body`，HTTP 和 Node 放顶层）。
- `thinking_budget: <正整数>`：限制思考 token 数，超出后立刻输出回答。默认值是模型的最大思维链长度。适用于 Qwen3.x、Qwen3-VL，以及百炼托管的 GLM、Kimi（kimi-k3 除外）。
- `reasoning_effort`：目前只写了 `qwen3.8-omni-flash` 支持。Responses API 用 `reasoning.effort`。
- `preserve_thinking: true`：保留历史思考（qwen3.8-max、qwen3.7-max 等支持），开启后历史思考按输入计费。
- 默认行为（官方「支持的模型」表）：
  - **混合思考，默认开启**：qwen3.8-max、qwen3.8-flash、qwen3.8-27b、qwen3.7-max、qwen3.7-plus、qwen3.7-flash、qwen3.6-plus/flash、qwen3.5-plus/flash
  - **混合思考，默认关闭**：`qwen-plus`、`qwen-flash`（Qwen3 一代及之后的快照）
  - **只有思考模式**：qwen3.8-2.4t-a95b、qwen3.7-max-preview、qwen3.7-max-2026-05-17
- ⚠️ 官方文档前后不一致：错误码页说「部分模型（如 `qwen3.7-plus`）不能把 `enable_thinking` 设为 false」，但深度思考页把 qwen3.7-plus 列为混合思考（可关），常见问题里也教了怎么关。需要实测。
- 其他限制：开启思考时**不支持 JSON mode / 结构化输出**；部分开源版（如 qwen3.5-27b）只支持流式调用。

OFF：
```json
{"model":"qwen3.8-flash","messages":[{"role":"user","content":"你好"}],
 "enable_thinking":false}
```
ON（限制预算）：
```json
{"model":"qwen3.8-flash","messages":[{"role":"user","content":"你好"}],
 "enable_thinking":true,"thinking_budget":2048,"stream":true}
```

### 5.3 思考内容返回与计费
- `reasoning_content`（流式在 `delta.reasoning_content`），用量在 `usage.completion_tokens_details.reasoning_tokens`。
- 官方计费说明：**思考内容按输出 Token 计费**。有些混合模型思考和非思考的输出价不同：只要输出了思考过程，**全部输出 token 都按思考价计**；如果开了思考但模型实际没输出思考，就按非思考价计。

### 5.4 视觉
- `qwen3.8-max`、`qwen3.8-max-0902`、`qwen3.8-flash` 原生支持图片和视频（1M 上下文，单图最高约 1600 万像素）。⚠️ 这一条来自搜索结果对官方视觉页的摘要，没有逐字核对。
- 专门的视觉 / OCR 模型：`qwen3-vl-plus`（混合思考）、`qwen-vl-ocr`（0.3 / 0.5）、`qwen3.5-ocr`（0.5 / 2）。
- 格式：OpenAI `{"type":"image_url","image_url":{"url":"<URL 或 data URL>"}}`。

### 5.5 价格（元 / M tokens，华北 2 北京，原价；输出价已包含思维链）
| 模型 | 单次输入长度 | 输入 | 输出（非思考） | 输出（思考） |
|---|---|---|---|---|
| qwen3.8-max | ≤1M | 12 | 36 | 36 |
| qwen3.8-flash | ≤1M | 0.8 | 2.7 | 2.7 |
| qwen3.7-max | ≤1M | 12 | 36 | 36 |
| qwen3.7-plus | ≤256K / 256K–1M | 2 / 6 | 8 / 24 | 8 / 24（页面标注限时 8 折） |
| qwen3.7-flash | ≤32K / 32–256K / 256K–1M | 0.2 / 0.6 / 1.2 | 0.8 / 2.4 / 4.8 | 同左 |
| qwen3.6-plus | ≤256K / 256K–1M | 2 / 8 | 12 / 48 | 12 / 48 |
| qwen3.6-flash | ≤256K / 256K–1M | 1.2 / 4.8 | 7.2 / 28.8 | 同左 |
| qwen3.5-plus | ≤128K / 128–256K / 256K–1M | 0.8 / 2 / 4 | 4.8 / 12 / 24 | 同左 |
| **qwen-plus** | ≤128K / 128–256K / 256K–1M | 0.8 / 2.4 / 4.8 | **2 / 20 / 48** | **8 / 24 / 64** |
| **qwen-flash** | ≤128K / 128–256K / 256K–1M | 0.15 / 0.6 / 1.2 | 1.5 / 6 / 12 | 同左 |
| qwen-max（旧，只有非思考） | — | 2.4 | 9.6 | — |
| qwen3-vl-plus | ≤32K / 32–128K / 128–256K | 1 / 1.5 / 3 | 10 / 15 / 30 | 同左 |

- 阶梯计价按**单次请求的输入 token 总量**确定档位，整次请求的所有 token 都按这一档的单价计。
- 只有 `qwen-plus` 这一类老模型「思考比非思考贵 4 倍」（2 vs 8）。新一代 Qwen3.5+ 思考和非思考同价。
- 北京区域每个模型新开通有 100 万 token 免费额度（90 天）。Batch 半价。缓存另有折扣（命中约为输入价的 10%，⚠️ 各模型具体比例没有逐个核对）。
- 新加坡（国际）区域价格更高（例如 qwen3.8-max 是 14.988 / 44.965）。

### 5.6 限速
- RPM / TPM 按模型区分，按主账号合并计算，具体值在控制台查看。试用域名 RPM 是 1000。⚠️ 没有收录各模型的具体数字。

---

## 6. 对 RightWrite 的影响（统一思考档位映射）

RightWrite 的统一档位是：`off` / `low` / `medium` / `high` / `model-default`（model-default 就是什么字段都不发）。

### 6.1 各厂商的能力分三类
| 类型 | 厂商 / 模型 | 说明 |
|---|---|---|
| **A. 可关 + 可分档** | DeepSeek（flash / v4-pro）、豆包 seed-2.x、智谱 GLM-5.2（部分） | 五个档位基本都能对上 |
| **B. 只能开 / 关** | Kimi K2.6、智谱 GLM-5.1 / 5 / 4.7 / 4.6 / 4.5 / 4.6V、千问（用 budget 模拟分档） | low/medium/high 都等于「开」；千问可以用 `thinking_budget` 模拟 |
| **C. 始终思考，只能调档** | Kimi K3、智谱 GLM-5.3 / 5.3-Flash / FlashX、千问「仅思考」模型 | **没法真正 off**，off 只能降成最低档（或者在 UI 上禁止选 off） |
| **D. 不可控** | Kimi K2.7-Code（始终思考，没有档位） | 只能 model-default |

### 6.2 建议的映射表（给后端翻译层 / 「思考格式」配置用）
| 统一档位 | DeepSeek | Kimi K2.6 | Kimi K3 | GLM-5.3 系列 | GLM-5.2 | GLM-5.1 及以下 / 4.6V | 豆包 seed-2.x | 千问 Qwen3.x |
|---|---|---|---|---|---|---|---|---|
| off | `thinking.type=disabled` | `thinking.type=disabled` | ❌ 降成 `reasoning_effort=low` 并提示 | ❌ 降成 `thinking.type=enabled`+`reasoning_effort=low` | `thinking.type=disabled` | `thinking.type=disabled` | `thinking.type=disabled`（effort 不传，或只传 minimal） | `enable_thinking=false` |
| low | `enabled` + `reasoning_effort=low` | `enabled`（不能分档） | `reasoning_effort=low` | `enabled` + `low` | `enabled` + `high`（low 会被映射成 high） | `enabled` | `enabled` + `low` | `enable_thinking=true` + `thinking_budget≈1024`* |
| medium | `enabled` + `high`（medium 本来就映射成 high） | `enabled` | `high` | `enabled` + `high` | `enabled` + `high` | `enabled` | `enabled` + `medium` | `true` + `budget≈4096`* |
| high | `enabled` + `high`（或 max） | `enabled` | `max` | `enabled` + `max` | `enabled` + `max` | `enabled` | `enabled` + `high` | `true` + 不设 budget（用模型上限） |
| model-default | 不发 | 不发 | 不发 | 不发 | 不发 | 不发 | 不发 | 不发 |

\* 千问 budget 的具体数值是**我们自己定的建议**，不是官方档位，要按辅导对话的延迟和效果实测后再调。

### 6.3 实现层面的注意事项
1. **字段位置**：`thinking`、`enable_thinking`、`thinking_budget` 都放在 HTTP body 顶层（Open WebUI 直接转发 JSON 时就是顶层，不需要 extra_body）；`reasoning_effort` 也放顶层。
2. **Kimi 不能发 temperature / top_p 等采样参数**，否则报错。翻译层要按模型把这些字段剔掉。DeepSeek 思考模式下这些字段被忽略，但不会报错。
3. **「只能调档、关不掉」的模型**（Kimi K3、GLM-5.3 系列、千问仅思考模型、Kimi K2.7-Code）：管理员表里的「思考控制」不应该给 off 选项；或者选 off 时自动降成最低档，并在 UI 上标明「该模型无法关闭思考」。
4. **默认值差别很大**：DeepSeek、Kimi K2.6、GLM、豆包、新千问默认都**开着**思考，只有 `qwen-plus` / `qwen-flash` 默认**关着**。所以「model-default」在不同模型上意思完全不同。辅导对话如果追求响应快，建议显式发 off，别依赖默认值。
5. **识图 / OCR 步骤**：建议显式关思考或用最低档（DeepSeek-flash off、豆包 off、GLM-4.6V off、千问 `enable_thinking=false`）。GLM-5.3-Flash 关不掉思考，用它做识图会更慢、更贵。另外注意 Kimi Tier0 的并发 1、RPM 3。
6. **首次通读 / 读者检查**：维持当前决定（不跟老师的设置走），由管理员在「AI 步骤设置」表里单独定。
7. **计费**：各家思考 token 都按输出价计；豆包按原始思考 token 计费，但返回的只是摘要；千问老 `qwen-plus` 思考输出贵 4 倍。DeepSeek 高峰价（工作日白天）是空闲价的 2 倍。
8. **思考内容回传**：只在工具调用（tools）场景下必须回传（DeepSeek 不回传会 400；Kimi K3 / K2.7 要求原样回传）。RightWrite 普通辅导对话不带 tools，一般不受影响。但如果以后给辅导对话加工具，就要处理回传。

### 6.4 待 CC 用真实 Key 实测的清单
- [ ] 后台现在接入的三个模型的**准确 model ID**（Kimi 用的是 k2.6 还是 k3？GLM 用的是哪一版？DeepSeek 是 `deepseek-flash` 吗？）
- [ ] 每个模型：off / low / high 三档各发一次，记录有没有 `reasoning_content`、`reasoning_tokens` 是多少、首 token 延迟和总耗时
- [ ] Kimi：带 `temperature` 时是否真的报错；K3 传 `thinking` 是否报错
- [ ] GLM-5.3 系列：传 `disabled` 是否报错（文档说会）
- [ ] DeepSeek：旧名 `deepseek-chat` / `deepseek-reasoner` 现在是什么行为
- [ ] 千问：`qwen3.7-plus` 设 `enable_thinking=false` 是否报错（文档前后矛盾）
- [ ] 豆包：`thinking.type=auto` 是否报错；`reasoning_content` 是否只是摘要
- [ ] 识图：8 张图并发时，各家是否出现 429 / 1302 等限流错误
