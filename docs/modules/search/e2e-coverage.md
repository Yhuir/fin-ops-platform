# Search E2E Coverage

当前没有独立 Browser E2E 覆盖要求。

| Spec ID | 状态 | 覆盖 | 说明 |
| --- | --- | --- | --- |
| `SEARCH-E2E-001` | `not-applicable` | API/runtime tests | `/api/search` 无独立前端 route；现有覆盖来自 `tests/test_search_pending_sql_runtime.py`、`tests/test_search_api.py`、worker registry 和 relation/import 写后零 fan-out、访问时收敛 regression。 |
