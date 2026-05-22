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
  --json

/opt/miniconda3/bin/python3 scripts/backfill-runtime-read-models.py \
  --run-worker \
  --max-iterations 200 \
  --lock-timeout-seconds 30 \
  --task-timeout-seconds 60 \
  --statement-timeout-seconds 30 \
  --json
```

`--backfill-oa-children` 从已有 `app.oa_applications.normalized_payload` 重新投影到 `app.oa_application_items` 和 `app.oa_attachments`，便于后续 worker 走结构化 SQL join。`--run-worker` 只 claim PostgreSQL durable queue；Redis 只影响 wakeup/cache，不影响正确性。

长期 worker 建议拆分为：

- `worker-workbench`：`--enable-workbench-read-model-refresh --event-type workbench.read_model.refresh`
- `worker-search`：`--enable-search-read-model-refresh --event-type search.read_model.refresh`
- `worker-pending-invoice`：`--enable-pending-invoice-read-model-refresh --event-type pending_invoice.read_model.refresh`
- `worker-cost-tax`：`--enable-cost-statistics-read-model-refresh --enable-tax-offset-read-model-refresh --event-type cost_statistics.read_model.refresh --event-type tax_offset.read_model.refresh`
- `worker-oa-sync`：`--enable-oa-sync --event-type oa.sync`

每个长期 worker 都应设置 `--lock-timeout-seconds`、`--task-timeout-seconds` 和 `--statement-timeout-seconds`。`lock_timeout` 释放 stale `processing` 事件，`task_timeout` 限制单个 handler 的 wall-clock 时间，`statement_timeout` 限制单条 PostgreSQL 语句。

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
  tests/test_cost_statistics_sql_runtime.py \
  tests/test_tax_offset_sql_runtime.py \
  tests/test_workbench_sql_runtime.py \
  tests/test_search_pending_sql_runtime.py \
  tests/test_app_postgres_mode.py \
  tests/test_runtime_bootstrap.py \
  tests/test_oa_projection_sql_runtime.py \
  tests/test_file_object_storage.py \
  -q

git diff --check
./scripts/check-local-runtime.sh --require-backend
```

## Source Version Guard

`job.read_model_dirty_scopes.source_version` 每次 enqueue refresh 都递增，并写入 outbox payload。Workbench worker 将该版本写入 `read_model.workbench_snapshots`、`read_model.workbench_rows` 和 `read_model.workbench_candidate_matches` 的 `source_versions.source_version`。

Repository 写入边界会拒绝更老的 source_version 覆盖较新的 read model。这是防旧任务覆盖新结果的最后一道数据库侧保护。
