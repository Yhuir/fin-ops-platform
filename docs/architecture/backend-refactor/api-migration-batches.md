# API 迁移批次

本文记录 Axum + PostgreSQL 后端迁移批次。每个批次必须先冻结旧 Python API 契约，再实现 Axum route/service/repository 边界，并说明与旧实现的差异。

## Batch 1：P3-09A 低风险只读 API

范围：

- `GET /health`
- `GET /healthz`
- `GET /readyz`
- `GET /metrics`
- `GET /api/app-metadata`
- `GET /api/session/me`
- `GET /api/workbench/settings`

禁止迁移：

- 导入预览、导入确认、导入撤回。
- 工作台主查询、行详情、忽略、异常、核销确认/撤回。
- 数据重置、项目同步、设置保存。
- OA 源库查询或生产切流。

分层：

| 层 | 文件 | 职责 |
| --- | --- | --- |
| Route | `rust/fin-ops-api/crates/fin-ops-api/src/routes/low_risk_read.rs` | 解析 HTTP、返回旧契约兼容 JSON、映射错误。 |
| Service | `rust/fin-ops-api/crates/fin-ops-api/src/services/low_risk_read.rs` | 维护只读用例边界；session 不伪造身份。 |
| Repository | `rust/fin-ops-api/crates/fin-ops-api/src/repositories/low_risk_read.rs` | 提供可替换的只读投影来源；P3-09A 使用默认兼容投影，后续可改为 PostgreSQL settings/session 表。 |

契约冻结：

- `GET /health` 保留旧 Python foundation health 的顶层字段：`service`、`version`、`status`、`entrypoints`、`capabilities`、`storage`、`future_modules`、`seed_counts`、`module_boundaries`。
- `GET /api/session/me` 成功响应字段保留旧 Python 契约；P3-09A 尚未接 OA identity adapter，因此不返回成功身份，不伪造用户。
- `GET /api/workbench/settings` 保留旧 Python 设置读取字段；P3-09A 不读取 app Mongo、不触发项目同步、不保存设置。

旧 Python 与 Axum 差异：

| 接口 | 差异 | 原因 |
| --- | --- | --- |
| `/health` | `version` 是 Axum crate version；`seed_counts` 默认为 0。 | Axum 不加载 Python demo seed，也不读取 Python runtime state。 |
| `/api/session/me` | 有 token 时当前返回 `503 oa_identity_unavailable`。 | OA identity adapter 尚未迁移；不能伪造当前用户。 |
| `/api/workbench/settings` | 返回默认空项目/银行映射和默认访问控制配置。 | PostgreSQL settings 表和 app Mongo 设置迁移尚未进入本批次。 |

验收 fixture：

- `docs/dev/api-fixtures/low-risk-read-apis.json`

进入下一批前置：

- 若要让 Axum 承接真实登录态，必须先设计 OA identity adapter 或 session projection 表。
- 若要让设置页面展示真实项目和银行映射，必须先完成 app settings PostgreSQL 表和只读 repository 查询。

## Batch 2：P3-09B 导入历史、文件元数据和 upload preflight

范围：

- `GET /imports/templates`
- `GET /imports/batches`
- `GET /imports/batches/{batch_id}`
- `GET /imports/files/{file_id}`
- `GET /api/files/objects/{file_object_id}`
- `POST /imports/files/upload-preflight`

禁止迁移：

- 导入预览、导入确认、导入重试、导入撤回。
- 真实生产文件上传或对象存储写入。
- OA 源库访问、生产切流或 app Mongo 冻结。

分层：

| 层 | 文件 | 职责 |
| --- | --- | --- |
| Route | `rust/fin-ops-api/crates/fin-ops-api/src/routes/import_files.rs` | 解析 HTTP query/path/body，返回旧前端兼容 JSON，隐藏数据库错误和内部存储细节。 |
| Service | `rust/fin-ops-api/crates/fin-ops-api/src/services/import_files.rs` | 冻结导入模板契约，校验 upload preflight，生成不含业务敏感文件名的对象键。 |
| Repository | `rust/fin-ops-api/crates/fin-ops-api/src/repositories/import_files.rs` | 只读 PostgreSQL `app.import_batches`、`app.import_files`、`app.file_objects`。 |

契约冻结：

