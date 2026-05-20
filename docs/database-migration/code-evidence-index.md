# 代码证据索引

本文记录数据库迁移前必须引用的代码证据。后续 Codex 执行迁移任务时，必须先读取对应文件，不得凭本文摘要直接改代码。

## 入口和装配

| 文件 | 迁移证据 |
| --- | --- |
| `backend/src/fin_ops_platform/app/main.py` | CLI 入口，当前支持 `--check` 和启动 HTTP 服务。后续可加 migration/export/import 命令，或新增独立 tools module。 |
| `backend/src/fin_ops_platform/app/server.py` | 当前主 HTTP server。`Application.__init__` 创建 `ApplicationStateStore`，加载 persisted state，初始化所有 service，并绑定 `MongoOAAdapter`。迁移期 repository、dual-write、shadow-read 都会触达此文件。 |
| `backend/src/fin_ops_platform/app/auth.py` | OA session 和权限上下文。迁移不能破坏 actor/user id 获取，因为写操作审计依赖该上下文。 |
| `backend/src/fin_ops_platform/app/routes_workbench.py` | 旧 workbench route adapter，部分测试仍可引用。 |
| `backend/src/fin_ops_platform/app/routes_tax.py` | 税金 route adapter。 |
| `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` | 往来款 route adapter 和 in-memory extra service。 |

阶段 00 路由副作用索引：

- `Application.__init__` 创建 `ApplicationStateStore`，读取 OA sync state，初始化 `OASyncService`、runtime services、后台恢复和 ETC 恢复逻辑。
- `MongoOAAdapter` 只在 `_initialize_runtime_services()` 中根据配置创建，注入 `IntegrationHubService`、`AppSettingsService`、`WorkbenchQueryService`、`OAManualImportService`。
- `/api/workbench/actions/*`、`/api/workbench/settings/*`、`/imports/*`、`/api/bank-details/*`、`/api/no-oa-bank-batches/*`、`/api/batch-accounting/*`、`/api/turnover-ledger/*`、`/api/tax-offset/*`、`/api/etc/*` 是主要写入和 read model 失效面。
- `/api/background-jobs/*` 写 job acknowledge/retry 状态；`/api/app-health/*` 主要读健康快照和 SSE。
- `/health`、`/foundation/seed`、`/api/session/me`、`/api/oa-sync/status` 主要只读，但 session/permission 结果会影响所有 mutation 审计和授权。

## 领域模型

| 文件 | 迁移证据 |
| --- | --- |
| `backend/src/fin_ops_platform/domain/models.py` | `Invoice`、`BankTransaction`、`ReconciliationCase`、`ImportedBatch`、`MatchingRun` 等核心 dataclass。PostgreSQL 表字段必须从这里和实际 payload 双向校准。 |
| `backend/src/fin_ops_platform/domain/enums.py` | 发票、流水、核销、导入、匹配等状态枚举。迁移时不能猜状态值，必须以枚举和生产数据分布为准。 |

阶段 00 已确认的迁移状态值和 identity 证据：

- `InvoiceStatus`：`pending`、`partially_reconciled`、`reconciled`、`pending_offline_confirmation`、`pending_offset`、`pending_invoice_issue`、`pending_invoice_receive`。
- `TransactionStatus`：`pending`、`partially_reconciled`、`reconciled`、`classified_as_prepayment`、`classified_as_advance_receipt`、`pending_refund`、`pending_counterparty_confirmation`。
- `BatchStatus`：`pending`、`completed`、`completed_with_errors`、`reverted`、`failed`。
- `ImportDecision`：`created`、`status_updated`、`duplicate_skipped`、`suspected_duplicate`、`error`。
- `MatchingResultType`：`automatic_match`、`suggested_match`、`manual_review`。
- 发票稳定 identity：优先数电发票号，其次发票代码+发票号码，再到税号/日期/金额组合；银行流水稳定 identity：`bank:{account_no}:{trade_time}:{direction}:{amount}:{counterparty_name}`。

## 持久化和 Mongo

