# 当前状态盘点

本文记录 2026-05-20 对仓库代码和服务器的只读盘点。盘点过程中未修改 MongoDB、PostgreSQL、服务器文件或业务数据。

## 代码入口

仓库入口：

- `README.md`：当前后端 Python、前端 React、生产 app Mongo + GridFS、OA Mongo 只读接入。
- `ARCHITECTURE.md`：长期方向明确建议财务主业务事实迁入 PostgreSQL，OA 原始库保持只读。
- `backend/README.md`：启动脚本默认 `FIN_OPS_STORAGE_MODE=mongo_only`。
- `docs/architecture/persistence-and-read-models.md`：当前 app Mongo detailed collections 和 read model 原则。
- `docs/architecture/backend-refactor/*`：已有 Axum/PostgreSQL 长期重构方向，可作为远期参考，但本次迁移第一阶段不要求一次性完成 Axum 重写。

后端核心代码：

- `backend/src/fin_ops_platform/app/server.py`：当前 HTTP 主入口，`Application` 负责装配 state store、OA adapter、业务服务、后台任务和 API 路由。
- `backend/src/fin_ops_platform/services/state_store.py`：app 持久化唯一聚合入口，当前支持 app Mongo detailed collections、GridFS 和本地 pickle/JSON 兼容路径。
- `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`：OA Mongo 只读 adapter，负责付款申请、日常报销、项目、附件发票解析缓存、OA 可用月份等读取逻辑。
- `backend/src/fin_ops_platform/domain/models.py`：核心领域模型，包括 `Invoice`、`BankTransaction`、`ReconciliationCase`、`ImportedBatch`、`MatchingRun` 等。
- `web/src/features/*/api.ts`：前端 API client，迁移期必须保持响应 DTO 兼容。

## 后端服务边界

当前后端没有 repository 层，业务服务大多通过 snapshot 初始化，并在写操作后由 `Application` 调用 `ApplicationStateStore.save_*` 持久化。

主要业务服务分组：

| 分组 | 关键服务 | 迁移关注点 |
| --- | --- | --- |
| 导入 | `imports.py`、`import_file_service.py`、`import_preview_audit.py` | 导入批次、行级结果、文件元数据、GridFS 文件、幂等和撤回。 |
| 工作台 | `workbench_query_service.py`、`workbench_action_service.py`、`workbench_read_model_service.py` | 单月/all 工作台 read model、行详情、确认/撤回/异常操作。 |
| 配对和候选 | `workbench_pair_relation_service.py`、`workbench_candidate_match_service.py`、`workbench_matching_orchestrator.py` | 关系事实、候选匹配、dirty scope、后台重建。 |
| 异常 | `workbench_exception_case_service.py`、`workbench_exception_application_service.py`、`workbench_override_service.py` | 异常 case、忽略、备注、投影、审计历史。 |
| 银行明细 | `bank_details_service.py`、`bank_transaction_category_service.py` | 流水查询、分类覆盖、分类审计。 |
| 税金/ETC | `tax_offset_service.py`、`tax_certified_import_service.py`、`etc_service.py`、`etc_reconciliation_service.py` | 已认证发票、ETC 票据、业务批次、附件和任务。 |
| 成本统计 | `cost_statistics_service.py`、`cost_statistics_read_model_service.py` | 成本统计 read model、下钻、导出。 |
| OA | `mongo_oa_adapter.py`、`oa_manual_import_service.py`、`oa_sync_service.py` | OA Mongo 只读、附件发票缓存、手工导入状态、同步状态。 |
| 运维 | `background_job_service.py`、`app_health_service.py`、`settings_data_reset_service.py` | 后台任务、健康状态、数据重置和受保护目标。 |

## 阶段 00 代码阅读补充

本阶段按 prompt 使用只读子代理并行阅读后端入口、持久化/OA、领域模型、工作台/免 OA/往来、税金/ETC/运维、前端 API 和测试。子代理只返回摘要，未写文件；本文档由主线程统一更新。

