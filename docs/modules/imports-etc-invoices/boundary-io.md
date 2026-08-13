# ETC发票导入模块边界与 I/O

日期：2026-07-22

## 模块化状态

- 状态：close
- 当前边界可信度：high
- 目标边界：ETC 发票导入通过 ETC parsers/import job/reconciliation services 进入 ETC 批次和发票附件识别链路。
- 当前闭环：Web preview 把 task/version/hash、原始 ZIP file object、preview fingerprint/counts/match edges 持久化到 `app.etc_import_sessions` / `app.etc_import_session_files`；独立 worker 只按 durable session id 重载并处理。预览热路径只展开一次 ZIP manifest 并复用已解析 XML，安全限制、匹配、allowlist 裁剪和 import audit 共用同一事实；嵌套 ZIP 保留原始存储路径，并单独生成 GB18030/UTF-8 可读展示路径。对账需求按车牌、通行起止时间、金额和票数做全局一对一分配，禁止使用开票时间代替通行时间。页面统一 Audit 已登记为 direct-canonical、zero own read model、ETC internal-relation consumer。
- 当前缺口：真实 confirm/worker drain、外部 ETC control total 和 OA 草稿仍是发布前 external smoke/evidence 风险，不由数据库 Audit 伪装为已证明；59 ZIP preview 的 PostgreSQL session commit 与 MinIO verified write 已有生产 smoke 证据。
- 旧代码删除状态：进程内 `_import_sessions` / `_etc_reconciliation_import_previews`、inline confirm 和旧 `POST /api/etc/import` 410 runtime surface 已删除；历史污染清理由 `docs/operations/invoice-pool-cleanup.md` 和独立工具负责。

## 职责边界

### 负责

- ETC 发票文件/ZIP 上传、过滤、解析、预览和确认。
- 触发 ETC reconciliation 与附件识别领域流程；普通确认不触发页面 read model lifecycle fan-out。
- 为 ETC 票据管理页面提供导入后业务事实。
- 后台导入 job 完成后，`result_summary` 必须返回精确 affected months；普通导入的页面 read model targets 与 operation barrier targets 为空，queued admission 阶段不得伪造 targets。
- 相同 import idempotency key 只接受相同 request fingerprint；瞬时失败把业务 job 归还 pending 并由 durable outbox 重试，达到最大次数才终态失败。用户再次确认同一请求时，terminal failed/partial job 必须原子复用原 job id 并重新 queued/pending，禁止新建冲突 job；不同 fingerprint 返回结构化 `409 idempotency_conflict`。processing lease 只有超时后才能被其它 worker 接管。
- background job 运行状态只按 canonical `job_id` 单行读写；禁止 ETC 导入 worker 全量回写历史 background job snapshot，历史 raw payload 的旧 id 不得污染当前任务。

### 不负责

- 不直接维护 ETC 票据页面 UI 状态。
- 不直接写 workbench relation/read model。
- 不处理普通发票导入模板。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| ETC 文件/ZIP | `ImportEtcInvoicesPage.tsx` | 原件先经 verified file-object I/O 登记；route 不保存 bytes |
| 预览确认 | import workflow | preview application service 持久化 session；confirm 只创建 durable job/outbox |
| 页面手动刷新 | import workflow | 重新读取当前可导入的 ETC 对账任务；保留当前文件选择，不执行浏览器 reload 或跨页面 refresh。 |

ETC preview 与 confirm 都是写入操作，必须在 multipart/JSON 解析前通过共享 mutation guard；confirm job owner 只取已认证 session username，不再调用容错型 owner resolver 或接受客户端 actor。
| Reconciliation trigger | ETC services | 产生后续候选和 lifecycle |
| Ready task selector | `EtcReconciliationTaskService.list_ready_for_import_tasks()` | 下拉标题使用 reconciliation task `title`；导入页不得自行缓存旧标题，手动刷新重新读取当前 ready tasks。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| ETC import preview/result | 前端页面 | 可审计、可失败恢复；missing requirement 返回需求 ID、缺票数、金额、车牌、通行时间和处理提示，非法 ZIP 明确阻止确认 |
| ETC import session/files | PostgreSQL + object storage | metadata/edge 在 PostgreSQL；ZIP bytes 只经窄 file-object port；import worker 必须用与 API 相同的对象存储环境配置构造 state store，才能跨进程重载 `minio://` / S3 archive ref |
| Worker 完成后的 ETC 查询 | PostgreSQL state store -> reconciliation/business batch/invoice query services | 独立 worker 持久化 task、business batch 和 invoice 后，常驻 API 的只读查询入口必须先重载 PostgreSQL snapshot；不得继续返回进程启动时的旧内存状态，也不得依赖重启 API 才可见 |
| OA 草稿后续状态 | ETC 票据管理页面 | 导入模块只产出 imported business batch；不得创建、检测、重试或恢复 OA 草稿。用户发起创建后 creating/pending 都由 ETC 票据页作为暂存，并只接受两个 manual-status 决定 |
| 导入文件事实列表 | `/api/import-facts/files`、HTTP SLO probe | 只返回分页文件摘要字段；不得输出完整 `raw_payload`、`row_results`、`normalized_rows`，预览明细只能走导入 session/preview 边界 |
| ETC batch/invoice facts | ETC services | 供 ETC 票据管理读取 |
| Ready task title | `/imports/etc-invoices` 下拉 | 展示 linked reconciliation task 当前标题，与 business batch `title` 保持同步 |
| Existing canonical metadata delta | `ImportNormalizationService.upsert_etc_invoice(...)` -> `EtcExistingInvoiceLinkService` | 返回 `{invoice, changed}`；只有字段或 source link 真正变化的 invoice 才持久化并贡献 affected month。无 canonical match 或幂等重放必须返回空月份、零 refresh I/O |
| Affected scope | 页面 owner / 必要领域任务 | 只按真实 changed months 返回精确影响；幂等重放为零影响，不在写路径展开 workbench/relation/tax/cost 页面 refresh jobs |
| Job completion result envelope | background job result summary / ETC 票据页 | 返回 `affected_months`、`affected_scope_keys`；普通导入的 `read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` 为空，页面立即结束导入反馈，后续页面访问精确收敛 |
| Imported-invoices removal | ETC reconciliation/business batch service | 只清理 ETC task/import batch/business batch 自有事实并返回 changed months；不得返回或执行 canonical invoice 删除计数 |

