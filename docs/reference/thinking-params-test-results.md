# 思考档位实测结果（RightWrite 现网接入的服务商）

- 实测日期：2026-10-18（北京时间）。对照资料：[国内大模型思考参数与价格参考](llm-thinking-params-pricing.md)。
- 对象：现网 Open WebUI 配置里的 OpenAI 兼容连接（只读读取，没有改动服务器）。连接与模型如下：

| 连接（Base URL） | 自动识别的思考格式（修正后） | 现网配置的模型 |
|---|---|---|
| `https://api.deepseek.com` | `deepseek` | `deepseek-flash`、`deepseek-v4-pro` |
| `https://open.bigmodel.cn/api/paas/v4` | `zhipu` | `glm-5.3`、`glm-5.3-flash`、`glm-5.3-flashx` |
| `https://api.moonshot.cn/v1` | `kimi` | `kimi-k2.6`、`kimi-k3` |
| `https://api.openai.com/v1` | `openai` | 没配 Key，未使用 |

- 现网还没有部署 PR #2：所有模型都没勾「思考控制」，也没设初稿图片识别模型（图片导入在现网是关的）。
- 方法：每个模型、每个统一档位（model_default / off / low / medium / high）各发一条短请求。请求体用本仓库 `backend/open_webui/utils/thinking.py` 翻译，和 OpenAI 兼容路由实际发出的一致。另对可看图的模型发一张 64×64 的小图，并按参考文档的待实测清单单独构造了几条请求。
- 提示词是「1+1等于几？只回答数字。」，`max_tokens` 为 300，逐条顺序发送。共 113 次调用、约 8.8K tokens，按参考文档的高峰单价粗估不到 0.2 元。
- 记录项：HTTP 状态与报错原文、`reasoning_content` 的字数、`usage.completion_tokens_details.reasoning_tokens`、`completion_tokens`、总耗时。「—」表示响应里没有这一项。
- 局限：题目太简单，同一模型在相邻档位之间的思考量差别会被噪声盖过。这些数据能说明「这个字段被接受、能关掉思考」，但不能用来比较 low / medium / high 的效果。各档效果要在真实辅导对话里再看。

## 结论

1. **Kimi 原来没认出来**。`api.moonshot.cn` 被当成 OpenAI，按 `reasoning_effort` 发。K2.6 不理这个字段，「关」照样思考（51 个推理 token）。修正后用 `thinking.type=disabled` 关思考，K2.6 和 K3 都能真正关掉。
2. **K3 可以关思考，与参考文档不符**。参考文档说 K3 不接受 `thinking` 字段，实测传 `{"type":"disabled"}` 返回 200，也没有思考内容。K3 接受 `reasoning_effort` 的 minimal、low、medium、high。
3. **GLM-5.3 系列（5.3、5.3-flash、5.3-flashx）关不掉思考**。原来的翻译在「关」时发 `thinking.type=disabled`，三个模型都返回 400（code 1210：「该模型始终思考，不支持关闭思考；请使用 low、high 或 max。」），学生关掉思考的那一轮会直接报错。`reasoning_effort=medium` 也返回 400，报错原文同样是 1210。修正后，「关」退到 `reasoning_effort=low`；实测 low 几乎不思考（0–2 个推理 token）。
4. **DeepSeek 原来只发开 / 关**，low、medium、high 三档发出的请求完全一样。DeepSeek 接受 `reasoning_effort` 的 low、medium、high（medium 由服务端归到 high）。修正后各档分别发 low、high、max。
5. **Kimi 不接受改采样参数**。K2.6、K3 传 `temperature=0.3` 都返回 400（「only 1 is allowed」），K2.6 传 `top_p=0.9` 也返回 400（「only 0.95 is allowed」）。10-19 补测：两个模型的 `top_p`（只能 0.95）、`n`（只能 1）、`presence_penalty` 与 `frequency_penalty`（只能 0）都固定；关掉思考时 `temperature` 只能 0.6，传 1 也 400。管理员如果在 Kimi 模型上设了这些参数，每次请求都会失败；现在发送前一律去掉，见下文「Kimi 的固定采样参数」。
6. **DeepSeek 旧模型名还能用**：`deepseek-chat` 不思考，`deepseek-reasoner` 思考，都返回 200。
7. **看图**：`deepseek-flash`、`glm-5.3-flash`、`kimi-k2.6`、`kimi-k3` 都正确认出了图里的黑色方块。修正后的「关」同样适用于看图请求。
8. **偶发错误**：`deepseek-flash` 有一次读超时（180 秒），`glm-5.3-flash` 有一次 500（「网络错误」，用了 90 秒）。同样的请求各重发 3 次都返回 200，属于服务商偶发故障，与翻译无关。现在辅导对话与平台步骤都会自动重发，见文末。