代码规模盘点：

- `backend/src/fin_ops_platform/app`：7 个入口/路由文件。
- `backend/src/fin_ops_platform/domain`：3 个领域文件。
- `backend/src/fin_ops_platform/services`：77 个 service 文件。
- `web/src/features`：39 个 feature 文件。
- `web/src/pages`：13 个页面文件。
- `tests`：85 个后端测试文件。
- `web/src/test`：44 个前端测试文件。

CLI 和启动行为：

- `backend/src/fin_ops_platform/app/main.py` 的模块入口是 `python3 -m fin_ops_platform.app.main`。
- 参数包括 `--host`、`--port`、`--check`；`--check` 不启动 HTTP server、OA polling worker 或 dirty scope worker，但会先完整执行 `build_application(data_dir=default_data_dir())`。
- 因此 `--check` 仍会创建 `ApplicationStateStore`、加载 persisted state、创建 runtime services、执行启动恢复钩子，并打印 readiness summary。

`Application` 初始化顺序：

1. 根据 `data_dir` 创建 `ApplicationStateStore`。
2. 初始化 data reset job 状态和锁。
3. 读取 `_state_store.load_oa_sync_state()`。
4. 创建 `OASyncService` 并恢复 poll fingerprints。
5. 初始化 OA sync、workbench matching、ETC detection 等锁和标记。
6. 构建 demo seed。
7. 调用 `_initialize_runtime_services(self._load_persisted_state())`。
8. 恢复中断的 cost statistics cache warmup job。
9. 恢复 pending ETC OA detection loop。
10. 如需要，执行历史 ETC repair reconcile。

`MongoOAAdapter` 在 `_initialize_runtime_services()` 中通过 `load_mongo_oa_settings(...)` 创建，只注入到 OA 读取、设置选项、工作台查询和手工 OA 导入相关服务；app 写入仍发生在 app state store 或后续 PostgreSQL 目标库。

路由副作用摘要：

| API 组 | 迁移关注点 |
| --- | --- |
| `/health`、`/foundation/seed`、`/api/session/me`、`/api/oa-sync/status` | 主要只读；session 依赖 OA identity 和 access control。 |
| `/api/workbench`、`/api/workbench/ignored`、`/api/workbench/rows/*` | 读取工作台 DTO、行详情和 ignored rows；必须保持前端 DTO 兼容。 |
| `/api/workbench/actions/*` | 写 overrides、exception cases、pair relations；失效 workbench/cost read model，可触发后台重建。 |
| `/api/workbench/settings/*` | 写 app settings、手工 OA 导入、项目、数据重置 job；数据重置是高风险写操作。 |
| `/imports/*` | 预览、确认、撤回、文件 retry/confirm 写导入状态、发票/流水、文件元数据，可能创建 background job。 |
| `/api/bank-details/*` | 查询银行流水和账号；分类 PATCH 写分类和 turnover/workbench 派生关系，失效 read model。 |
| `/api/no-oa-bank-batches/*` | 提交/撤回免 OA 批次，写 batch、pair relation 和 audit。 |
| `/api/batch-accounting/*` | 提交/撤回批量核算关系，写 pair relation，返回 affected months。 |
| `/api/turnover-ledger/*` | 读取/导出往来台账，确认/撤回写 turnover relations，extra 写台账扩展字段。 |
| `/api/tax-offset/*` | tax offset GET cache miss 可持久化 read model；认证导入确认写 records/batches 并失效 tax read model。 |
| `/api/etc/*` | ETC task、发票、导入批次、业务批次、OA draft/detection、附件文件读写和后台任务，状态面最复杂。 |
| `/api/cost-statistics/*` | 读取/导出成本统计；explorer cache miss 可持久化 read model，all scope 可触发 warmup job。 |
| `/api/background-jobs/*`、`/api/app-health/*` | 后台任务 acknowledge/retry 写 job 状态；app health/SSE 读取依赖、dirty scope、任务和 alert。 |
| legacy `/integrations/oa/*`、`/projects/*`、`/matching/*`、`/reconciliation/*`、`/ledgers/*` | 保留旧 API 面；迁移期不能只验证新 `/api/*` 路径。 |

