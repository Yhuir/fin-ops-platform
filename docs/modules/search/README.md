# Search 模块维护入口

- Module key: `search`
- 类型: 资源/API 模块
- Route: `/api/search`
- Page key: `N/A`

## 修改前必读

- `docs/dev/api-contracts.md`
- `docs/modules/search/boundary-io.md`
- `docs/modules/search/tests.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/operations/runtime-worker-governance.md`

## 代码入口

- `backend/src/fin_ops_platform/app/server.py`：当前 `/api/search` route 和 direct `SearchService.search(...)` HTTP 映射入口。
- `backend/src/fin_ops_platform/services/search_service.py`：`/api/search` 页面/API 读取事实源，直接组装搜索 rows、groups 和统计 payload。
- `backend/src/fin_ops_platform/services/read_model_manifest.py`：当前不再登记 `search` read model。
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`：当前不再登记 Search read-model worker lanes。
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`：当前不再包含 Search SQL index 读写方法；保留非 Search legacy read-model repositories。

## 当前边界

`search` 是资源/API 模块，不是独立前端页面。当前 `/api/search` 直接调用 `SearchService.search(...)` 组装业务 payload；页面合同不返回 `read_model_status`、`read_model_scope_key`、`refresh_enqueued`、`read_model_unavailable` 或等价 freshness 字段。Search freshness service、refresh producer、`search.read_model.refresh` worker lanes、manifest 和 App Status read-model registration 已删除。

Search SQL index/projection storage 已删除，fresh PostgreSQL migrations 不再创建 `read_model.search_index_rows`。历史 `search_pending_sql_projection.py` 已随 pending-invoice legacy projection 删除，不得重新接入 Search 页面读取。

## 维护触发器

- `/api/search` response shape、status、error、filter、scope 或 permission 变化。
- direct search query contract 变化。
- pending invoice compatibility behavior 变化但不得重新引入 Search SQL index/projection。
- 任何会影响 direct search payload、权限、过滤或 Go hot-path admission 的改动。

## 本目录文件

- `state-machine.md`：Search direct API 和已删除 read-model worker 状态。
- `tests.md`：七类测试适用性、现有测试入口和验证命令。
- `implementation-notes.md`：实施记录、边界决策、风险和后续事项。
- `e2e-spec.md`：当前不适用；`/api/search` 没有独立前端页面。
- `e2e-coverage.md`：当前不适用；由 API/runtime/integration 覆盖。
