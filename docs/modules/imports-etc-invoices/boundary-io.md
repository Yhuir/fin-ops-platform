# ETC发票导入模块边界与 I/O

日期：2026-07-22

## 模块化状态

- 状态：close
- 当前边界可信度：high
- 目标边界：ETC 发票导入通过 ETC parsers/import job/reconciliation services 进入 ETC 批次和发票附件识别链路。
- 当前闭环：Web preview 把 task/version/hash、原始 ZIP file object、preview fingerprint/counts/match edges 持久化到 `app.etc_import_sessions` / `app.etc_import_session_files`；独立 worker 只按 durable session id 重载并处理。预览热路径以已验证的 MinIO/S3 object ref 作为附件存在性事实，不重复下载全部历史 ETC 附件；archive verified write 与 session repository commit 成功后直接返回已持久化 session，只有后续 validate/worker 重载才读取 ZIP bytes。对账需求的全局发票组合只接收已满足车牌与日期窗口的候选，避免无关发票进入组合搜索或被错误分配。页面统一 Audit 已登记为 direct-canonical、zero own read model、ETC internal-relation consumer。
- 当前缺口：真实 confirm/worker drain、外部 ETC control total 和 OA 草稿仍是发布前 external smoke/evidence 风险，不由数据库 Audit 伪装为已证明；59 ZIP preview 的 PostgreSQL session commit 与 MinIO verified write 已有生产 smoke 证据。
- 旧代码删除状态：进程内 `_import_sessions` / `_etc_reconciliation_import_previews`、inline confirm 和旧 `POST /api/etc/import` 410 runtime surface 已删除；历史污染清理由 `docs/operations/invoice-pool-cleanup.md` 和独立工具负责。

## 职责边界

### 负责

- ETC 发票文件/ZIP 上传、过滤、解析、预览和确认。
- 触发 ETC reconciliation 与附件识别领域流程；普通确认不触发页面 read model lifecycle fan-out。
- 为 ETC 票据管理页面提供导入后业务事实。
- 后台导入 job 完成后，`result_summary` 必须返回精确 affected months；普通导入的页面 read model targets 与 operation barrier targets 为空，queued admission 阶段不得伪造 targets。

### 不负责

- 不直接维护 ETC 票据页面 UI 状态。
- 不直接写 workbench relation/read model。
- 不处理普通发票导入模板。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| ETC 文件/ZIP | `ImportEtcInvoicesPage.tsx` | 原件先经 verified file-object I/O 登记；route 不保存 bytes |
| 预览确认 | import workflow | preview application service 持久化 session；confirm 只创建 durable job/outbox |
| Reconciliation trigger | ETC services | 产生后续候选和 lifecycle |
| Ready task selector | `EtcReconciliationTaskService.list_ready_for_import_tasks()` | 下拉标题使用 reconciliation task `title`；ETC business batch title 修改后由 ETC 票据管理同步该 task title，导入页不得自行派生或缓存旧标题 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| ETC import preview/result | 前端页面 | 可审计、可失败恢复 |
| ETC import session/files | PostgreSQL + object storage | metadata/edge 在 PostgreSQL；ZIP bytes 只经窄 file-object port；import worker 必须用与 API 相同的对象存储环境配置构造 state store，才能跨进程重载 `minio://` / S3 archive ref |
| Worker 完成后的 ETC 查询 | PostgreSQL state store -> reconciliation/business batch/invoice query services | 独立 worker 持久化 task、business batch 和 invoice 后，常驻 API 的只读查询入口必须先重载 PostgreSQL snapshot；不得继续返回进程启动时的旧内存状态，也不得依赖重启 API 才可见 |
| 导入文件事实列表 | `/api/import-facts/files`、HTTP SLO probe | 只返回分页文件摘要字段；不得输出完整 `raw_payload`、`row_results`、`normalized_rows`，预览明细只能走导入 session/preview 边界 |
| ETC batch/invoice facts | ETC services | 供 ETC 票据管理读取 |
| Ready task title | `/imports/etc-invoices` 下拉 | 展示 linked reconciliation task 当前标题，与 business batch `title` 保持同步 |
| Existing canonical metadata delta | `ImportNormalizationService.upsert_etc_invoice(...)` -> `EtcExistingInvoiceLinkService` | 返回 `{invoice, changed}`；只有字段或 source link 真正变化的 invoice 才持久化并贡献 affected month。无 canonical match 或幂等重放必须返回空月份、零 refresh I/O |
| Affected scope | 页面 freshness gateway / 必要领域任务 | 只按真实 changed months 返回精确影响；幂等重放为零影响，不在写路径展开 workbench/relation/tax/search/cost 页面 refresh jobs |
| Job completion result envelope | background job result summary / ETC 票据页 | 返回 `affected_months`、`affected_scope_keys`；普通导入的 `read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` 为空，页面立即结束导入反馈，后续页面访问精确收敛 |
| Imported-invoices removal | ETC reconciliation/business batch service | 只清理 ETC task/import batch/business batch 自有事实并返回 changed months；不得返回或执行 canonical invoice 删除计数 |

## 持久化与投影

