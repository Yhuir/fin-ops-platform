# 后端开发

## 结构

```text
backend/src/fin_ops_platform/
  app/       HTTP 入口、路由、鉴权、响应组装
  domain/    领域模型和枚举
  services/  业务服务、适配层、持久化和投影
```

## 入口

- `app/server.py`：当前主 HTTP server 和路由分发。
- `app/worker.py`：独立 runtime worker 入口，使用 PostgreSQL durable queue，不依赖 API in-process thread。
- `app/auth.py`：OA token 提取、会话识别和权限判断。
- `services/state_store.py`：当前 app 持久化入口。
- `services/runtime_queue.py`：`job.outbox_events` durable queue repository。
- `services/runtime_bootstrap.py`：lightweight bootstrap、repository injection context 和 legacy snapshot allowlist。
- `services/runtime_worker.py`：worker claim/complete/fail/retry runtime。
- `services/runtime_redis.py`：Redis 短 TTL cache、wakeup 和辅助锁 helper。
- `services/object_storage.py`：S3-compatible object storage repository 接口与配置骨架。
- `services/workbench_read_model_refresh.py`：`workbench.read_model.refresh` worker handler，按 dirty scope 重建工作台 SQL read model。
- `services/workbench_relation_read_model_refresh.py`：`workbench_relation.read_model.refresh` worker handler，按月份 shard 重建 OA/流水/发票统一关系分发 read model。
- `services/workbench_relation_read_facade.py`：下游页面读取 OA/流水/发票关系上下文的统一 fresh gate；页面 read model 不直接拼 `workbench_pair_relations`。
- `services/cost_statistics_read_model_refresh.py`：`cost_statistics.read_model.refresh` worker handler，按 dirty scope 重建成本统计 SQL read model。
- `services/mongo_oa_adapter.py`：OA Mongo 只读适配。
- `tools/check_import_fact_consistency.py`：导入事实 SQL cutover 后的批次、发票、流水、文件引用一致性检查。
- `tools/reconcile_workbench_read_model.py`：工作台旧 builder 与 SQL read model row id 对账工具。
- `tools/reconcile_cost_statistics_read_model.py`：成本统计旧 explorer 与 SQL read model 对账工具。

## 服务分层

- 导入：`imports.py`、`import_file_service.py`、`import_preview_audit.py`
- 工作台：`workbench_query_service.py`、`workbench_action_service.py`、`workbench_read_model_service.py`
- 配对：`workbench_pair_relation_service.py`、`workbench_matching_orchestrator.py`。当前迁移期仍可能由 `workbench_candidate_match_service.py` 承载旧自动候选链路；关联台自动决策重构落地后，它只能作为 legacy/internal compatibility 入口，不再是生产展示事实源。
- 异常：`workbench_exception_case_service.py`、`workbench_exception_application_service.py`
- 银行明细：`bank_details_service.py`、`bank_transaction_category_service.py`
- 税金/ETC：`tax_offset_service.py`、`etc_service.py`、`etc_reconciliation_service.py`
- 成本统计：`cost_statistics_service.py`、`cost_statistics_read_model_service.py`
- 运维：`background_job_service.py`、`app_health_service.py`、`app_health_alert_service.py`
- 运行时基础设施：`runtime_queue.py`、`runtime_worker.py`、`runtime_monitoring.py`

## 开发原则

