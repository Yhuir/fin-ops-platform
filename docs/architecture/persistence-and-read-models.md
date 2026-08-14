# 持久化与 Canonical Read 边界

日期：2026-08-15

## 当前持久化

- `app.*`：业务 canonical facts、active relations、设置和领域状态。
- `job.*`：background jobs、通用 outbox、attempt 与 worker heartbeat。
- MinIO/S3：原始文件与附件；`app.file_objects` 保存 verified pointer。
- OA Mongo：外部只读来源，只能通过 OA adapter/sync 边界访问。

App 没有运行时 read model schema。Migration `0149_remove_read_model_runtime.sql` 删除历史 projection schema
和 dirty-scope table；历史 migration/checksum 仍保留，不能改写已应用 migration。

## 页面读取

关联台、银行、OA、发票、ETC、税金、成本、往来、批量账务和设置页面都通过 page-specific repository
读取 PostgreSQL canonical facts。组合响应使用一个短 `REPEATABLE READ READ ONLY` snapshot，正式关系只读取
`app.workbench_pair_relations.status='active'` 并按模块规则筛选 relation mode。

- GET 不 enqueue、不轮询、不访问 Redis/RabbitMQ。
- rows、summary、statistics、facets、sort/page 来自同一 snapshot。
- 缺 repository/schema/contract 时 fail fast；禁止 local snapshot、App Mongo fallback、双读或 shadow read。
- 导入/附件列表分页有界，不在 API bootstrap 加载全量数据。

## 写入与后台任务

普通写通过 owner service/UoW 提交 canonical facts、version、audit、idempotency 与必要 domain job。页面写后最多
一次 normal GET。当前 worker exact-set 为 `oa-sync`、`workbench-matching`、`import`、
`settings-maintenance`；它们不创建页面读取副本。

## 性能与验证

- bounded pagination、statement timeout、set-based SQL、batch hydration、固定/有界 query count。
- 核心 GET 生产目标 p95 <= 1000ms、p99 <= 2000ms。
- 索引/SQL 优化以生产 timing 和 `EXPLAIN (ANALYZE, BUFFERS)` 为依据。
- 发布验证包括 canonical page/system audit、HTTP SLO、worker/queue health、旧事件负向审计和跨页回归。

Canonical owner 见 [`module-boundaries/canonical-facts.md`](module-boundaries/canonical-facts.md)，退役合同见
[`module-boundaries/read-model-contracts.md`](module-boundaries/read-model-contracts.md)。
