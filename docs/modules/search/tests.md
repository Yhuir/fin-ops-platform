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
