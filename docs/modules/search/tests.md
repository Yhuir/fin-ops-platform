# Search 测试矩阵

## 七类测试适用性

| 类别 | 适用性 | 当前入口 / 要求 |
| --- | --- | --- |
| 1. Business core unit tests | 条件适用 | 改 search ranking、group context、source fact selection 或匹配规则时适用。 |
| 2. Service-layer tests | 适用 | `SearchService` direct payload 变化必须覆盖；不得新增 Search SQL repository port。 |
| 3. API contract tests | 适用 | `/api/search` response shape、status、filter、permission 或 direct payload 行为变化必须覆盖；页面合同不得重新暴露 read-model freshness 字段。 |
| 4. Read model/cache/background job tests | 条件适用 | 仅在确认 Search read-model storage/refresh 不回流时做负向 guard；Search refresh/freshness/worker 和 Search SQL storage 已删除。 |
| 5. Frontend component and interaction tests | 当前不适用 | 当前没有独立 search 页面；若新增全局搜索 UI，必须补 Vitest/Browser e2e。 |
| 6. End-to-end business-flow integration tests | 条件适用 | Workbench relation/import/tax/cost/lifecycle 写入影响 search direct payload 时适用。 |
| 7. Existing feature regression tests | 适用 | 保持 Search worker/manifest/SQL storage 不回流和 `/api/search` direct API 行为。 |

## 当前测试入口

- `tests/test_search_api.py`
- `tests/test_search_service.py`
- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_rabbitmq_runtime.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_workbench_relation_repository.py`
- `tests/test_derived_data_lifecycle_service.py`

## 当前守卫

- `/api/search` 直接返回 `SearchService.search(...)` payload。
- `/api/search` 不返回 `read_model_status`、`read_model_scope_key`、`refresh_enqueued` 或 `read_model_unavailable`。
- `search.read_model.refresh` 不在 worker registry、manifest、App Status、RabbitMQ dispatcher 或 deploy env。
- `read_model.search_index_rows`、Search SQL repository/port/projection/state-store property 不回流。
- 历史 `search_pending_sql_projection.py` 已删除；不得作为 Search 或 pending-invoice projection 恢复。

## 建议验证

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_search_api.py tests/test_search_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py -k 'search_sql_index_storage_stays_removed or search_page_read_stays_direct or search_read_model_refresh_path_is_removed' -q
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_rabbitmq_runtime -v
```

## 未测风险

- 当前没有独立 Browser `/api/search` 页面入口；用户可见全局搜索 UI 若后续新增，必须补 Spec-first E2E。
- 真实 PostgreSQL/RabbitMQ/worker drain、high-row search direct payload performance 和生产用户流 smoke evidence 仍需 staging/production evidence；本地测试不能替代。
