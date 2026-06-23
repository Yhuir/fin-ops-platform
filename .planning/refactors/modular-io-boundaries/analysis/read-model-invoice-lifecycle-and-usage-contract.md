# Read Model Invoice Lifecycle And Usage Contract

**日期:** 2026-06-23
**Boundary:** `read-models:invoice-lifecycle-and-usage-contract`
**状态:** `closed-autonomous`
**范围:** `invoice_lifecycle`、`input_invoice_usage`、`output_invoice_collection` read model 合同守卫；不改 SQL、worker、route、API shape、前端行为、Go/Fiber、Go Worker 或生产状态。

## 执行结论

本轮审阅了 read-models、invoice lifecycle、domain-events-lifecycle、input-invoice-usage 和 output-invoice-collections 文档、状态机、测试矩阵以及上一轮 pending/OA payment 分析，并通过 CodeGraph/精准搜索检查 `InvoiceLifecycleReadFacade`、`InvoiceLifecycleReadModelRefreshService`、`InputInvoiceUsageReadModelService`、`InputInvoiceUsageReadModelDetailService`、`OutputInvoiceCollectionService`、`InvoiceUsageCollectionReadModelRefreshService`、repository ports、relation source version scope 校验和 production SQL repository fail-closed 测试。

当前代码已具备以下有效边界：

- `invoice_lifecycle` 是跨页面生命周期分发边界，规则 owner 是 `InvoiceLifecyclePolicy`，查询 owner 是 `InvoiceLifecycleReadFacade`，worker owner 是 `invoice-lifecycle`。
- `input_invoice_usage` 与 `output_invoice_collection` 是页面 read model，继续拥有筛选、分页、导出和页面 DTO，不替代生命周期事实源。
- 三者都使用 scoped incremental projection 与 fan-out `all` refresh command；页面 all 查询的 freshness proof 来自实际 month shards、source versions 与 active dirty/outbox，不应等待虚假的 global parent proof。
- 依赖 `workbench_relation` distribution 的页面 read model 必须使用对应 row/month scope 的 relation source versions；`input_invoice_usage` relation detail 已按 row 的 `read_model_scope_key` 校验 expected source versions。
- 生产 PostgreSQL runtime 下，input/output 页面缺少 SQL read repository、SQL view miss、schema/source stale 或非 fresh status 时 fail-closed 返回 refreshing 并入队；不得回退旧 live scan 伪 fresh。

本轮不改运行时代码，只把三者的 shared manifest 合同加硬：

- 三者必须保持 `self_managed_freshness`、`scoped_incremental`、`fan_out_command`、`gateway_force_refresh` 与 App Status operation barrier target。
- `invoice_lifecycle` 必须保持独立 worker、query owner、permission owner 和 lifecycle repository ports。
- `input_invoice_usage` 与 `output_invoice_collection` 可共享 `invoice-usage-collection` worker，但 repository ports 和 query owners 必须分离，防止一个页面的查询/清理/详情 port 污染另一个页面。

## 改动前影响分析

### 1. 模块范围

- 目标模块: `read-models`
- 关联页面/资源模块: `domain-events-lifecycle`、`input-invoice-usage`、`output-invoice-collections`
- 子边界: `invoice_lifecycle`、`input_invoice_usage`、`output_invoice_collection`
- 本次改动类型: manifest contract guard
- 是否改变业务行为: 否
- 是否改变 API response shape: 否
- 是否改变 SQL 查询或写入: 否
- 是否改变 worker refresh: 否
- 是否进入 Go / Fiber / Go Worker candidate: 否

### 2. 合同矩阵

| Contract | `invoice_lifecycle` | `input_invoice_usage` | `output_invoice_collection` | 本轮守卫 |
| --- | --- | --- | --- | --- |
| scope type | `invoice_lifecycle` | `input_invoice_usage` | `output_invoice_collection` | manifest test |
| query owner | `InvoiceLifecycleReadFacade` | `InputInvoiceUsageReadModelService` | `OutputInvoiceCollectionService` | manifest test |
| worker owner | `invoice-lifecycle` + secondary | `invoice-usage-collection` | `invoice-usage-collection` | manifest test |
| all scope | `fan_out_command` | `fan_out_command` | `fan_out_command` | manifest test |
| projection | `scoped_incremental` | `scoped_incremental` | `scoped_incremental` | manifest test |
| repository ports | lifecycle rows/scope/list lookup | input rows/save/mark/prune/detail | output rows/save/mark/prune | manifest test requires disjoint sets |

## State Machine Impact

