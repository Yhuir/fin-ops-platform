# 持久化、Legacy Read Model 与 Direct API 读路径

## 当前持久化

当前生产主读写以 PostgreSQL 为 app 状态库：

- app 业务事实、设置、后台任务、健康告警和 direct query/projection storage 进入 PostgreSQL。
- 原始上传文件和附件对象进入 MinIO/S3，PostgreSQL `app.file_objects` 保存 verified object pointer。
- app Mongo 旧路径保留为迁移观察期回滚、shadow-read、导出和审计工具。
- OA 原始数据只由独立 worker 或迁移/shadow/audit 工具通过 Mongo adapter 只读读取，不写 OA Mongo。

PostgreSQL 中的业务唯一真相、owner matrix、允许写入口和跨模块读写规则以 `module-boundaries/canonical-facts.md` 为准。本文只说明持久化、Direct API 读路径和 legacy read model 下线原则；具体业务事实仍由各 owner 模块管理，不由 read model 模块接管。

2026-06-26 的目标架构变更：页面读取迁移为 direct API，不再新增或扩展页面 read model。当前文中 `read_model.*`、dirty scope、read model worker 和 freshness gate 描述属于 legacy inventory；迁移目标见 `direct-api-read-architecture.md`。

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
- `read_model.workbench_snapshots` / `read_model.workbench_rows` / `read_model.workbench_groups` / `read_model.workbench_group_rows` / `read_model.workbench_summary` / `read_model.workbench_generations`：旧 Workbench 页面 projection storage，已由 `0076_drop_legacy_workbench_projection_storage.sql` 下线。
- `read_model.workbench_candidate_matches`：自动匹配候选；生产读取不再 fallback 到 `state:workbench_candidate_matches`。
- `job.read_model_dirty_scopes`：legacy read model 待重算范围；不再作为页面读取或 App Status 事实源。
- `job.background_jobs`：后台任务。
- `audit.app_health_alerts`：健康告警。

## Direct API 读路径原则

工作台、搜索、成本统计和税金抵扣这类页面不能在每次请求时从所有来源实时拼全量数据。新的正确路径是 direct API + 可索引 SQL：

1. 写操作更新最小 canonical facts 并写审计。
2. 页面 GET 通过 query service/repository 直接读取 canonical facts、OA SQL projection 和导入事实。
3. 查询必须下推分页、过滤、排序和聚合到 SQL，并用索引和 `EXPLAIN` 保护重路径。
4. 搜索和导出读取同一套 direct API / repository 事实口径。
5. 只有真实后台任务未完成时才暴露 job 状态；不再用 read model freshness 表达页面数据是否可读。

旧 read model 原则只用于保护 legacy 路径不伪装 current/direct payload，不得作为新页面读取模式。

## Direct API 影响传播

以下动作必须通过 direct refetch、affected scopes/job diagnostics、短 TTL cache invalidation 或真实后台任务传播影响：

- 导入确认或撤回。
- OA 同步。
- 确认关联、撤回关联。
- 异常处理和撤销。
- 银行流水分类变更。
- 免 OA 批次提交、撤回、版本冲突。
- 项目状态设置变更。
- 税金/ETC 导入确认。

## 导入事实读取边界

发票、银行流水、导入批次和导入文件属于基础事实，不再作为生产 API 的构造期全量 snapshot 依赖扩大。PostgreSQL store 暴露 `import_fact_repository`，用于：

- `ImportNormalizationService` 去重和确认前重检：按 `source_unique_key` / `data_fingerprint` 查询 SQL，不要求启动时注入完整 `imports.invoices` 或 `imports.transactions`。
- `/api/bank-details/transactions`：优先使用 `list_bank_transactions_page()` 在 SQL 中分页和过滤，不先加载全量流水。
- `/api/import-facts/invoices`、`/api/import-facts/batches`、`/api/import-facts/files`：按 SQL repository 分页读取发票、批次状态和导入文件。