| 文件 | 迁移证据 |
| --- | --- |
| `backend/src/fin_ops_platform/services/state_store.py` | 当前 app 持久化核心。包含 app Mongo 配置、detailed collections、GridFS bucket、pickle payload 读写、所有 `load_*` / `save_*` 边界。PostgreSQL repository 必须覆盖这些公共方法。 |
| `backend/src/fin_ops_platform/services/mongo_oa_adapter.py` | OA Mongo 只读读取。包含 `MongoOASettings`、form id、状态归一化、OA records、附件发票解析缓存、ETC OA 检测候选。迁移禁止改为写 OA Mongo。 |
| `backend/src/fin_ops_platform/services/oa_adapter.py` | OA adapter protocol 和 in-memory adapter。PostgreSQL OA 投影应兼容该抽象。 |
| `backend/src/fin_ops_platform/services/oa_manual_import_service.py` | 手工导入 OA 行状态依赖 state store 的 `load_manual_oa_imports`、`add_manual_oa_imports`、`remove_manual_oa_import`。 |
| `backend/src/fin_ops_platform/services/oa_sync_service.py` | OA sync dirty/synced/error 状态。后续应落 `app.oa_sync_watermarks` 和 `job` 表。 |
| `backend/src/fin_ops_platform/services/oa_attachment_invoice_service.py` | OA 附件下载和发票解析。缓存迁移需保留 parser version 和 cache key。 |

### `ApplicationStateStore` collection 常量

阶段 00 已只读核对 `state_store.py` 中的 app Mongo collection 常量。PostgreSQL 设计和 backfill 必须覆盖这些集合或明确标记为可重建：

- legacy/snapshot：`application_state`、`imports_state`、`file_import_sessions_state`、`matching_state`、`import_file_metadata`、`app_state_meta`、`imports_meta`、`file_imports_meta`、`matching_meta`。
- 导入事实：`import_batches`、`invoices`、`bank_transactions`、`file_import_sessions`、`file_import_files`、`matching_runs`、`matching_results`。
- 工作台：`workbench_overrides_meta`、`workbench_row_overrides`、`workbench_exception_cases_meta`、`workbench_exception_cases`、`workbench_pair_relations_meta`、`workbench_pair_relations`、`workbench_read_models_meta`、`workbench_read_models`、`workbench_candidate_matches_meta`、`workbench_candidate_matches`、`workbench_matching_dirty_scopes_meta`、`workbench_matching_dirty_scopes`。
- 银行/免 OA/往来：`bank_transaction_categories_meta`、`bank_transaction_categories`、`no_oa_bank_batches_meta`、`no_oa_bank_batches`、`no_oa_bank_batch_audit_log`、`turnover_relations_meta`、`turnover_relations`、`turnover_relation_audit_log`、`turnover_ledger_extras_meta`、`turnover_ledger_extras`。
- 读模型：`cost_statistics_read_models_meta`、`cost_statistics_read_models`、`tax_offset_read_models_meta`、`tax_offset_read_models`。
- OA/app 设置：`oa_attachment_invoice_cache`、`oa_sync_state`、`manual_oa_imports`、`app_settings`。
- 税金/ETC/运维：`tax_certified_imports_meta`、`tax_certified_import_sessions`、`tax_certified_import_batches`、`tax_certified_import_records`、`etc_state`、`etc_reconciliation_state`、`historical_etc_repair_bundles`、`historical_etc_repair_parsed_seeds`、`historical_etc_repair_states`、`background_jobs`、`app_health_alerts`。
- 文件：GridFS bucket `import_file_blobs`，引用前缀 `gridfs://`。

### `ApplicationStateStore` public 方法覆盖

后续 repository interface 必须覆盖以下公共方法语义，而不是只覆盖当前调用最多的几个方法：

