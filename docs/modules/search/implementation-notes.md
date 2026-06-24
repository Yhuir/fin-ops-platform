# Search 实施记录

## 2026-06-24 - selected as next modular IO read model pilot

- 目标：在 no-OA bank batch 本地支持 accounted 后，选择下一个非 Go read model pilot。
- 决策：选择 `search`，下一条边界为 `read-models:search-repository-port-extraction`。
- 理由：`search` 影响 Workbench、bank、invoice、pending invoice、invoice lifecycle、tax/cost/import fan-out 和用户跳转上下文；当前 query/source-version/enqueue/rebuild/invalidation helper 仍主要在 `Application`，比 `bank_account_balance` 的支撑型缺口更值得先处理。
- 首切范围：新增 `SearchReadModelRepositoryPort`，只暴露 manifest 登记的 `search_index(...)` 与 `save_search_index_rows(...)`，并让 SQL read/projection paths 走窄 port。
- 非目标：不改 search ranking、API shape、worker event、scope policy、queue schema、Redis/cache、permissions、frontend behavior、Go/Fiber 或 Go Worker。
- 状态：`search` 仍是 `implementation-gap-open`；本记录不是 module closure。
