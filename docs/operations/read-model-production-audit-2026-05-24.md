# Read Model 生产审计 2026-05-24

本审计针对当前 PostgreSQL/RabbitMQ/Redis 生产形态，结论只适用于 production PostgreSQL runtime。旧 Mongo/local snapshot 路径只允许用于迁移、shadow、审计和显式 legacy bootstrap。

## 服务器实测基线

2026-05-24 在服务器 `fin-ops.service` 使用中的 PostgreSQL 库实测：

| 对象 | 行数 | 体积 | 结论 |
| --- | ---: | ---: | --- |
| `read_model.workbench_rows` | 2527 | 45 MB | 行数小但 payload 重，必须继续避免全量首屏读取。 |
| `read_model.workbench_groups` | 1348 | 51 MB | 首屏分页可接受，数据增长后依赖排序/筛选索引。 |
| `read_model.workbench_summary` | 7 | 240 kB | summary 热读路径正确。 |
| `read_model.workbench_snapshots` | 37 | 17 MB | 只能保留审计、导出、兼容，不应作为首屏热读。 |
| `read_model.search_index_rows` | 1801 | 11 MB | 已结构化，关键词搜索当前数据量可接受。 |
| `read_model.pending_invoice_rows` | 431 | 2640 kB | 已结构化；0022 后新增 `scope_key`，worker scope 改为 `direction:filter:YYYY-MM`。 |
| `read_model.cost_statistics_read_models` | 38 | 648 kB | 兼容 snapshot；0022 后 API 热读优先使用 `cost_statistics_rows`。 |
| `read_model.tax_offset_read_models` | 6 | 600 kB | 兼容 snapshot；0022 后 API 热读优先使用 `tax_offset_items`。 |
| `read_model.cost_statistics_rows` | 新增 | - | 成本统计行级 SQL read model。 |
| `read_model.tax_offset_items` | 新增 | - | 税金抵扣 item 级 SQL read model。 |
| `read_model.no_oa_bank_batch_rows` | 新增 | - | 免 OA 批次 SQL read model。 |
| `read_model.turnover_ledger_rows` | 新增 | - | 往来款台账 SQL read model。 |

EXPLAIN 摘要：

- `workbench_summary(scope_key='all')`：约 0.02 ms，走唯一索引。
- `workbench_groups(scope_key='all', zone='open')`：约 1.8 ms，当前数据量小，Planner 使用顺序扫描；已补默认排序索引防止增长后退化。
- `search_index_rows ILIKE '%云南%'`：约 15 ms，当前小表使用顺序扫描；表增长后应确认 `pg_trgm` 和 trigram GIN 被使用。
- `pending_invoice_rows(direction='expense')`：约 4.3 ms，当前小表使用顺序扫描；已补 direction-only page index。
- `cost_statistics_read_models(scope_key='active:2026-04')`：约 0.02 ms，走唯一索引。
- `tax_offset_read_models(scope_key='2026-01')`：当前小表顺序扫描，风险低。

后台状态：

- `dirty_scopes` 无未完成项。
- 活跃 RabbitMQ consumer 已覆盖 `workbench`、`search/pending_invoice`、`cost/tax`、`oa.sync`、`file_object.gridfs_migration`、`import.process.requested`。
- 存在一个 `fin-ops-worker@oa-rabbitmq.service` 无注册 handler，只在心跳里显示 `no_registered_event_types`，应从 systemd 中移除或改成真实 `oa.sync` worker，避免误导监控。
- `pg_stat_statements` 未通过 `shared_preload_libraries` 加载，当前不能用它做长期 SQL p95 归因；AppHealth rolling window 只能代表当前进程样本。

## 分片结论

| Read model | 当前 shard | 结论 | 收口要求 |
| --- | --- | --- | --- |
| Workbench | 月份 shard + `all` 聚合 | 合理。`all` 是聚合读模型，不应每次请求重算。 | 保持首屏 `summary + groups page`，详情按 group/row 定位。 |
| Search | 月份 shard | 合理。搜索事实来自 `workbench_rows`，适合作为跨域搜索索引。 | 数据增长后按 `scope_month/source_kind/status` 控制搜索范围。 |
| Pending invoice | `direction:filter:YYYY-MM` | 0022 后已按月细化。Legacy `direction:filter` 只作为 fan-out 入口。 | 保持 API 日期范围查询走 SQL；worker 不再单事件重建全部方向/筛选数据。 |
| Cost statistics | `project_scope:YYYY-MM` | 月份 shard 合理；0022 后热读使用行级表。 | `cost_statistics_read_models` 保留兼容 snapshot，不能再作为唯一热路径。 |
| Tax offset | `YYYY-MM` | 月份 shard 合理；0022 后热读使用 item 表。 | `tax_offset_read_models` 保留兼容 snapshot，不能再作为唯一热路径。 |
| Batch accounting | 借用 workbench rows | 有 SQL read model 辅助，但不是独立 read model。 | 如果页面继续高频使用，应建 `batch_accounting_rows`。 |
| No-OA bank batches | `no_oa_bank_batch_rows` | 已有 SQL read path；冷启动缺行时仍会回到领域服务构建并持久化。 | 下一步可把构建动作拆到独立 worker。 |
| Turnover ledger | `turnover_ledger_rows` | 已有 SQL read path；冷启动缺行时由领域服务构建并回填，变更时清空。 | 下一步可把构建动作拆到独立 worker，并补 grouped view 行级投影。 |