## 当前 API 表面

后端主要 API 组：

- `/health`
- `/api/session/me`
- `/api/app-health`
- `/api/background-jobs/*`
- `/imports/*`
- `/api/workbench/*`
- `/api/workbench/actions/*`
- `/api/workbench/settings/*`
- `/api/oa-sync/status`
- `/api/bank-details/*`
- `/api/no-oa-bank-batches/*`
- `/api/batch-accounting/*`
- `/api/turnover-ledger/*`
- `/api/etc/*`
- `/api/tax-offset/*`
- `/api/cost-statistics/*`
- `/api/search`
- `/integrations/oa/*`
- `/projects/*`
- `/matching/*`
- `/reconciliation/*`
- `/ledgers/*`

迁移必须保持现有前端 DTO 和错误语义兼容，除非单独执行 API 合约变更。

## App Mongo 代码集合边界

`ApplicationStateStore` 当前登记的 detailed collections 包括：

- `import_batches`
- `invoices`
- `bank_transactions`
- `bank_transaction_categories`
- `file_import_sessions`
- `file_import_files`
- `matching_runs`
- `matching_results`
- `workbench_row_overrides`
- `workbench_exception_cases`
- `workbench_pair_relations`
- `workbench_read_models`
- `workbench_candidate_matches`
- `workbench_matching_dirty_scopes`
- `no_oa_bank_batches`
- `no_oa_bank_batch_audit_log`
- `turnover_relations`
- `turnover_relation_audit_log`
- `turnover_ledger_extras`
- `cost_statistics_read_models`
- `tax_offset_read_models`
- `oa_attachment_invoice_cache`
- `oa_sync_state`
- `manual_oa_imports`
- `app_settings`
- `tax_certified_import_sessions`
- `tax_certified_import_batches`
- `tax_certified_import_records`
- `etc_state`
- `etc_reconciliation_state`
- `historical_etc_repair_bundles`
- `historical_etc_repair_parsed_seeds`
- `historical_etc_repair_states`
- `background_jobs`
- `app_health_alerts`

另外存在 legacy snapshot collections：

- `application_state`
- `imports_state`
- `file_import_sessions_state`
- `matching_state`
- `import_file_metadata`
- `app_state_meta`

文件存储：

- GridFS bucket：`import_file_blobs`
- GridFS collections：`import_file_blobs.files`、`import_file_blobs.chunks`

State store 公共持久化边界：

