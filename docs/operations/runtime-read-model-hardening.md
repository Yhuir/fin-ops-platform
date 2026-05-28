# Runtime Read Model Hardening

本页记录 SQL-native worker/read model 收口后的运维验证入口。这里的脚本只做 audit、shadow reconciliation 和 EXPLAIN 采样，不允许作为生产 API fallback 使用。

## Reconciliation 命令

本地或服务器环境先加载 PostgreSQL/Redis/MinIO 配置，然后执行：

```bash
set -a
source .runtime/fin_ops_platform/local-postgres.env
set +a

/opt/miniconda3/bin/python3 scripts/reconcile-runtime-read-models.py \
  --scope-key 2025-12 \
  --explain \
  --json
```

可选旧 builder 对账输入：

```bash
/opt/miniconda3/bin/python3 scripts/reconcile-runtime-read-models.py \
  --scope-key 2025-12 \
  --legacy-workbench-json /path/to/legacy-workbench-2025-12.json \
  --json
```

`--legacy-workbench-json` 必须来自人工 shadow/audit 导出，不能在生产 request handler 内动态构建。

## Backfill / Worker Drain 命令

API 启动只负责请求处理，不会自动补齐所有历史月份的 SQL read model。生产或本地同构环境需要显式运行 backfill 和长期 worker：

```bash
set -a
source .runtime/fin_ops_platform/local-postgres.env
set +a

/opt/miniconda3/bin/python3 scripts/backfill-runtime-read-models.py \
  --backfill-oa-children \
  --enqueue-missing \
  --invoice-expand-all \
  --json

/opt/miniconda3/bin/python3 scripts/backfill-runtime-read-models.py \
  --run-worker \
  --max-iterations 200 \
  --lock-timeout-seconds 30 \
  --task-timeout-seconds 60 \
  --statement-timeout-seconds 30 \
  --json
```

`--backfill-oa-children` 从已有 `app.oa_applications.normalized_payload` 重新投影到 `app.oa_application_items` 和 `app.oa_attachments`，便于后续 worker 走结构化 SQL join。`--run-worker` 只 claim PostgreSQL durable queue；Redis 只影响 wakeup/cache，不影响正确性。`FIN_OPS_QUEUE_BACKEND` 默认 `postgres`；RabbitMQ 未来只能投递 outbox envelope，不能替代 `job.outbox_events` 和 `job.read_model_dirty_scopes`。

工作台 worker/backfill 完成后必须同时覆盖：

- `read_model.workbench_rows`：行级分页、搜索、详情定位。
- `read_model.workbench_groups`：首屏 `open/paired` group 分页、服务端筛选、搜索和排序。
- `read_model.workbench_snapshots`：兼容期、审计、导出、对账，不作为首屏热路径。

`/api/workbench/groups` 可使用 Redis 短 TTL page cache，key 包含 read model schema version、source version、分页、筛选、搜索、排序和 `detail_level` 参数。Redis miss 回 PostgreSQL；Redis 清空不能改变业务结果。工作台 schema 变更时必须提升 schema version，让旧 Redis page cache 与旧 SQL projection payload 自然失效。

## Workbench Generation 一致性契约

工作台 read model 采用 generation 原子发布。生产运行时必须满足：

- `read_model.workbench_generations` 中同一个 `scope_key` 只能有一个 `status='active'` 的 generation。
- active generation 的 `group_count` 必须等于 `read_model.workbench_groups` 中同 generation 的实际 group 数。
- active generation 如果 `row_count > 0`，则同 generation 的 `read_model.workbench_group_rows` 必须存在实际非 summary 行。
- `save_workbench_read_models()` 不允许因为 `changed_scope_keys` 中某个 scope 不在 snapshot 里，就按 `scope_key` 删除 `workbench_rows`、`workbench_groups`、`workbench_group_rows`、`workbench_summary` 或 `workbench_snapshots`。
- `all` scope 只能从一致的 active month shards 聚合；任何 month shard metadata 与实际 rows/groups 不一致时，新 `all` generation 必须标记 failed，保留旧 active all generation。
- Redis page cache key 必须包含 active `generation_id`；Redis 不能作为 read model 正确性的事实源。

迁移 `0036_workbench_generation_consistency.sql` 提供 `read_model.workbench_generation_consistency` view。排障时优先执行：

```sql
select *
from read_model.workbench_generation_consistency
where status = 'active'
  and consistency_status = 'inconsistent'
order by scope_key;
```

只要该查询有结果，页面和 app health 必须显示 failed/error，不能显示“数据已最新”。

## Workbench Rehydrate 命令

当生产 active generation 出现一致性失败，正式恢复动作是重新从 PostgreSQL facts 构建所有 month shards，然后由一致性校验通过后发布 `all`。不要手工 delete/update read model 表。