| 方法组 | 方法 |
| --- | --- |
| 全局快照 | `load()`、`save(payload)` |
| 设置/OA 状态 | `load_app_settings()`、`save_app_settings()`、`load_oa_sync_state()`、`save_oa_sync_state()`、`load_manual_oa_imports()`、`save_manual_oa_imports()`、`add_manual_oa_imports()`、`remove_manual_oa_import()` |
| OA 附件缓存 | `load_oa_attachment_invoice_cache_entry()`、`save_oa_attachment_invoice_cache_entry()`、`clear_oa_attachment_invoice_cache()` |
| 导入和文件 | `store_import_file()`、`read_import_file()`、`delete_import_files()`、`import_session_exists()`、`import_file_exists()`、`import_batch_exists()`、`invoice_exists()`、`transaction_exists()` |
| 工作台 | `load_workbench_pair_relations()`、`save_workbench_pair_relations()`、`load_workbench_read_models()`、`save_workbench_read_models()`、`load_workbench_candidate_matches()`、`save_workbench_candidate_matches()`、`save_workbench_matching_dirty_scopes()`、`save_workbench_overrides()`、`save_workbench_exception_cases()` |
| 银行/免 OA/往来/读模型 | `load_bank_transaction_categories()`、`save_bank_transaction_categories()`、`load_no_oa_bank_batches()`、`save_no_oa_bank_batches()`、`load_turnover_relations()`、`save_turnover_relations()`、`load_turnover_relation_audit_log()`、`save_turnover_relation_audit_log()`、`load_turnover_ledger_extras()`、`save_turnover_ledger_extras()`、`load_cost_statistics_read_models()`、`save_cost_statistics_read_models()`、`load_tax_offset_read_models()`、`save_tax_offset_read_models()` |
| 税金/ETC | `load_tax_certified_imports()`、`save_tax_certified_imports()`、`load_etc_state()`、`save_etc_state()`、`load_etc_reconciliation_state()`、`save_etc_reconciliation_state()`、`store_etc_reconciliation_file()`、`read_etc_reconciliation_file()`、`store_etc_invoice_file()`、`read_etc_invoice_file()`、`etc_invoice_file_exists()`、`delete_etc_invoice_file()` |
| 历史 ETC/运维 | `save_historical_etc_repair_bundle()`、`load_historical_etc_repair_bundle_metadata()`、`read_historical_etc_repair_bundle()`、`save_historical_etc_repair_parsed_seed()`、`load_historical_etc_repair_parsed_seeds()`、`load_historical_etc_repair_parsed_seed()`、`load_historical_etc_repair_states()`、`save_historical_etc_repair_states()`、`load_background_jobs()`、`save_background_jobs()`、`load_app_health_alerts()`、`save_app_health_alerts()` |

关键证据：许多 Mongo document 的 `payload` 是 Python pickle/Binary；迁移工具不得手写 BSON/pickle 解析入库，必须复用现有 Python 读路径或业务 service 导出规范化对象。

### OA 只读边界

`MongoOAAdapter` 的 Mongo 访问只读：`find(...)`、`count_documents(...)`、`sort()`、`limit()`；未发现 insert/update/delete/drop/createIndex。OA 源库硬约束：

- 源库：`form_data_db`。
- 源 collection：`form_data`。
- 默认 form id：支付申请 `2`、日常报销 `32`、项目主数据 `17`。
- 禁止写入、建索引、修复、清洗或保存 app 迁移状态到 `form_data_db.form_data`。

OA row id 和状态规则：

- 支付申请：`oa-pay-{external_id}`；日常报销：`oa-exp-{external_id}`。
- `external_id` 优先 `data.flowRequestId`，其次 `data.processId`，最后 Mongo `_id`。
- 完成状态归一化为 `completed`，进行中归一化为 `in_progress`；默认导入只接受 `completed`。
- 附件发票 parser version 为 `2026-05-11-evidence-machine-payment`，cache schema 为 `2026-05-11-evidence-v1`，cache key 必须包含 source attachment identity、size、modified time、parser/cache schema。

PostgreSQL OA 投影只允许作为 app 自己的只读同步投影，建议字段包括 `oa_source_id`、`form_id`、`form_type`、`row_id`、`workflow_no`、`status`、`applicant`、`application_date`、`approved_at`、`project_id`、`project_name`、`amount`、`source_updated_at`、`normalized_payload`、`raw_payload`。