- 全局快照：`load()`、`save(payload)` 组合 detailed collections，并兼容 legacy `application_state`、`imports_state`、`file_import_sessions_state`、`matching_state`。
- 设置和 OA 状态：`load_app_settings` / `save_app_settings`、`load_oa_sync_state` / `save_oa_sync_state`、`load_manual_oa_imports` / `save_manual_oa_imports` / `add_manual_oa_imports` / `remove_manual_oa_import`。
- OA 附件缓存：`load_oa_attachment_invoice_cache_entry`、`save_oa_attachment_invoice_cache_entry`、`clear_oa_attachment_invoice_cache`。
- 导入和文件：`store_import_file`、`read_import_file`、`delete_import_files`、`import_session_exists`、`import_file_exists`、`import_batch_exists`、`invoice_exists`、`transaction_exists`。
- 工作台：`load_workbench_pair_relations` / `save_workbench_pair_relations`、`load_workbench_read_models` / `save_workbench_read_models`、`load_workbench_candidate_matches` / `save_workbench_candidate_matches`、`save_workbench_matching_dirty_scopes`、`save_workbench_overrides`、`save_workbench_exception_cases`。
- 银行、免 OA、往来、成本、税金：`load_bank_transaction_categories` / `save_bank_transaction_categories`、`load_no_oa_bank_batches` / `save_no_oa_bank_batches`、`load_turnover_relations` / `save_turnover_relations`、`load_turnover_relation_audit_log` / `save_turnover_relation_audit_log`、`load_turnover_ledger_extras` / `save_turnover_ledger_extras`、`load_cost_statistics_read_models` / `save_cost_statistics_read_models`、`load_tax_offset_read_models` / `save_tax_offset_read_models`。
- 税金认证和 ETC：`load_tax_certified_imports` / `save_tax_certified_imports`、`load_etc_state` / `save_etc_state`、`load_etc_reconciliation_state` / `save_etc_reconciliation_state`、`store_etc_reconciliation_file`、`read_etc_reconciliation_file`、`store_etc_invoice_file`、`read_etc_invoice_file`、`etc_invoice_file_exists`、`delete_etc_invoice_file`。
- 历史 ETC 修复和运维：`save_historical_etc_repair_bundle`、`load_historical_etc_repair_bundle_metadata`、`read_historical_etc_repair_bundle`、`save_historical_etc_repair_parsed_seed`、`load_historical_etc_repair_parsed_seeds`、`load_historical_etc_repair_parsed_seed`、`load_historical_etc_repair_states`、`save_historical_etc_repair_states`、`load_background_jobs` / `save_background_jobs`、`load_app_health_alerts` / `save_app_health_alerts`。

迁移约束：当前 Mongo 里大量 `payload` 是 Python pickle/Binary，不能按 Mongo sample 字段直接建表或手写解析；正式 backfill 必须复用 `ApplicationStateStore` 或业务 service 导出规范化结构。

## 领域状态和业务事实

核心模型和状态值来自 `domain/models.py`、`domain/enums.py`、导入 identity service 和业务 service，而不是 Mongo 样本推断：

- 发票：`Invoice` 持有开票日期、购销方、金额/税额、发票号码/代码/数电号、状态、来源批次、附件/metadata 等；稳定 identity 优先数电号，其次代码+号码，再到税号/日期/金额组合。
- 银行流水：`BankTransaction` 持有账号、交易时间、方向、金额、对方、摘要、余额、状态和 metadata；稳定 identity 是 `bank:{account_no}:{trade_time}:{direction}:{amount}:{counterparty_name}`。
- 导入批次：`ImportedBatch` 和 `ImportedBatchRowResult` 记录预览/确认/撤回、行级创建/更新/跳过/疑似重复/错误、source snapshot 和 audit。
- 核销和匹配：`ReconciliationCase`、`ReconciliationLine`、`MatchingRun`、`MatchingResult` 保留旧核销和 matching run/result 面，迁移时不能丢。
- 枚举状态包括发票 `pending/partially_reconciled/reconciled/pending_offset/...`，流水 `pending/partially_reconciled/reconciled/classified_as_prepayment/...`，导入 `pending/completed/completed_with_errors/reverted/failed`，匹配 `automatic_match/suggested_match/manual_review`，以及异常、免 OA、往来、ETC、后台任务等 service 内状态。

应拆列字段：稳定 ID、scope month、status、version、amount、date/time、actor、source batch、row ids、relation ids、case ids、source_versions、cache schema/parser version。可保留 JSONB 的字段：原始 payload、前端展示字段、detail fields、audit details、parser artifacts、规则解释和兼容旧字段。

## 工作台、关系和读模型

