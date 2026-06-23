# Read Model Search And No-OA Bank Batch Contract

**日期:** 2026-06-23
**Boundary:** `read-models:search-and-no-oa-bank-batch-contract`
**状态:** `closed-autonomous`
**范围:** `search` 与 `no_oa_bank_batch` read-side freshness/status 合同守卫；不改 SQL、worker、route、API shape、前端行为、Go/Fiber、Go Worker 或生产状态。

## 执行结论

本轮审阅了 read-models、no-OA bank batch 产品/模块文档、状态机、测试矩阵、上一轮 cost/tax/turnover analysis，并通过 CodeGraph/精准搜索检查 `SearchPendingReadModelRefreshService`、`NoOaBankBatchApplicationService`、`NoOaBankBatchReadModelRefreshService`、search/no-OA repository ports、scope policy、freshness/status 语义和生产 fail-closed 测试入口。

当前代码已具备以下有效边界：

- `search` 使用 `partitioned_scoped_index`，`search:all` 是 fan-out command，查询侧 freshness 由 search read API 自管；`SearchPendingReadModelRefreshService` 不接受 `Application` fallback dependency。
- `no_oa_bank_batch` 使用 `scoped_incremental`，`all`/month scope 由 scope policy 注册，GET list missing/stale 时只 enqueue refresh，不在热路径同步重建批次。
- no-OA 写入仍由 `NoOaBankBatchApplicationService` 和 relation command service 保护，本轮不改变 submit/withdraw/tag-selection 或 worker rebuild。
- 两者 repository ports 不相交：search 只占 `search_index` / `save_search_index_rows`，no-OA 只占 `list_no_oa_bank_batch_rows`。

本轮只新增 manifest contract guard，锁定 search/no-OA 的 query freshness owner、projection strategy、all-scope semantics、worker ownership、permission owner、test owner 和 repository port contract，防止后续 legacy read path 或 Go/Fiber carve-out 误把两条读链路混用。

## 改动前影响分析

### 1. 模块范围

- 目标模块: `read-models`
- 关联页面模块: `no-oa-bank-batches`
- 子边界: `search`、`no_oa_bank_batch`
- 本次改动类型: manifest contract guard
- 是否改变业务行为: 否
- 是否改变 API response shape: 否
- 是否改变 SQL 查询或写入: 否
- 是否改变 worker refresh: 否
- 是否进入 Go / Fiber / Go Worker candidate: 否

### 2. 合同矩阵

| Contract | `search` | `no_oa_bank_batch` | 本轮守卫 |
| --- | --- | --- | --- |
| query contract | `self_managed_freshness` | `self_managed_freshness` | manifest test |
| projection | `partitioned_scoped_index` | `scoped_incremental` | manifest test |
| all scope | `fan_out_command` | `fan_out_command` | manifest test |
| primary worker | `search` | `no-oa-bank-batch` | manifest test |
| auxiliary worker | `search-pending` / `search-secondary` / `search-tertiary` | none | manifest test |
| repository ports | `search_index` / `save_search_index_rows` | `list_no_oa_bank_batch_rows` | manifest test requires disjoint sets |
| permission owner | `search_api_session` | `no_oa_bank_batch_api_session` | manifest test |

## State Machine Impact

