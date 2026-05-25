# 发票使用/收款 Read Model Backfill Runbook

本 runbook 覆盖 `进项发票使用情况` 与 `销项发票收款情况` 的 SQL read model 上线、补数和预热。正确性来源是 PostgreSQL：

- `read_model.input_invoice_usage_rows` / `read_model.input_invoice_usage_scopes`
- `read_model.output_invoice_collection_rows` / `read_model.output_invoice_collection_scopes`
- `job.read_model_dirty_scopes`
- `job.outbox_events`

RabbitMQ 只投递 outbox envelope；Redis 暂不接入这两个页面。后续只有 SQL read model p95 仍不达标时，Redis 才能作为短 TTL page cache，且 miss/error 必须回 PostgreSQL read model。

## 前置条件

1. 已应用包含发票使用/收款 read model 表和索引的 PostgreSQL migration。
2. API 已运行在 PostgreSQL runtime，不允许回退到请求热路径 live scan。
3. Worker 环境具备写 `job.*`、写 `read_model.*`、读 `app.*` 的数据库权限。
4. 服务器上的 `EnvironmentFile` 只由 root/部署用户可读；不要把数据库或 RabbitMQ 凭据写进命令历史。

## Dry-run

先只生成计划，不写 `job.read_model_dirty_scopes` 或 `job.outbox_events`：

```bash
set -a
source .runtime/fin_ops_platform/local-postgres.env
set +a

PYTHONPATH=backend/src \
python3 scripts/backfill-runtime-read-models.py \
  --enqueue-invoice-usage-collection \
  --invoice-scope all \
  --dry-run \
  --json
```

如果希望上线前直接按当前发票月份展开为 shard：

```bash
PYTHONPATH=backend/src \
python3 scripts/backfill-runtime-read-models.py \
  --enqueue-invoice-usage-collection \
  --invoice-expand-all \
  --dry-run \
  --json
```

`--invoice-expand-all` 会分别读取进项和销项发票月份。没有月份时保留 `all` umbrella scope，由 worker 标记空 scope。

## Enqueue

只预热这两个页面：

```bash
PYTHONPATH=backend/src \
python3 scripts/backfill-runtime-read-models.py \
  --enqueue-invoice-usage-collection \
  --invoice-expand-all \
  --reason invoice_usage_collection_release_warmup \
  --priority high \
  --json
```

跟随全量 runtime read model backfill 一起补：

```bash
PYTHONPATH=backend/src \
python3 scripts/backfill-runtime-read-models.py \
  --backfill-oa-children \
  --enqueue-missing \
  --invoice-expand-all \
  --reason runtime_backfill \
  --json
```

只补单月：

```bash
PYTHONPATH=backend/src \
python3 scripts/backfill-runtime-read-models.py \
  --enqueue-invoice-usage-collection \
  --invoice-scope 2026-05 \
  --reason manual_month_rebuild \
  --json
```

## Worker Drain

一次性 drain：

```bash
PYTHONPATH=backend/src \
python3 scripts/backfill-runtime-read-models.py \
  --run-worker \
  --max-iterations 300 \
  --lock-timeout-seconds 60 \
  --task-timeout-seconds 120 \
  --statement-timeout-seconds 60 \
  --json
```

长期 worker 建议单独实例：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --worker-id worker-invoice-usage-collection-1 \
  --worker-kind invoice-usage-collection-read-model \
  --enable-input-invoice-usage-read-model-refresh \
  --enable-output-invoice-collection-read-model-refresh \
  --event-type input_invoice_usage.read_model.refresh \
  --event-type output_invoice_collection.read_model.refresh \
  --lock-timeout-seconds 300 \
  --task-timeout-seconds 120 \
  --statement-timeout-seconds 60 \
  --max-attempts 5
```

RabbitMQ consumer 灰度时只改 transport：

```bash
FIN_OPS_QUEUE_BACKEND=rabbitmq \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --worker-id worker-invoice-usage-collection-rabbitmq-1 \
  --worker-kind invoice-usage-collection-read-model \
  --enable-input-invoice-usage-read-model-refresh \
  --enable-output-invoice-collection-read-model-refresh \
  --event-type input_invoice_usage.read_model.refresh \
  --event-type output_invoice_collection.read_model.refresh \
  --lock-timeout-seconds 300 \
  --task-timeout-seconds 120 \
  --statement-timeout-seconds 60 \
  --max-attempts 5
```

RabbitMQ message 不携带业务 payload；consumer 收到 envelope 后仍必须回 PostgreSQL claim event。

## 验证

Worker 配置：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-input-invoice-usage-read-model-refresh \
  --enable-output-invoice-collection-read-model-refresh \
  --event-type input_invoice_usage.read_model.refresh \
  --event-type output_invoice_collection.read_model.refresh \
  --check
```

队列和 dirty scope：

```sql
select scope_type, scope_key, status, source_version, updated_at
from job.read_model_dirty_scopes
where scope_type in ('input_invoice_usage', 'output_invoice_collection')
order by updated_at desc;

select event_type, scope_key, status, attempts, source_version, last_error
from job.outbox_events
where event_type in (
  'input_invoice_usage.read_model.refresh',
  'output_invoice_collection.read_model.refresh'
)
order by created_at desc;
```

Read model 覆盖：

```sql
select scope_key, row_count, generated_at, cache_status, source_versions
from read_model.input_invoice_usage_scopes
order by scope_key desc;

select scope_key, row_count, generated_at, cache_status, source_versions
from read_model.output_invoice_collection_scopes
order by scope_key desc;
```

API smoke：

```bash
curl -sS 'http://127.0.0.1:8000/api/input-invoice-usage/rows?month=2026-05&page=1&page_size=50' | jq .
curl -sS 'http://127.0.0.1:8000/api/output-invoice-collections/rows?month=2026-05&page=1&page_size=50' | jq .
```

预期：

- fresh scope 返回 `200`，`read_model_status=fresh`。
- missing/stale scope 返回 `202`，`read_model_status=refreshing`，并写 dirty scope/outbox。
- fresh empty scope 返回 `200` 空 rows，不应继续 enqueue。

## 失败处理和回滚

- 单个 event 失败后先看 `job.outbox_events.last_error`，修复事实数据或 projection bug 后通过 queue repository 的 requeue 入口重试。
- RabbitMQ 异常时停止 dispatcher/consumer，恢复 `FIN_OPS_QUEUE_BACKEND=postgres`，启动 PostgreSQL polling worker。
- 不要直接删除业务事实。需要清空 read model 时，应先备份对应 `read_model.*` 表，再按 scope 删除 rows/scopes，并重新 enqueue scope。
- 如果 projection schema 有 bug，先暂停 invoice usage/collection worker，部署修复后按月重新 enqueue。API 在 missing/stale 时会返回 `202 refreshing`，不会回退 live scan。

## 验收命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_invoice_usage_collection_backfill \
  tests.test_invoice_usage_collection_sql_runtime \
  tests.test_rabbitmq_runtime \
  -v

git diff --check
```
