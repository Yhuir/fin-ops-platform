# 2026-06-01 销项发票收款情况 Runtime Boundary Execution Prompt

> 用途：交给 Codex 在 `main` 上最终执行。该 prompt 专门用于确认并补齐 `销项发票收款情况` 页面在 Redis、RabbitMQ、SQL read model、runtime queue、worker 下的生产级整合边界。执行时必须遵守当前 Python-first 后端重构架构，不写救急方案。

```text
/goal 在 main 上确认并补齐“销项发票收款情况”页面的 Redis/RabbitMQ/read model/runtime queue 生产级整合边界：PostgreSQL 是事实源；RabbitMQ 只通过 PostgreSQL outbox/runtime queue 作为 transport；Redis 不作为必需依赖，若接入只能位于 SQL read model 之后做带 source_version/generation 的短 TTL cache；server.py 只做 route dispatch/对象装配/统一 JSON 与错误包装，业务实现必须落在 app route facade、Invoices service/usecase、repository、worker/runtime queue 边界内。

硬约束：
1. 在 main 工作，不新建分支，保留并顺着现有未提交改动工作，不回退用户改动。
2. 先读 AGENTS.md、README.md、ARCHITECTURE.md、docs/index.md、docs/architecture/backend-refactor/read-model-and-external-services.md、docs/dev/backend.md、docs/dev/api-contracts.md。
3. 使用 CodeGraph 优先梳理结构调用链；literal path/event/key 用 rg。
4. 不在 server.py 新增业务逻辑；server.py 只能 import、route dispatch、route object 装配、统一 JSON/error 包装。
5. service 不读取 headers，不直接 import Redis/RabbitMQ/OA Mongo driver；route facade 解析 OARequestSession 并传 actor_id、tenant、权限、trace/idempotency。
6. 写操作必须在同一 PostgreSQL transaction 内提交 lifecycle facts、audit/event、dirty scope、outbox；优先复用 RuntimeQueueRepository.enqueue_read_model_refresh_in_transaction。
7. API miss/stale/schema/source_versions 不匹配时返回 202/read_model_status=refreshing，只 enqueue durable refresh，不在请求线程 rebuild 或扫描 legacy snapshot。
8. Redis 不是本页必需项；除非已有 SQL read model 后置 cache 抽象，否则不要新增 Redis。若新增，key 必须包含 source_version 或 active generation、scope、标准化查询 hash；Redis miss/error 必须回 PostgreSQL read model。
9. RabbitMQ 不是业务事实源；只能通过 PostgreSQL outbox envelope，由 dispatcher/worker 传输 output_invoice_collection.read_model.refresh。

任务图：

Serial 0 - 基线确认：
- 运行 git status --short --branch，确认在 main。
- 阅读指定文档并摘出本页必须遵守的 Redis/RabbitMQ/read model 边界。

Parallel 1A - 后端静态链路审计：
- 用 CodeGraph/rg 梳理 /api/output-invoice-collections/* -> routes_output_invoice_collections.py -> OutputInvoiceCollectionQueryService / LifecycleService / ReceiptService -> PostgresOutputInvoiceCollectionLifecycleRepository -> RuntimeQueueRepository 的链路。
- 确认 server.py 没有新增业务实现，只做 dispatch/装配。

Parallel 1B - Runtime queue / RabbitMQ 审计：
- 确认 SUPPORTED_EVENT_TYPES、DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES、rabbitmq staging preflight、worker handler、backfill command 均包含 output_invoice_collection.read_model.refresh。
- 确认 lifecycle/receipt writes 使用 transaction-bound dirty/outbox writer。

Parallel 1C - Redis 边界审计：
- 查找 output invoice collection 相关业务 service、route、repository 是否直接 import/use redis/runtime_redis。
- 若无生产性能证据，不接入 Redis；只补文档和 guard/test。

Parallel 1D - Contract tests 审计：
- 确认 tests 覆盖 runtime queue transaction-bound writer、RabbitMQ allowlist/worker handler、output invoice collection API stale/202、lifecycle write permission/idempotency。
- 若缺少本页 Redis/RabbitMQ 边界机械门禁，先写失败测试，再补最小实现或文档。

Serial 2 - 必要补齐：
- 只在发现缺口时修改代码。
- 优先补测试和文档；只有缺口会导致生产链路不可靠时才改 service/repository/runtime queue/worker。
- 禁止新增业务层 Redis/RabbitMQ 直接调用。

Serial 3 - 验证：
- PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_rabbitmq_runtime tests.test_rabbitmq_staging_preflight tests.test_deploy_runtime_examples tests.test_output_invoice_collection_service tests.test_output_invoice_collection_lifecycle tests.test_output_invoice_collection_api tests.test_invoice_usage_collection_sql_runtime tests.test_postgres_migrations -v
- cd web && npm test -- OutputInvoiceCollections --run
- cd web && npm run build
- git diff --check

最终输出：
- 结论：该页面是否需要 Redis、是否需要 RabbitMQ、接入边界是什么。
- 实际修改文件与原因。
- 验证命令与结果。
- 未完成风险或后续建议。
```

