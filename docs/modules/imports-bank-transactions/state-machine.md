# 银行流水导入 状态机

> 修改 `银行流水导入` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

| 状态 | 含义 | 事实源 |
| --- | --- | --- |
| `files_selected` | 用户在浏览器中选择了待导入文件，尚未预览。 | 前端本地 File state |
| `files_configured` | 每个银行流水文件都选择了银行账户映射。 | 前端 file selections + settings bank account mappings |
| `previewing` | 正在调用 `/imports/files/preview`。 | 前端请求状态 |
| `preview_ready` | 后端已创建 import session，文件级 preview 可确认。 | `FileImportSession.files[].status` |
| `file_error` / `unrecognized_template` | 某文件损坏、无法识别或模板不支持；同 session 其他 ready 文件仍可确认。 | `FileImportService.preview_files` |
| `preview_stale` | 预览后底层已存在记录或 audit 发生变化；确认被拒绝。 | `ImportPreviewStaleError` / API `409 preview_stale` |
| `queued` | 确认后创建 background `file_import` job，可能同时创建 `import.process.requested` durable event。 | background job + `job.import_jobs` / runtime queue |
| `processing` | import worker 或 inline background job 正在确认 selected files。 | `ImportJobWorker` / background job service |
| `confirmed` | selected files 已持久化并触发下游刷新/匹配。 | import session / import batch / row facts |
| `failed` | 确认任务失败，job 记录错误，session 可重试或重新预览。 | background job / import job |

### 允许流转

- `files_selected -> files_configured`：银行流水模式下每个文件都选择有效银行账户映射。
- `files_configured -> previewing -> preview_ready`：文件上传成功，后端能识别模板或保留文件级错误。
- `preview_ready -> preview_stale`：确认前 audit 检测到底层事实变化。
- `preview_ready -> queued`：至少一个 selected file 可确认，API 创建 idempotent background job。
- `queued -> processing -> confirmed`：import worker 或 inline job 确认 selected files，持久化 import facts，并触发 Workbench matching / read model fan-out。
- `failed -> files_configured/previewing`：用户重试 session files 或重新预览。

### 禁止流转

- 没有银行账户映射时禁止预览银行流水文件。
- 任一 selected file 缺少银行映射时禁止预览。
- `preview_stale` 后禁止继续确认旧 session；必须重新预览。
- unknown selected file id 必须返回 404，不得静默跳过。
- 已有 idempotency key 的 confirm 不得创建重复 import job。
- 不能把 `queued` / `processing` 展示成下游 read model 已 fresh。

## UI 状态

| 状态 | 页面行为 |
| --- | --- |
| settings loading | 银行流水模式进入页面后加载银行账户映射；未完成前不能完整配置文件。 |
| empty | 未选择文件时展示上传区域和说明；不创建 session。 |
| selected | 展示文件列表和每文件银行选择；清空/移除文件会清空 preview。 |
| previewing | 预览按钮 loading，禁用重复预览和确认。 |
| preview_ready | 展示 audit counts、文件状态、重复组、跳过明细、银行选择冲突；只允许确认 `preview_ready` 文件。 |
| conflict dialog | 文件识别账号与用户选择账号冲突时，确认前弹出冲突确认。 |
| confirming | 确认按钮 loading；App Health `blocksMutations` 时禁止确认并提示重新进入。 |
| job queued | 返回 `job` 时显示“已开始后台导入”，不立即宣称下游刷新完成。 |
| success | inline 完成时可提示导入完成，并刷新 Workbench 状态；后台 job 由 App Status/Health 展示进度。 |
| error | preview/confirm/retry/session fetch 失败展示错误；`preview_stale` 使用固定“重新预览”提示。 |
| session restore | 支持通过 session id 恢复 preview；离开/返回页面不能保留 in-flight 请求。 |
| permission disabled/hidden | 当前页面通过 App Health `blocksMutations` 做系统不可用防护；若后续接入细粒度权限，需补 API 403 和前端 disabled/hidden。 |

## Read Model / Worker 状态

银行流水导入本身不是 read model 页面；它触发多个下游 read model 和后台任务。

| 状态 | 含义 | 导入页处理 |
| --- | --- | --- |
| `queued` | `file_import` background job / `import.process.requested` event 已创建。 | 显示后台导入已开始，用户可去 App Status/App Health 查看。 |
| `processing` | import worker 执行 `file_import.confirm` processor。 | 不阻塞页面离开；不能重放旧 confirm。 |
| `succeeded` | selected files 已确认，结果 summary 写入 job。 | 下游 read model 可能仍在 refreshing。 |
| `failed` | import job 或 background job 失败。 | 暴露错误，允许 retry 或重新预览。 |
| `refreshing/stale` | 银行明细、账户余额、Workbench、Workbench relation、matching、invoice lifecycle、cost/search 等下游 dirty。 | 导入页不伪装这些页面 fresh；由下游页面和 App Status 展示。 |
| `fresh` | 下游 worker 完成对应 scope refresh。 | 由银行明细/关联台/成本统计等页面读取。 |

Refresh / fan-out 来源：

- `/imports/files/confirm` inline 或 worker confirm selected files。
- `ImportProcessingService.execute_file_import_confirm_job(...)` enqueue Workbench auto matching。
- `_persist_state_with_workbench_invalidation(...)` 触发 Workbench 及成本统计相关刷新。
- `DerivedDataLifecycleService` 的 `bank_import_confirmed` 映射到 `bank_account_balance`、`bank_detail`、`workbench`、`workbench_relation`、`workbench_matching`、`invoice_lifecycle`、`cost_statistics`、`search`。

失败恢复：

1. 查看 background job / import job 的 `status`、`stage`、`last_error` 和 `result_summary`。
2. 如果是 `preview_stale`，重新预览，不复用旧 session confirm。
3. 如果是 worker/queue 失败，确认 `import` worker、`import.process.requested` event、RabbitMQ/Redis/Postgres queue 状态。
4. 如果导入确认已成功但下游页面 stale，检查对应 read model dirty scope 和 worker readiness。
5. 禁止通过前端本地状态手动标记下游页面 fresh。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 首轮测试闭环状态机补齐 | 明确文件/session/job/worker/read model 状态和禁止流转 | `tests/test_import_*`、`tests/test_import_job_queue.py`、`web/src/test/ImportCenterPage.test.tsx` |
