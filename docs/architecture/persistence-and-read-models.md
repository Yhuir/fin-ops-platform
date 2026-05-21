# 持久化与读模型

## 当前持久化

当前生产主读写以 PostgreSQL 为 app 状态库：

- app 业务事实、设置、后台任务、健康告警和主要读模型进入 PostgreSQL。
- 原始上传文件和附件对象进入 MinIO/S3，PostgreSQL `app.file_objects` 保存 verified object pointer。
- app Mongo 旧路径保留为迁移观察期回滚、shadow-read、导出和审计工具。
- OA 原始数据只由独立 worker 或迁移/shadow/audit 工具通过 Mongo adapter 只读读取，不写 OA Mongo。

生产 API/worker 主路径不得读取：

- `ApplicationStateStore.load()` / `PostgresStateStore.load_bootstrap_snapshot()` full snapshot。
- `app.app_settings` 中的 `state:*` JSON 作为业务事实 fallback。
- App Mongo snapshot 或 local pickle snapshot。
- GridFS 文件内容 fallback。
- OA Mongo direct adapter fallback。

这些旧路径只允许出现在 `backend/src/fin_ops_platform/tools/`、shadow-read rehearsal、migration/backfill worker、audit/export 和短期 rollback 工具中；进入 API production bootstrap 时必须通过 SQL repository、durable queue、Redis helper、object storage 和轻量配置注入。

相关代码：

- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/`
- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`

## 主要表 / 旧集合语义

- `app.import_batches`、`app.invoices`、`app.bank_transactions`：导入后的核心对象。
- `app.import_files`、`app.file_objects`：导入文件元数据和对象存储指针。
- `app.workbench_row_overrides`：忽略、备注等覆盖。
- `app.workbench_pair_relations`：确认关联、免 OA 批次等关系事实。
- `read_model.workbench_snapshots`：工作台 scope 级页面快照和版本元数据。
- `read_model.workbench_rows`：工作台行级 read model，支持按 scope/month/filter/page 查询。
- `read_model.workbench_candidate_matches`：自动匹配候选；生产读取不再 fallback 到 `state:workbench_candidate_matches`。
- `job.read_model_dirty_scopes`：read model 待重算范围。
- `job.background_jobs`：后台任务。
- `audit.app_health_alerts`：健康告警。

## 读模型原则

工作台、搜索、成本统计和税金抵扣这类页面不能在每次请求时从所有来源实时拼全量数据。正确路径：

1. 写操作更新最小事实。
2. 标记受影响 scope。
3. 同步小修补或异步重建 read model。
4. 页面优先读取新鲜 read model。
5. 搜索和导出读取同一套事实或同口径投影。

## 缓存失效

以下动作必须失效相关 read model 或搜索缓存：

- 导入确认或撤回。
- OA 同步。
- 确认关联、撤回关联。
- 异常处理和撤销。
- 银行流水分类变更。
- 免 OA 批次提交、撤回、stale。
- 项目状态设置变更。
- 税金/ETC 导入确认。

## 导入事实读取边界

发票、银行流水、导入批次和导入文件属于基础事实，不再作为生产 API 的构造期全量 snapshot 依赖扩大。PostgreSQL store 暴露 `import_fact_repository`，用于：

- `ImportNormalizationService` 去重和确认前重检：按 `source_unique_key` / `data_fingerprint` 查询 SQL，不要求启动时注入完整 `imports.invoices` 或 `imports.transactions`。
- `/api/bank-details/transactions`：优先使用 `list_bank_transactions_page()` 在 SQL 中分页和过滤，不先加载全量流水。
- `/api/import-facts/invoices`、`/api/import-facts/batches`、`/api/import-facts/files`：按 SQL repository 分页读取发票、批次状态和导入文件。

production bootstrap 不再调用 `PostgresStateStore.load_bootstrap_snapshot()` 或 `ApplicationStateStore.load()`。这些 full/compat snapshot 入口只保留给 migration、shadow、test 和显式 `FIN_OPS_BOOTSTRAP_MODE=legacy` 场景。新迁移模块必须通过 SQL repository/read model 注入，不能读取 `state:imports`、`state:file_imports` 或 `state:full_state` 来构造发票、银行流水、导入文件全量内存索引。

