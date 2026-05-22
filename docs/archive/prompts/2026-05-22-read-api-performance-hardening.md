# Codex 最终执行 Prompt：读 API 性能生产级整合

## /goal

在不切换后端语言的前提下，完成读 API 性能生产级整合：让 `/api/workbench/groups` 列表页只返回真正摘要与 preview rows，让 `tax-offset` 支持小 payload summary/read path 并在 Redis 异常时降级到 SQL read model，让 PostgreSQL 连接池在启动时可预热并为只读 read model 保留独立配置入口；最后重新验证 p95、DB share、Redis 命中和 Python CPU，只有当数据层已快但 Python/调度仍饱和时才进入 Go read API sidecar。

## 背景判断

- `summary` 和 `search` 当前主要受 DB/连接池影响，不适合先用 Go sidecar 解决。
- `groups paired summary` 仍然过大，原因是列表页摘要仍携带完整行数组和 collapsed 明细。
- `tax-offset` Redis 命中后仍慢且有失败请求，原因是整月整包 JSON payload 太大，且 Redis timeout/连接异常会冒泡到 API。
- Python CPU 未持续打满，因此优先做读模型、payload 契约、缓存和连接池，而不是换语言。

## 并行探索任务

1. Workbench groups 路径：
   - 读取 `PostgresReadModelRepository.get_workbench_groups_page`、`_compact_workbench_group_for_summary_page`、前端 `WorkbenchCandidateGroup` 映射和列表展示。
   - 输出：列表页需要保留的字段、可裁剪字段、计数字段和测试入口。

2. Tax-offset 路径：
   - 读取 `/api/tax-offset`、SQL read model、Redis key、refresh/invalidation 逻辑。
   - 输出：兼容旧接口的小 payload 新接口方案、Redis 容错点、测试入口。

3. Postgres pool/search/summary 路径：
   - 读取 `PostgresConnection`、`PostgresStateStore`、`state_store_factory`、summary/search repository 和 migrations。
   - 输出：pool 预热、只读连接配置、pg_stat/EXPLAIN 验证方案。

## 串行执行任务

1. 文档和计划
   - 在 `docs/archive/prompts/` 保存本 prompt。
   - 在 `docs/superpowers/plans/` 保存执行计划、验收标准和回滚点。

2. Groups 真摘要契约
   - `detail_level=summary` 不再返回全量 `oa_rows`、`bank_rows`、`invoice_rows`、`collapsed_rows`。
   - 每个 pane 只返回最多 3 条 preview rows。
   - 增加 `row_counts` 与 `collapsed_row_counts`，前端计数优先使用这些字段。
   - 保留 `/api/workbench/groups/detail` 作为完整明细加载路径。
   - 补后端 repository/API 测试和前端 mapper/count 测试。

3. Tax-offset 小 payload 与 Redis 容错
   - 保持旧 `/api/tax-offset` 兼容。
   - 新增 `GET /api/tax-offset/summary?month=YYYY-MM`，返回 `month`、`summary`、各 section count、read model metadata，不返回明细数组。
   - 使用独立 Redis key：`tax_offset:summary:{YYYY-MM}`。
   - Redis get/set/delete timeout 或连接错误不得打断 API，记录后继续 SQL/read model 路径。
   - 补 Redis timeout fallback、summary Redis hit/miss 测试。

4. Postgres pool 预热和只读配置入口
   - `PostgresConnection` 增加 `warm_up()`，pool enabled 时调用 `pool.wait(timeout=...)`。
   - `state_store_factory` 构造 Postgres store 后预热连接。
   - 支持可选 `FIN_OPS_POSTGRES_READ_DATABASE_URL` 和 read pool min/max 配置；未配置时读写共用，保证回滚简单。
   - `PostgresStateStore` 读模型 repository 可使用 read connection，写路径继续使用 write connection。
   - 补 settings/factory/state store 单测。

5. 验证
   - 后端：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime tests.test_tax_offset_sql_runtime tests.test_state_store_factory_preflight tests.test_postgres_state_store -v`
   - 前端：`cd web && npm test -- --run WorkbenchApi.test.ts TaxOffsetPage.test.tsx`
   - 编译：`python3 -m py_compile` 相关 Python 文件；必要时 `cd web && npm run build`。
   - 如本地服务可用，重测 p95、DB share、Redis hit、Python CPU。

## Go sidecar 进入条件

只有第一阶段后同时满足任意 2-3 条，才进入 Go read API sidecar：

- 核心只读接口 p95 仍高于 300-500ms。
- `connection_acquire_ms + sql_execute_fetch_ms` 低于总耗时 30%-40%，但整体 p95 仍高。
- Python CPU 或 worker 持续 70%-90% 以上。
- Redis/read model 命中后仍慢，瓶颈转移到 Python 对象构造、JSON 序列化、并发调度。
- 水平扩 Python 的机器成本、内存和部署复杂度明显高于拆 sidecar。
