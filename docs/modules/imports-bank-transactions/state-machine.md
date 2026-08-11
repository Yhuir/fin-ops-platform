# 银行流水导入 状态机

> 修改 `银行流水导入` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

| 状态 | 含义 | 事实源 |
| --- | --- | --- |
| `files_selected` | 用户在浏览器中选择了待导入文件，尚未预览。 | 前端本地 File state |
| `files_configured` | 每个银行流水文件都选择了银行账户映射。 | 前端 file selections + settings bank account mappings |
| `previewing` | 正在调用 `/imports/files/preview`。 | 前端请求状态 |
| `preview_ready` | 后端已创建 import session，文件级 preview 可确认。 | `FileImportSession.files[].status` |
| `reverted` | 用户在确认前显式放弃 preview，服务端已终结 session/file/pending batch。 | `app.import_files` + `app.import_batches`；不影响 canonical transaction |
| `mapping_required` / `unrecognized_template` | 已定位银行表头但核心 canonical 字段不完整；后端返回候选列，等待用户补充映射，不生成可确认行。 | `FileImportSession.files[].mapping_fields` |
| `file_error` / `unrecognized_template` | 文件损坏、无法定位表头或不是支持的文件类型；同 session 其他 ready 文件仍可确认。 | `FileImportService.preview_files` |
| `preview_stale` | 预览后底层已存在记录或 audit 发生变化；确认被拒绝。 | `ImportPreviewStaleError` / API `409 preview_stale` |
| `queued` | 确认后创建 background `file_import` job，银行流水 selected files 必须携带 `affected_domains=["imports_bank_transactions"]` 和 `/imports/bank-transactions` route；可能同时创建 `import.process.requested` durable event。 | background job + `job.import_jobs` / runtime queue |
| `processing` | import worker 或 inline background job 正在确认 selected files。 | `ImportJobWorker` / background job service |
| `confirmed` | selected files 已持久化并触发下游刷新/匹配。 | import session / import batch / row facts |
| `failed` | 确认任务失败，job 记录错误，session 可重试或重新预览。 | background job / import job |

### 允许流转

- `files_selected -> files_configured`：银行流水模式下每个文件都选择有效银行账户映射。
- `files_configured -> previewing -> preview_ready`：文件上传成功，后端能识别模板或保留文件级错误。
- `previewing -> mapping_required -> preview_ready`：自动归一不完整时，用户提交当前文件的字段映射；后端重新校验并解析。相同标准化表头签名后续可直接复用已保存人工映射。
- `preview_ready -> preview_stale`：确认前 audit 检测到底层事实变化。
- `preview_ready -> queued`：至少一个 selected file 可确认，API 创建 idempotent background job。
- `queued -> processing -> confirmed`：import worker 或 inline job 确认 selected files，持久化 import facts 与必要 Workbench matching 领域任务；不触发页面 read model fan-out，消费者访问时按 source version 收敛。
- `failed -> files_configured/previewing`：用户重试 session files 或重新预览。
- `preview_ready -> reverted`：只有 session owner 可显式放弃；重复请求幂等。

### 禁止流转

- 没有银行账户映射时禁止预览银行流水文件。
- 任一 selected file 缺少银行映射时禁止预览。
- 核心字段映射不完整、同一源列映射到多个互斥核心字段或映射列不存在时禁止产生 preview rows 和确认。
- 银行流水页面禁止使用旧 `/imports/preview`、`/imports/confirm` JSON 状态流；页面 I/O 只能进入 file/session 状态机。
- `preview_stale` 后禁止继续确认旧 session；必须重新预览。
- unknown selected file id 必须返回 404，不得静默跳过。
- 已有 idempotency key 的 confirm 不得创建重复 import job。
- 任一银行流水 preview/retry 不得写回其它 session，更不得把其它进程已确认的发票或银行导入降级为 pending。
- 不能把 `queued` / `processing` 展示成下游 read model 已 fresh。
- 已 `reverted`、已确认或有 pending/processing/succeeded import job 时禁止 discard/confirm；GET/review/retry/confirm/discard 必须校验 session owner。

## UI 状态

| 状态 | 页面行为 |
| --- | --- |
| settings loading | 银行流水模式进入页面后加载银行账户映射；未完成前不能完整配置文件。 |
| empty | 未选择文件时展示上传区域和说明；不创建 session。 |
| selected | 展示文件列表和每文件银行选择；清空/移除文件会清空 preview。 |
| previewing | 预览按钮 loading，禁用重复预览和确认。 |
| preview_ready | 展示 audit counts、文件状态、重复组、跳过明细、银行选择冲突；只允许确认 `preview_ready` 文件。 |
| mapping required | 在当前文件下展示 HeroUI 字段选择；保存只重试该文件，成功后回到 `preview_ready`，失败保留映射草稿和明确错误。 |
| conflict dialog | 文件识别账号与用户选择账号冲突时，确认前弹出冲突确认。 |
| confirming | 确认按钮 loading；App Health `blocksMutations` 时禁止确认并提示重新进入。 |
| job queued | 返回 `job` 时显示“已开始后台导入”，不立即宣称下游刷新完成。 |
| success | inline 完成时提示导入完成；仅当响应声明 `operation_barrier_targets` 时等待这些 targets，禁止请求 Workbench 页面探测刷新。后台 job 由 App Status/Health 展示进度。 |
| error | preview/confirm/retry/session fetch 失败展示错误；`preview_stale` 使用固定“重新预览”提示。 |
| session restore | 有本地 session id 时精确恢复；本地缺失/失效时从 `GET /imports/files/sessions?mode=bank_transaction` 恢复当前用户最新活跃 preview。离开/返回页面不能保留 in-flight 请求。 |
| discard | 点击清空已预览内容时先调用服务端 discard；成功后才清本地，失败则保留预览并显示错误。 |
| permission disabled/hidden | 当前页面通过 App Health `blocksMutations` 做系统不可用防护；若后续接入细粒度权限，需补 API 403 和前端 disabled/hidden。 |

