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
