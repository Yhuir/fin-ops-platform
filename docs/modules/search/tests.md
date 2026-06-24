# Search 测试矩阵

## 七类测试适用性

| 类别 | 适用性 | 当前入口 / 要求 |
| --- | --- | --- |
| 1. Business core unit tests | 条件适用 | 改 search ranking、group context、source fact selection 或匹配规则时适用。 |
| 2. Service-layer tests | 适用 | repository port、projection builder、worker handler、freshness/source-version 变化必须覆盖。 |
| 3. API contract tests | 适用 | `/api/search` response shape、status、filter、permission 或 stale/refreshing 行为变化必须覆盖。 |
| 4. Read model/cache/background job tests | 适用 | `search.read_model.refresh`、`search:all` fan-out、dirty/outbox/readiness、source-version stale skip 必须覆盖。 |
| 5. Frontend component and interaction tests | 当前不适用 | 当前没有独立 search 页面；若新增全局搜索 UI，必须补 Vitest/Browser e2e。 |
| 6. End-to-end business-flow integration tests | 条件适用 | Workbench relation/import/tax/cost/lifecycle 写入影响 search 时适用。 |
| 7. Existing feature regression tests | 适用 | 保持 pending invoice/search compatibility、worker lanes、manifest contract 和 API fallback 行为。 |

## 当前测试入口

- `tests/test_search_pending_sql_runtime.py`
- `tests/test_search_api.py`
- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_rabbitmq_runtime.py`
- `tests/test_workbench_relation_repository.py`
- `tests/test_derived_data_lifecycle_service.py`

## 2026-06-24 - repository port extraction

- 新增：`tests/test_search_pending_sql_runtime.py::SearchReadModelRepositoryPortTests::test_port_excludes_unrelated_read_model_methods`。
- 覆盖：search port 只暴露 `search_index(...)` 和 `save_search_index_rows(...)`，不暴露 pending invoice、bank detail、no-OA 或 workbench relation 方法。
- 验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest -v
```

## 2026-06-24 - app rebuild helper quarantine

- 新增：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_search_rebuild_helpers_stay_out_of_application`。
- 覆盖：`server.py` 不再拥有 `rebuild_search_index_scope(...)` / `_build_search_index_rows_for_month(...)`；`SearchPendingSqlProjectionBuilder` 继续拥有 search rebuild，并通过 `SearchReadModelRepositoryPort` 保存。
- 验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_rebuild_helpers_stay_out_of_application tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest -v
```

## 2026-06-24 - query freshness service extraction

- 新增：`tests/test_search_pending_sql_runtime.py::SearchQueryFreshnessServiceTests`。
- 新增：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_search_query_freshness_helpers_stay_out_of_application`。
- 覆盖：SQL miss 返回 refreshing 并入队、fresh SQL payload 不触发 live scan/source-version enqueue、source-version mismatch 标记 stale 并入队；`server.py` 不再拥有 search SQL payload/helper source-version proof。
- 验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_query_freshness_helpers_stay_out_of_application tests.test_search_pending_sql_runtime.SearchQueryFreshnessServiceTests tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest -v
```

## 2026-06-24 - refresh producer and invalidation extraction

- 新增：`tests/test_search_pending_sql_runtime.py::SearchReadModelRefreshProducerTests`。
- 新增：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_search_refresh_producer_helpers_stay_out_of_application`。
- 覆盖：search refresh producer 通过 gateway enqueue、month/all scope 归一化、invalidation 月份/`all` fallback、gateway unavailable 返回 false；`server.py` 不再拥有 search refresh/invalidation helper。
- 验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application tests.test_search_pending_sql_runtime.SearchReadModelRefreshProducerTests tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest -v
```

## 下一 slice 必跑建议

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## 未测风险

- 当前没有独立 Browser `/api/search` 页面入口；用户可见全局搜索 UI 若后续新增，必须补 Spec-first E2E。
- 真实 PostgreSQL/RabbitMQ/worker drain、high-row search index performance 和 App Status readiness 仍需 staging/production evidence；本地测试不能替代。