- `GET /imports/templates` 保留旧 Python `TEMPLATE_DEFINITIONS` 字段：`template_code`、`label`、`file_extensions`、`record_type`、`allowed_batch_types`、`required_headers`。
- 导入历史来自 `app.import_batches`，筛选值必须符合 `0002_imports_files.sql` 的状态和 batch type 约束。
- 文件元数据来自 `app.import_files` 与 `app.file_objects`，只返回对象元数据，不返回文件内容、下载签名、对象存储 secret 或解析 traceback。
- upload preflight 只做文件名、扩展名、content type、byte size、sha256、purpose 校验和 sha256 去重检查；不会写入 `app.file_objects`，不会上传文件。

旧 Python 与 Axum 差异：

| 接口 | 差异 | 原因 |
| --- | --- | --- |
| `/imports/templates` | Axum 使用静态冻结模板，不进入旧 Python 解析服务。 | 本批次只迁移模板读取契约。 |
| `/imports/batches*` | Axum 读取 PostgreSQL 迁移表，不读取 app Mongo 旧会话集合。 | 目标事实源为 PostgreSQL；旧数据需经迁移工具进入 staging/facts 后暴露。 |
| `/imports/files/upload-preflight` | 新增前置校验接口，不返回预签名 URL。 | 当前批次不授权真实文件上传，不写对象存储。 |

验收 fixture：

- `docs/dev/api-fixtures/import-file-read-apis.json`

进入下一批前置：

- 若要启用真实上传，必须补服务端上传/对象写入事务、对象存储权限、checksum 验证和失败回滚。
- 若要迁移导入确认写入，必须先完成 audit、outbox、read model rebuild 与幂等策略验证。

## Batch 3：P3-09C 单月工作台 Read Model 和 Search 只读 API

范围：

- `GET /api/workbench?month=YYYY-MM`
- `GET /api/workbench/ignored?month=YYYY-MM`
- `GET /api/workbench/read-model/status?month=YYYY-MM`
- `GET /api/workbench/rows/{row_id}?month=YYYY-MM`
- `GET /api/search`

禁止迁移：

- 核销确认/撤回、异常处理、忽略/取消忽略等工作台写操作。
- `month=all` 工作台全量实时拼装。
- 请求路径全量重建 read model。
- OA 源库扫描或事实表跨表实时模糊搜索。

分层：

| 层 | 文件 | 职责 |
| --- | --- | --- |
| Route | `rust/fin-ops-api/crates/fin-ops-api/src/routes/read_models.rs` | 解析 query/path，返回旧前端兼容 JSON，映射公开错误。 |
| Service | `rust/fin-ops-api/crates/fin-ops-api/src/services/read_models.rs` | 校验单月范围、附加 read model 状态、分组 search 结果、递归移除敏感字段。 |
| Repository | `rust/fin-ops-api/crates/fin-ops-api/src/repositories/read_models.rs` | 只读 `read_model.workbench_snapshots`、`read_model.workbench_rows`、`read_model.search_index_rows`。 |

契约冻结：

- `/api/workbench` 返回 snapshot payload 原形，并附加 `read_model_status`；旧前端会忽略未知字段。
- `/api/workbench/ignored` 来自 `workbench_snapshots.ignored_rows`，不回退扫描行表或事实表。
- `/api/workbench/rows/{row_id}` 返回 `workbench_rows.payload`，并附加行级 read model 状态；建议携带 `month` 命中单月分区。
- `/api/search` 只查 `search_index_rows`，返回旧 `SearchService` 的 `oa_results`、`bank_results`、`invoice_results` 分组字段。

旧 Python 与 Axum 差异：

| 接口 | 差异 | 原因 |
| --- | --- | --- |
| `/api/workbench?month=all` | Axum P3-09C 返回 400 `all_time_workbench_not_supported`。 | 本批次只做单月 read model 命中路径，禁止请求路径全量拼 all-time。 |
| `/api/workbench` | stale 时返回旧 snapshot + `read_model_status`，不即时重建。 | 重建应由 outbox/Worker 调度，不由页面请求触发。 |
| `/api/search` | 不遍历工作台 snapshot，也不跨事实表查询。 | 搜索索引独立存储在 `read_model.search_index_rows`，由 pg_trgm/GIN 支撑。 |

索引验收说明：