- 全局工作流状态: `AutonomousContinue`，当前执行状态为 `autonomous-continue-after-pending-invoice-and-oa-pending-payment-contract`。
- 选中边界进入前状态: `read-models:invoice-lifecycle-and-usage-contract` 为 `pending`。
- 已审阅状态机文件:
  - `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
  - `docs/modules/read-models/state-machine.md`
  - `docs/modules/domain-events-lifecycle/state-machine.md`
  - `docs/modules/input-invoice-usage/state-machine.md`
  - `docs/modules/output-invoice-collections/state-machine.md`
- 全局状态机定义: definition unchanged。本轮未新增、重命名或改变 workflow state、transition、guard、stop/defer condition 或 completion criterion；只推进单个 queue boundary 从 `pending` 到 `closed-autonomous`。
- 模块状态机定义: definition unchanged。本轮只新增合同守卫，不改变业务状态、UI 状态、read model 状态、worker 状态、operation barrier 状态、force-refresh 状态、permission 状态或 legacy-retirement 状态。
- 成功流转: `pending` -> `closed-autonomous`，自动执行状态更新为 `autonomous-continue-after-invoice-lifecycle-and-usage-contract`。
- defer/block 流转: 若 manifest/verification 失败且无法三轮内收敛，应记录 `deferred-module-failure`；若需要生产写或敏感凭据，应记录 `needs-human-production-gate`。本轮未触发。
- 完成时必须更新: 本 analysis、`tests/test_read_model_manifest.py`、read-models tests/implementation notes、相关模块 state-machine 变更记录、`autonomous/STATE.md`、`autonomous/MODULE-QUEUE.md`、`autonomous/JOURNAL.md`、`autonomous/NEXT-PROMPT.md`。

## Legacy 退役与污染防护

| Legacy / pollution risk | 当前状态 | 本轮处理 | 后续 |
| --- | --- | --- | --- |
| 页面直接重算 lifecycle，绕过 `invoice_lifecycle` read boundary | 产品文档禁止，read facade/refresh tests 已覆盖 | manifest guard 锁定 lifecycle owner/ports | legacy-read-path-removal slice 查旧 live scan 和 route fallback |
| `input_invoice_usage:all` / `output_invoice_collection:all` 被当 queryable parent proof | 文档和 SQL runtime tests 已覆盖 fan-out/month proof | manifest guard 锁定 fan-out command | 后续继续查旧 all-proof producer |
| input/output 共用 worker 后 repository ports 混用 | manifest 已分列 ports | 新 test 要求三者 port sets 互不相交 | repository split slice 可按 port owner 小步迁移 |
| relation source versions 用 global `workbench_relation:all` 污染 month proof | 现有 SQL runtime/API tests 覆盖 input/output all scope 和 detail scope | analysis 记录，不重复改 runtime | 后续改 relation facade/source versions 必须扩展业务测试 |
| 生产 SQL repository missing 时 live scan | input/output API/SQL runtime tests 已覆盖 fail-closed | analysis 记录，不改 runtime | server.py/legacy removal slice 继续隔离旧 fallback |

## 七类测试映射

| 类别 | 是否适用 | 本轮覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改 lifecycle policy、支付/收款状态、认证状态、relation 或金额规则 |
| 2. Service-layer tests | 适用 | manifest guard 锁定 query owner、permission owner、worker owner、repository port owner |
| 3. API contract tests | 不适用 | 无 HTTP status、response shape、错误字段或权限行为变化；既有 API tests 继续覆盖 refreshing/fail-closed |
| 4. Read model/cache/background job tests | 适用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_invoice_lifecycle_and_usage_manifest_preserve_scoped_contracts` 锁定 scope/worker/force-refresh/port 合同 |
| 5. Frontend component and interaction tests | 不适用 | 无前端行为变化 |
| 6. End-to-end business-flow integration tests | 不适用 | 本轮不触发 import/relation/write/worker 链路 |
| 7. Existing feature regression tests | 适用 | 既有 invoice lifecycle、input usage、output collection SQL runtime/API 和 derived lifecycle tests 作为后续必要验证集 |

## 环境与验证限制

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 是否需要真实 PostgreSQL: 否，本轮是 manifest/test guard。
- 是否需要真实 worker/outbox/readiness: 否。
- 是否会写生产数据: 否。
- 生产验证: 不适用。
- 敏感凭据处理: 未读取、未记录凭据。

## 后续边界

下一步推进 `read-models:cost-tax-ledger-summary-contract`：

- 聚焦 `cost_statistics`、`tax_offset`、`turnover_ledger` 的 partitioned scoped rollup/incremental 合同、query gateway ownership、repository port owner 和 production fail-closed。
- 继续优先 contract/guard/analysis，不做大规模 SQL 拆分、Go/Fiber 或 Go Worker 实现。