- 工作台行关系按行类型分字段：OA 行用 `oa_bank_relation`，银行行用 `invoice_relation`，发票行用 `invoice_bank_relation`。
- 标准关系值包括 `fully_linked`、`pending_match`、`pending_invoice_match`、`pending_collection`；Live 工作台还会映射 `automatic_match`、`suggested_match`、`manual_review`、`internal_transfer_pair`、`salary_personal_auto_match`。
- `WorkbenchOverrideService` 快照包含 `case_counter`、`projection_version`、`row_overrides`，可覆盖 `case_id`、`exception_case_id`、关系字段、可用动作、ignored、handled exception、projection fields、source versions 和候选 evidence。
- `WorkbenchExceptionCaseService` schema version 为 2，case id 形如 `WEX-000001`，状态覆盖 `open/ignored/reopened/legacy_confirmed/confirmed/closed/cancelled/settled`，保留 history 和 v2 audit。
- `WorkbenchPairRelationService` history 记录 operation id/type、before/after relations、affected row ids、note、amount_check、created_by/created_at。
- dirty scope 以 `YYYY-MM` 月份维护；`take_dirty_scopes` 取出后从队列删除，失败时 `requeue_dirty_scopes` 增加 attempt count。
- `WorkbenchReadModelService` schema 为 `workbench_read_model_service.v1`，freshness 比较 `source_versions`，包括 exception rules/projection/case snapshot/pair relation/candidate/turnover/matching rules 等版本。
- `WorkbenchMatchingOrchestrator.run()` 每月先删候选、再生成候选，最后删除该月和 `all` read model。

## 导入、文件和幂等

- `preview_import()` 创建 pending preview，保存 batch、row results 和 normalized rows。
- `confirm_import(batch_id)` 只处理 pending batch；非 pending 返回现有批次以保证幂等；确认前会重新检查重复。
- `created` 会写 Invoice/BankTransaction 并登记唯一索引；`status_updated` 只用于 invoice；`duplicate_skipped` 会合并发票来源信息或跳过银行流水；`suspected_duplicate` 和 `error` 不落事实表。
- `revert_import(batch_id)` 幂等，删除 created 的发票/流水，恢复 `status_updated` 的旧状态，并把 batch 标记为 reverted。
- 文件导入依赖 `store_import_file`、`read_import_file`、`import_session_exists`、`import_file_exists`。Mongo 模式使用 `gridfs://...`，本地模式写 runtime 文件，`mongo_only` 没有 GridFS 时会失败。

## 税金、ETC、设置和运维

- 已认证税金导入是“上传 Excel -> 预览 -> 确认”，只保留勾选/认证、发票正常、有效抵扣税额大于 0 的记录；唯一键优先数电号，其次代码+号码，最后销售方+日期+税额。
- `TaxOffsetReadModelService` scope 为 `YYYY-MM`，schema 为 `2026-05-tax-offset-month-v1`。
- ETC 事实包括 `EtcInvoice`、`EtcImportSession`、`EtcImportBatch`、`EtcBatch`、`EtcBusinessBatch`、`EtcReconciliationTask`，涉及 ZIP/XML/PDF、对账源文件、补充凭证、OA draft 和 OA detection。
- ETC 业务批次同一 task 只允许一个 active batch，状态覆盖导入、复核、OA 草稿、OA 检测、手工标记、迁移冲突和删除等多个阶段。
- OA detection 优先匹配 `business_batch_id=...` marker，其次 `etc_batch_id=...` marker，还必须校验 form id、金额、发票数量、申请人/组织、创建窗口和流程状态。
- 设置包括项目完成状态、手工项目、OA 同步项目快照、银行尾号映射、访问控制名单、列布局、OA 保留截止日期、OA 导入过滤、OA 发票抵扣申请人。
- `BackgroundJobService` 状态包括 queued、running、succeeded、partial_success、failed、cancelled、acknowledged、superseded；重启会把 stale queued/running 标记为 failed。
- `SettingsDataResetService` 会写 state store 并删除导入文件 blob，保护目标包括 `form_data_db.form_data`、`fin_ops_platform_app.app_settings`、`fin_ops_platform_app.*_meta`、`fin_ops_platform_app.import_file_metadata`。

## 前端兼容面和测试保护

前端迁移期最敏感的兼容点：

