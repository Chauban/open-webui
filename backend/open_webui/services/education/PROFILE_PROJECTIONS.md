# 作业写作成长画像投影

成长画像分为两个边界：

- `profile_evidence_snapshot` 保存提交时冻结的事实证据。记录只追加，不更新、不删除。
- `profile_metric_projection` 保存指定正式算法对一份证据及一次批改 revision 的计算结果。
- `student_profile_aggregate_projection` 保存学生全局或班级范围的趋势、洞察和完整度汇总；每次输入投影集合变化都追加新的 aggregate revision。

编辑事件同时保存客户端毫秒级发生时间、客户端顺序和服务端接收时间。过程指标使用客户端发生时间；接收时间只用于采集审计，避免网络批量上报把多次编辑错误压缩到同一时间点。

默认画像 GET 只读取分页明细投影和已物化 aggregate revision，不遍历全部历史投影。带时间、作业或轮次筛选的临时报表只聚合派生投影，仍不会读取原始版本、编辑操作、来源映射或聊天记录。新提交和批改在写事务中立即生成当前算法投影与聚合投影；单份分析需要刷新时，使用教师分析 POST 接口从不可变 evidence 显式重算。

## 显式批量重算

在 `open-webui/backend` 目录执行：

```powershell
.venv\Scripts\python.exe -m open_webui.services.education.profile_recompute `
  --requested-by <管理员用户ID> `
  --batch-size 200
```

可选参数：

- `--student-id`：只重算一个学生。
- `--assignment-id`：只重算一个作业。
- `--activate`：全部目标成功后把当前代码中的指标版本设为正式版本；存在任何失败时拒绝激活。

每次运行写入 `profile_projection_run`，记录范围、代码构建版本、配置哈希、成功数、失败数和逐项错误。任务按不可变证据主键做 keyset 分批，可安全重复运行；相同输入必须得到相同输出哈希。

发布新算法必须同时提升 `PROFILE_METRIC_VERSION`。同一版本的公式配置或代码校验和发生变化时，写入会直接失败，防止静默覆盖已经发布的算法结果。生产构建应设置 `WEBUI_BUILD_HASH`，用于保存准确的代码提交标识。

## 迁移原则

迁移 `a4d8f2c6b1e9` 完成事实/投影拆分，`b7c1e4a9d2f6` 收敛最终聚合和编辑事件时间结构。两者都是有意不兼容的前向迁移，只允许教育写作证据表为空时执行；检测到旧画像、提交、版本、反思、分析、来源或编辑数据会立即失败，要求先显式清理，不执行回填或自动修复。
