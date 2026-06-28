# Search 状态机

## Page Read 状态

`/api/search` 当前是 direct API 读取：route 调用 `SearchService.search(...)` 并直接返回业务 payload。页面读取不再暴露 `read_model_status`、`read_model_scope_key`、`refresh_enqueued`、`read_model_unavailable` 或等价 freshness 字段；SQL search index missing/stale/source mismatch 不阻断该 API。

## 已删除的 Legacy Read Model 状态

Search freshness service、refresh producer、`search.read_model.refresh` worker lanes、manifest 和 App Status read-model registration 已删除。`fresh`、`refreshing`、`stale`、`failed`、`unavailable` 不再是 `/api/search` 的页面读取状态。

## Worker 状态

- 无 Search read-model worker lane。
- `pending-invoice` worker 和 `pending_invoice.read_model.refresh` 已删除。
- `search-pending`、`search`、`search-secondary`、`search-tertiary` 已从 worker registry、部署 env 和 systemd 启动清单删除。

## 非法状态

- `/api/search` 页面响应重新返回 `read_model_status`、`refresh_enqueued`、scope key 或 `read_model_unavailable`。
- 页面/API 从 legacy worker 同步 rebuild 后返回 `read_model_status` 或等价 freshness 字段。
- 重新新增 `search.read_model.refresh`、Search freshness service、Search refresh producer、Search manifest/App Status registration 或 Search worker lane。
- Search repository port 暴露非 manifest-listed 方法，或继续把 pending invoice repository 方法混入 search port。
- Go/Fiber/Go Worker 直接继承现有 `Application` search helper 作为边界。

## 变更记录

| 日期 | 变更 | 状态机影响 | 测试/验证 |
| --- | --- | --- | --- |
| 2026-06-24 | 建立 search 模块维护骨架，并选择 search 作为下一 read model pilot | 历史记录；后续 direct API cleanup 已删除 Search port/read-model refresh/SQL storage | `bash scripts/verify.sh docs` |
| 2026-06-24 | OA projection sync Search fan-out 曾改走 `SearchReadModelRefreshProducer` | 历史状态；2026-06-27 删除 Search refresh path 后，OA sync 不再 enqueue Search read model refresh。 | `tests.test_oa_projection_sync_service.OaProjectionSyncServiceTests.test_oa_sync_no_longer_enqueues_search_read_model_refresh` |
| 2026-06-24 | Runtime import-state Search fan-out 曾改走 `SearchReadModelRefreshProducer` | 历史状态；2026-06-27 删除 Search refresh path 后，runtime import-state 不再 enqueue Search read model refresh。 | `tests.test_runtime_worker_read_model_refresh_scopes` |
| 2026-06-24 | Search worker `search:all` shard fan-out 曾改走 `SearchReadModelRefreshProducer` | 历史状态；2026-06-27 删除 Search worker lanes 后，不再存在 Search all-scope fan-out command。 | `tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_read_model_refresh_path_is_removed` |
| 2026-06-24 | Post-all-scope local closure audit | 历史状态；Search local support accounting 已被 2026-06-27 direct API / refresh-path deletion 替代。 | 当前验证见 2026-06-27 删除行。 |
| 2026-06-27 | `/api/search` 页面读取改为 direct `SearchService.search(...)` | 页面读取状态机不再使用 SQL read model freshness gate | `PYTHONPATH=backend/src python3 -m pytest tests/test_search_api.py tests/test_search_service.py -q` |
| 2026-06-27 | Search SQL index storage/projection 删除 | Fresh PostgreSQL migrations 不再创建 `read_model.search_index_rows`；Search repository port、state-store property 和 projection rebuild helper 已删除 | `tests/test_postgres_migrations.py`、`tests/test_platform_runtime_boundary_guards.py` |
| 2026-06-28 | 删除 Search/pending-invoice legacy projection 文件 | `SearchQueryFreshnessService`、`SearchReadModelRefreshProducer`、`search.read_model.refresh`、Search worker lanes、manifest、App Status registration、`SearchPendingSqlProjectionBuilder` 和 pending-invoice worker/projection/repository 均不再存在 | `tests/test_platform_runtime_boundary_guards.py`、`tests/test_runtime_worker_registry.py`、`tests/test_read_model_manifest.py`、`tests/test_deploy_runtime_examples.py`、`tests/test_rabbitmq_runtime.py` |
| 2026-06-27 | Workbench import-state scope helper 合并 | Search 状态不变；同步删除 Workbench import-state 测试中的旧 Search refresh 断言，保持 import-state 不再投递 Search read model refresh | `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests.test_runtime_worker_read_model_refresh_scopes -v` |