## 导入

| 文件 | 迁移证据 |
| --- | --- |
| `backend/src/fin_ops_platform/services/imports.py` | `ImportNormalizationService` 管理导入预览、确认、批次、发票、流水、撤回。PostgreSQL 的 `import_batches`、`invoices`、`bank_transactions` 必须覆盖该服务状态。 |
| `backend/src/fin_ops_platform/services/import_file_service.py` | 文件导入 session、file、模板检测、Excel 解析、文件读取。迁移必须保持 `store_import_file` / `read_import_file` 兼容。 |
| `backend/src/fin_ops_platform/services/import_preview_audit.py` | 导入预览审计和重复判定。PostgreSQL 唯一约束和幂等键应与这里一致。 |
| `backend/src/fin_ops_platform/services/invoice_identity_service.py` | 发票 identity 规则。 |
| `backend/src/fin_ops_platform/services/bank_transaction_identity_service.py` | 银行流水 identity 规则。 |

## 工作台、核销、异常

| 文件 | 迁移证据 |
| --- | --- |
| `backend/src/fin_ops_platform/services/workbench_query_service.py` | 工作台读模型消费方，依赖 OA、银行、发票、关系、覆盖、异常、候选。 |
| `backend/src/fin_ops_platform/services/live_workbench_service.py` | 现场构建 workbench payload。迁移 read model 时必须保证 DTO 等价。 |
| `backend/src/fin_ops_platform/services/workbench_read_model_service.py` | 当前 read model snapshot 管理。PostgreSQL read model 表应保留 scope key、source_versions、payload。 |
| `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py` | 关系事实、active relation、撤回、history。PostgreSQL 关系表必须覆盖 case_id、row_ids、status、relation_mode、history。 |
| `backend/src/fin_ops_platform/services/workbench_override_service.py` | 行级覆盖、忽略、异常和关系投影。迁移必须保留 projection_version 和 changed_row_ids 失效语义。 |
| `backend/src/fin_ops_platform/services/workbench_exception_case_service.py` | 异常 case、settlement case、审计事件、关闭/重开/取消。 |
| `backend/src/fin_ops_platform/services/workbench_exception_application_service.py` | 异常操作 preview/apply。 |
| `backend/src/fin_ops_platform/services/workbench_candidate_match_service.py` | 候选匹配 snapshot、candidate key、scope fresh、stale scope。 |
| `backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_service.py` | dirty scope 队列。后续迁 `job.workbench_matching_dirty_scopes`。 |
| `backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py` | 候选生成 orchestration 和 read model 失效。 |
| `backend/src/fin_ops_platform/services/workbench_matching_rules.py` | 候选匹配规则。 |
| `backend/src/fin_ops_platform/services/workbench_amount_check_service.py` | 确认关系金额校验，关系表需保留 amount_check。 |
| `backend/src/fin_ops_platform/services/reconciliation.py` | 旧手工核销服务和 case 模型。 |
| `backend/src/fin_ops_platform/services/matching.py` | 旧 matching run/result。 |

阶段 00 工作台证据：

- 工作台行关系按行类型分别使用 `oa_bank_relation`、`invoice_relation`、`invoice_bank_relation`；关系表必须可表达 row ids、relation mode、status、amount_check、source_versions、special_metadata 和 active/withdrawn 历史。
- `WorkbenchOverrideService` 快照字段包括 `case_counter`、`projection_version`、`row_overrides`，row override 可覆盖 case、exception、relation、ignored、handled exception、candidate evidence、OA exemption 等。
- `WorkbenchExceptionCaseService` schema version 为 2，case id 形如 `WEX-000001`，active 状态会进入 `row_case_index`，并保留 history/audit。
- `WorkbenchReadModelService` schema 为 `workbench_read_model_service.v1`，freshness 依赖 `source_versions`；candidate/matching/exception/pair relation/turnover relation 变更必须触发 scope 失效。
- `WorkbenchMatchingDirtyScopeService` 按 `YYYY-MM` 维护 dirty scope，失败重排会增加 attempt count；PostgreSQL 目标应落 job/outbox 类表。