- 不在路由层写复杂规则。
- 不直接读写 OA 原始集合，必须走 adapter。
- 影响工作台展示的写操作必须考虑 read model 和 search cache 失效。
- 影响 OA/流水/发票关联关系的写操作必须标记 `workbench_relation` dirty/enqueue；下游页面必须通过 `WorkbenchRelationReadFacade` 消费关系上下文。
- 导入确认必须重新校验幂等性。
- 导入事实读取必须优先走 PostgreSQL `import_fact_repository`；发票、银行流水、批次和导入文件列表不得在生产 API path 通过 `imports` snapshot 全量加载后分页。
- 关联台自动决策重构完成后，工作台读取必须优先消费 PostgreSQL `app.workbench_pair_relations` 手工事实、`read_model.workbench_reconciliation_decisions` 自动决策，以及 `read_model.workbench_rows` / `read_model.workbench_groups` / `read_model.workbench_group_rows` 投影；迁移期旧 `read_model.workbench_candidate_matches` 只能作为替换前的现行实现或 shadow 对账来源，不得继续扩展成新的展示事实源；`/api/workbench` 不得在生产请求路径调用 `_build_raw_workbench_payload()` 同步 rebuild。
- 新服务需要 snapshot/persistence 时，优先明确状态边界，不继续扩大整包状态。
- 新后台任务优先写入 `job.outbox_events`，由独立 worker claim；不要把新生产机制挂在 API 进程内 thread 上。RabbitMQ 未来只能投递 `RuntimeQueueEvent.to_envelope()`，不能成为事实源。
- `LEGACY_SNAPSHOT_ALLOWLIST` 在 production 模块层面必须保持为空；legacy full snapshot 只允许 migration、shadow、test 或显式 `bootstrap_mode=legacy` 场景使用，并保持 `app/server.py` 不直接调用 `state_store.load()`。
- 生产 API/worker 主路径不得新增 App Mongo snapshot、`state:*` JSON、GridFS 或 direct OA Mongo fallback。迁移、shadow-read、audit、rollback 代码必须放在 `tools/`、显式 worker handler 或 legacy bootstrap 边界内，并在测试中标注 `bootstrap_mode="legacy"`。

工作台 SQL read model worker：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-workbench-read-model-refresh \
  --worker-kind workbench-read-model \
  --event-type workbench.read_model.refresh \
  --lock-timeout-seconds 300 \
  --task-timeout-seconds 60 \
  --statement-timeout-seconds 30 \
  --max-attempts 5
```

本地 smoke 可用 `--check` 查看 handler、queue、Redis 配置，不会开始 claim：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker --enable-workbench-read-model-refresh --worker-kind workbench-read-model --check
```

关联台自动配对 dirty scope worker：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-workbench-matching \
  --worker-kind workbench-matching \
  --workbench-matching-batch-size 10 \
  --workbench-matching-lease-seconds 600 \
  --workbench-matching-retry-delay-seconds 60 \
  --poll-interval-seconds 5 \
  --task-timeout-seconds 900 \
  --statement-timeout-seconds 120
```

这个 worker 消费 `job.workbench_matching_dirty_scopes` 并写入
`read_model.workbench_reconciliation_decisions`。它必须和
`workbench.read_model.refresh` worker 同时长期运行；只有 read-model worker
不会生成新的自动配对决策。

工作台关系分发 read model worker：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-workbench-relation-read-model-refresh \
  --worker-kind workbench-relation-read-model \
  --event-type workbench_relation.read_model.refresh \
  --lock-timeout-seconds 300 \
  --task-timeout-seconds 120 \
  --statement-timeout-seconds 60 \
  --max-attempts 5
```

`read_model.workbench_relation_rows` 给每个对象保留一行，包含 `linked_oa`、
`linked_bank_transactions`、`linked_input_invoices`、`linked_output_invoices`。
无关联对象也必须存在，状态为 `unlinked` 且 linked arrays 为空。待找发票、
OA 待付款、进项发票使用、销项发票收款、银行明细关系标签等页面 read model worker 只能通过
`WorkbenchRelationReadFacade` 消费这些上下文；不得新增页面直接 SQL join
`app.workbench_pair_relations` 生成自己的关系口径。

手工确认/撤回关系会在事务内标记 `workbench_relation`、待找发票、OA 待付款、
进项发票使用、销项发票收款、银行明细、搜索、成本、税金和免 OA 批次等 read model
dirty scope。`read_model.workbench_reconciliation_decisions` 中 `paired` 自动决策也会进入
分发 producer；决策 upsert/expire 后必须标记对应月份的 `workbench_relation` dirty。

Queue 配置边界：