## Native SQL 结论

合格：

- `workbench_summary`、`workbench_groups`、`workbench_rows` 是结构化 SQL 热路径。
- `search_index_rows` 是结构化搜索 read model。
- `pending_invoice_rows` 是结构化分页 read model，worker scope 已细化为 `direction:filter:YYYY-MM`。
- `cost_statistics_rows` 是成本统计行级 read model，API 从行表重建 `time_rows/project_rows/expense_type_rows`。
- `tax_offset_items` 是税金抵扣 item 级 read model，API 从 item 表重建各类发票明细。
- `/api/bank-details/transactions` 原审计时直接分页读 `app.bank_transactions`；2026-05-25 用户确认银行明细需要生产级独立 read model 后，该结论废止。生产热路径应走 `read_model.bank_detail_rows`，缺失/过期时由 `bank_detail.read_model.refresh` 异步刷新。

不合格或需收口：

- `read_model.cost_statistics_read_models` 和 `read_model.tax_offset_read_models` 仍保留兼容 snapshot，但不再是唯一热读事实。
- `/api/turnover-ledger?view=grouped` 仍需要后续补 grouped view 专用投影；当前行级 read model 覆盖默认 flat list。

## Redis 边界

不是所有 read model 都要接 Redis。规则：

- 应接 Redis：高频、重复、只读、payload 大、可由 source_version 判定新鲜度的页面片段，例如 `workbench/groups` page cache、`cost_statistics` month/explorer、`tax_offset` month。
- 不优先接 Redis：`search_index_rows`、`pending_invoice_rows` 这类结构化 SQL 分页查询。先依赖索引和 SQL，只有 p95 超过目标且 SQL plan 已合理时再加短 TTL cache。
- 禁止：Redis 存业务事实、存不可重建结果、作为 worker ack/fail 状态源。

## RabbitMQ 边界

所有异步 read model refresh 都可以接 RabbitMQ，但 RabbitMQ 只做唤醒和投递：

- 事实源：`job.outbox_events`、`job.read_model_dirty_scopes`。
- 消息内容：只包含 envelope 的 `event_id/scope_key/source_version` 等小字段。
- worker 消费：收到 RabbitMQ message 后必须回 PostgreSQL `claim_event_by_id()`，完成后先 PostgreSQL `ack_event()`，再 RabbitMQ ack；consumer idle heartbeat 还会低频 drain PostgreSQL durable queue，避免 RabbitMQ 消息缺失导致 stale `processing` 事件长期卡住。

不需要接 RabbitMQ 的场景：

- 纯 SQL 分页查询本身。
- Redis cache miss 的同步读取。
- 小型设置读取。

需要接 RabbitMQ 的场景：

- workbench/search/pending/cost/tax read model refresh。
- OA sync、file object migration、import job processing。
- 将来新增的 `batch_accounting`、`no_oa_bank_batch`、`turnover_ledger` read model refresh。

## 生产收口顺序

1. 应用 `0021_read_model_hot_path_indexes.sql`，确保当前 read model 热路径具备增长余量。
2. 移除或修正无 handler 的 `fin-ops-worker@oa-rabbitmq.service`。
3. 应用 `0022_read_model_native_closeout.sql`，新增 `cost_statistics_rows`、`tax_offset_items`、`no_oa_bank_batch_rows`、`turnover_ledger_rows`，并回填/重建对应 read model。
4. 确认 cost/tax worker 重新跑过目标月份，确保行级表有数据；旧 snapshot 只做兼容和审计。
5. 确认 pending invoice legacy scope 只负责 fan-out，实际处理的是 `direction:filter:YYYY-MM`。
6. 对 `/api/turnover-ledger?view=grouped` 建 grouped view 专用投影，或明确该视图不进高频路径。
7. 生产启用 `pg_stat_statements` 的 `shared_preload_libraries`，长期用真实 SQL p95/p99 和 AppHealth rolling window 双重观察。

## 当前回答四个问题

1. 分片是否合理：Workbench/Search/Cost/Tax 的月度 shard 方向合理；Pending invoice 已细化为 `direction:filter:YYYY-MM`；No-OA/Turnover 已有首版独立 SQL read model。
2. 是否 native SQL：Workbench/Search/Pending/Cost/Tax 默认热路径已走结构化 SQL 表；Cost/Tax snapshot 只做兼容。
3. 是否需要 read model 的地方都有：高频默认路径已补 No-OA、Turnover flat list；Batch accounting 借用 workbench rows，后续高频再独立建表。
4. 是否所有 read model 都要 Redis/RabbitMQ：RabbitMQ 用于异步 refresh，不用于查询；Redis 只给热点大 payload 短 TTL，不应覆盖所有 read model。