- Workbench：`source_kind`、关系字段、`relation_amount_check`、`special_metadata`、`affected_months`、`changed_scopes`、settings 子结构和 data reset job/result。
- Imports：`stored_file_path`、`preview_batch_id`、`batch_id`、`row_results`、audit counts、银行选择字段、可返回的 background `job`。
- ETC：大量 snake/camel 双兼容字段，必须稳定 `version`、`expectedVersion`、`idempotencyKey`、OA detection 字段、import/audit arrays、task source file ids。
- No OA、bank details、batch accounting：必须保持 `version/expected_version` 乐观锁、`affected_months`、relation/category/status 字段和错误 message 语义。
- App health/background jobs：SSE `app_health`、job id 双写、retry/acknowledge、attention/superseded、affected months。

现有测试可复用的保护面：

- `tests/test_state_store.py` 有 `FakeMongoClient`、`FakeCollection`、`FakeGridFSBucket`，可复用来写 PostgreSQL repository parity tests。
- 后端 API/service 已覆盖 workbench、imports、ETC、tax、cost、turnover、no OA、bank details、settings/data reset、app health、background jobs。
- 前端 API/page tests 已覆盖 DTO mapping、HTML/JSON 错误、stale preview、background job mapping、主要页面交互。
- PostgreSQL 后续应新增 repository/DAO contract、事务原子性、乐观锁冲突、文件存储兼容、query parity、background job recovery、error envelope、migration fidelity、permission/audit 测试。

阶段 00 不解决上述数据库风险，只建立代码证据索引和后续阶段必须满足的约束。

## 服务器只读探测

服务器登录已验证：

- 主机：`139.155.5.132`
- 用户：`root`
- 系统：OpenCloudOS，Linux 6.6.104
- `fin-ops.service`：active/running
- 后端监听：`127.0.0.1:18001`
- Nginx：监听 `80`、`443`
- MongoDB：监听 `27017`
- PostgreSQL：监听 `127.0.0.1:5432`
- Redis：监听 `127.0.0.1:6379`
- Docker：已安装但当前无运行容器

部署路径：

- `/opt/fin-ops/current`
- `/opt/fin-ops/fin-ops.env`
- `/opt/fin-ops/data`
- `/www/wwwroot/fin-ops`
- `/data/backups/fin_ops`

服务配置摘要：

- `FIN_OPS_STORAGE_MODE=mongo_only`
- `FIN_OPS_APP_MONGO_HOST=127.0.0.1`
- `FIN_OPS_APP_MONGO_DATABASE=fin_ops_platform_app`
- `FIN_OPS_OA_MONGO_HOST=127.0.0.1`
- `FIN_OPS_OA_MONGO_DATABASE=form_data_db`
- `FIN_OPS_OA_MONGO_COLLECTION=form_data`

密码、token、secret、URI 未写入本文档。

## App Mongo 只读盘点

数据库：`fin_ops_platform_app`

- MongoDB version：`4.2.6`
- collections：`51`
- objects：`14859`
- dataSize：约 `123.7 MB`
- storageSize：约 `120.5 MB`
- indexes：`53`
- indexSize：约 `3.5 MB`

核心集合计数：

