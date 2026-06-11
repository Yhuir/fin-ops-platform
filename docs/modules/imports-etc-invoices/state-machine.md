# ETC发票导入状态机

> 修改 `ETC发票导入` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。

## 业务状态

### Reconciliation Task

事实源：`EtcReconciliationTaskService`。

| 状态 | 含义 | 导入语义 |
| --- | --- | --- |
| `draft` / `reviewing` | 对账任务仍在编辑或复核 | 不能作为 ETC zip 导入任务 |
| `ready_for_import` / confirmed task | 对账已确认，具备 `confirmed_item_set_hash` | 可在 `/imports/etc-invoices` 中选择并预览 zip |
| `importing` | ETC import confirm 已开始，任务被锁定 | 不允许重复 preview/confirm；等待 job |
| `imported` | 导入成功，绑定 import batch/business batch | 不能重复导入，除非先移除已导入发票 |
| `import_failed` / ready retry | confirm job 失败或 partial success | 可按当前 task/version/hash 重新预览或重试 |
| `closed` / `deleted` | 任务关闭或本地删除 | 不能导入 |

### Zip Preview

事实源：`preview_etc_zip_for_task(...)`、`EtcService.preview_import_zips(...)` 和 `_etc_reconciliation_import_previews[session_id]`。

| 状态 | 含义 | 允许流转 |
| --- | --- | --- |
| `task_selected` | 前端已选择 ready task | `zip_selected`、切换 task |
| `zip_selected` | 本地选择一个或多个 zip 文件 | `previewing`、清空 |
| `previewing` | 调用 `/api/etc/import/preview` | `preview_ready`、`preview_blocked`、`error`、unmount cleanup |
| `preview_ready` | 生成 ETC import session 和 reconciliation filter | `confirming`、重新预览、清空 |
| `preview_blocked` | 缺少必要 ETC 发票、匹配歧义或无 allowlist | 不能 confirm；需要修正 task/source/zip |
| `preview_stale` | canonical invoice 或 import session 已变化 | 只能重新预览 |
| `task_preview_stale` | task version/hash/source facts 已变化 | 清空 preview，重新读取 task 后再 preview |

### Confirm / Job

| 状态 | 含义 | 允许流转 |
| --- | --- | --- |
| `confirming` | 前端提交 `/api/etc/import/confirm` | `queued`、`error` |
| `queued` | `etc_invoice_import` background job 创建 | `processing`、`failed`、可轮询 |
| `processing` | `etc_invoice_import.confirm` processor 正在写入 | `succeeded`、`partial_success`、`failed` |
| `succeeded` | 所有匹配发票导入成功，task 标记 imported | downstream refreshing |
| `partial_success` | 部分 item 失败，task 标记 import failed 可重试 | 保留错误，允许重试 |
| `failed` | job 或 service 失败 | task 标记 import failed，不能把旧 preview 当 fresh |

### ETC Business Batch / OA Manual Status

ETC zip confirm 会创建或复用 task-scoped business batch。后续状态主要由 ETC 票据管理页面维护，但导入模块必须知道其回归影响：

- `draft` / `imported`：本地 ETC 发票已导入，尚未创建 OA 草稿。
- `oa_confirmation_pending`：已创建 OA 草稿，等待用户人工确认。
- `manually_marked_submitted` / submitted：生成 folded `etc_invoice_summary`，散票隐藏，等待关联台普通配对。
- `not_submitted`：释放本地 ETC 发票占用，回到未提交链路。
- `deleted`：本地业务批次、导入事实、summary row 或散票占用被清理；不删除真实 OA。

## 禁止流转

- 没有 ready reconciliation task 不得 preview。
- 非 `.zip` 文件不得进入 ETC import preview。
- `preview_blocked`、`preview_stale`、`task_preview_stale` 不得 confirm。
- task version 或 `confirmed_item_set_hash` 不匹配时不得继续 import。
- `queued` / `processing` 不得让 ETC、关联台、税金或成本页面显示 fresh。
- business batch 已创建 OA 草稿后不得追加补充导入，除非先 revoke 回未提交链路。
- 删除 submitted business batch 不得删除真实 OA 草稿或 OA 已提交事实。

## UI 状态

- loading：ready task 加载、zip preview、confirm、job polling、source task refresh 时展示局部 loading；route unmount 必须清理 in-flight preview 状态。
- empty：没有 ready task 时展示不可导入原因，不显示可确认按钮。
- error：非 zip、缺少 task、unknown task、storage unavailable、queue unavailable、job failed、manual status failed 必须有可见反馈。
- stale/refreshing：`stale_reconciliation_task_preview` 清空 preview 并要求重新预览；downstream stale/refreshing 由各自 read model status 呈现。
- permission disabled/hidden：当前导入写权限由后端 contract 决定；若未来增加前端权限显示，必须补隐藏/禁用交互测试。

## Read Model / Worker 状态

| 状态 | 事实源 | UI/调用方语义 |
| --- | --- | --- |
| `fresh` | 下游 read model source_versions 与 ETC/canonical facts 匹配 | 页面可展示并允许依赖 fresh 的写入 |
| `missing` | read model scope 不存在 | API 应 enqueue refresh 并返回 refreshing/missing 语义 |
| `refreshing` | dirty scope/job 已排队或处理中 | 页面显示刷新中，不能把旧数据当最终结果 |
| `stale` | source_versions 或 dirty scope 表明旧数据 | 页面禁用依赖 fresh 的写入，提示刷新 |
| `failed` | import job、worker 或 read model refresh 失败 | App Status/App Health 应暴露阻塞或 busy 详情 |
| `unavailable` | durable queue、repository、对象存储或 worker plane 不可用 | 不能用 cache 伪造 fresh |

刷新触发来源：

- `etc_import_confirmed`
- `etc_reconciliation_task_deleted`
- business batch manual OA status submitted/not submitted
- business batch delete / submitted summary reset
- historical ETC repair / existing batch link

失败恢复：

- ETC import job failure 通过 background job 和 reconciliation task `import_failed` 暴露。
- `partial_success` 需要保留失败 item，允许用户按当前 task 重新预览或重试。
- 下游 read model failure 由对应 worker/readiness 负责，ETC 导入页不能替下游页面做 fresh 判定。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 首轮补齐 ETC 发票导入状态机 | 明确 task/zip preview/confirm job/business batch/read model 状态边界 | `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`web/src/test/ImportCenterPage.test.tsx`、`bash scripts/verify.sh docs` |
