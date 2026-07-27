# Search 模块维护入口

- Module key：`search`
- 类型：共享 read-model API 模块
- Route：`/api/search`
- Page key：`N/A`

## 修改前必读

- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/modules/search/boundary-io.md`
- `docs/modules/runtime-workers/boundary-io.md`
- `docs/operations/runtime-worker-governance.md`

## 当前代码入口

- Route / assembly：`backend/src/fin_ops_platform/app/server.py`
- Query freshness：`backend/src/fin_ops_platform/services/search_query_freshness_service.py`
- Refresh producer：`backend/src/fin_ops_platform/services/search_read_model_refresh_producer.py`
- Worker service：`backend/src/fin_ops_platform/services/search_read_model_refresh.py`
- SQL projection：`backend/src/fin_ops_platform/services/search_sql_projection.py`
- Repository port：`backend/src/fin_ops_platform/services/search_read_model_repository.py`
- SQL repository：`backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Manifest/worker：`read_model_manifest.py`、`runtime_worker_registry.py`

## 当前边界

Search 是三个保留共享 read model 之一，只承担搜索索引：

- `/api/search` 在 payload I/O 前验证 scope freshness；missing/stale 时只入队当前月份并 fail closed。
- `search:all` 只用于显式维护 fan-out，不是可查询 parent projection。
- worker 按月份读取 canonical search source，source proof 未变化时 no-op；变化时按 `row_id` upsert 并删除同 scope stale rows。
- 普通 import、OA sync、relation 或页面写入不 fan-out Search refresh。
- `search-pending` worker、pending-invoice 兼容 projector 和 Workbench generation 输入已删除。
- Search 不提供页面 rows/summary/detail，也不能被目标页面用作事实源或 fallback。

## 文档

- `boundary-io.md`：输入、输出、持久化、worker 与依赖方向。
- `tests.md`：Search API、scope、freshness、worker 和 repository 回归。
- `implementation-notes.md`：历史实施记录，不覆盖当前合同。
