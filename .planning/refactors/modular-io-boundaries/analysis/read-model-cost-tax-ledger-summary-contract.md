# Read Model Cost Tax Ledger Summary Contract

**日期:** 2026-06-23
**Boundary:** `read-models:cost-tax-ledger-summary-contract`
**状态:** `closed-autonomous`
**范围:** `cost_statistics`、`tax_offset`、`turnover_ledger` read model 合同守卫；不改 SQL、worker、route、API shape、前端行为、Go/Fiber、Go Worker 或生产状态。

## 执行结论

本轮审阅了 read-models、cost-tax 产品规格、cost-statistics、tax-offset、turnover-ledger 文档、状态机、测试矩阵以及上一轮 invoice lifecycle/input/output analysis，并通过 CodeGraph/精准搜索检查 `CostStatisticsQueryService`、`TaxOffsetQueryService`、`TurnoverLedgerQueryService`、`ReadModelQueryGateway`、`ReadModelScopePolicyRegistry`、repository ports、parent/fan-out scope semantics 和 production fail-closed 测试。

当前代码已具备以下有效边界：

- `cost_statistics` 是 partitioned scoped parent rollup；`active:all` / `all:all` 是 queryable parent aggregate，必须从已物化月份 shard 聚合并写真实 readiness，不能被降级为普通 fan-out-only `all`。
- `tax_offset` 是 month scoped incremental；`all` 只用于 worker fan-out 到月份 shard，不是普通 tax payload scope。
- `turnover_ledger` 当前主读 scope 是 `all`，通过 `ReadModelQueryGateway` 和 `turnover-ledger` worker 维护 freshness；projection 必须依赖 fresh `workbench_relation` distribution，non-fresh 时不保存半成品。
- 三者都通过 `read_model_query_gateway` 合同暴露 freshness，不应在生产 SQL repository missing/miss/stale 时走旧 live rebuild 伪 fresh。
- `cost_statistics` 与 `tax_offset` 共享旧 `cost-tax` 兼容消费者，但 primary worker 必须分别是 `cost-statistics` 与 `tax-offset`；`turnover_ledger` 必须保持独立 worker 和 repository ports。

本轮不改运行时代码，只把三者的 shared manifest 合同加硬：

- `cost_statistics` 必须保持 `queryable_parent_aggregate` 与 `partitioned_scoped_parent_rollup`。
- `tax_offset` 与 `turnover_ledger` 必须保持 `fan_out_command` 与 `partitioned_scoped_incremental`。
- 三者必须保持独立 query owner、permission owner 和 repository port contract，避免 cost/tax/turnover summary read model 互相污染。

## 改动前影响分析

### 1. 模块范围

- 目标模块: `read-models`
- 关联页面模块: `cost-statistics`、`tax-offset`、`turnover-ledger`
- 子边界: `cost_statistics`、`tax_offset`、`turnover_ledger`
- 本次改动类型: manifest contract guard
- 是否改变业务行为: 否
- 是否改变 API response shape: 否
- 是否改变 SQL 查询或写入: 否
- 是否改变 worker refresh: 否
- 是否进入 Go / Fiber / Go Worker candidate: 否

### 2. 合同矩阵

| Contract | `cost_statistics` | `tax_offset` | `turnover_ledger` | 本轮守卫 |
| --- | --- | --- | --- | --- |
| query contract | `read_model_query_gateway` | `read_model_query_gateway` | `read_model_query_gateway` | manifest test |
| projection | `partitioned_scoped_parent_rollup` | `partitioned_scoped_incremental` | `partitioned_scoped_incremental` | manifest test |
| all scope | `queryable_parent_aggregate` | `fan_out_command` | `fan_out_command` | manifest test |
| primary worker | `cost-statistics` | `tax-offset` | `turnover-ledger` | manifest test |
| auxiliary worker | `cost-tax` compat | `cost-tax` compat | none | manifest test |
| repository ports | cost read/write parent+rows contract | tax read/write month contract | turnover list/save/clear rows contract | manifest test requires disjoint sets |

## State Machine Impact