```bash
set -a
source .runtime/fin_ops_platform/local-postgres.env
set +a

/opt/miniconda3/bin/python3 scripts/rehydrate-workbench-read-models.py --json
```

仅重建指定月份：

```bash
/opt/miniconda3/bin/python3 scripts/rehydrate-workbench-read-models.py \
  --scope 2026-01 \
  --scope 2026-02 \
  --json
```

脚本行为：

- 调用 SQL projection builder 重建每个 month shard。
- 每个 month shard 发布后读取 `/refresh-status` 同口径的 consistency 状态；失败立即退出。
- 最后调用 all-scope aggregate-only 发布；如果任一 parent shard 不一致，`all` 标记 failed 并保留旧 active。
- 输出每个 scope 的 `active_generation_id`、`read_model_status`、`consistency_status` 和错误原因。

长期 worker 建议拆分为：

- `worker-workbench`：`--enable-workbench-read-model-refresh --worker-kind workbench-read-model --event-type workbench.read_model.refresh`
- `worker-workbench-matching`：`--enable-workbench-matching --worker-kind workbench-matching`，消费 `job.workbench_matching_dirty_scopes`，生成 `read_model.workbench_reconciliation_decisions`。它不使用 `--event-type`，也不依赖 RabbitMQ 作为事实源。
- `worker-search`：`--enable-search-read-model-refresh --worker-kind search-read-model --event-type search.read_model.refresh`
- `worker-pending-invoice`：`--enable-pending-invoice-read-model-refresh --worker-kind pending-invoice-read-model --event-type pending_invoice.read_model.refresh`。Legacy `expense:all` / `income:all` 事件只做 fan-out，实际 rebuild scope 必须是 `direction:filter:YYYY-MM`。
- `worker-invoice-usage-collection`：`--enable-input-invoice-usage-read-model-refresh --enable-output-invoice-collection-read-model-refresh --worker-kind invoice-usage-collection-read-model --event-type input_invoice_usage.read_model.refresh --event-type output_invoice_collection.read_model.refresh`。
- `worker-cost-tax`：`--enable-cost-statistics-read-model-refresh --enable-tax-offset-read-model-refresh --worker-kind runtime --event-type cost_statistics.read_model.refresh --event-type tax_offset.read_model.refresh`
- `worker-oa-sync`：`--enable-oa-sync --worker-kind oa-sync --event-type oa.sync`

不要启动无 handler 的 `fin-ops-worker@oa-rabbitmq.service`。如果 systemd 中已存在该实例，应停止并 disable，改用 `fin-ops-worker@oa-sync-rabbitmq.service` 或等价命名，并确保 `FIN_OPS_WORKER_ARGS` 包含 `--enable-oa-sync --event-type oa.sync`。

每个长期 worker 都应设置 `--lock-timeout-seconds`、`--task-timeout-seconds`、`--statement-timeout-seconds` 和 `--max-attempts`。`lock_timeout` 释放 stale `processing` 事件，`task_timeout` 限制单个 handler 的 wall-clock 时间，`statement_timeout` 限制单条 PostgreSQL 语句，`max_attempts` 超限后进入 PostgreSQL `dead_lettered`，再由运维修复后手动 `requeue_event`。

## 本地样本结果

2026-05-22 对 `scope_key=2025-12` 的样本输出摘要：

```text
workbench.row_count = 43
workbench.rows_by_status = paired:40, open:3
workbench.rows_by_source_kind = bank:5, invoice:2, oa:12, oa_attachment_invoice:24
workbench.candidate_matches_by_status = needs_review:2
tax_offset.rows = 1
cost_statistics.rows = 0
queue.outbox_events.pending = 18
dirty_scopes.pending = pending_invoice:5, search:4, tax_offset:4, workbench:5
```

EXPLAIN 摘要：

```text
workbench_page: uses workbench_rows_scope_key_status_idx
pending_invoice: uses pending_invoice_rows_page_idx
cost_statistics: uses cost_statistics_read_models_scope_key_key
search_index: planner used Seq Scan for small local sample with ILIKE '%发票%'
tax_offset: planner used Seq Scan for tiny local sample
```

如果生产数据量变大后 `search_index` 仍然持续 Seq Scan，需要优先检查 `pg_trgm`、`search_index_rows_search_trgm` 是否存在，以及查询是否仍使用可被 trigram GIN 支持的 `ILIKE`/相似度条件。

## 验证门槛

发布前至少运行：

