# Search 模块维护入口

- Module key: `search`
- 类型: 资源/API 模块
- Route: `/api/search`
- Page key: `N/A`

## 修改前必读

- `docs/modules/read-models/README.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/read-models/tests.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/operations/runtime-worker-governance.md`

## 代码入口

- `backend/src/fin_ops_platform/app/server.py`：当前 `/api/search` route、SQL read model HTTP 映射、Search service/producer 依赖组装和 legacy/local fallback 入口。
- `backend/src/fin_ops_platform/services/search_query_freshness_service.py`：Search SQL read model miss/stale/source-version freshness contract。
- `backend/src/fin_ops_platform/services/search_read_model_refresh_producer.py`：Search refresh enqueue、invalidation scope normalization 和上游 fan-out producer boundary。
- `backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py`：`search.read_model.refresh` 与兼容 pending invoice refresh worker handler。
- `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`：search index projection builder 与 pending invoice 兼容 projection builder。
- `backend/src/fin_ops_platform/services/read_model_manifest.py`：`search` read model manifest contract。
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`：`search`、`search-secondary`、`search-tertiary` 和兼容 `search-pending` worker registration。
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`：过渡期 SQL repository owner，包含 `search_index(...)` 与 `save_search_index_rows(...)`。

## 当前边界

`search` 是 read model API/索引模块，不是独立前端页面。当前 `/api/search` 优先读取 SQL read model；SQL payload missing、stale 或 source-version mismatch 时必须返回 non-fresh status 并通过 `ReadModelRefreshGateway` 入队，不能同步 live scan 后伪装 fresh。

`search:all` 是 fan-out command，不是页面 freshness parent proof。worker 应把 `all` 展开为 month shard；month shard rebuild 后才能写入 search index rows。

当前本地已完成 repository port、query freshness service、refresh producer、rebuild helper quarantine、生产 repository-unavailable fail-closed、OA projection sync Search fan-out producer boundary、runtime import-state Search fan-out producer boundary、Search worker `search:all` shard fan-out producer boundary 和 post-all-scope local closure audit。审计未发现剩余本地 implementation gap；Search local support 已进入 `production-evidence-deferred`，但不是全局模块闭环。真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍需后续生产证据或显式人工 gate。

## 维护触发器

- `/api/search` response shape、status、error、filter、scope 或 permission 变化。
- search index source/schema version、scope policy、worker event、worker lane、RabbitMQ dispatch 或 App Status registry 变化。
- search projection source facts、WorkBench relation dependency、pending invoice compatibility behavior 或 repository port 变化。
- 任何会影响 search stale/fresh 判断、refresh enqueue、operation barrier target 或 Go hot-path admission 的改动。

## 本目录文件

- `state-machine.md`：Search read model、worker 和 legacy/compat 状态。
- `tests.md`：七类测试适用性、现有测试入口和验证命令。
- `implementation-notes.md`：实施记录、边界决策、风险和后续事项。
- `e2e-spec.md`：当前不适用；`/api/search` 没有独立前端页面。
- `e2e-coverage.md`：当前不适用；由 API/runtime/integration 覆盖。