- 单月工作台主读使用 `workbench_snapshots.scope_key` 主键：`workbench:{YYYY-MM}`。
- 行详情建议传 `month`，命中 `workbench_rows(scope_month, row_type, row_id)` 或分区内 row_id 条件；不访问 OA 或 app 事实表。
- 搜索使用 `search_index_rows_text_trgm_idx` 支撑 `searchable_text ilike '%' || q || '%'`；单月搜索带 `scope_month` 定位分区。

验收 fixture：

- `docs/dev/api-fixtures/workbench-search-read-apis.json`

进入下一批前置：

- 若要开放工作台写操作，必须先验证 audit、outbox、read model rebuild、幂等和生产 dry-run 对账报告。
- 若要支持 all-time 工作台，必须先落后台 all-time snapshot 或异步聚合，不得在 API 请求路径实时拼装。

## Batch 4：Prompt G 剩余业务读 API 和 Shadow Validation

范围：

- `GET /api/no-oa-bank-batches`
- `GET /api/no-oa-bank-batches/{batch_id}`
- `GET /api/bank-details/accounts`
- `GET /api/bank-details/transactions`
- `GET /api/turnover-ledger`
- `GET /api/turnover-ledger/export-preview`
- `GET /api/turnover-ledger/relations/{relation_id}`
- `GET /api/tax-offset`
- `POST /api/tax-offset/calculate`
- `GET /api/tax-offset/certified-imports`
- `POST /api/etc/import`
- `GET /api/etc/invoices`
- `GET /api/etc/batches`
- `GET /api/etc/batches/{batch_id}`
- `GET /api/cost-statistics`
- `GET /api/cost-statistics/explorer`
- `GET /api/cost-statistics/export-preview`
- `GET /api/cost-statistics/projects/{project_name}`
- `GET /api/cost-statistics/transactions/{transaction_id}`
- `GET /api/workbench/settings/data-reset/jobs/active`
- `GET /api/workbench/settings/data-reset/jobs/{job_id}`
- `GET /api/oa-sync/status`
- `GET /api/app-health`
- `GET /api/app-health/stream`
- `scripts/tools/api_shadow_validate.py`
- `docs/dev/api-fixtures/api-route-inventory.json`
- `docs/dev/api-fixtures/business-api-shadow-validation.json`

禁止迁移：

- bank-details 分类写入。
- turnover-ledger 确认、撤回、extra 更新和二进制导出。
- ETC 导入、对账任务、附件/票根文件、OA draft、提交状态写入和批次写操作。
- settings 项目同步、项目增删、data reset 创建/执行。
- projects、ledgers、reminders、imports confirm/revert、matching run/results。
- migration mapper、outbox worker、auth internals。

分层：

| 层 | 文件 | 职责 |
| --- | --- | --- |
| Route | `rust/fin-ops-api/crates/fin-ops-api/src/routes/business_read.rs` | 解析业务读 API HTTP query/path，返回公开错误 shape。 |
| Service | `rust/fin-ops-api/crates/fin-ops-api/src/services/business_read.rs` | 校验月份、项目范围、状态桶，拼接旧前端兼容 DTO 和 read model status。 |
| Repository | `rust/fin-ops-api/crates/fin-ops-api/src/repositories/business_read.rs` | 只读 PostgreSQL facts/read models；不访问 app Mongo 或 OA Mongo。 |
| Tool | `scripts/tools/api_shadow_validate.py` | 同时请求 Python 和 Axum，输出字段、排序、金额、日期 diff 与 GO/NO_GO 报告。 |
| Tool | `scripts/tools/api_route_inventory_check.py` | 校验 route inventory schema、机器可读 `source_categories`，并检查 Python/Rust route 与前端引用是否进入 inventory，避免遗漏路由或把 legacy-only 状态误判为可切流。 |

事实源：