```bash
PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m pytest \
  tests/test_runtime_state_policy.py \
  tests/test_runtime_queue.py \
  tests/test_runtime_worker.py \
  tests/test_runtime_monitoring.py \
  tests/test_runtime_infrastructure_postgres_integration.py \
  tests/test_postgres_migrations.py \
  tests/test_cost_statistics_sql_runtime.py \
  tests/test_tax_offset_sql_runtime.py \
  tests/test_workbench_sql_runtime.py \
  tests/test_search_pending_sql_runtime.py \
  tests/test_invoice_usage_collection_backfill.py \
  tests/test_invoice_usage_collection_sql_runtime.py \
  tests/test_app_postgres_mode.py \
  tests/test_runtime_bootstrap.py \
  tests/test_oa_projection_sql_runtime.py \
  tests/test_file_object_storage.py \
  -q

git diff --check
./scripts/check-local-runtime.sh --require-backend
```

## Source Version Guard

`job.read_model_dirty_scopes.source_version` 每次 enqueue refresh 都递增，并写入 outbox `source_version` 物理列和 payload。Workbench worker 将该版本写入 `read_model.workbench_snapshots`、`read_model.workbench_rows`、`read_model.workbench_groups` 和 `read_model.workbench_candidate_matches` 的 `source_versions.source_version`。

Repository 写入边界会拒绝更老的 source_version 覆盖较新的 read model。Workbench worker 完成 dirty scope 时也带 `source_version` guard；旧 event 即使重复投递，也不能把更高版本 dirty scope 标记为 done。

## 失败和 DLQ 策略

- 可重试错误：worker 调用 `fail_event(... retryable=True)`，按指数退避更新 `available_at`。
- 不可重试错误：标记 `failed`，写 `last_error` 和 `raw_payload.runtime_failure`。
- 超过最大次数：标记 `dead_lettered`，写 `dead_lettered_at`，保留 `trace_id`、`scope_type`、`scope_key` 和 `source_version`。
- 运维修复后：通过 repository 的 `requeue_event(event_id, reason=...)` 重置 attempts 并回到 pending。
- RabbitMQ DLQ 只能作为投递层信号；PostgreSQL `failed/dead_lettered` 才是可审计事实。

## RabbitMQ 接入和回滚

RabbitMQ 生产切换分四步，不能一次性把 worker 全量翻到 broker：

1. 在 staging 配置 `FIN_OPS_TEST_DATABASE_URL` 和 `RABBITMQ_TEST_URL`，运行 RabbitMQ staging preflight。
2. 确认生产 PostgreSQL migration 已应用到 RabbitMQ publish state 和 envelope view；缺少 `0016/0017/0018` 时不能启动生产 dispatcher。
3. PostgreSQL polling worker 保持运行，执行 `python3 -m fin_ops_platform.app.rabbitmq_topology --apply` 创建 durable topology。该命令必须使用 topology/bootstrap 用户，不使用 dispatcher 或 worker 运行时账号。
4. 启动 `python3 -m fin_ops_platform.app.rabbitmq_dispatcher --shadow-publish`，观察 `rabbitmq_publish_failed_backlog`、`rabbitmq_dispatcher_lag_seconds`、RabbitMQ DLQ 和 publisher confirm latency。完整 topology 覆盖 `workbench.read_model.refresh`、`search.read_model.refresh`、`pending_invoice.read_model.refresh`、`cost_statistics.read_model.refresh`、`tax_offset.read_model.refresh`、`oa.sync`、`file_object.gridfs_migration` 和 `import.process.requested`；生产灰度时用 `RABBITMQ_DISPATCH_EVENT_TYPES` 控制实际发布范围。
5. 将一个 workbench worker 设置 `FIN_OPS_QUEUE_BACKEND=rabbitmq`，确认 RabbitMQ consumer 收到 envelope 后仍回 PostgreSQL claim/ack/fail。
6. 稳定后增加 consumer 数量和 `RABBITMQ_PREFETCH`，保留 `FIN_OPS_QUEUE_BACKEND=postgres` 回滚配置。

systemd 和 env 模板：

- `deploy/oa/systemd/fin-ops-rabbitmq-topology.service.example`
- `deploy/oa/systemd/fin-ops-rabbitmq-dispatcher.service.example`
- `deploy/oa/systemd/fin-ops-worker@.service.example`
- `deploy/oa/env/fin-ops.rabbitmq-topology.env.example`
- `deploy/oa/env/fin-ops.rabbitmq-dispatcher.env.example`
- `deploy/oa/env/fin-ops.rabbitmq-worker.env.example`

凭据边界：