## Read Model / Worker 状态

银行流水导入本身不是 read model 页面；它触发多个下游 read model 和后台任务。

| 状态 | 含义 | 导入页处理 |
| --- | --- | --- |
| `queued` | `file_import` background job / `import.process.requested` event 已创建。 | 显示后台导入已开始，用户可去 App Status/App Health 查看。 |
| `processing` | import worker 执行 `file_import.confirm` processor。 | 不阻塞页面离开；不能重放旧 confirm。 |
| `succeeded` | selected files 已确认，结果 summary 写入 job。 | 下游 read model 可能仍在 refreshing。 |
| `failed` | import job 或 background job 失败。 | 暴露错误，允许 retry 或重新预览。 |
| `refreshing/stale` | 后续访问的消费页发现 canonical source version mismatch，并为自己的精确 scope 入队。 | 导入页不伪装这些页面 fresh；由被访问页面和 App Status 展示。 |
| `fresh` | 被访问页面的 worker 完成对应 scope refresh。 | 由银行明细/关联台/成本统计等消费页读取。 |

访问时 refresh 来源：

- `/imports/files/confirm` inline 或 worker confirm selected files。
- `ImportProcessingService.execute_file_import_confirm_job(...)` enqueue Workbench auto matching。
- `ImportProcessingService` 输出所选 session/batch 的精确 persistence delta、source version 与空页面 targets；不调用 derived lifecycle。
- 银行明细、账户余额、Workbench、成本统计等页面在进入/重新可见时，由各自 query owner 比较 canonical source proof 并只刷新当前精确 scope。

失败恢复：

1. 查看 background job / import job 的 `status`、`stage`、`last_error` 和 `result_summary`。
2. 如果是 `preview_stale`，重新预览，不复用旧 session confirm。
3. 如果是 worker/queue 失败，确认 `import` worker、`import.process.requested` event、RabbitMQ/Redis/Postgres queue 状态。
4. 如果导入确认已成功但消费页 stale，先实际访问该页，再检查该页 query gateway 创建的精确 dirty scope 和 worker readiness。
5. 禁止通过前端本地状态手动标记下游页面 fresh。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-08-11 | 服务端恢复、owner 隔离和显式放弃闭环 | 预览不再依赖单一浏览器 key；AppHealth 可区分待确认、队列、处理、完成、失败和放弃 | `tests/test_import_lifecycle_service.py`、`tests/test_import_file_api.py`、`web/src/test/ImportCenterPage.test.tsx` |
| 2026-08-11 | 候选版本定点恢复旧 background snapshot 污染产生的银行导入死信 | 只对白名单 job/event/session/files 做 dry-run fingerprint 验真；先完成 canonical 导入再 resolve 精确死信 | `tests/test_import_audit_repair_ops.py` |
| 2026-08-08 | 银行表头统一为 canonical 字段解析与人工映射闭环 | 删除按银行 exact-header 分支；兼容元数据账号、单位/括号差异，未知核心字段 fail closed 并可按表头签名复用人工映射 | `test_ccb_current_export_header_uses_metadata_account_and_unit_aliases`、`test_manual_mapping_is_reused_for_same_header_signature`、`bank transaction import maps an unknown amount header and retries the same file` |
| 2026-07-22 | preview 持久化改为 session-scoped exact delta | 银行预览不再携带历史 session/batch，避免跨导入域 stale snapshot 丢失更新 | `test_preview_session_persistence_payload_excludes_unrelated_sessions_and_canonical_facts`、`test_stale_api_preview_cannot_downgrade_another_process_confirmed_import` |
| 2026-06-11 | 首轮测试闭环状态机补齐 | 明确文件/session/job/worker/read model 状态和禁止流转 | `tests/test_import_*`、`tests/test_import_job_queue.py`、`web/src/test/ImportCenterPage.test.tsx` |
| 2026-06-16 | 修复银行流水导入 job 的 App Status 域 | 银行流水文件确认后的 background job 不再误归到发票导入页；generic import fallback 覆盖全部导入域 | `tests.test_import_file_api`、`tests.test_app_status_overview_service` |
| 2026-07-05 | 模块边界 close 与旧 wrapper 删除 | 银行流水页面 file/session 状态机锁定；`server.py` 不再保留 import confirm processor wrapper | `tests.test_platform_runtime_boundary_guards` |