| API | Axum source |
| --- | --- |
| bank-details accounts/transactions | `app.bank_transactions`、手工分类追加 `app.bank_transaction_categories`。 |
| no-OA list/detail | `app.no_oa_bank_batches`、detail 追加 `app.bank_transactions`、`app.bank_transaction_categories`。 |
| turnover-ledger flat/grouped read-only, export-preview, and relation detail | `app.bank_transactions`、active `app.bank_transaction_categories.raw_payload.category_code`；按 Python turnover category/export-preview/detail rules and SHA1 relation ids 实时派生，不读取 app Mongo 或按 `app.turnover_relations` 猜测。 |
| tax offset month/calculate | `read_model.tax_offset_read_models`；calculate 只从 payload 即时计算 summary，不写事实、不触发 rebuild。 |
| tax certified imports list | `app.invoice_certifications` joined to `app.invoices`。 |
| ETC direct import removed route | Static legacy compatibility contract；返回 410 `etc_direct_import_removed`，不写数据库、不访问对象存储、不访问 OA。 |
| ETC invoice list | `app.invoices` ETC columns and legacy-compatible `raw_payload` fields；不回查 Python 本地文件、app Mongo 或 OA 源库。 |
| ETC batch list/detail | `app.invoices` ETC columns and legacy-compatible `raw_payload` fields grouped by `etc_import_batch_id`/`etc_submission_batch_id`；不回查 Python 本地文件、app Mongo、OA 源库或 reconciliation task state。 |
| cost statistics month/all/explorer/project detail | `read_model.cost_statistics_read_models`。 |
| cost statistics transaction detail | `app.bank_transactions` 定位月份，`read_model.cost_statistics_read_models` 提供成本行，`read_model.workbench_rows` 提供 `summary_fields/detail_fields`。 |
| workbench month/ignored/status/row reads | `read_model.workbench_snapshots`、`read_model.workbench_rows`；只读取单月 read model，不在请求路径 rebuild，不读取 app Mongo。 |
| workbench action writes and exception apply | PostgreSQL workbench facts、transactional write command、job/outbox read-model invalidation；要求 OA actor、`expected_version`、`idempotency_key`，shadow 仅可对隔离 local/staging fixture 数据执行。 |
| file object metadata/access | `app.file_objects` 加 object-storage access provider；返回元数据和有界 access grant，不返回对象内容、对象存储 secret 或原始 GridFS 内容。 |
| background jobs active/detail reads | `job.worker_tasks` 中 `visibility='system'` 的 task；返回旧 Python `jobs/active_jobs/attention_jobs` 或 `{job}` envelope，不读取 Python `background_jobs`。 |
| settings data-reset job reads | `job.worker_tasks` 中 `task_type='settings_data_reset'` 的 task；不执行 reset，不读取 Python background_jobs。 |
| OA sync status | `app.oa_sync_runs`、`app.oa_sync_watermarks`。 |
| AppHealth JSON snapshot + SSE stream | `app.oa_sync_runs`、`app.oa_sync_watermarks`、`job.worker_tasks`、`read_model.workbench_snapshots` 和 OA identity adapter；SSE stream 复用同一 snapshot 并发送 `app_health`/`heartbeat`，不读取 app Mongo alerts/dirty scope state。 |

旧 Python 与 Axum 差异：

