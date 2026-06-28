# Search E2E Coverage

当前没有独立 Browser E2E 覆盖要求。

| Spec ID | 状态 | 覆盖 | 说明 |
| --- | --- | --- | --- |
| `SEARCH-E2E-001` | `not-applicable` | API/runtime tests | `/api/search` 无独立前端 route；direct API 读取覆盖来自 `tests/test_search_api.py`、`tests/test_search_service.py`、worker registry 和 relation/import fan-out regression。 |
