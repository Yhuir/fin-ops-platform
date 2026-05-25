# 2026-05-25 发票使用/收款 Read Model Backfill 生产执行 Prompt

/goal Add a production backfill and warm-up path for `input_invoice_usage` and `output_invoice_collection` SQL read models, integrated with the existing PostgreSQL durable queue, dirty scopes, RabbitMQ-compatible worker flow, runbook documentation, and verification. Do not add Redis in this step; Redis remains only an optional short-TTL SQL page cache after SQL read model correctness and worker convergence are proven.

## 背景

- `进项发票使用情况` 和 `销项发票收款情况` 已迁到 PostgreSQL SQL read model + dirty scope + worker refresh。
- API miss/stale 已经只 enqueue refresh 并返回 `202 refreshing`，不再在请求热路径 live scan。
- 生产上线还需要显式 backfill/warm-up 入口：迁移后先把历史 scope enqueue 到 durable queue，由 worker drain，避免首个业务用户触发整批历史重建。
- RabbitMQ 可以参与投递，但 source of truth 仍是 PostgreSQL `job.outbox_events`、`job.read_model_dirty_scopes` 和 `read_model.*` 表。Redis 不作为一致性来源。

## 串行主线

1. 先读现有 `scripts/backfill-runtime-read-models.py`、`app.worker`、`RuntimeQueueRepository.enqueue_read_model_refresh`、RabbitMQ event type、`docs/operations/runtime-read-model-hardening.md`，沿用现有生产入口。
2. 先写失败测试，锁定：
   - invoice read model backfill 可以 dry-run 输出计划，不写 dirty scope/outbox；
   - 可以 enqueue `input_invoice_usage` 和 `output_invoice_collection` 的 `all` scope；
   - 可以把 `all` 展开成当前 invoice month shards 后逐月 enqueue；
   - run-worker 参数注册两个 invoice read model handler 和两个 event type；
   - invalid month/scope 要 fail fast。
3. 实现 backfill/enqueue 服务或 helper，保持可测试纯函数边界。不要把业务事实 payload 放进 RabbitMQ message；只调用 `enqueue_read_model_refresh(scope_type, scope_key, reason, priority, trace_id)`。
4. 集成现有 `scripts/backfill-runtime-read-models.py`：
   - 新增只针对这两个页面的 enqueue 入口；
   - `--enqueue-missing` 覆盖这两个新增 read model；
   - 支持 `--dry-run`、`--reason`、`--invoice-scope` 或等价 scope 参数；
   - `--run-worker` 能 drain 新 event type，且保留现有 worker flags。
5. 补生产 runbook：
   - migration 后的 dry-run、enqueue、worker drain、长期 worker systemd/env 配置；
   - 验证 SQL、API、dirty scope、outbox、worker check；
   - RabbitMQ 灰度和 PostgreSQL polling 回滚边界；
   - Redis 暂不接入，后续只有 p95 仍不达标才在 SQL 后加短 TTL page cache。
6. 运行聚焦测试和相关 runtime/RabbitMQ 测试；能跑全量就跑全量。最后跑 `git diff --check`。

## 可并行任务

- 任务 A：测试与 backfill planner。负责纯函数/runner 测试、dry-run、scope validation、month expansion。
- 任务 B：脚本集成。负责 `scripts/backfill-runtime-read-models.py` 参数、JSON report、worker drain 参数。
- 任务 C：运维文档。负责 `docs/operations/` runbook、索引、README 入口和 RabbitMQ/Redis 边界。
- 集成必须串行：由一个执行者合并任务 A/B/C，跑测试，确认没有与已有 pending invoice/workbench backfill 入口冲突。

## 验收标准

- 生产 backfill 命令能只为 `input_invoice_usage` 和 `output_invoice_collection` enqueue refresh。
- dry-run 不写 `job.read_model_dirty_scopes` 或 `job.outbox_events`，但输出将要 enqueue 的 target/scope/reason。
- 支持 `all` umbrella scope，也支持 `YYYY-MM` month shard。`all` 可由 worker fan-out，也可在 backfill 入口展开成 month shards。
- `--run-worker` 注册：
  - `--enable-input-invoice-usage-read-model-refresh`
  - `--enable-output-invoice-collection-read-model-refresh`
  - `--event-type input_invoice_usage.read_model.refresh`
  - `--event-type output_invoice_collection.read_model.refresh`
- RabbitMQ 仍只投递 envelope；worker consumer 收到消息后仍回 PostgreSQL claim event。
- 文档必须说明权限、审计、回滚、数据一致性和验证方式。
- 不把 Redis 接入本次路径；后续若 p95 仍高，只允许 Redis 做 SQL read model 后面的短 TTL page cache。
