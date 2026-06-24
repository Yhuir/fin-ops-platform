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

## 2026-06-24 - production repository unavailable fail closed

- 目标：生产 PostgreSQL runtime 下，`/api/search` 缺少 SQL read repository 时不能回退到 legacy/local live scan。
- 审计结论：local closure audit 发现缺口：`SearchQueryFreshnessService.get_payload(...)` 返回 `None` 后，`Application._handle_api_search(...)` 仍会调用 `SearchService.search(...)`。
- 改动：当 `_requires_sql_read_model_runtime()` 为 true 且 SQL search repository 不可用时，`/api/search` 返回 HTTP `503`、`error=read_model_unavailable`、`read_model_status=unavailable`，并通过 `SearchReadModelRefreshProducer` 入队 `api_sql_repository_unavailable`。
- 保持不变：legacy/local 非 PostgreSQL fallback 仍可用；SQL miss/fresh/stale 行为、search ranking、worker event、scope policy、queue schema、Redis/cache、权限和前端行为均不变。
- 后续：已执行 `read-models:search-post-fail-closed-local-implementation-closure-audit`，并拆出 OA projection sync Search producer boundary。

## 2026-06-24 - OA projection sync Search refresh producer boundary

- 目标：让 OA projection sync 影响 Search read model 的 fan-out 也走统一 Search producer，避免 Search refresh enqueue ownership 分散在上游服务。
- 审计结论：`OAProjectionSyncService._mark_downstream_dirty(...)` 仍直接 `ReadModelRefreshGateway.enqueue_many("search", target_scopes, reason="oa_projection_sync")`。该路径没有绕过 durable gateway/scope policy，但绕过了 `SearchReadModelRefreshProducer` 的统一边界。
- 改动：`OAProjectionSyncService` 新增 `search_read_model_refresh_producer` 依赖；默认兼容构造 `SearchReadModelRefreshProducer`；生产 worker 装配显式传入 Search producer；`_mark_downstream_dirty(...)` 调用 producer `enqueue(...)`；静态 guard 防止直接 `enqueue_many("search", ...)` 回流。
- 保持不变：OA sync target scopes、Workbench/OA pending payment/pending invoice fan-out、Search worker event、scope policy、queue schema、API shape、Redis/cache、权限和前端行为均不变。
- 下一步：执行 `read-models:search-post-oa-projection-sync-local-implementation-closure-audit`。

## 2026-06-24 - runtime import-state Search refresh producer boundary

- 目标：让 runtime import-state 持久化后的 Search fan-out 也走统一 Search producer，避免高频 import-state path 继续保留 Search refresh enqueue 的第二套 owner。
- 审计结论：post-OA-sync audit 发现 `_RuntimeWorkerDerivedLifecycle.persist_import_state(...)` 仍直接调用 generic `_enqueue_scopes("search", ..., reason="import_state_changed")`。该路径仍经过 `ReadModelRefreshGateway` 和 scope policy registry，但绕过了 `SearchReadModelRefreshProducer`。
- 改动：`_RuntimeWorkerDerivedLifecycle` 新增可注入 `search_read_model_refresh_producer`，默认以现有 `ReadModelRefreshGateway` 构造 `SearchReadModelRefreshProducer`；`persist_import_state(...)` 的 Search fan-out 改为调用 producer；runtime worker scope test 覆盖 producer delegation；platform guard 防止 `_enqueue_scopes("search", ...)` 或 direct `enqueue_many("search", ...)` 回流。
- 保持不变：import-state target scopes、Workbench/Workbench relation/invoice lifecycle/pending invoice/invoice usage/OA pending payment/bank detail/balance/cost/tax fan-out、Search worker event、scope policy、queue schema、API shape、Redis/cache、权限、审计和前端行为均不变。
- 下一步：执行 `read-models:search-post-runtime-import-state-local-implementation-closure-audit`，确认是否只剩真实 PostgreSQL/worker/App Status/high-row/browser evidence，或是否还有其他本地旧路径需要拆分。

## 2026-06-24 - Search worker all-scope fan-out producer boundary

- 目标：让 Search worker 处理 `search:all` 时的 month shard fan-out 也走统一 Search producer，避免 worker 内部保留第二套 Search enqueue owner。
- 审计结论：post-runtime-import-state audit 发现 `SearchPendingReadModelRefreshService._enqueue_search_scope_shards(...)` 仍直接创建 `ReadModelRefreshGateway` 并调用 `enqueue_many("search", shard_keys, reason="search_all_shard")`。该路径是 Search 模块内部 worker fan-out，且仍经过 durable gateway/scope policy registry，但绕过了 `SearchReadModelRefreshProducer`。
- 改动：`SearchReadModelRefreshProducer` 新增 `enqueue_scope_keys(...)`，保持原 `enqueue(...)` boolean contract；普通 scope normalization 保留 caller order；`SearchPendingReadModelRefreshService` 新增可注入 producer，并让 `search:all` shard fan-out 调用 producer；新增 service-layer test 和 static guard。
- 保持不变：`search:all` 仍只作为 fan-out command；worker 仍从 projection builder 读取 shard list；`enqueued_scope_keys` 顺序、payload shape、dirty scope completion、pending invoice fan-out、Search API、worker event、queue schema、Redis/cache、权限、审计和前端行为均不变。
- 下一步：执行 `read-models:search-post-all-scope-worker-fanout-local-implementation-closure-audit`，确认是否只剩真实 PostgreSQL/worker/App Status/high-row/browser evidence，或是否还有其他本地旧路径需要拆分。