```text
FIN_OPS_QUEUE_BACKEND=postgres
RABBITMQ_URL=amqp://rabbitmq.internal
RABBITMQ_VHOST=/finops
RABBITMQ_EXCHANGE=finops.events
RABBITMQ_WORKBENCH_QUEUE=finops.workbench.read_model.refresh
RABBITMQ_WORKBENCH_ROUTING_KEY=workbench.read_model.refresh
RABBITMQ_DEAD_LETTER_EXCHANGE=finops.events.dlx
RABBITMQ_WORKBENCH_DEAD_LETTER_QUEUE=finops.workbench.read_model.refresh.dlq
RABBITMQ_PREFETCH=10
RABBITMQ_PUBLISH_CONFIRM=true
RABBITMQ_HEARTBEAT_SECONDS=60
RABBITMQ_BLOCKED_CONNECTION_TIMEOUT_SECONDS=300
RABBITMQ_MANAGEMENT_URL=http://rabbitmq.internal:15672
RABBITMQ_MANAGEMENT_USERNAME=finops_monitor
RABBITMQ_MANAGEMENT_PASSWORD=***
RABBITMQ_SHADOW_PUBLISH=false
```

默认仍是 PostgreSQL queue。启用 RabbitMQ 时必须同时运行：

- `python3 -m fin_ops_platform.app.rabbitmq_topology --apply`：显式创建 durable exchange/queue/DLX/DLQ。
- `python3 -m fin_ops_platform.app.rabbitmq_dispatcher`：从 PostgreSQL outbox 发布 envelope，publisher confirm 后才标记 `publish_status=published`。
- `python3 -m fin_ops_platform.app.worker`：`FIN_OPS_QUEUE_BACKEND=rabbitmq` 时进入 RabbitMQ consumer 模式，收到消息后仍回 PostgreSQL claim `event_id` 对应任务。

RabbitMQ 消息体不得携带 read model payload 或页面 snapshot。回滚时停止 dispatcher/consumer，把 worker 改回 `FIN_OPS_QUEUE_BACKEND=postgres` 即可继续 polling PostgreSQL outbox。

工作台首屏读取使用拆分后的 SQL-native 契约：

- `/api/workbench/summary?month=all`：返回 summary、`read_model_status`、`generated_at`，以及轻量 `oa_status`/`invoice_inventory` 状态诊断；不得返回投影 group 或行级快照。
- `/api/workbench/groups?month=all&zone=open|paired&page=1&page_size=200&detail_level=summary`：从 `read_model.workbench_groups` 返回当前页 group 摘要，支持 `status`、`source_kind`、兼容搜索 `search`、分栏搜索 `search_by_pane`、受控排序 `sort=oa|bank|invoice:asc|desc`、`column_filters` 和 `time_filters`。分栏搜索、列筛选和时间筛选通过 `read_model.workbench_group_rows` 命中 group；同一栏内必须命中同一行，多个栏之间按交集组合，不读取 `workbench_snapshots` 大 JSON。`detail_level` 默认为 `full` 以兼容旧调用；前端首屏和 load-more 必须显式传 `summary`。
- `/api/workbench/groups/detail?month=all&zone=open|paired&group_id=...`：从同一 SQL read model 返回单个 group 的完整 payload。列表页不得通过扩大 page size 或读取旧 snapshot 获取详情。
- `/api/workbench/refresh-status`：返回 workbench dirty scopes、worker heartbeat/lag、outbox backlog、最近错误和 source version。
- `/api/workbench` 继续支持 `month`、`page`、`page_size`、`status`、`source_kind`、`search` 作为兼容接口；前端首屏不得依赖它。

`read_model.workbench_rows`、`read_model.workbench_groups` 和 `read_model.workbench_group_rows` 是页面热路径。`read_model.workbench_snapshots.payload/raw_payload` 只用于审计、导出、对账和兼容期。Groups 接口可使用 Redis 短 TTL page cache；Redis key 必须包含 read model schema version、source version、分页、列筛选、时间筛选、`search`、`search_by_pane`、排序、`detail_level` 和过滤语义版本，Redis miss 必须回 PostgreSQL read model，Redis 清空不影响正确性。工作台 DTO/schema 变更必须提升 schema version，防止旧 Redis page cache 或旧 SQL projection payload 被当成新契约使用。`/api/workbench/summary` 和 `/api/workbench/groups` 输出 `workbench_api_metric` 结构化日志，生产指标系统按 endpoint 聚合 p95。

