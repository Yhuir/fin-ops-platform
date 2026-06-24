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
