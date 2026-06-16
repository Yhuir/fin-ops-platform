# 发票导入状态机

> 修改 `发票导入` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。

## 业务状态

### FileImportSession

事实源：`FileImportService` session snapshot，API 输出由 `/imports/files/*` 返回。

| 状态 | 含义 | 允许流转 |
| --- | --- | --- |
| `files_selected` | 前端本地状态，用户已选择一个或多个文件 | `files_configured`、清空 |
| `files_configured` | 每个文件已选择 `input_invoice` 或 `output_invoice` | `previewing`、清空 |
| `previewing` | 前端正在调用 `/imports/files/preview` | `preview_ready`、`preview_ready_with_errors`、`error`、unmount cleanup |
| `preview_ready` | 所有可识别文件生成 preview batch，可选择确认 | `confirming`、重新预览、清空 |
| `preview_ready_with_errors` | 至少一个文件不可识别或存在 file-level error | 可确认其中 `preview_ready` 文件，或重试/重新预览 |
| `preview_stale` | 后端检测当前 preview 与最新发票事实不一致 | 只能重新预览 |
| `confirming` | 前端已提交确认，等待同步结果或 job | `queued`、`confirmed`、`error` |
| `queued` | 确认交给 `file_import` background job；发票文件确认 job 的 App Status domain 为 `imports_invoices`、route 为 `/imports/invoices` | `processing`、`failed`、轮询 |
| `processing` | import worker 正在处理确认 | `confirmed`、`failed` |
| `confirmed` | 选中文件已确认，发票事实写入或已幂等确认 | 下游 read model 仍需 freshness 判断 |
| `skipped` | 未选中文件或没有可确认 preview batch | 终态，可重新上传 |
| `failed` | job 或同步确认失败 | 可重试或重新预览，不能把旧结果当 fresh |

### 发票事实与生命周期

- `input_invoice` / `output_invoice` batch type 是导入事实方向，不能在 confirm 后被前端随意改写。
- 发票 source links、canonical invoice identity、duplicate decisions 由 `ImportNormalizationService` 决定。
- `invoice_import_confirmed` 是 derived lifecycle 入口，必须先覆盖 `invoice_lifecycle`，再影响待找发票、税金、进项/销项/OA 待付款、成本统计和搜索。
- job 成功只代表导入写入完成，不代表下游页面 fresh。

## 禁止流转

- 未选择每文件 `batch_type` 时不得预览发票导入。
- `unrecognized_template` / file-level error 文件不得被当作 confirmed。
- `preview_stale` 不得继续 confirm；必须重新预览。
- `queued` / `processing` 不得向下游页面报告 fresh。
- `confirmed` 后不得绕过 lifecycle/dirty scope 直接让下游 read model 复用旧 cache。
- unknown selected file ids 必须失败，不能静默忽略。

## UI 状态

- loading：文件 preview、confirm、job polling、session restore 时显示当前导入动作；卸载后不得保留 in-flight 状态污染新路由。
- empty：未选择文件时不能显示可确认状态。
- error：文件读取失败、模板不识别、权限/API 错误、job failure 必须有用户可见反馈。
- stale/refreshing：`preview_stale` 显示重新预览提示；下游页面 stale/refreshing 由各自 read model status 呈现。
- permission disabled/hidden：当前导入写权限由后端 contract 决定；若未来增加前端权限显示，必须补隐藏/禁用交互测试。
- session persistence：同一路由重挂载可恢复 preview；清空文件必须清理 persisted preview。

## Read Model / Worker 状态

| 状态 | 事实源 | UI/调用方语义 |
| --- | --- | --- |
| `fresh` | 下游 read model source_versions 与发票事实匹配 | 页面可展示并允许对应写入 |
| `missing` | read model scope 不存在 | API 应 enqueue refresh 并返回 refreshing/missing 语义 |
| `refreshing` | dirty scope/job 已排队或处理中 | 页面显示刷新中，不能把旧数据当最终结果 |
| `stale` | source_versions 或 dirty scope 表明旧数据 | 页面禁用依赖 fresh 的写入，提示刷新 |
| `failed` | worker/job/readiness 失败 | App Status/App Health 应暴露阻塞或 busy 详情 |
| `unavailable` | durable queue、repository 或 worker plane 不可用 | 不能用 Redis/RabbitMQ cache 伪造 fresh |

刷新触发来源：

- `invoice_import_confirmed`
- `manual_invoice_confirmed`
- `tax_certified_import_confirmed`
- `pair_relation_changed` / `workbenchRelationUpdated` 相关下游链路
- `startup_stale_scan` 默认关闭，且不直接刷新发票相关 read model；它只标记 workbench matching dirty scopes。

失败恢复：

- import job failure 通过 background job 状态和 App Status 暴露。
- 下游 read model failure 由对应 worker/readiness 负责，导入页不能替下游页面做 fresh 判定。
- 重新预览可恢复 `preview_stale`，但不能修复 worker/read model failed。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-16 | 补齐发票确认 job 的 App Status domain/route contract | `file_import` 发票确认不再落到泛化导入页面，跨页状态反馈可回到 `/imports/invoices`；共享 `import.process.requested` 仍作为多导入域兜底 | `tests/test_import_file_api.py::ImportFileApiTests::test_confirm_files_imports_only_selected_files_from_session`、`tests/test_app_status_overview_service.py`、`web/src/test/AppStatusIndicator.test.tsx` |
| 2026-06-11 | 首轮补齐发票导入状态机 | 明确 file/session/job/lifecycle/read model 状态边界 | `tests/test_import_*`、`web/src/test/ImportCenterPage.test.tsx`、`bash scripts/verify.sh docs` |