## 免 OA、批量核算、往来款

| 文件 | 迁移证据 |
| --- | --- |
| `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py` | 免 OA 批次事实、状态、version、审计。 |
| `backend/src/fin_ops_platform/services/no_oa_legacy_relation_migration_service.py` | 旧关系迁免 OA 批次规则。 |
| `backend/src/fin_ops_platform/services/batch_accounting_service.py` | 批量核算 submit/withdraw，与 workbench relation 和 no OA 状态交互。 |
| `backend/src/fin_ops_platform/services/turnover_relation_service.py` | 往来关系、审计、按银行流水重建。 |
| `backend/src/fin_ops_platform/services/turnover_ledger_service.py` | 往来台账读取。 |
| `backend/src/fin_ops_platform/services/turnover_ledger_extra_service.py` | 台账额外字段。 |
| `backend/src/fin_ops_platform/services/turnover_ledger_export_service.py` | 台账导出。 |

阶段 00 关系类写入证据：

- `NoOaBankBatchService` schema 为 `2026-05-no-oa-bank-batch-v1`，提交只允许 draft 并校验 `expected_version`，撤回允许 submitted 或仍有 active no-OA relation 的 stale；submit/withdraw 都写 audit 并递增 version。
- `BatchAccountingService.submit()` 为特定银行流水和 OA 行创建 `manual_confirmed` relation，金额不一致必须 note；`withdraw()` 要求原因并撤回 active batch accounting relation。
- `TurnoverRelationService` schema 为 `2026-05-turnover-relation-v1`，状态包括 `suggested/deterministic/confirmed/conflict/stale/withdrawn`；分类或流水变更会使 confirmed 变 conflict、其他变 stale。

## 银行明细、成本统计、搜索

| 文件 | 迁移证据 |
| --- | --- |
| `backend/src/fin_ops_platform/services/bank_details_service.py` | 银行账号和流水查询。PostgreSQL 必须提供分页、筛选、搜索能力。 |
| `backend/src/fin_ops_platform/services/bank_transaction_category_service.py` | 银行流水分类覆盖和审计。 |
| `backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py` | 自动分类建议。 |
| `backend/src/fin_ops_platform/services/bank_transaction_effective_category_provider.py` | 分类读取 provider。 |
| `backend/src/fin_ops_platform/services/cost_statistics_service.py` | 成本统计、下钻和导出。 |
| `backend/src/fin_ops_platform/services/cost_statistics_read_model_service.py` | 成本统计 read model 管理。 |
| `backend/src/fin_ops_platform/services/search_service.py` | 全局搜索。迁移后应优先读取 `read_model.search_index_rows`。 |

阶段 00 查询和缓存证据：

- `BankTransactionCategoryService` 更新分类时要求 actor，可选 `expected_version`，并写 audit；有效分类是人工优先、自动其次、否则未分类。
- `CostStatisticsReadModelService` schema 为 `2026-05-cost-statistics-explorer-v1`，scope key 为 `project_scope:month`，`project_scope` 仅 `active/all`，month 支持 `YYYY-MM/all`。
- `SearchService` 有 known months、month index、query 三层 TTL 缓存，默认 30 秒；索引字段覆盖 OA、银行、发票和 ignored rows。

## 税金和 ETC