production bootstrap 不再调用 `PostgresStateStore.load_bootstrap_snapshot()` 或 `ApplicationStateStore.load()`。这些 full/compat snapshot 入口只保留给 migration、shadow、test 和显式 `FIN_OPS_BOOTSTRAP_MODE=legacy` 场景。新迁移模块必须通过 SQL repository/direct query service 注入，不能读取 `state:imports`、`state:file_imports` 或 `state:full_state` 来构造发票、银行流水、导入文件全量内存索引。

`PostgresStateStore.save()` 不再默认写 `state:full_state`。如果 migration/shadow/test 需要旧 whole snapshot round-trip，必须在对应工具进程显式启用 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT=1`，并且该开关不能作为 production API/worker fallback。已迁移 direct query/service 在 SQL 表为空时返回业务空结果或明确 unavailable/error，不再读取 `state:workbench_*`、`state:cost_statistics_read_models` 或 `state:tax_offset_read_models`。

PostgreSQL store 默认不会自动从 data dir 探测 legacy GridFS reader；GridFS reader 只能由 `file_object.gridfs_migration` worker 或手动校验/回滚工具显式注入。production API 读取文件时只接受 `migration_status='verified'` 的对象存储记录。

导入事实写入 `app.invoices` / `app.bank_transactions` / `app.import_batches` 后，只能通知真实后台任务或仍保留的非页面派生任务。页面级 Workbench/cost/tax/read-model refresh worker lane 已下线；Search 不再进入 dirty/outbox，页面通过 direct API payload 读取。

## 工作台 direct API 与 legacy projection 边界

`/api/workbench` 的生产页面读取边界是 direct API DTO；页面不得以旧 Workbench projection storage、dirty scope、refresh-status 或 Workbench read-model readiness 作为数据源或 freshness gate。

- `workbench.read_model.refresh` worker lane、CLI flag、registry/manifest/App Status 绑定、deploy env、rehydrate/backfill 脚本和 producers 已删除。
- `read_model.workbench_*` 表只作为历史存储/迁移审计对象存在；不得新增页面依赖或修复脚本依赖。
- Pair relations、row overrides、exception cases 等写路径必须写 canonical facts、审计和真实下游信号；不得再写 `scope_type="workbench"` dirty scope 或旧投影 outbox 来等待页面投影收敛。
- local pickle 和显式 legacy bootstrap 仍可用于旧测试/迁移验证，但不能作为 production API/worker fallback。

旧 Workbench generation 只作为 legacy storage/migration 语义：

- 不得把 active generation 当作页面数据版本边界或 Redis page cache 的 current proof。
- 如果历史表仍需审计，metadata 必须和 `workbench_groups` / `workbench_group_rows` / `workbench_summary` 中同 generation 的实际数据一致。
- 旧兼容 snapshot 的 `changed_scope_keys` 不能触发按 `scope_key` 删除 active generation 底层数据。缺失 scope 表示未提供新 payload，不表示可以清空已发布 generation。
- `all` scope 聚合只属于历史 projection 审计；页面 GET 不读取该聚合。
- `read_model.workbench_generation_consistency` 只作为旧存储迁移排障入口，不作为生产页面健康事实。

对账工具：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.reconcile_workbench_read_model --scope-key 2026-05
```

旧 Workbench projection 校验工具已退出当前运行边界；不要把旧 builder、generation 校验或 `read_model.workbench_rows` 对比路径重新放回 API 请求路径。

## 工作台关系 direct API 边界

OA、银行流水、进项发票、销项发票之间的两两/三栏关系上下文统一由 canonical relation facts 通过 direct API 组装：

