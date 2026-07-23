# Search 测试矩阵

> 2026-07-22 Phase 27 当前合同：普通 import、relation、规则与 OA 写入零 Search fan-out；`/api/search` 访问发现 source-version mismatch 后才经 gateway 入队 exact scope。本文后续 2026-06/07 的 fan-out 记录只保留为历史回归溯源，不是当前 writer 合同。

## 七类测试适用性

| 类别 | 适用性 | 当前入口 / 要求 |
| --- | --- | --- |
| 1. Business core unit tests | 条件适用 | 改 search ranking、group context、source fact selection 或匹配规则时适用。 |
| 2. Service-layer tests | 适用 | repository port、projection builder、worker handler、freshness/source-version 变化必须覆盖。 |
| 3. API contract tests | 适用 | `/api/search` response shape、status、filter、permission 或 stale/refreshing 行为变化必须覆盖。 |
| 4. Read model/cache/background job tests | 适用 | `search.read_model.refresh`、`search:all` fan-out、dirty/outbox/readiness、source-version stale skip 必须覆盖。 |
| 5. Frontend component and interaction tests | 当前不适用 | 当前没有独立 search 页面；若新增全局搜索 UI，必须补 Vitest/Browser e2e。 |
| 6. End-to-end business-flow integration tests | 条件适用 | Workbench relation/import/tax/cost/lifecycle 写入后访问 Search、验证 access-time 收敛时适用。 |
| 7. Existing feature regression tests | 适用 | 保持 pending invoice/search compatibility、worker lanes、manifest contract 和 API fallback 行为。 |

## 当前测试入口

- `tests/test_search_pending_sql_runtime.py`
- `tests/test_search_api.py`
- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_rabbitmq_runtime.py`
- `tests/test_workbench_relation_repository.py`
- `tests/test_derived_data_lifecycle_service.py`

## 2026-07-06 - Search source-version unchanged skip

- 新增：`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_search_index_scope_summary_reads_versions_without_loading_rows`。
- 新增：`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_search_projection_skips_unchanged_scope_without_workbench_scan`。
- 更新：`tests/test_search_pending_sql_runtime.py::SearchReadModelRepositoryPortTests::test_port_excludes_unrelated_read_model_methods` 覆盖 `search_index_scope_summary(...)` narrow port。
- 覆盖：Search worker 在 source_versions 未变化时只读 scope summary 并返回 `source_versions_unchanged`，不扫描 `read_model.workbench_rows`，不调用 `save_search_index_rows(...)`。
- 验证命令：

```bash
PYTHONPATH=backend/src:. python3 -m pytest tests/test_search_pending_sql_runtime.py tests/test_search_api.py tests/test_read_model_manifest.py tests/test_runtime_worker_registry.py -q
```

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

## 2026-06-24 - production repository unavailable fail closed

- 新增：`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_search_api_requires_sql_repository_in_production_without_live_scan`。
- 覆盖：生产 PostgreSQL runtime 下 `/api/search` 缺少 SQL repository 时返回 unavailable、入队 `api_sql_repository_unavailable`，并且不调用 legacy/local live scan。
- 验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_search_api_requires_sql_repository_in_production_without_live_scan tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_search_api_miss_enqueues_refresh_without_sync_scan tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_search_api_reads_sql_index tests.test_search_api -v
```

## 2026-06-24 - OA projection sync Search producer boundary

- 新增：`tests/test_oa_projection_sync_service.py::OaProjectionSyncServiceTests::test_oa_sync_search_refresh_uses_search_producer_boundary`。
- 更新：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_search_refresh_producer_helpers_stay_out_of_application` 防止 `OAProjectionSyncService` 重新直接 `enqueue_many("search", ...)`。
- 覆盖：OA sync 下游 Search refresh fan-out 走 `SearchReadModelRefreshProducer`，同时保持 Workbench/OA pending payment/pending invoice fan-out 和 Search dirty scope 行为。
- 验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_projection_sync_service.OaProjectionSyncServiceTests.test_oa_sync_search_refresh_uses_search_producer_boundary tests.test_oa_projection_sync_service.OaProjectionSyncServiceTests.test_oa_sync_marks_oa_pending_payment_read_model_dirty_for_progress_rows tests.test_oa_projection_sql_runtime.OAProjectionSqlRuntimeTests.test_oa_sync_worker_persists_projection_and_marks_downstream_scopes_dirty tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v
```