- 全局工作流状态: `AutonomousContinue`，当前执行状态为 `autonomous-continue-after-invoice-lifecycle-and-usage-contract`。
- 选中边界进入前状态: `read-models:cost-tax-ledger-summary-contract` 为 `pending`。
- 已审阅状态机文件:
  - `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
  - `docs/modules/read-models/state-machine.md`
  - `docs/modules/cost-statistics/state-machine.md`
  - `docs/modules/tax-offset/state-machine.md`
  - `docs/modules/turnover-ledger/state-machine.md`
- 全局状态机定义: definition unchanged。本轮未新增、重命名或改变 workflow state、transition、guard、stop/defer condition 或 completion criterion；只推进单个 queue boundary 从 `pending` 到 `closed-autonomous`。
- 模块状态机定义: definition unchanged。本轮只新增合同守卫，不改变业务状态、UI 状态、read model 状态、worker 状态、operation barrier 状态、force-refresh 状态、permission 状态或 legacy-retirement 状态。
- 成功流转: `pending` -> `closed-autonomous`，自动执行状态更新为 `autonomous-continue-after-cost-tax-ledger-summary-contract`。
- defer/block 流转: 若 manifest/verification 失败且无法三轮内收敛，应记录 `deferred-module-failure`；若需要生产写或敏感凭据，应记录 `needs-human-production-gate`。本轮未触发。
- 完成时必须更新: 本 analysis、`tests/test_read_model_manifest.py`、read-models tests/implementation notes、相关模块 state-machine 变更记录、`autonomous/STATE.md`、`autonomous/MODULE-QUEUE.md`、`autonomous/JOURNAL.md`、`autonomous/NEXT-PROMPT.md`。

## Legacy 退役与污染防护

| Legacy / pollution risk | 当前状态 | 本轮处理 | 后续 |
| --- | --- | --- | --- |
| `cost_statistics:active:all` / `all:all` 被误改为 fan-out-only parent | 文档和 SQL runtime tests 已覆盖 parent aggregate | manifest guard 锁定 `queryable_parent_aggregate` | legacy-read-path-removal slice 查旧 scope producer |
| `tax_offset:all` 被当普通月份 payload | tax-offset state/tests 已覆盖 all fan-out | manifest guard 锁定 fan-out command | 后续若改 tax worker 必须跑 SQL runtime tests |
| `turnover_ledger` 绕过 gateway 返回 stale grouped payload | query service/read model tests 已覆盖 stale/missing enqueue | manifest guard 锁定 query gateway owner/ports | 后续 legacy fallback removal 单独处理 |
| cost/tax 旧 `cost-tax` worker 成为唯一 owner | manifest 已有 primary/auxiliary 区分 | 新 test 锁定 primary workers 与 compat auxiliary | Go/worker admission 前不得合并 owner |
| repository ports 混用 | manifest 已分列 ports | 新 test 要求三者 port sets 互不相交 | repository split slice 可按 port owner 小步迁移 |

## 七类测试映射

| 类别 | 是否适用 | 本轮覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改成本归因、税额试算、外部往来闭环、金额或状态规则 |
| 2. Service-layer tests | 适用 | manifest guard 锁定 query owner、permission owner、worker owner、repository port owner |
| 3. API contract tests | 不适用 | 无 HTTP status、response shape、错误字段或权限行为变化；既有 API tests 继续覆盖 refreshing/fail-closed |
| 4. Read model/cache/background job tests | 适用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_cost_tax_and_turnover_manifest_preserve_summary_contracts` 锁定 scope/worker/force-refresh/port 合同 |
| 5. Frontend component and interaction tests | 不适用 | 无前端行为变化 |
| 6. End-to-end business-flow integration tests | 不适用 | 本轮不触发 import/relation/write/worker 链路 |
| 7. Existing feature regression tests | 适用 | 既有 cost statistics、tax offset、turnover ledger SQL runtime/API/query/refresh tests 作为后续必要验证集 |

## 环境与验证限制

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 是否需要真实 PostgreSQL: 否，本轮是 manifest/test guard。
- 是否需要真实 worker/outbox/readiness: 否。
- 是否会写生产数据: 否。
- 生产验证: 不适用。
- 敏感凭据处理: 未读取、未记录凭据。

## 后续边界

下一步推进 `read-models:search-and-no-oa-bank-batch-contract`：

- 聚焦 `search` 与 `no_oa_bank_batch` 的 read-side freshness/status contracts、scope policy、query owner、repository ports 和 production fail-closed。
- 继续优先 contract/guard/analysis，不做大规模 SQL 拆分、Go/Fiber 或 Go Worker 实现。