| Collection | Count | 说明 |
| --- | ---: | --- |
| `app_settings` | 1 | 设置、权限、项目状态、银行账号映射。 |
| `background_jobs` | 111 | 后台任务。 |
| `bank_transactions` | 431 | 银行流水。 |
| `invoices` | 391 | 发票。 |
| `import_batches` | 6 | 导入批次。 |
| `file_import_sessions` | 11 | 文件导入会话。 |
| `file_import_files` | 31 | 文件导入条目。 |
| `import_file_blobs.files` | 445 | GridFS 文件元数据。 |
| `import_file_blobs.chunks` | 709 | GridFS 文件块。 |
| `oa_attachment_invoice_cache` | 7066 | OA 附件发票解析缓存。 |
| `workbench_candidate_matches` | 5276 | 工作台候选匹配。 |
| `workbench_pair_relations` | 142 | 工作台确认关系。 |
| `workbench_exception_cases` | 2 | 异常 case。 |
| `workbench_row_overrides` | 2 | 行级覆盖。 |
| `no_oa_bank_batches` | 79 | 免 OA 批次。 |
| `no_oa_bank_batch_audit_log` | 91 | 免 OA 审计日志。 |
| `cost_statistics_read_models` | 30 | 成本统计 read model。 |
| `tax_certified_import_records` | 盘点脚本已识别集合 | 已认证发票导入记录，后续正式导出需记录精确数量。 |
| `etc_state` | 1 | ETC 状态 snapshot。 |
| `etc_reconciliation_state` | 1 | ETC 对账任务 snapshot。 |
| `historical_etc_repair_bundles` | 3 | 历史 ETC 修复包。 |
| `historical_etc_repair_parsed_seeds` | 3 | 历史 ETC 修复解析种子。 |
| `historical_etc_repair_states` | 4 | 历史 ETC 修复状态。 |

观察：

- 当前 app 数据量不大，但状态形态复杂，很多集合仍保留 `payload` pickle/binary。
- 当前大头不是银行流水/发票，而是 `oa_attachment_invoice_cache` 和 `workbench_candidate_matches`。
- `workbench_read_models` 当前 count 为 0，说明 read model 可以优先设计为可重建，而不是逐字节迁移。
- 当前 Mongo 索引很少，多数 collection 只有 `_id_`。PostgreSQL 迁移后需要按真实查询补组合索引和搜索索引。

## OA Mongo 只读盘点

数据库：`form_data_db`

- MongoDB version：`4.2.6`
- collections：`1`
- objects：`6113`
- dataSize：约 `86.0 MB`
- storageSize：约 `20.4 MB`
- indexes：`1`
- collection：`form_data`

样本字段：

- `_id`
- `form_id`
- `data`
- `repairer`
- `modifiedTime`
- `_class`

硬约束：

- OA Mongo 是外部系统源库，只读。
- 本迁移不得写入 `form_data_db`。
- 后续如建立 PostgreSQL OA 投影，必须保留 `oa_source_id`、`form_id`、`source_updated_at` 和 `raw_payload`，且同步任务使用只读账号。

## PostgreSQL 只读盘点

PostgreSQL：

- version：`PostgreSQL 16.12`
- 已存在数据库：`fin_ops`、`postgres`、`template0`、`template1`
- `fin_ops` 当前约 `7.9 MB`
- 当前扩展：仅 `plpgsql`

迁移需要补充扩展：

- `pgcrypto`：UUID 和 digest。
- `pg_trgm`：模糊搜索。
- `btree_gin`：组合 GIN 场景。

## 当前风险和后续阶段处理要求

这些风险不是开始阶段 00 的前置条件；它们是阶段 00 盘点出的迁移约束。必须在后续对应阶段处理，不能在正式 backfill、双写或切库前忽略。

- app 生产仍是 `mongo_only`，不能直接把读路径切到 PostgreSQL。
- 许多数据通过 pickle/binary payload 持久化，不能依赖 Mongo sample field 直接建表。
- 当前服务以 `Application` 聚合持久化，缺少 repository interface；如果直接改 `state_store.py`，风险会扩散到所有业务。
- OA Mongo 当前使用同一 Mongo server，但必须在权限和代码上明确隔离。
- PostgreSQL 已安装但尚未完成账号拆分、扩展、schema、备份/PITR 和 migration 管理。
- 前端已经依赖大量 DTO、错误 envelope、snake/camel alias、SSE 和 background job 字段，PostgreSQL 切换必须先做合约测试。
- ETC、数据重置、批量核算、免 OA、往来关系等路径存在跨实体写入，后续 PostgreSQL repository 必须用事务和乐观锁保障原子性。