- topology/bootstrap 用户只用于 `rabbitmq_topology --apply`。
- dispatcher 用户只发布 envelope，publisher confirm 成功后才更新 PostgreSQL publish 状态。
- worker 用户只消费 queue；consumer 收到 RabbitMQ message 后必须回 PostgreSQL claim event，并在 idle heartbeat 上低频执行 PostgreSQL queue drain，用于接管超时 `processing` event 或 RabbitMQ 未唤醒的 pending event。
- monitor 用户只读 RabbitMQ Management API。
- `RABBITMQ_URL` 和 `FIN_OPS_POSTGRES_DATABASE_URL` 只能放在服务器 root-only `EnvironmentFile`。

staging preflight：

```bash
FIN_OPS_TEST_DATABASE_URL=postgresql://fin_ops_test:***@postgres.internal:5432/fin_ops_test \
RABBITMQ_TEST_URL=amqps://finops_test:***@rabbitmq.internal:5671/%2Ffinops \
RABBITMQ_URL=amqps://finops_dispatcher:***@rabbitmq.internal:5671/%2Ffinops \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.run_rabbitmq_staging_preflight \
  --json \
  --output docs/database-migration/reports/rabbitmq-staging-preflight.json
```

`run_rabbitmq_staging_preflight` 会执行真实 PostgreSQL runtime queue 集成测试、真实 RabbitMQ 临时 topology/publish/consume 测试、`rabbitmq_topology --check`、dispatcher shadow check 和 RabbitMQ consumer worker check。缺少真实环境变量时必须返回非零，不能作为生产验收通过。

确认 staging broker topology 可写后，再显式执行：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.run_rabbitmq_staging_preflight \
  --json \
  --apply-topology \
  --output docs/database-migration/reports/rabbitmq-staging-preflight-apply-topology.json
```

回滚步骤：

```bash
# 1. 停止 rabbitmq_dispatcher 和 rabbitmq consumer 进程。
# 2. 恢复 worker 环境变量。
FIN_OPS_QUEUE_BACKEND=postgres

# 3. 启动原 PostgreSQL polling worker。
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker \
  --enable-workbench-read-model-refresh \
  --event-type workbench.read_model.refresh
```

workbench RabbitMQ worker 灰度示例：

```bash
PYTHONPATH=backend/src FIN_OPS_QUEUE_BACKEND=rabbitmq \
python3 -m fin_ops_platform.app.worker \
  --worker-id worker-workbench-rabbitmq-1 \
  --worker-kind workbench-read-model \
  --enable-workbench-read-model-refresh \
  --event-type workbench.read_model.refresh \
  --lock-timeout-seconds 300 \
  --task-timeout-seconds 60 \
  --statement-timeout-seconds 30 \
  --max-attempts 5
```

shadow publish 验收阈值：

- `rabbitmq_publish_failed_backlog = 0`。
- `rabbitmq_dispatcher_lag_seconds` 不持续增长。
- RabbitMQ workbench queue depth 可解释，不出现持续增长且 `consumer_count=0` 的状态。
- DLQ count 为 0；若大于 0，必须先按 event_id 回 PostgreSQL 查事实和失败原因。
- PostgreSQL `job.outbox_events.publish_status='published'` 只能在 publisher confirm 后出现。

剩余事件族灰度顺序：

1. `search.read_model.refresh` + `pending_invoice.read_model.refresh`：共用 search/pending worker，可先灰度。
2. `cost_statistics.read_model.refresh` + `tax_offset.read_model.refresh`：共用 cost-tax worker。
3. `oa.sync`：依赖 OA Mongo 配置，必须在低峰窗口单独切。
4. `file_object.gridfs_migration`：涉及对象存储和历史文件，必须在确认没有大批量迁移积压后切。

每一组都按同一模式执行：确认 topology 已 apply，扩展 `RABBITMQ_DISPATCH_EVENT_TYPES`，观察 shadow publish，停止旧 PostgreSQL polling worker，启动对应 `fin-ops-worker@<name>.service`，触发一条受控事件，验证 PostgreSQL `published/done`、RabbitMQ queue depth 为 0、DLQ 为 0，再 enable 新 worker。失败时停止 RabbitMQ worker，缩回 dispatcher allowlist，恢复旧 polling worker。

运维排查命令：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_queue_ops inspect --event-id <uuid>
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_queue_ops requeue --event-id <uuid> --reason operator_repair
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_queue_ops republish --event-id <uuid> --reason broker_recovery
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_queue_ops replay-unpublished --dry-run --limit 100
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_queue_ops replay-unpublished --execute --limit 100
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_queue_ops pause-dispatcher
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_queue_ops resume-dispatcher
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_queue_ops pause-consumer
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_queue_ops resume-consumer
```

`pause-dispatcher` 会让 dispatcher 不再 claim publishable outbox；`pause-consumer` 用于进程启动前阻断 RabbitMQ consumer。已经运行中的 consumer 仍应由进程管理器停止，避免 broker delivery 反复 requeue。