## 修正后的映射（本仓库 `utils/thinking.py`）

| 统一档位 | `deepseek` | `kimi` | `zhipu`（GLM-5.3 系列） | `zhipu`（GLM-5.2） | `zhipu`（更早型号） | `doubao` | `qwen` |
|---|---|---|---|---|---|---|---|
| off | `thinking.type=disabled` | `thinking.type=disabled` | `enabled` + `reasoning_effort=low`（关不掉，退到最低档） | `thinking.type=disabled` | `disabled`（GLM-4.7、4.5V 关不掉又没有档位，各档都不发） | `thinking.type=disabled` | `enable_thinking=false` |
| low | `enabled` + `low` | K3：`reasoning_effort=low`；K2.6：`thinking.type=enabled` | `enabled` + `low` | `enabled` + `low` | `enabled` | `enabled` + `low` | `true` + `thinking_budget=1024` |
| medium | `enabled` + `high` | K3：`reasoning_effort=high`；K2.6：同上 | `enabled` + `high` | `enabled` + `high` | `enabled` | `enabled` + `medium` | `true` + `thinking_budget=4096` |
| high | `enabled` + `max` | K3：`reasoning_effort=max`；K2.6：同上 | `enabled` + `max` | `enabled` + `max` | `enabled` | `enabled` + `high` | `true`，不设预算 |
| model_default | 不发 | 不发 | 不发 | 不发 | 不发 | 不发 | 不发 |

- 自动识别改为按主机名后缀匹配。新增 `moonshot.cn` / `moonshot.ai` → `kimi`，`z.ai` → `zhipu`，`maas.aliyuncs.com` / `dashscope-intl.aliyuncs.com` → `qwen`；原来合在一起的 `thinking_type` 格式拆成 `deepseek`、`zhipu`、`doubao`。
- 豆包、千问没有接入现网，没有实测。映射按参考文档 §4.2、§5.2 写：豆包关思考时 `reasoning_effort` 只能填 minimal，所以干脆不发；千问高档不设预算。
- Kimi K3 开思考时不发 `thinking.type=enabled`：思考默认就是开的，参考文档也说 K3 不接受这个值（本次只验证了 disabled）。K2.6 只有开 / 关（2026-10-19 起）：低、中、高都发 `thinking.type=enabled`（实测 200），不发 `reasoning_effort`。
- 哪些模型只有开 / 关，写在 `utils/thinking.py` 的 `MODEL_THINKING_SUPPORT`；发送时的翻译和界面（模型列表里每个模型带的 `thinking_support`，管理员在模型编辑页勾了思考控制、或在 AI 步骤设置里选到这类模型时会看到提示）读同一张表。

## 逐档结果

「修正前」一列是旧翻译发出的字段和结果；带「重发」字样的是偶发错误重试后的结果。


#### `deepseek-flash`

