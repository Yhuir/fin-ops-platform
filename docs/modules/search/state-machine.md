# Search 状态机

## Read Model 状态

| 状态 | 含义 | 合法来源 |
| --- | --- | --- |
| `fresh` | SQL search index payload 的 schema/source versions 与当前 expected contract 匹配。 | `/api/search` SQL read path。 |
| `refreshing` | SQL payload missing、scope 正在 dirty/outbox active，或 repository unavailable。 | `/api/search` fresh gate、App Status、runtime queue。 |
| `stale` | SQL payload 存在但 source/schema mismatch。 | `/api/search` source-version gate。 |
| `failed` | worker/runtime queue 对 `search.read_model.refresh` 记录失败。 | Runtime worker / App Status。 |
| `unavailable` | SQL read model repository 或 storage contract 不可用。 | API fresh gate / App Status。 |

## Worker 状态

- `search`、`search-secondary`、`search-tertiary` 是 search primary/parallel worker lanes。
- `search-pending` 是兼容组合 worker，仍可处理 `search.read_model.refresh` 与 `pending_invoice.read_model.refresh`，但不能成为新的 search owner。
- `search:all` 只能作为 fan-out command；不得直接发布假 fresh parent proof。

## 非法状态

- 页面/API 从 live service 同步 rebuild 后返回 `read_model_status=fresh`。
- search read model service 或 worker 直接写 `job.outbox_events` / `job.read_model_dirty_scopes`，绕过 `ReadModelRefreshGateway` 或等价事务 contract。
- Search repository port 暴露非 manifest-listed 方法，或继续把 pending invoice repository 方法混入 search port。
- Go/Fiber/Go Worker 直接继承现有 `Application` search helper 作为边界。

## 变更记录

| 日期 | 变更 | 状态机影响 | 测试/验证 |
| --- | --- | --- | --- |
| 2026-06-24 | 建立 search 模块维护骨架，并选择 search 作为下一 read model pilot | 不改变运行时状态定义；记录下一步应先抽 `SearchReadModelRepositoryPort` | `bash scripts/verify.sh docs` |
| 2026-06-24 | OA projection sync Search fan-out 改走 `SearchReadModelRefreshProducer` | 不改变 read model 状态；Search refresh enqueue ownership 从 OA sync 直接 `enqueue_many("search", ...)` 收敛到 Search producer boundary | `PYTHONPATH=backend/src python3 -m unittest tests.test_oa_projection_sync_service.OaProjectionSyncServiceTests.test_oa_sync_search_refresh_uses_search_producer_boundary tests.test_oa_projection_sql_runtime.OAProjectionSqlRuntimeTests.test_oa_sync_worker_persists_projection_and_marks_downstream_scopes_dirty tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v` |
| 2026-06-24 | Runtime import-state Search fan-out 改走 `SearchReadModelRefreshProducer` | 不改变 read model 状态；高频 import-state refresh ownership 从 runtime worker generic `_enqueue_scopes("search", ...)` 收敛到 Search producer boundary | `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v` |
| 2026-07-05 | Runtime import-state Search fan-out 进一步收口到 `import_state_changed` lifecycle executor | 不改变 Search read model 状态；persist callback 不再直接逐个 fan out downstream read model，Search producer 由 `search_cache` domain executor override 调用 | `tests.test_runtime_worker_read_model_refresh_scopes.RuntimeWorkerReadModelRefreshScopeTests.test_import_state_search_refresh_uses_search_producer_boundary` |
| 2026-06-24 | Search worker `search:all` shard fan-out 改走 `SearchReadModelRefreshProducer` | 不改变 read model 状态；worker all-scope fan-out ownership 从 direct gateway enqueue 收敛到 Search producer boundary，`search:all` 仍是 fan-out command | `PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime.SearchReadModelRefreshProducerTests tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_refresh_handler_expands_search_all_into_month_shards tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_refresh_handler_expands_search_all_through_search_producer_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v` |
| 2026-06-24 | Post-all-scope local closure audit | 不改变 read model 状态定义；本地 Search 支持已 accounted 并转为 `production-evidence-deferred`，但真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍未闭环 | `PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_oa_projection_sync_service tests.test_oa_projection_sql_runtime tests.test_runtime_worker_read_model_refresh_scopes tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v` |