- Own read model：无独立 manifest entry；页面 Audit `registered_read_model_keys=[]`。
- 逻辑影响 read model：`workbench`、`workbench_relation`、`invoice_lifecycle`、`search`、`tax_offset`、`cost_statistics`；普通导入不直接投递这些页面模型，页面访问通过各 owner freshness gateway 收敛。显式维护命令的 targets 只由对应 owner 返回。
- Worker：`etc_invoice_import.confirm` 只走 `job.import_jobs` + `import.process.requested`；worker 幂等执行 `begin_import`，Web 不 inline。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/imports/ImportEtcInvoicesPage.tsx` |
| Frontend components | `web/src/components/imports/ImportWorkflowPage.tsx` |
| Frontend feature | `web/src/features/etc/api.ts`、`features/etc/types.ts`、`features/imports/importRoutes.ts` |
| Backend route | `routes_etc_import.py`、`routes_etc_reconciliation.py`、ETC import dispatch in `server.py` |
| Backend service | `etc_service.py`、`etc_reconciliation_service.py`、`etc_reconciliation_zip_filter.py`、`etc_document_parsers.py`、`import_processing_service.py` |
| Recognition/lifecycle | `invoice_attachment_recognition_service.py`、`derived_data_lifecycle_service.py`、`runtime_worker_handlers.py` |
| Tests | `tests/test_etc_*.py`、`tests/test_import*.py`、`web/e2e/imports-etc-invoices-flow.spec.ts` |

## 依赖方向

- 允许依赖：ETC parsers, import job queue, reconciliation service, attachment recognition。
- 必须通过：ETC import/reconciliation service。
- 禁止绕过：导入流程直接写 workbench relation；把 repair 工具作为常规 API；删除/重导链路调用通用 import service 清理 `app.invoices` 里的 legacy ETC canonical 污染；用 ETC issue/passage 日期为无变化重放伪造 changed month；恢复 `include_all=true`、写后页面 fan-out 或 direct Cost/repair fan-out。

## 测试与验证

- `tests/test_etc_backend.py`
- `tests/test_etc_reconciliation_import_cleanup_service.py`
- `tests/test_import_job_queue.py`
- `tests/test_import_processing_service.py`
- `web/src/test/EtcTicketManagementPage.test.tsx`
- `web/e2e/imports-etc-invoices-flow.spec.ts`

## 当前缺口和删除条件

- ETC zip parser/filter 变更必须覆盖导入、票据管理和关联台候选回归。
- 旧 ETC canonical 污染清理不再属于本模块 runtime I/O；如果生产历史数据仍有污染，只能按 `docs/operations/invoice-pool-cleanup.md` 在备份、dry-run 和用户确认后处理。

## Canonical facts ownership

- Owned facts: `app.etc_invoices`、ETC 导入 session/batch facts、与 ETC 发票导入直接相关的 `app.import_*` facts。
- Shared facts: `app.invoices` 仍由 canonical invoice pool owner 管理；ETC 只能通过受控 existing-link/promotion port 关联，不创建第二发票池。
- Allowed writes: ETC import preview/confirm/job、ETC import processing service、受控 batch invoice link adapter。
- Allowed reads: ETC import/query ports、canonical invoice existing-link ports。
- Downstream outputs: ETC tickets canonical facts，以及 workbench、workbench_relation、tax/cost/search 可比较的 source-version 变化；各页面访问 gateway 自行创建精确 dirty scope。
- Forbidden paths: `app.etc_invoices` 不得被当作 canonical invoice pool；ETC metadata 不得绕过 invoice owner 直接写 `app.invoices`。
- Old code deletion: 旧 ETC 导入 fallback、pickle/import snapshot 写事实路径、runtime canonical cleanup surface 已删除；historical repair / invoice-pool cleanup 工具保留不算页面/API closure 阻断。

## Audit v19 session 版本边界（2026-07-12）

- migration 0101 为新 `app.etc_import_sessions` 设置 `audit_contract_revision=etc-import-page-audit.v1` 默认值，不回填历史/合成 session。
- 当前 revision session 必须严格证明 ZIP file object/hash、preview requirement edge、fingerprint、task version、job/outbox；缺失一律阻断。
- revision 为 NULL 的历史 session 只报告 `legacy_session_provenance_unproven`；禁止从当前 ETC invoice 反向生成不存在的 ZIP/session 证据。
- v20 中 import batch/invoice edge 按历史事件成员与当前 provenance owner 两个不同方向证明；重复导入不会覆盖首个 owner，也不能因此被误报为关系缺失。
- `preview_ready`/`failed` 历史 session 只有在其精确 `task_id` 当前已进入正式 `imported` 或 `closed` 时，才可作为已被后续正式结果覆盖并降为 warning；未完成 task、活动 job/outbox、缺失 task 或其它关系冲突仍必须阻断。该口径复用 ETC 票据 Audit 的 `COVERED_IMPORT_TASK_STATUSES`，禁止两套覆盖规则漂移。
- `succeeded` session 的精确 task 可以处于导入完成时的 `imported`，也可以在后续 OA 提交流程合法推进为 `closed`；两者复用同一 `COVERED_IMPORT_TASK_STATUSES`。`partial_success` 仍要求 `ready_for_import`，其它状态与缺失 output edge 继续阻断。