所有正式 read model 必须遵守统一 freshness contract：

- writer 发布 read model 时写入 `source_versions`；API 读取时用当前 `expected_source_versions(scope)` 比较 persisted vs expected。
- `source_versions` 至少包含本 read model schema/source version，以及会改变投影口径的上游版本，例如银行明细自动标签规则版本、OA 附件发票解析版本、OA projection sync 版本、关系/分类快照版本。
- 不一致不能当作 `fresh` 返回。worker 化 read model 只能返回 `refreshing`/`stale` 并 enqueue durable refresh；已有稳定行可以继续作为非 fresh 最近可用结果展示。工作台继续用 generation 原子发布校验，其他单表 read model 使用 `source_versions + schema + dirty scope` 校验。
- Redis 只做短 TTL cache；key 必须包含 read model schema/source version 或 generation id，以及标准化查询参数 hash。Redis 命中不能绕过 SQL read model freshness 判断。
- 当前覆盖：workbench matching/read model、bank detail、cost statistics、tax offset、search、pending invoice、input invoice usage、output invoice collection、No-OA batch rows 和 turnover ledger rows。No-OA/Turnover 仍沿用现有状态表/同步重建路径，但 SQL 读取不能把旧 `source_versions` 误判为 fresh。

成本统计 SQL read model worker：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-cost-statistics-read-model-refresh \
  --event-type cost_statistics.read_model.refresh \
  --lock-timeout-seconds 300 \
  --task-timeout-seconds 60 \
  --statement-timeout-seconds 30
```

`/api/cost-statistics/explorer` 和 `/api/cost-statistics` month summary 在 PostgreSQL read model 存在且 `source_versions` 匹配时从 SQL 返回，并用 Redis 短 TTL 缓存热点 `month/all + project_scope` payload。Redis key 必须包含成本统计 schema version、上游 source_versions hash 和查询 scope；Redis 清空后仍会回落 PostgreSQL；SQL miss/stale/source_versions 不匹配时返回 `202 Accepted` 和 `read_model_status=refreshing`，只 enqueue durable refresh。

税金抵扣 SQL read model worker：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-tax-offset-read-model-refresh \
  --event-type tax_offset.read_model.refresh \
  --lock-timeout-seconds 300 \
  --task-timeout-seconds 60 \
  --statement-timeout-seconds 30
```

`/api/tax-offset` 在 PostgreSQL read model 存在且 `source_versions` 匹配时从 SQL 返回，并用 Redis 短 TTL 缓存热点 month payload。Redis key 必须包含税金抵扣 schema version、上游 source_versions hash 和查询 scope；Redis 清空后仍会回落 PostgreSQL；SQL miss/stale/source_versions 不匹配时返回 `202 Accepted` 和 `read_model_status=refreshing`，只 enqueue durable refresh。

搜索和待找发票 read model worker：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-search-read-model-refresh \
  --enable-pending-invoice-read-model-refresh \
  --event-type search.read_model.refresh \
  --event-type pending_invoice.read_model.refresh \
  --lock-timeout-seconds 300 \
  --task-timeout-seconds 60 \
  --statement-timeout-seconds 30
