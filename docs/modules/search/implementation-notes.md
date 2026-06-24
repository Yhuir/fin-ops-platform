# Search 实施记录

## 2026-06-24 - selected as next modular IO read model pilot

- 目标：在 no-OA bank batch 本地支持 accounted 后，选择下一个非 Go read model pilot。
- 决策：选择 `search`，下一条边界为 `read-models:search-repository-port-extraction`。
- 理由：`search` 影响 Workbench、bank、invoice、pending invoice、invoice lifecycle、tax/cost/import fan-out 和用户跳转上下文；当前 query/source-version/enqueue/rebuild/invalidation helper 仍主要在 `Application`，比 `bank_account_balance` 的支撑型缺口更值得先处理。
- 首切范围：新增 `SearchReadModelRepositoryPort`，只暴露 manifest 登记的 `search_index(...)` 与 `save_search_index_rows(...)`，并让 SQL read/projection paths 走窄 port。
- 非目标：不改 search ranking、API shape、worker event、scope policy、queue schema、Redis/cache、permissions、frontend behavior、Go/Fiber 或 Go Worker。
- 状态：`search` 仍是 `implementation-gap-open`；本记录不是 module closure。

## 2026-06-24 - repository port extraction

- 目标：为 `search` 建立窄 read model repository port，避免 SQL read/projection save 路径继续依赖 broad `PostgresReadModelRepository` surface。
- 改动：新增 `SearchReadModelRepositoryPort`；`PostgresStateStore.search_sql_read_repository` 返回该 port；`SearchPendingSqlProjectionBuilder.rebuild_search_index_scope(...)` 通过该 port 调用 `save_search_index_rows(...)`；manifest repository owner 更新为 `SearchReadModelRepositoryPort`。
- 保持不变：`/api/search` response shape、fresh/stale/refreshing 语义、search ranking、group context、worker event、scope policy、queue schema、Redis/cache、permissions、frontend behavior 均不变。
- 测试覆盖：`SearchReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods`；复跑 search SQL runtime、search API 和 read model manifest 测试。
- 下一步：`read-models:search-freshness-helper-boundary-audit` 审计 app-owned fresh gate/source-version/enqueue/rebuild/invalidation helper，必要时拆第一条 extraction/quarantine boundary。

## 2026-06-24 - app rebuild helper quarantine

- 目标：删除未调用的 app-owned search rebuild 旧路径，避免 `Application` 继续拥有 search index rebuild 行为。
- 审计结论：`Application.rebuild_search_index_scope(...)` 无调用者；`_build_search_index_rows_for_month(...)` 只被该 app-level rebuild helper 调用。worker/runtime rebuild owner 是 `SearchPendingSqlProjectionBuilder.rebuild_search_index_scope(...)`。
- 改动：删除 `Application.rebuild_search_index_scope(...)` 和 `_build_search_index_rows_for_month(...)`；新增 platform boundary guard 防止它们回到 `server.py`。
- 保持不变：`/api/search` fresh gate、source-version mismatch、refresh enqueue、search ranking、worker event、scope policy、queue schema 和 API shape 均不变。
- 下一步：抽取或隔离 `/api/search` SQL fresh/stale/miss payload assembly、expected source-version proof 和 refresh enqueue helper。

## 2026-06-24 - query freshness service extraction

- 目标：把 `/api/search` SQL read model miss/stale/source-version payload assembly 和 expected source-version proof 从 `Application` 移到显式 service 边界。
- 改动：新增 `SearchQueryFreshnessService` 与 `SearchIndexSourceVersionsProvider`；删除 `Application._get_search_payload_from_sql_read_model(...)` 与 `_search_index_expected_source_versions(...)`；`/api/search` route 只负责参数校验、HTTP status 映射和无 SQL repository 时的 legacy/local fallback。
- 保持不变：search API response shape、status code 行为、SQL miss enqueue reason、source-version stale reasons、search ranking、group context、worker event、scope policy、queue schema、Redis/cache、权限和前端行为均不变。
- 测试覆盖：新增 service-layer tests 覆盖 SQL miss/fresh/source-version mismatch；新增 platform guard 防止 app-owned query freshness helper 回到 `server.py`；复跑 search API/runtime/manifest 相关测试。
- 下一步：审计并拆分 `Application._enqueue_search_read_model_refresh(...)` 与 `_invalidate_search_read_model_scopes(...)`，决定抽取 search refresh producer/invalidation service 还是保留 compat-only wrapper。

## 2026-06-24 - refresh producer and invalidation extraction

- 目标：把 search refresh enqueue 和 invalidation scope normalization 从 `Application` 移到显式 producer。
- 审计结论：`Application._enqueue_search_read_model_refresh(...)` 与 `_invalidate_search_read_model_scopes(...)` 都只是 gateway-backed producer / scope normalization helper，适合抽到 search read model producer。
- 改动：新增 `SearchReadModelRefreshProducer`；删除旧 app-owned refresh/invalidation helper；`SearchQueryFreshnessService`、settings update、import-state invalidation、Workbench invalidation 和 derived lifecycle search cache invalidation 改为调用 producer。
- 保持不变：refresh 仍通过 `ReadModelRefreshGateway`，scope type 仍为 `search`，reason/metadata 透传保持不变；search API、worker event、scope policy、queue schema、Redis/cache、权限和前端行为均不变。
- 下一步：执行 `read-models:search-local-implementation-closure-audit`，确认是否只剩真实 PostgreSQL/worker/App Status/high-row/browser evidence defer，还是仍有本地 implementation gap。