`PostgresStateStore.save()` 不再默认写 `state:full_state`。如果 migration/shadow/test 需要旧 whole snapshot round-trip，必须在对应工具进程显式启用 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT=1`，并且该开关不能作为 production API/worker fallback。已迁移 read model loader 在 SQL 表为空时返回空结果或 refreshing 状态，不再读取 `state:workbench_*`、`state:cost_statistics_read_models` 或 `state:tax_offset_read_models`。

PostgreSQL store 默认不会自动从 data dir 探测 legacy GridFS reader；GridFS reader 只能由 `file_object.gridfs_migration` worker 或手动校验/回滚工具显式注入。production API 读取文件时只接受 `migration_status='verified'` 的对象存储记录。

导入事实写入 `app.invoices` / `app.bank_transactions` / `app.import_batches` 后，必须同时 upsert `job.read_model_dirty_scopes` 并写入 `job.outbox_events`，通知 `workbench`、`cost`、`tax`、`search` 后续投影或 read model 收敛。

## 工作台 SQL read model 边界

`/api/workbench` 的生产读取边界是 `PostgresReadModelRepository.get_workbench_view()`：

- `read_model.workbench_snapshots` 提供兼容现有前端的 grouped payload 和 `generated_at` / `source_versions` / `cache_status` 元数据。
- `read_model.workbench_rows` 提供 `page`、`page_size`、`status`、`source_kind`、`search` 的行级查询 DTO，返回在 `rows_page`。
- `job.read_model_dirty_scopes` 提供 stale/refreshing 状态。API miss 或 dirty scope 未完成时只 enqueue `workbench.read_model.refresh`，不会在请求路径调用旧 `_build_raw_workbench_payload()`。
- production PostgreSQL runtime 如果未配置 workbench SQL read repository，会返回 `read_model_unavailable` 并尝试 enqueue refresh，不会退回旧同步 builder。local pickle 和显式 legacy bootstrap 仍可用于旧测试/迁移验证。
- standalone worker 用 `python3 -m fin_ops_platform.app.worker --enable-workbench-read-model-refresh` claim PostgreSQL durable queue 后重建对应 scope，并写回 `read_model.workbench_snapshots`、`read_model.workbench_rows` 和 candidate tables。
- Pair relations、row overrides、exception cases 等写路径只标记受影响 scope dirty，并由 worker 收敛；生产读取不再使用 `state:workbench_read_models` 或 `state:workbench_candidate_matches` fallback。

对账工具：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.reconcile_workbench_read_model --scope-key 2026-05
```

该工具只用于迁移校验，会在工具进程内调用旧 builder 生成 row id 集合，并与 `read_model.workbench_rows` 对比；不要把旧 builder 重新放回 API 请求路径。

## 成本统计 SQL read model 边界

`/api/cost-statistics/explorer` 和 `/api/cost-statistics` month summary 的生产读取边界是 `read_model.cost_statistics_read_models`：

- API 先读 Redis 短 TTL 热点缓存，miss 后读 PostgreSQL read model；Redis 清空不影响已构建结果返回。month summary 由已构建 explorer `time_rows` 聚合成原有 response shape，不单独在请求里重算事实。
- PostgreSQL miss 或 dirty scope pending 时只 enqueue `cost_statistics.read_model.refresh`，不会在 API 请求里同步调用 `CostStatisticsService.get_explorer()` 重算大范围统计。
- production PostgreSQL runtime 未配置成本统计 SQL repository 时同样返回 `read_model_unavailable` / `refreshing`，不回落到内存 read model 或同步计算。
- standalone worker 用 `python3 -m fin_ops_platform.app.worker --enable-cost-statistics-read-model-refresh` claim durable queue 后，从发票、银行流水、关系事实和现有工作台读模型口径构建 explorer payload，并写回 `read_model.cost_statistics_read_models`。
- 发票、银行流水、pair relation、row override、exception case 等影响成本口径的写路径必须标记 `cost_statistics` dirty scope，并失效 `cost_statistics:explorer:{project_scope}:{month}` 与 `cost_statistics:month:{project_scope}:{month}` Redis key。

