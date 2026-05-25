# 2026-05-25 销项收款/进项使用 SQL Read Model 生产级执行 Prompt

/goal Implement production-grade SQL-native read models for `销项发票收款情况` and `进项发票使用情况`, including month sharding, durable dirty scopes, worker refresh, RabbitMQ routing compatibility, SQL-first API read paths, and verification. Redis may be added only after SQL correctness exists and only as a short-TTL hot cache; Redis must never be the source of truth or a stale-data fallback.

## 背景

- 当前两个页面仍从发票、流水、OA、配对关系 live query 组装行数据；数据量上来后 `/rows` 与 `/filter-options` 会触发重复全量扫描。
- 现有 `pending_invoice` 和 `search` 已经有生产级 SQL read model 模式：API 先读 SQL；miss/stale/schema-stale 时写入 `job.read_model_dirty_scopes` 和 outbox，返回 `202 refreshing`，不在 API 热路径同步全量重建。
- 用户要求不是救急方案：必须用 read model + dirty scope + worker 的一体化方案，支持 shard + native SQL 高性能；RabbitMQ 可接入；Redis 只能作为 SQL read model 之后的短 TTL 加速层。

## 串行主线

1. 先补测试，锁定 API miss/stale 不回落 live scan、SQL fresh 命中返回 200、fresh empty scope 返回 200 空数据、worker 扩展 `all` 到 month shards、RabbitMQ 支持新事件类型。
2. 新增 migration，建立 `read_model.input_invoice_usage_rows/scopes` 与 `read_model.output_invoice_collection_rows/scopes`，保留 payload，同时写入 native 查询列、scope、source_versions、generated_at、cache_status、raw_payload 和必要索引。
3. 扩展 `PostgresReadModelRepository` 和 `PostgresStateStore`，实现两个 read model 的 list/save/mark scope 方法。过滤、排序、分页必须在 SQL native columns 上完成，payload 只作为返回体。
4. 新增 projection builder：按 `YYYY-MM` shard 重建 `input_invoice_usage` 与 `output_invoice_collection` 行，`all` 只负责展开为月份 shard，不在 API 请求里同步重建。
5. 新增 refresh service：处理 `input_invoice_usage.read_model.refresh` 和 `output_invoice_collection.read_model.refresh`，校验 event/scope，展开 umbrella scope，完成 shard refresh，并用 `event.source_version` 调用 `complete_read_model_refresh`。
6. 改 worker：新增两个 enable flag，注册 handler，补 RabbitMQ supported event types / default dispatch types。
7. 改 API：`/api/input-invoice-usage/rows`、`/api/input-invoice-usage/filter-options`、`/api/output-invoice-collections/rows`、`/api/output-invoice-collections/filter-options` 先读 SQL read model。SQL miss/stale/schema-stale 返回 `202 refreshing`；SQL fresh 返回 `200`；只有非 PostgreSQL/未配置 read repository 的 legacy 本地模式允许继续 live query。
8. 补 refresh/invalidation helper。涉及发票导入、银行流水导入、OA/配对关系/规则变化时，至少 enqueue `all` 或受影响月份 scope，保证生产最终一致性。
9. 运行相关单测、迁移测试、应用 check；能跑全量时跑全量。验证失败要修复或明确剩余风险。

## 可并行任务

- 任务 A：schema/repository。负责 migration、repository list/save/mark scope、迁移测试。
- 任务 B：worker/queue。负责 projection builder、refresh service、worker flag、RabbitMQ event type、worker 单测。
- 任务 C：API/runtime。负责 server SQL-first handlers、filter-options 基于 SQL rows、dirty enqueue、API 单测。
- 集成阶段必须串行，由一个执行者合并并跑完整验证，避免三个任务分别定义不同 scope key 或 payload 形状。

## 验收标准

- 新 scope type：`input_invoice_usage`、`output_invoice_collection`。
- 新 event type：`input_invoice_usage.read_model.refresh`、`output_invoice_collection.read_model.refresh`。
- scope key：月份 shard 使用 `YYYY-MM`；umbrella 使用 `all`。
- SQL fresh empty 是合法状态：返回 200，rows 为空，`read_model_status=fresh`。
- SQL miss/stale/schema mismatch：返回 202，rows 为空，`read_model_status=refreshing`，写 dirty scope/outbox。
- API 热路径不得同步扫描全部银行流水、发票、OA 和关系。
- Redis 若接入，key 必须包含 schema/version、scope、normalized query hash，TTL 短且 best-effort；Redis miss/error 必须回到 SQL read model，不得回到 live scan。
- RabbitMQ 只是 outbox dispatch/worker transport，业务 payload 不放进消息体，source of truth 仍是 PostgreSQL dirty scope/read model。