| 档位 | 修正后发出的字段 | 结果 | reasoning_content 字数 | reasoning_tokens | completion_tokens | 耗时 | 修正前发出的字段 → 结果 |
|---|---|---|---|---|---|---|---|
| model_default | （不发） | 200 | 75 | 21 | 23 | 1.27s | （不发） → 200，reasoning_tokens 26 |
| off | `{"thinking": {"type": "disabled"}}` | 200 | 0 | — | 1 | 0.68s | `{"thinking": {"type": "disabled"}}` → 200，无思考 |
| low | `{"thinking": {"type": "enabled"}, "reasoning_effort": "low"}` | 200（首发 ReadTimeout，重发 3 次均 200） | 47 | 31 | 33 | 0.87s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 27 |
| medium | `{"thinking": {"type": "enabled"}, "reasoning_effort": "high"}` | 200 | 73 | 21 | 23 | 0.89s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 26 |
| high | `{"thinking": {"type": "enabled"}, "reasoning_effort": "max"}` | 200 | 101 | 33 | 35 | 0.9s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 27 |

#### `deepseek-v4-pro`

| 档位 | 修正后发出的字段 | 结果 | reasoning_content 字数 | reasoning_tokens | completion_tokens | 耗时 | 修正前发出的字段 → 结果 |
|---|---|---|---|---|---|---|---|
| model_default | （不发） | 200 | 71 | 44 | 46 | 1.64s | （不发） → 200，reasoning_tokens 31 |
| off | `{"thinking": {"type": "disabled"}}` | 200 | 0 | — | 1 | 1.51s | `{"thinking": {"type": "disabled"}}` → 200，无思考 |
| low | `{"thinking": {"type": "enabled"}, "reasoning_effort": "low"}` | 200 | 53 | 32 | 34 | 1.95s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 31 |
| medium | `{"thinking": {"type": "enabled"}, "reasoning_effort": "high"}` | 200 | 51 | 32 | 34 | 1.67s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 34 |
| high | `{"thinking": {"type": "enabled"}, "reasoning_effort": "max"}` | 200 | 131 | 41 | 43 | 2.13s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 39 |

#### `glm-5.3`