对账工具：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.reconcile_cost_statistics_read_model --month 2026-05 --project-scope active
```

## 税金抵扣 SQL read model 边界

`/api/tax-offset` 的生产读取边界是 `read_model.tax_offset_read_models`：

- API 先读 Redis 短 TTL `tax_offset:month:{month}` 热点缓存，miss 后读 PostgreSQL read model；Redis 清空不影响已构建结果返回。
- PostgreSQL miss 或 dirty scope pending 时只 enqueue `tax_offset.read_model.refresh`，不会在 API 请求里同步调用 `TaxApiRoutes.get_tax_offset()` 计算整月 payload。
- production PostgreSQL runtime 未配置税金 SQL repository 时返回 `read_model_unavailable` / `refreshing`，不回落到内存 read model 或同步计算。
- standalone worker 用 `python3 -m fin_ops_platform.app.worker --enable-tax-offset-read-model-refresh` claim durable queue 后，按既有 `TaxOffsetService` 口径从发票、认证抵扣状态、关系事实构建月度 payload，并写回 `read_model.tax_offset_read_models`。
- 发票导入、认证抵扣导入、关系变更和影响税金口径的设置写入必须标记 `tax_offset` dirty scope，并失效 `tax_offset:month:{month}` Redis key。

对账工具：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.reconcile_tax_offset_read_model --month 2026-05
```

## 搜索和待找发票 SQL read model 边界

`/api/search` 的生产读取边界是 `read_model.search_index_rows`，`/api/pending-invoices/rows` 的生产读取边界是 `read_model.pending_invoice_rows`：

- API 只做结构化 SQL 查询和分页；read model miss/stale 时 enqueue `search.read_model.refresh` 或 `pending_invoice.read_model.refresh`，不在请求里同步扫描全量发票、流水、OA 或关系数据。
- `read_model.search_index_rows` 按 `scope_month`、`source_kind`、`status` 和 trigram `searchable_text/project_name/counterparty_name` 建索引，用于全局搜索和跳转 payload。
- `read_model.pending_invoice_rows` 按 `direction/filter_group/trade_date` 建分页索引，并用 trigram `searchable_text` 支持关键字过滤。
- standalone worker 用 `python3 -m fin_ops_platform.app.worker --enable-search-read-model-refresh --enable-pending-invoice-read-model-refresh` claim durable queue 后，从 facts、工作台关系和银行标签设置构建 read model。
- 补票、银行标签设置、pair relation、row override、exception case、导入 facts 等影响结果的写路径必须标记 search/pending invoice dirty scope。

## OA projection SQL 边界

OA Mongo 是外部 read-only source，只允许由独立 worker 拉取；App runtime 读取 OA 行时走 PostgreSQL projection：

- `app.oa_applications` 保存 OA 单据 facts/projection payload，并用 `scope_month,row_id` 支持工作台按月读取。
- `PostgresOAProjectionAdapter` 实现 `WorkbenchQueryService` 需要的 OA adapter 协议；PostgreSQL state store 存在时，工作台读取 OA 行不访问 Mongo，不依赖全量内存同步。
- `POST /integrations/oa/sync` 只 enqueue `oa.sync` durable event，不在 API 请求里执行同步。
- standalone worker 用 `python3 -m fin_ops_platform.app.worker --enable-oa-sync --event-type oa.sync` 从 OA Mongo 拉取并 upsert projection。
- worker 完成后标记 `workbench`、`search` 和 `pending_invoice` 相关 dirty scope。OA source 临时不可用只影响后续 sync job，不破坏已有 SQL projection 查询。
- API server 默认不启动 in-process OA polling，也不会在 production bootstrap 构造 direct `MongoOAAdapter`。如需本地排障旧路径，必须显式使用 `FIN_OPS_BOOTSTRAP_MODE=legacy`，并确保不作为生产请求路径运行。

## 生产演进建议

- 保持 PostgreSQL primary 观察期，暂不删除 app Mongo 回滚路径。
- OA Mongo 继续只读保留，只作为 worker source，不纳入 app runtime state。
- 继续用 repository 替代剩余兼容 snapshot。
- 新模块通过 production bootstrap 注入 repository、queue、cache 和 object storage 配置；`LEGACY_SNAPSHOT_ALLOWLIST` 必须保持为空，构造期 full snapshot 依赖不得进入 production 主路径。
- 对高频查询建立明确索引和 `EXPLAIN ANALYZE` 验证。
- 将 read model 重建放入后台任务。

详细重构计划见 `backend-refactor/README.md`。