| 接口 | 差异 | 处理 |
| --- | --- | --- |
| bank-details accounts/transactions | Axum 不从 app Mongo、Python auto-category service 或 workbench relation tag projection 补字段；auto category 为空，relation tag 使用旧服务无 provider 时的默认值。 | 必须通过 shadow fixture 解释或补齐 PostgreSQL/read_model 事实源后再切流。 |
| no-OA list/detail | Axum 不从 app Mongo 或 Python relation tag projection 补字段；只返回 PostgreSQL facts 和 batch `raw_payload` 中已有兼容展示字段。 | 必须通过 shadow fixture 解释或阻塞。 |
| turnover-ledger flat/grouped read-only, export-preview, and relation detail | Axum 从 bank/category facts 派生 relation/group/export preview/detail rows；relation id 使用 Python SHA1 row-id digest，allocation lots、lot rows、manual extra、confirm/withdraw state 不从 app Mongo 或 `app.turnover_relations` 猜测。 | shadow fixture 必须解释 lot/allocation、排序、日期、金额格式、manual audit/extras diff；写入、二进制导出和 extra 路由仍阻塞。 |
| ETC invoice list | Axum 不回查 Python 本地附件路径或对象存储，因此 `has_pdf/has_xml` 当前固定为 false；导入批次/OA draft side effects 不在读取路径执行。 | `has_pdf/has_xml` 必须在 shadow fixture 解释；切流前若业务需要附件实时状态，应补对象存储事实源。 |
| ETC batch list/detail | Axum 从 ETC invoice facts 聚合 batch summary/detail，不读取 Python `EtcImportBatch`/OA draft/reconciliation task in-memory state；`supplementItems` 为空，OA linked applicant/apply amount 等未冻结字段为空字符串。 | shadow fixture 必须解释 supplement/OA linked 字段、附件存在性、排序和金额格式 diff；批次写操作仍阻塞。 |
| background jobs active/detail reads | Axum 使用 PostgreSQL `job.worker_tasks` 目标状态机；`retrying` 映射为旧前端 `queued`，`dead_lettered` 映射为 `failed`，确认/替代状态不在核心 task 状态机内。 | staging shadow 必须使用已迁移到 worker task 的 system job；旧 Python 内存/pickle-only job 或 owner-private job 会产生预期外 diff，不能切流。 |
| settings data-reset job reads | Axum 使用 `job.worker_tasks`，不读取 Python `background_jobs`，且只暴露 data-reset task legacy polling shape。 | 旧 Python 内存/pickle job 与 PostgreSQL worker task 并存期间，staging shadow 必须使用同一迁移后的 job id。 |
| workbench read/action routes | Axum 单月读取来自 read model；写命令来自 PostgreSQL transactional command 和 job/outbox，不读取旧 Python app Mongo state。`POST /api/workbench/exception/preview` 没有 Axum route。 | staging shadow 必须使用同一套迁移后的 rows/relations/exception cases 和一次性幂等键；exception preview 保持阻塞直到独立 read_model preview 合同冻结。 |
| file object metadata/access | Axum 可在对象存储已配置时返回 presigned access URL；Python 旧路径可能没有同等 access envelope。 | shadow report 必须解释 access grant 差异，且 URL/presigned URL 值必须被 `[REDACTED]` 脱敏。 |
| tax/cost read model | Axum 不在请求路径 rebuild；缺失 read model 返回 404。 | staging 必须先跑 read model rebuild。 |
| ETC direct import removed route | Axum 与旧 Python 一样返回 410，提示使用 preview/confirm。 | 无业务数据 diff；shadow fixture 必须验证状态码和 error shape。 |
| OA sync status | Axum 从 PostgreSQL sync run/watermark 读状态，不触发 OA 源库访问。 | 日期格式差异需在 shadow 报告中列明。 |
| AppHealth JSON snapshot + SSE stream | Axum JSON snapshot 和 `/api/app-health/stream` 均复用 PostgreSQL/read_model/job facts；app Mongo alerts 和旧 Python `workbench_matching_dirty_scopes` state 不迁移。matching running/failed 来自 `job.worker_tasks`，dirty scopes 来自 stale workbench snapshots。 | shadow fixture 需解释 `generated_at`、state_store backend、SSE content-type 和旧 Python app_health timing/age metrics 差异。 |

验收 fixture：

- `docs/dev/api-fixtures/business-api-shadow-validation.json`
- `docs/dev/api-fixtures/api-route-inventory.json`

进入下一批前置：

- bank-details 写入、turnover-ledger 写入/二进制导出/extra/FIFO lots、ETC 写入/对账/附件、settings data reset 创建/执行等高风险路径必须先补 PostgreSQL/read_model/job/object-storage contract fixture，且 shadow validation 对本批已迁移路由为 `GO`。
- 任一未解释 diff 均保持 `NO_GO`，不得切生产流量。
- `api_shadow_validation` readiness gate 必须同时看到同名 `api-shadow-validation-report-YYYYMMDD.json` 和 `.md` 证据；JSON 需证明 fixture 校验、endpoint 计数和所有结果均为 `GO`，Markdown 需包含 `Gate: **GO**`。
- Inventory 中任一未迁移 Python route 必须写入 `blocked_routes` 逐路由 blocker；生成的 route-level inventory 会把 blocker 展开到每条 route。缺少 blocker 视为 `NO_GO`，避免用领域级说明掩盖遗漏路由或未冻结响应字段。
- Inventory 检查同时扫描旧 Python `readiness_summary.entrypoints`。任一 readiness entrypoint 没有被 route inventory 覆盖时视为 `NO_GO`，用于捕捉 dispatch 正则扫描遗漏的委托路由或仅在 readiness 中公布的业务入口。