| 档位 | 修正后发出的字段 | 结果 | reasoning_content 字数 | reasoning_tokens | completion_tokens | 耗时 | 修正前发出的字段 → 结果 |
|---|---|---|---|---|---|---|---|
| model_default | （不发） | 200 | 247 | 63 | 66 | 2.16s | （不发） → 200，reasoning_tokens 51 |
| off | `{"thinking": {"type": "enabled"}, "reasoning_effort": "low"}` | 200 | 0 | 0 | 3 | 1.2s | `{"thinking": {"type": "disabled"}}` → 400 {"error":{"code":"1210","message":"该模型始终 |
| low | `{"thinking": {"type": "enabled"}, "reasoning_effort": "low"}` | 200 | 0 | 0 | 3 | 1.12s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 71 |
| medium | `{"thinking": {"type": "enabled"}, "reasoning_effort": "high"}` | 200 | 0 | 0 | 3 | 1.21s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 64 |
| high | `{"thinking": {"type": "enabled"}, "reasoning_effort": "max"}` | 200 | 171 | 40 | 43 | 1.72s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 69 |

#### `glm-5.3-flash`

| 档位 | 修正后发出的字段 | 结果 | reasoning_content 字数 | reasoning_tokens | completion_tokens | 耗时 | 修正前发出的字段 → 结果 |
|---|---|---|---|---|---|---|---|
| model_default | （不发） | 200 | 170 | 48 | 53 | 2.87s | （不发） → 200，reasoning_tokens 81 |
| off | `{"thinking": {"type": "enabled"}, "reasoning_effort": "low"}` | 200 | 0 | 0 | 3 | 1.13s | `{"thinking": {"type": "disabled"}}` → 400 {"error":{"code":"1210","message":"该模型始终 |
| low | `{"thinking": {"type": "enabled"}, "reasoning_effort": "low"}` | 200 | 0 | 0 | 3 | 1.12s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 48 |
| medium | `{"thinking": {"type": "enabled"}, "reasoning_effort": "high"}` | 200 | 0 | 0 | 3 | 1.06s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 51 |
| high | `{"thinking": {"type": "enabled"}, "reasoning_effort": "max"}` | 200 | 234 | 65 | 68 | 2.66s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 71 |

#### `glm-5.3-flashx`

| 档位 | 修正后发出的字段 | 结果 | reasoning_content 字数 | reasoning_tokens | completion_tokens | 耗时 | 修正前发出的字段 → 结果 |
|---|---|---|---|---|---|---|---|
| model_default | （不发） | 200 | 253 | 62 | 66 | 1.59s | （不发） → 200，reasoning_tokens 64 |
| off | `{"thinking": {"type": "enabled"}, "reasoning_effort": "low"}` | 200 | 0 | 0 | 3 | 1.28s | `{"thinking": {"type": "disabled"}}` → 400 {"error":{"code":"1210","message":"该模型始终 |
| low | `{"thinking": {"type": "enabled"}, "reasoning_effort": "low"}` | 200 | 0 | 0 | 3 | 1.39s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 56 |
| medium | `{"thinking": {"type": "enabled"}, "reasoning_effort": "high"}` | 200 | 0 | 0 | 3 | 1.46s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 72 |
| high | `{"thinking": {"type": "enabled"}, "reasoning_effort": "max"}` | 200 | 194 | 53 | 56 | 1.51s | `{"thinking": {"type": "enabled"}}` → 200，reasoning_tokens 56 |

#### `kimi-k2.6`

| 档位 | 修正后发出的字段 | 结果 | reasoning_content 字数 | reasoning_tokens | completion_tokens | 耗时 | 修正前发出的字段 → 结果 |
|---|---|---|---|---|---|---|---|
| model_default | （不发） | 200 | 69 | 41 | 44 | 2.58s | （不发） → 200，reasoning_tokens 51 |
| off | `{"thinking": {"type": "disabled"}}` | 200 | 0 | 1 | 4 | 0.62s | `{"reasoning_effort": "minimal"}` → 200，reasoning_tokens 51 |
| low | `{"reasoning_effort": "low"}` | 200 | 70 | 42 | 45 | 1.17s | `{"reasoning_effort": "low"}` → 200，reasoning_tokens 92 |
| medium | `{"reasoning_effort": "high"}` | 200 | 88 | 51 | 54 | 1.28s | `{"reasoning_effort": "medium"}` → 200，reasoning_tokens 54 |
| high | `{"reasoning_effort": "max"}` | 200 | 142 | 85 | 88 | 1.69s | `{"reasoning_effort": "high"}` → 200，reasoning_tokens 49 |

#### `kimi-k3`

| 档位 | 修正后发出的字段 | 结果 | reasoning_content 字数 | reasoning_tokens | completion_tokens | 耗时 | 修正前发出的字段 → 结果 |
|---|---|---|---|---|---|---|---|
| model_default | （不发） | 200 | 123 | 40 | 56 | 5.0s | （不发） → 200，reasoning_tokens 101 |
| off | `{"thinking": {"type": "disabled"}}` | 200 | 0 | — | 11 | 3.21s | `{"reasoning_effort": "minimal"}` → 200，reasoning_tokens 25 |
| low | `{"reasoning_effort": "low"}` | 200 | 23 | 18 | 34 | 4.0s | `{"reasoning_effort": "low"}` → 200，reasoning_tokens 29 |
| medium | `{"reasoning_effort": "high"}` | 200 | 32 | 23 | 39 | 4.18s | `{"reasoning_effort": "medium"}` → 200，reasoning_tokens 28 |
| high | `{"reasoning_effort": "max"}` | 200 | 133 | 39 | 55 | 4.45s | `{"reasoning_effort": "high"}` → 200，reasoning_tokens 29 |

#### 图片输入（修正后的关思考 vs 不发）

| 模型 | 档位 | 发出的字段 | 结果 | reasoning_tokens | 答案 | 耗时 |
|---|---|---|---|---|---|---|
| `deepseek-flash` | model_default | （不发） | 200 | 28 | 黑色 | 0.81s |
| `deepseek-flash` | off | `{"thinking": {"type": "disabled"}}` | 200 | — | 黑色 | 0.95s |
| `glm-5.3-flash` | model_default | （不发） | 200 | 57 | 黑色 | 2.05s |
| `glm-5.3-flash` | off | `{"thinking": {"type": "enabled"}, "reasoning_effort": "low"}` | 500 首发 500（网络错误，错误id 2026101823…），重发 3 次均 200，reasoning_tokens 0 | — |  | 90.32s |
| `kimi-k2.6` | model_default | （不发） | 200 | 37 | 黑色 | 2.71s |
| `kimi-k2.6` | off | `{"thinking": {"type": "disabled"}}` | 200 | 1 | 黑色。 | 0.73s |
| `kimi-k3` | model_default | （不发） | 200 | 60 | 黑色 | 5.03s |
| `kimi-k3` | off | `{"thinking": {"type": "disabled"}}` | 200 | — | 黑色 | 4.62s |

#### 文档里待核实的项与已知差距（直接构造的请求）

| 模型 | 场景 | 发出的字段 | 结果 | reasoning_tokens |
|---|---|---|---|---|
| `deepseek-flash` | enabled+effort low | `{"thinking": {"type": "enabled"}, "reasoning_effort": "low"}` | 200 | 37 |
| `deepseek-flash` | enabled+effort high | `{"thinking": {"type": "enabled"}, "reasoning_effort": "high"}` | 200 | 20 |
| `deepseek-flash` | enabled+effort medium | `{"thinking": {"type": "enabled"}, "reasoning_effort": "medium"}` | 200 | 25 |
| `deepseek-flash` | disabled+effort low | `{"thinking": {"type": "disabled"}, "reasoning_effort": "low"}` | 200 | — |
| `deepseek-chat` | legacy name | （不发） | 200 | — |
| `deepseek-reasoner` | legacy name | （不发） | 200 | 23 |
| `glm-5.3-flash` | thinking disabled | `{"thinking": {"type": "disabled"}}` | 400：{"error":{"code":"1210","message":"该模型始终思考，不支持关闭思考；请使用 low、high 或 max。"}} | — |
| `glm-5.3-flash` | enabled+effort low | `{"thinking": {"type": "enabled"}, "reasoning_effort": "low"}` | 200 | 2 |
| `glm-5.3-flash` | enabled+effort medium | `{"thinking": {"type": "enabled"}, "reasoning_effort": "medium"}` | 400：{"error":{"code":"1210","message":"该模型始终思考，不支持关闭思考；请使用 low、high 或 max。"}} | — |
| `glm-5.3-flash` | enabled+effort max | `{"thinking": {"type": "enabled"}, "reasoning_effort": "max"}` | 200 | 60 |
| `glm-5.3` | enabled+effort low | `{"thinking": {"type": "enabled"}, "reasoning_effort": "low"}` | 200 | 0 |
| `kimi-k2.6` | temperature 0.3 | `{"temperature": 0.3}` | 400：invalid temperature: only 1 is allowed for this model | — |
| `kimi-k2.6` | top_p 0.9 | `{"top_p": 0.9}` | 400：invalid top_p: only 0.95 is allowed for this model | — |
| `kimi-k2.6` | thinking disabled | `{"thinking": {"type": "disabled"}}` | 200 | 1 |
| `kimi-k2.6` | thinking enabled | `{"thinking": {"type": "enabled"}}` | 200 | 50 |
| `kimi-k2.6` | reasoning_effort low | `{"reasoning_effort": "low"}` | 200 | 50 |
| `kimi-k3` | temperature 0.3 | `{"temperature": 0.3}` | 400：invalid temperature: only 1 is allowed for this model | — |
| `kimi-k3` | thinking disabled | `{"thinking": {"type": "disabled"}}` | 200 | — |
| `kimi-k3` | effort low | `{"reasoning_effort": "low"}` | 200 | 30 |
| `kimi-k3` | effort high | `{"reasoning_effort": "high"}` | 200 | 20 |
| `kimi-k3` | effort medium | `{"reasoning_effort": "medium"}` | 200 | 18 |


#### Kimi 的固定采样参数（2026-10-19 补测）

同样只读取现网 Kimi 连接的 Key，每条一句「1+1等于几？只回答数字。」、`max_tokens` 300，共 20 次调用、897 tokens。没写思考的是默认（开着思考）。

| 场景 | `kimi-k2.6` | `kimi-k3` |
|---|---|---|
| `n=2` | 400：invalid n: only 1 is allowed for this model | 400：同左 |
| `n=1` | 200 | 200 |
| `presence_penalty=0.5` | 400：invalid presence_penalty: only 0 is allowed for this model | 400：同左 |
| `presence_penalty=0` | 200 | 200 |
| `frequency_penalty=0.5` | 400：invalid frequency_penalty: only 0 is allowed for this model | 400：同左 |
| `frequency_penalty=0` | 200 | 200 |
| `top_p=0.9` | 400（10-18） | 400：invalid top_p: only 0.95 is allowed for this model |
| `top_p=0.95` | — | 200 |
| `top_p=1.0` | — | 400：同上 |
| 关思考 + `temperature=1` | 400：invalid temperature: only 0.6 is allowed for this model | 400：同左 |
| 关思考 + `temperature=0.6` | 200 | 200 |
| 关思考 + `top_p=0.95` | 200 | — |

结论：这五个参数在 K2.6、K3 上都只接受一个值，而 `temperature` 的值还随思考开关变（开 1、关 0.6；参考文档说 K3 固定 1.0，与实测不符）。所以 `kimi` 格式发送前一律去掉这五个参数，不管值是多少，由服务商取它自己的值。

## 仍待处理

- **Kimi 的采样参数（已处理）**：`kimi` 格式发送前一律去掉 `temperature`、`top_p`、`n`、`presence_penalty`、`frequency_penalty`（K2.6、K3 实测都只接受一个值，见上文）。规则表在 `utils/thinking.py` 的 `FIXED_SAMPLING_PARAMS`；管理员在模型编辑页设了这类参数、或在连接设置里选到 Kimi 时会看到同一张表生成的提示。K2.7 等现网没有的 Kimi 模型没测，按同一张表处理。
- **K2.6 的思考力度（已处理）**：K2.6 收到 `reasoning_effort` 不报错，但看不出有没有生效（同一档位多次之间推理 token 在 41–92 之间波动）。现在按只有开 / 关处理：低、中、高都只发 `thinking.type=enabled`，管理员界面写明。
- **关不掉思考的模型（已处理，部分未实测）**：`MODEL_THINKING_SUPPORT` 里记了 GLM-5.3 系列（实测）、GLM-4.7、GLM-4.5V、Kimi K2.7-Code（后三个按参考文档，现网没有，未实测）。这类模型从不发会 400 的 `disabled`：能分档的「关」退到最低档（GLM-5.3 发 `low`）；不分档的各档都不发，按模型默认（K2.7-Code 文档说显式传只能 `{type: enabled, keep: all}`，干脆不传）。管理员在模型编辑页、AI 步骤设置里选到这类模型时看到提示；学生端「深度思考」开关换成「这个模型始终开着」，回复上记实际生效的档位。千问「仅思考」模型参考文档没给出型号名，没有收进表。
- **偶发故障（已处理）**：作业辅导对话和通读、试读、班级归纳等平台步骤现在自动重发（`utils/retry.py`）：遇 429、5xx、连接失败或超时，按 1、2、4 秒（±25% 抖动）最多发 4 次，只在回复开始往下送之前重发：一次性回复读完响应体、流式回复读到第一段才算发成，所以等响应体或等第一段超时也会重发。流式回复第一段及此后两段之间最多等 45 秒，过 60 秒不再开始新的一次（一直等不来约 90 秒报错）；一次性回复最多等 90 秒，过 120 秒不再开始新的一次（约 180 秒报错）。两者超时后都还能再发一次。图片识别仍按页自己重发，两者不叠加。
- 通读、试读等平台步骤默认「模型默认」，在这三家都等于开着思考；需要控制成本时，在「AI 步骤设置」里显式选档位。