| 文件 | 迁移证据 |
| --- | --- |
| `backend/src/fin_ops_platform/services/tax_certified_import_service.py` | 已认证发票导入 session/batch/record。 |
| `backend/src/fin_ops_platform/services/tax_offset_service.py` | 税金抵扣页面计算。 |
| `backend/src/fin_ops_platform/services/tax_offset_read_model_service.py` | 税金 read model。 |
| `backend/src/fin_ops_platform/services/etc_service.py` | ETC 发票、批次、业务批次、OA draft、导入、撤回。 |
| `backend/src/fin_ops_platform/services/etc_reconciliation_service.py` | ETC 对账 task、文件、确认、导入状态。 |
| `backend/src/fin_ops_platform/services/etc_reconciliation_models.py` | ETC 对账 dataclass 和状态。 |
| `backend/src/fin_ops_platform/services/etc_reconciliation_matcher.py` | ETC 匹配规则。 |
| `backend/src/fin_ops_platform/services/etc_reconciliation_zip_filter.py` | ETC zip 过滤和确认。 |
| `backend/src/fin_ops_platform/services/etc_document_parsers.py` | ETC PDF/OCR/文本解析。 |
| `backend/src/fin_ops_platform/services/etc_oa_detection.py` | ETC 业务批次关联 OA 检测，依赖 `MongoOAAdapter` 状态归一化。 |
| `backend/src/fin_ops_platform/services/historical_etc_repair_service.py` | 历史 ETC 修复包、解析种子、状态。 |

阶段 00 税金和 ETC 证据：

- 已认证税金导入只持久化已勾选/已认证、发票正常、有效抵扣税额大于 0 的记录；唯一键优先数电号，其次代码+号码，最后销售方+日期+税额。
- `TaxOffsetReadModelService` scope 为 `YYYY-MM`，schema 为 `2026-05-tax-offset-month-v1`。
- ETC 状态面包括 `EtcInvoice`、`EtcImportSession`、`EtcImportBatch`、`EtcBatch`、`EtcBusinessBatch`、`EtcReconciliationTask`，附件文件横跨 GridFS/local/state store 外部引用。
- `EtcBusinessBatch` 绑定 `task_id`，同一 task 只允许一个 active 业务批次；必须保留 version、audit events、import attempts、OA draft/detection 字段。
- ETC OA detection 只读 OA，优先 marker `business_batch_id=...`，其次 `etc_batch_id=...`，并校验 form id、金额、发票数量、申请人/组织、创建窗口和流程状态。

## 设置、权限、运维

| 文件 | 迁移证据 |
| --- | --- |
| `backend/src/fin_ops_platform/services/app_settings_service.py` | 设置读取/更新、项目同步、银行账号映射、权限用户名、OA 保留和导入设置。 |
| `backend/src/fin_ops_platform/services/access_control_service.py` | 权限判定。迁移必须保持设置和环境变量 fallback。 |
| `backend/src/fin_ops_platform/services/oa_role_sync_service.py` | OA MySQL 角色同步，可写外部 MySQL；与本次 OA Mongo 只读约束不同，需单独审计。 |
| `backend/src/fin_ops_platform/services/background_job_service.py` | 后台任务生命周期、幂等、重试、确认。 |
| `backend/src/fin_ops_platform/services/app_health_service.py` | 健康快照，依赖 read model、dirty scope、background jobs。 |
| `backend/src/fin_ops_platform/services/app_health_alert_service.py` | 健康告警。 |
| `backend/src/fin_ops_platform/services/settings_data_reset_service.py` | 数据重置高风险操作。迁移后必须重新验证受保护目标。 |
| `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py` | 派生数据失效和执行计划。 |

## 前端 API 证据

迁移后必须保持以下 feature API 的路径和 DTO 兼容：

- `web/src/features/workbench/api.ts`
- `web/src/features/appHealth/api.ts`
- `web/src/features/backgroundJobs/api.ts`
- `web/src/features/bankDetails/api.ts`
- `web/src/features/batchAccounting/api.ts`
- `web/src/features/cost-statistics/api.ts`
- `web/src/features/etc/api.ts`
- `web/src/features/imports/*`
- `web/src/features/noOaBankBatches/api.ts`
- `web/src/features/tax/api.ts`
- `web/src/features/turnoverLedger/api.ts`

主要页面：

- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/pages/SettingsPage.tsx`
- `web/src/pages/AppHealthOperationsPage.tsx`
- `web/src/pages/NoOaBankBatchPage.tsx`
- `web/src/pages/CostStatisticsPage.tsx`
- `web/src/pages/TaxOffsetPage.tsx`
- `web/src/pages/TurnoverLedgerPage.tsx`
- `web/src/pages/imports/*`

阶段 00 前端合约证据：

| feature | PostgreSQL 切换必须兼容的字段/语义 |
| --- | --- |
| session | `user_id`、`display_name`、`access_tier`、`can_access_app`、`can_mutate_data`、`can_admin_access`。 |
| background jobs | `job_id`/`jobId`、`short_label`/`shortLabel`、`affected_months`/`affectedMonths`、`retry_mode`、`attention`、`superseded_by_job_id`。 |
| app health | SSE 事件 `app_health`、`dirty_scopes`、`matching_dirty_scopes`、`matching_running_scopes`、`primary_running`、`primary_attention`。 |
| imports | `stored_file_path`、`preview_batch_id`、`batch_id`、`row_results`、audit counts、银行选择字段、可选 `job`。 |
| tax | `input_plan_items` 与旧 `input_items` 兼容、`certified_*` rows、`locked_certified_input_ids`、金额字符串格式。 |
| ETC | snake/camel 双兼容、`version`、`expectedVersion`、`idempotencyKey`、OA detection 字段、import/audit arrays、task source file ids。 |
| workbench | row DTO、`source_kind`、关系字段、`relation_amount_check`、`special_metadata`、`affected_months`、`changed_scopes`、settings 子结构。 |
| no OA / bank / batch accounting / turnover | `version/expected_version` 乐观锁、`affected_months`、relation/category/status 字段、错误 `message`。 |

错误处理差异：`backgroundJobs`、`noOaBankBatches`、`bankDetails`、`batchAccounting`、`turnoverLedger`、`etc` 对 HTML/非法 JSON 处理较完整；`imports`、`tax`、`cost-statistics` 更依赖 `response.json()`。迁移阶段要补齐 API 合约测试，避免 PostgreSQL constraint 或代理错误泄漏成前端 parse error。

## 测试入口

后端：

- `tests/test_state_store.py`
- `tests/test_workbench_api.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_workbench_query_service.py`
- `tests/test_workbench_pair_relation_service.py`
- `tests/test_workbench_candidate_match_service.py`
- `tests/test_workbench_settings_sync_api.py`
- `tests/test_import_api.py`
- `tests/test_import_file_api.py`
- `tests/test_import_service.py`
- `tests/test_no_oa_bank_batch_*`
- `tests/test_batch_accounting_api.py`
- `tests/test_bank_details_service.py`
- `tests/test_cost_statistics_*`
- `tests/test_tax_*`
- `tests/test_etc_*`
- `tests/test_app_health_*`
- `tests/test_background_job_service.py`
- `tests/test_settings_data_reset_service.py`

前端：

- `web/src/test/*`
- `web/src/test/apiMock.ts`
- `web/src/test/TurnoverLedgerApi.test.ts`
- `web/src/test/BankDetailsApi.test.ts`

基础验证命令：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test
cd web && npm run build
```

PostgreSQL 后续新增测试类别：

- Repository/DAO contract tests：覆盖 Mongo detailed collection 到 PostgreSQL 表的 save/load/delete/增量更新等价性。
- Transaction atomicity tests：覆盖批量核算、免 OA、workbench actions、settings data reset、cost cache invalidation、ETC task/import/draft。
- Optimistic locking tests：覆盖 `expected_version/version` 冲突，并保持稳定 409/code/message。
- File storage compatibility tests：覆盖 `stored_file_path`、`gridfs://` legacy migration、二进制导入文件和 ETC source files。
- Query parity tests：用同一 fixtures 对比 Mongo fake 和 PostgreSQL backend 的 workbench、cost、turnover、bank detail、tax DTO。
- Background job recovery tests：覆盖 queued/running/interrupted/superseded/retry/acknowledge。
- Migration fidelity tests：覆盖 Decimal、时间戳、中文文本、数组、JSONB、pickle/Binary 规范化导出。