- 手工确认关系事实源仍是 `app.workbench_pair_relations`；确定性自动关系来自 `read_model.workbench_reconciliation_decisions` 中 `paired` 状态的决策，未配对区候选关系来自 `read_model.workbench_reconciliation_decisions` 中仍处于 open/proposed 展示状态的决策。页面读取必须通过 direct API/query service 从 canonical relation facts 组装上下文。
- distribution 必须区分 `relation_status='linked'` 与 `relation_status='candidate'`：linked 表示可作为已确认关系读取的上下文；candidate 只表示关联台未配对候选展示，不得作为 confirmed write fact、支付完成证明或 row 独占关系。
- 旧 `read_model.workbench_relation_scopes`、`read_model.workbench_relation_groups` 和 `read_model.workbench_relation_rows` 已由迁移删除；不得作为 fallback、freshness proof 或运行时刷新对象恢复。
- `WorkbenchRelationReadFacade` 是下游页面统一读取入口。待找发票、OA 待付款、进项发票使用、销项发票收款、银行明细关系标签等页面不得再直接 join `app.workbench_pair_relations`、`app.invoices`、OA projection 或 OA 附件票缓存来拼关系。
- 分发 rows 必须覆盖无关联对象：`relation_status='unlinked'`、`group_ids=[]`、`linked_*=[]`。页面需要显示空 OA/空发票时直接消费空数组，不再自行补空。
- OA 附件发票关系必须来自 canonical invoice / OA facts；不得从旧 `read_model.workbench_rows` 回捞 `linked_input_invoices`。
- `workbench-relation` standalone worker、`workbench_relation.read_model.refresh` event、manifest/App Status/deploy env 绑定和 `workbench_relation` dirty scope 已删除，不得恢复为页面读取前置条件。
- 写入或撤回 pair relation 时，事务内 writer 只触发真实下游 affected scopes/outbox/cache invalidation；不再标记 `workbench_relation` dirty/outbox。自动决策 upsert/expire 只影响对应月份的 direct Workbench/matching facts。
- 该机制不是关联台 UI payload 复用。各页面保留自己的 direct query、筛选、状态、权限和导出，只消费统一关系上下文作为上游事实；新增页面读取不得新增 SQL read model。

## 成本统计 direct API 与 legacy SQL read model 边界

`/api/cost-statistics/explorer` 和 `/api/cost-statistics` month summary 的页面/API 生产读取边界是 direct API/query service payload，不再以 `read_model.cost_statistics_read_models` 作为页面 freshness gate、ready proof 或请求期读取前置条件：

- API 按 direct query/service 口径从 canonical facts、OA projection、关系事实和必要的业务派生数据组装 payload；页面不得消费 `read_model_status`、旧操作屏障或自动 refresh/retry 字段来决定是否展示成本统计。
- Redis 若用于热点响应，只能是可删除短 TTL response cache；Redis 命中不能作为 freshness proof，Redis 清空也不能改变 direct API 的事实读取语义。
- `read_model.cost_statistics_read_models` 和相关 SQL rows 已由 forward migration 删除；不得恢复 cost statistics page read-model worker、App Status readiness、dirty scope 或请求期 freshness gate。
- 发票、银行流水、pair relation、row override、exception case 等影响成本口径的写路径只允许失效 direct/cache scope 或触发真实后台任务，不得重新标记页面 read-model dirty/outbox。

旧 `reconcile_cost_statistics_read_model` 对账工具已删除；成本统计核对以 direct API/query-service smoke 和业务导出回归为准。

## 税金抵扣 direct API 与 legacy SQL read model 边界

`/api/tax-offset` 的页面/API 生产读取边界是 direct `TaxOffsetQueryService` payload，不再以 `read_model.tax_offset_read_models` 作为页面 freshness gate、ready proof 或请求期读取前置条件：

- API 按 direct query/service 口径从发票、认证抵扣状态、关系事实和税金配置组装月度 payload；页面不得消费 read-model refreshing/stale 状态、旧操作屏障或自动 retry 字段来决定是否展示税金抵扣。
- Redis 若用于 `tax_offset:month:{month}` 等热点响应，只能是可删除短 TTL response cache；Redis 命中不能作为 freshness proof，Redis 清空也不能改变 direct API 的事实读取语义。
- `read_model.tax_offset_read_models` 和相关 SQL rows 已由 forward migration 删除；不得恢复 tax offset page read-model worker、App Status readiness、dirty scope 或请求期 freshness gate。
- 发票导入、认证抵扣导入、关系变更和影响税金口径的设置写入只允许失效 direct/cache scope 或触发真实后台任务，不得重新标记页面 read-model dirty/outbox。