## 持久化与投影

- Own read model：无独立 manifest entry；页面 Audit `registered_read_model_keys=[]`。
- 逻辑影响消费者：`workbench`、`workbench_relation`、invoice lifecycle、tax offset、cost statistics；普通导入不直接投递这些页面模型，页面访问通过各 owner 边界读取。显式维护命令的 targets 只由对应 owner 返回。
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
- ETC import preview/confirm 只保存 ETC 导入与批次事实；不得上传 OA 附件或调用 OA draft create。OA 草稿仍只能由 ETC 票据管理的独立人工动作触发。
- 旧 ETC canonical 污染清理不再属于本模块 runtime I/O；如果生产历史数据仍有污染，只能按 `docs/operations/invoice-pool-cleanup.md` 在备份、dry-run 和用户确认后处理。

## Canonical facts ownership

- Owned facts: `app.etc_invoices`、ETC 导入 session/batch facts、与 ETC 发票导入直接相关的 `app.import_*` facts。
- Shared facts: `app.invoices` 仍由 canonical invoice pool owner 管理；ETC 只能通过受控 existing-link/promotion port 关联，不创建第二发票池。
- ETC metadata link 是附加 provenance，不得覆盖 canonical invoice 已有的正式 input/output invoice import `source_batch_id` owner。历史上已经被写成 ETC import batch 的 owner，只有当同一 canonical invoice 存在精确一致的 `etc_invoice_import(batch_id)` source-link 时才允许继续读取；未知 owner 仍 fail closed。
- Allowed writes: ETC import preview/confirm/job、ETC import processing service、受控 batch invoice link adapter。
- Allowed reads: ETC import/query ports、canonical invoice existing-link ports。
- Downstream outputs: ETC tickets canonical facts，以及 workbench、workbench_relation、tax/cost 可比较的 source-version 变化；保留 read model 的页面访问 gateway 自行创建精确 dirty scope，direct-canonical 页面直接读取 facts。
- Forbidden paths: `app.etc_invoices` 不得被当作 canonical invoice pool；ETC metadata 不得绕过 invoice owner 直接写 `app.invoices`。
- Old code deletion: 旧 ETC 导入 fallback、pickle/import snapshot 写事实路径、runtime canonical cleanup surface 已删除；historical repair / invoice-pool cleanup 工具保留不算页面/API closure 阻断。

## Audit v19 session 版本边界（2026-07-12）

- migration 0101 为新 `app.etc_import_sessions` 设置 `audit_contract_revision=etc-import-page-audit.v1` 默认值，不回填历史/合成 session。
- 当前 revision session 必须严格证明 ZIP file object/hash、preview requirement edge、fingerprint、task version、job/outbox；缺失一律阻断。
- revision 为 NULL 的历史 session 只报告 `legacy_session_provenance_unproven`；禁止从当前 ETC invoice 反向生成不存在的 ZIP/session 证据。
- v20 中 import batch/invoice edge 按历史事件成员与当前 provenance owner 两个不同方向证明；重复导入不会覆盖首个 owner，也不能因此被误报为关系缺失。
- `preview_ready`/`failed` 历史 session 只有在其精确 `task_id` 当前已进入正式 `imported`、`closed` 或 `deleted` 时，才可作为已被后续正式结果覆盖并降为 warning；未完成 task、活动 job/outbox、缺失 task 或其它关系冲突仍必须阻断。`deleted` 只属于导入 session 的后续覆盖状态，不加入 ETC 票据页面的 active task 覆盖集合。
- `succeeded` session 的精确 task 可以处于导入完成时的 `imported`，也可以在后续 OA 提交流程合法推进为 `closed` 或由受控删除流程进入 `deleted`。`partial_success` 仍要求 `ready_for_import`，其它状态与缺失 output edge 继续阻断。
- 历史上已被合法删除 task 遗留的严格 session 可以通过 `import-audit-repair --retire-etc-session-id` 标记为 `etc-import-page-audit.v1.deleted-task-retired`；新审计仍把该 revision 当作严格合同逐项验证，标记只用于让旧审计在候选激活前识别其为归档历史。工具保留 session、ZIP/file-object 与 output edge，不允许活动 job/outbox 或隐式扫描目标。