```

`/api/search` 从 `read_model.search_index_rows` 查询，`/api/pending-invoices/rows` 从 `read_model.pending_invoice_rows` 分页查询。待找发票 projection 的 OA/发票关联事实来自 `WorkbenchRelationReadFacade`；分发 read model 不 fresh 时 pending projection 失败并等待 durable refresh，不回退同步扫描 `workbench_pair_relations`。`/api/input-invoice-usage/rows` 从 `read_model.input_invoice_usage_rows` 查询，`/api/output-invoice-collections/rows` 从 `read_model.output_invoice_collection_rows` 查询；对应 filter-options 必须基于 SQL read model 行集生成。SQL miss/stale/schema-stale/source_versions 不匹配时返回 `202 Accepted` 和 `read_model_status=refreshing`，只 enqueue durable refresh；API 请求路径不得同步扫描全量发票、流水、OA 或关系数据。

银行流水有效标签读取边界：

- `bank_detail` SQL projection 是 producer：它根据银行流水事实、人工/确认标签和自动标签规则计算 `effective_category_*`，并写入 `read_model.bank_detail_rows`。
- `BankTransactionTagReadFacade` 是 PostgreSQL runtime 下游 read gateway：pending invoice、turnover ledger、no-OA bank batch、live workbench 等需要“银行流水 + 有效标签”的下游只能通过它读取已投影结果，并由它处理 fresh/stale/missing、`source_versions` 和刷新 enqueue。
- `BankTransactionEffectiveCategoryProvider` 只保留为 legacy/local/on-demand fallback。它可以在没有 PostgreSQL bank detail read model 的兼容路径即时计算有效标签，但不得作为 PostgreSQL 生产下游读取入口。
- 只消费普通流水事实、不消费有效标签的模块不需要接入 Facade；不得为了复用而把 matching、reconciliation、invoice usage、output collection、OA pending payment、cost statistics、project costing 等模块改成依赖有效标签读取边界。

进项发票使用/销项发票收款 read model worker：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-input-invoice-usage-read-model-refresh \
  --enable-output-invoice-collection-read-model-refresh \
  --event-type input_invoice_usage.read_model.refresh \
  --event-type output_invoice_collection.read_model.refresh \
  --lock-timeout-seconds 300 \
  --task-timeout-seconds 300 \
  --statement-timeout-seconds 60
```

这两个 read model 的 scope type 分别是 `input_invoice_usage` 和 `output_invoice_collection`，月份 shard 使用 `YYYY-MM`，`all` 只展开为月份 shard。上线前用 `scripts/backfill-runtime-read-models.py --enqueue-invoice-usage-collection --invoice-expand-all` 预热历史月份，完整 runbook 见 `../operations/invoice-usage-collection-read-model-backfill.md`。RabbitMQ 只承载 outbox envelope，不携带页面 payload。Redis 若接入，只能放在 SQL read model 之后做短 TTL page cache；key 必须包含 schema/source version、scope 和标准化查询 hash，Redis miss/error 必须回 PostgreSQL read model。

OA projection sync worker：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
FIN_OPS_OA_MONGO_HOST=... \
FIN_OPS_OA_MONGO_DATABASE=... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-oa-sync \
  --event-type oa.sync \
  --lock-timeout-seconds 300 \
  --task-timeout-seconds 60 \
  --statement-timeout-seconds 30
```

PostgreSQL mode 下工作台 OA 行由 `app.oa_applications` projection 提供，`POST /integrations/oa/sync` 只写入 `oa.sync` durable queue event。API server 默认不启动 in-process OA polling；本地临时兼容旧轮询时才设置 `FIN_OPS_OA_POLLING_ENABLED=1`。

导入事实一致性检查：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.check_import_fact_consistency
```

工作台 read model 对账：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.reconcile_workbench_read_model --scope-key 2026-05
```

工作台旧 generation 清理必须在热路径修复发布稳定后执行，且先 dry-run：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.prune_workbench_generations \
  --keep-recent-generations-per-scope 3 \
  --keep-days 14 \
  --limit 500 \
  --dry-run
```

确认数据库备份或云快照后，离峰小批量执行：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.prune_workbench_generations \
  --keep-recent-generations-per-scope 3 \
  --keep-days 14 \
  --limit 500 \
  --execute
```

该工具只调用 `PostgresReadModelRepository.prune_workbench_generations()`，默认 dry-run，并且 repository 删除条件继续保护 `status='active'` generation。不要在 API 请求路径调用 generation retention。

成本统计 read model 对账：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.reconcile_cost_statistics_read_model --month 2026-05 --project-scope active
```

税金抵扣 read model 对账：

```bash
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://... \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.reconcile_tax_offset_read_model --month 2026-05
```
