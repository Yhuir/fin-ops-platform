# Read Model 生产收口执行 Prompt

/goal 生产级收口 fin-ops read model：应用 `0021_read_model_hot_path_indexes.sql`，移除无 handler worker 误配，将成本统计、税金抵扣、待找发票、免 OA 批次和往来款台账从运行时聚合或 JSON payload 热读收敛为 PostgreSQL SQL-native read model；RabbitMQ 只作为 refresh/import/sync/job 投递通道，Redis 只作为短 TTL 热点缓存，PostgreSQL outbox/dirty scopes 继续作为事实源。

## 串行主线

1. 固定数据库事实结构：新增行级 `cost_statistics_rows`、`tax_offset_items`、`no_oa_bank_batch_rows`、`turnover_ledger_rows`，细化 `pending_invoice_rows` 的 scope key/month 语义，补索引、grant 和 migration discovery tests。
2. 改造 repository：所有 API 热读优先从行级 read model 聚合或分页读取；兼容 snapshot 表只保留审计、导出和过渡读。
3. 改造 worker projection：成本统计从 `workbench_groups/workbench_rows` 投影到 `cost_statistics_rows`，不再读取 `workbench_snapshots.payload`；税金抵扣把 item list 写入 `tax_offset_items`；待找发票按 `direction:filter:YYYY-MM` shard rebuild。
4. 增加 no-OA 和 turnover read model 刷新边界：API 不再每次请求重扫全量流水；写路径/导入/分类/确认/撤回后 enqueue 对应 refresh。
5. 保持 RabbitMQ 边界：消息 envelope 只带 event id/scope/source version；consumer 继续回 PostgreSQL claim/ack/fail。
6. 保持 Redis 边界：只缓存 cost/tax 大 payload 或 summary；分页 SQL 不默认缓存。
7. 收口运维：文档化移除 `fin-ops-worker@oa-rabbitmq.service`，启用 `pg_stat_statements.shared_preload_libraries`，部署后验证 queue depth、DLQ、read model p95/p99。

## 可并行子任务

- 子任务 A：成本统计/税金抵扣行级 schema、repository、projection、测试。
- 子任务 B：待找发票月 shard、handler all-scope expansion、API dirty status、测试。
- 子任务 C：免 OA 批次和往来款台账 read model 查询边界、刷新事件和测试。
- 子任务 D：部署/运维文档、systemd/env 模板、pg_stat/RabbitMQ 验证清单。

## 验收

- `PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_migrations.py tests/test_postgres_test_utils.py -q`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_cost_statistics_sql_runtime.py tests/test_tax_offset_sql_runtime.py tests/test_search_pending_sql_runtime.py -q`
- 新增 no-OA/turnover read model focused tests 通过。
- `git diff --check` 通过。
- 生产部署时先 apply migration，再重启 dispatcher/worker，确认 RabbitMQ DLQ 为 0，相关 API p95/p99 在 AppHealth 内稳定。