## 2026-06-24 - runtime import-state Search producer boundary

- 新增：`tests/test_runtime_worker_read_model_refresh_scopes.py::RuntimeWorkerReadModelRefreshScopeTests::test_import_state_search_refresh_uses_search_producer_boundary`。
- 更新：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_search_refresh_producer_helpers_stay_out_of_application` 防止 runtime worker handlers 重新直接 `_enqueue_scopes("search", ...)` 或 `enqueue_many("search", ...)`。
- 覆盖：import-state 持久化后的 Search refresh fan-out 走 `SearchReadModelRefreshProducer`，同时 Workbench relation 等非 Search fan-out 继续通过原有 queue path。
- 验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v
```

## 2026-06-24 - Search worker all-scope fan-out producer boundary

- 更新：`tests/test_search_pending_sql_runtime.py::SearchReadModelRefreshProducerTests::test_enqueue_returns_false_when_gateway_unavailable` 覆盖 `enqueue_scope_keys(...)` unavailable contract。
- 新增：`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_refresh_handler_expands_search_all_through_search_producer_boundary`。
- 更新：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_search_refresh_producer_helpers_stay_out_of_application` 防止 `SearchPendingReadModelRefreshService` 重新直接 `enqueue_many("search", ...)`。
- 覆盖：`search:all` worker shard fan-out 走 `SearchReadModelRefreshProducer.enqueue_scope_keys(...)`，同时保留 existing shard order、payload shape 和 completion behavior。
- 验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime.SearchReadModelRefreshProducerTests tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_refresh_handler_expands_search_all_into_month_shards tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_refresh_handler_expands_search_all_through_search_producer_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v
```

## 2026-06-24 - post-all-scope local closure audit

- 新增测试：无。本 slice 是 analysis/accounting，没有改运行时代码或测试 contract。
- 复用覆盖：Search repository port、query freshness service、refresh producer、production fail-closed、OA fan-out、runtime import-state fan-out、Search worker all-scope fan-out、manifest、registry 和 static guard 测试。
- 结论：未发现剩余本地 implementation gap；Search local support 转为 `production-evidence-deferred`，不代表全局模块闭环。
- 验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_oa_projection_sync_service tests.test_oa_projection_sql_runtime tests.test_runtime_worker_read_model_refresh_scopes tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## 2026-07-03 - row-level no-op persistence

- 更新：`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_search_index_rows_are_saved_with_bulk_values`。
- 新增：`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_search_index_bulk_save_deletes_scope_when_result_is_empty`。
- 覆盖：Search index 保存路径按 `row_id` bulk upsert，no-op 行通过 `is distinct from` 跳过更新；同 scope stale rows 单独删除；空结果仍按 `scope_month` 删除，避免保留旧搜索结果。
- 回归目标：禁止恢复整月 delete + 全量 rewrite 的旧持久化逻辑。
- 验证命令：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_search_pending_sql_runtime.py -q
```

## 下一 slice 必跑建议

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_oa_projection_sync_service tests.test_oa_projection_sql_runtime tests.test_runtime_worker_read_model_refresh_scopes tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## 未测风险

- 当前没有独立 Browser `/api/search` 页面入口；用户可见全局搜索 UI 若后续新增，必须补 Spec-first E2E。
- 真实 PostgreSQL/RabbitMQ/worker drain、high-row search index performance、App Status readiness 和生产页面/用户流 smoke evidence 仍需 staging/production evidence；本地测试不能替代。

## 2026-07-22 Phase 27 搜索访问收敛回归

- `tests/test_search_api.py` 与 search freshness tests 必须证明访问时比较 exact source versions，仅在 missing/stale 时通过 gateway 入队 current month；fresh 时零队列 I/O。
- 普通 import/settings/relation 写不再直接发布 search refresh；旧 import-state/search lifecycle fan-out 测试应改为零事件断言。
- `search:all` 只保留为显式 maintenance fan-out command；不得从普通业务写路径恢复调用。