- 全局工作流状态: `AutonomousContinue`，当前执行状态为 `autonomous-continue-after-cost-tax-ledger-summary-contract`。
- 选中边界进入前状态: `read-models:search-and-no-oa-bank-batch-contract` 为 `pending`。
- 已审阅状态机文件:
  - `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
  - `docs/modules/read-models/state-machine.md`
  - `docs/modules/no-oa-bank-batches/state-machine.md`
- 全局状态机定义: definition unchanged。本轮未新增、重命名或改变 workflow state、transition、guard、stop/defer condition 或 completion criterion；只推进单个 queue boundary 从 `pending` 到 `closed-autonomous`。
- 模块状态机定义: definition unchanged。本轮只新增合同守卫，不改变业务状态、UI 状态、read model 状态、worker 状态、operation barrier 状态、force-refresh 状态、permission 状态或 legacy-retirement 状态。
- 成功流转: `pending` -> `closed-autonomous`，自动执行状态更新为 `autonomous-continue-after-search-and-no-oa-bank-batch-contract`。
- defer/block 流转: 若 manifest/verification 失败且无法三轮内收敛，应记录 `deferred-module-failure`；若需要生产写或敏感凭据，应记录 `needs-human-production-gate`。本轮未触发。
- 完成时必须更新: 本 analysis、`tests/test_read_model_manifest.py`、read-models tests/implementation notes、no-OA state-machine 变更记录、`autonomous/STATE.md`、`autonomous/MODULE-QUEUE.md`、`autonomous/JOURNAL.md`、`autonomous/NEXT-PROMPT.md`。

## Legacy 退役与污染防护

| Legacy / pollution risk | 当前状态 | 本轮处理 | 后续 |
| --- | --- | --- | --- |
| Search read API 被旧 pending invoice/search-pending worker owner 污染 | manifest 已区分 primary/auxiliary worker | 新 test 锁定 primary `search` 和 auxiliary worker 集合 | legacy-read-path-removal slice 查直接旧读路径 |
| Search repository port 与 no-OA list port 混用 | manifest 已分列 ports | 新 test 要求 port sets 互不相交 | repository split 按 port owner 小步迁移 |
| no-OA GET missing/stale 同步 rebuild 批次 | no-OA tests 已覆盖 missing/stale 不热路径 rebuild | manifest guard 锁定 self-managed freshness 与 no-OA query owner | 后续 legacy guard 查 live scan/direct fresh |
| `all` scope 被当 queryable parent proof | 文档规定两者 `all` 是 fan-out command | 新 test 锁定 fan-out semantics | legacy-read-path-removal slice 查 parent fake fresh |
| no-OA read model refresh 执行 relation repair 写入 | no-OA worker tests 已覆盖 refresh 不 repair relation | 本轮不改 worker，只登记合同 | 后续如改 worker 必跑 no-OA refresh tests |

## 七类测试映射

| 类别 | 是否适用 | 本轮覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改 search 规则、no-OA draft/submitted/withdrawn 状态、internal transfer、金额或权限规则 |
| 2. Service-layer tests | 适用 | manifest guard 锁定 query owner、permission owner、worker owner、repository port owner |
| 3. API contract tests | 不适用 | 无 HTTP status、response shape、错误字段或权限行为变化；既有 search/no-OA API tests 继续覆盖 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_search_and_no_oa_bank_batch_manifest_preserve_read_side_contracts` 锁定 scope/worker/force-refresh/port 合同 |
| 5. Frontend component and interaction tests | 不适用 | 无前端行为变化 |
| 6. End-to-end business-flow integration tests | 不适用 | 本轮不触发 submit/withdraw/import/worker 链路 |
| 7. Existing feature regression tests | 适用 | 既有 `tests/test_search_pending_sql_runtime.py`、`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_no_oa_bank_batch_read_model_refresh.py` 作为后续必要验证集 |

## 环境与验证限制

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 是否需要真实 PostgreSQL: 否，本轮是 manifest/test guard。
- 是否需要真实 worker/outbox/readiness: 否。
- 是否会写生产数据: 否。
- 生产验证: 不适用。
- 敏感凭据处理: 未读取、未记录凭据。

## 后续边界

下一步推进 `read-models:legacy-read-path-removal-guards`：

- 查找 live scan、direct queue write、direct `read_model_status=fresh`、direct source-version mismatch、direct SQL 写 `job.outbox_events` / `job.read_model_dirty_scopes` 等旧路径。
- 能删除的旧路径直接删除；不能删除的标为 compat-only，必须登记 owner、caller、禁止写入和删除条件。