旧 `reconcile_tax_offset_read_model` 对账工具已删除；税金抵扣核对以 direct API/query-service smoke 和业务导出回归为准。

## 搜索和待找发票读取边界

`/api/search` 的生产读取边界是 direct `SearchService.search(...)` business payload，`/api/pending-invoices/rows` 的生产读取边界是 direct `PendingInvoiceQueryService` payload：

- `/api/search` 不读取 SQL search read model、不返回 freshness 字段，也不 enqueue Search refresh；Search SQL index storage/projection 已从当前代码和 fresh PostgreSQL migrations 删除。
- 待找发票 API 不读取 `read_model.pending_invoice_rows/scopes`、不返回 freshness 字段，也不 enqueue `pending_invoice.read_model.refresh`。
- `SearchPendingSqlProjectionBuilder`、`PendingInvoiceReadModelRepositoryPort`、pending-invoice worker/manifest/AppStatus/deploy env 已删除；历史 pending-invoice read-model 表只保留在旧 migrations 中。
- 补票、银行标签设置、pair relation、row override、exception case、导入 facts 等影响结果的写路径通过 direct query/lifecycle 事实反映到页面，不能重新引入 pending-invoice read model gate。

## OA projection SQL 边界

OA Mongo 是外部 read-only source，只允许由独立 worker 拉取；App runtime 读取 OA 行时走 PostgreSQL projection：

- `app.oa_applications` 保存 OA 单据 facts/projection payload，并用 `scope_month,row_id` 支持工作台按月读取。
- `PostgresOAProjectionAdapter` 实现 `WorkbenchQueryService` 需要的 OA adapter 协议；PostgreSQL state store 存在时，工作台读取 OA 行不访问 Mongo，不依赖全量内存同步。
- `POST /integrations/oa/sync` 只 enqueue `oa.sync` durable event，不在 API 请求里执行同步。
- standalone worker 用 `python3 -m fin_ops_platform.app.worker --enable-oa-sync --event-type oa.sync` 从 OA Mongo 拉取并 upsert projection。
- worker 完成后写入 OA SQL projection、job/outbox 诊断和受影响业务 scope；Search 不再作为 OA 同步 dirty scope，`/api/search` 直接读取 canonical/projection facts。OA source 临时不可用只影响后续 sync job，不破坏已有 SQL projection 查询。
- API server 默认不启动 in-process OA polling，也不会在 production bootstrap 构造 direct `MongoOAAdapter`。如需本地排障旧路径，必须显式使用 `FIN_OPS_BOOTSTRAP_MODE=legacy`，并确保不作为生产请求路径运行。

## 生产演进建议

- 保持 PostgreSQL primary 观察期，暂不删除 app Mongo 回滚路径。
- OA Mongo 继续只读保留，只作为 worker source，不纳入 app runtime state。
- 继续用 repository 替代剩余兼容 snapshot。
- 新模块通过 production bootstrap 注入 repository、queue、cache 和 object storage 配置；`LEGACY_SNAPSHOT_ALLOWLIST` 必须保持为空，构造期 full snapshot 依赖不得进入 production 主路径。
- 对高频查询建立明确索引和 `EXPLAIN ANALYZE` 验证。
- 真实后台任务只用于 OA sync、import/file migration、Workbench matching、cache warmup 或受控修复，不用于页面 read-model 重建。
- 当前生产 read model 的分片、SQL-native、Redis/RabbitMQ 边界审计见 `../operations/read-model-production-audit-2026-05-24.md`。审计结论中标记的 `cost_statistics_rows`、`tax_offset_items`、`no_oa_bank_batch_rows` 和 `turnover_ledger_rows` 已由后续 forward migrations 删除；剩余 legacy projection 不应继续扩大 JSON snapshot 热读。

详细重构计划见 `backend-refactor/README.md`。
