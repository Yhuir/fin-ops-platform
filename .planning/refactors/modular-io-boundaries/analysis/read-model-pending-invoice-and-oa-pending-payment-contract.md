# Read Model Pending Invoice And OA Pending Payment Contract

**日期:** 2026-06-23
**Boundary:** `read-models:pending-invoice-and-oa-pending-payment-contract`
**状态:** `closed-autonomous`
**范围:** 待找发票与 OA 待付款 read model 合同守卫；不改 SQL、worker、route、API shape、前端行为、Go/Fiber、Go Worker 或生产状态。

## 执行结论

本轮审阅了 read-models、pending-invoices、oa-pending-payments 模块文档、状态机、测试矩阵、上一轮银行明细/账户余额分析，并通过 CodeGraph/精准搜索检查 `PendingInvoiceReadModelService`、`OaPendingPaymentReadModelService`、`read_model_scope_policy.py`、`SearchPendingReadModelRefreshService`、`InvoiceUsageCollectionReadModelRefreshService`、`SearchPendingSqlProjectionBuilder`、`InvoiceUsageCollectionSqlProjectionBuilder`、`PostgresReadModelRepository` pending/OA repository ports、workbench relation source version 读取和 production fail-closed 测试。

当前代码已具备以下有效边界：

- `pending_invoice` 使用专用 scope policy，接受 `expense|income:<filter>` 与可选月份 shard，拒绝裸 `all`、裸月份和非法 direction。
- `pending_invoice` 首屏 force refresh 需要 page-first-screen scope，不能只用裸 `all` 或单一默认 month 证明首屏 fresh。
- pending invoice rows/filter-options/read service 在 miss/stale/source mismatch 时返回 refreshing 并入队，不 live scan 旧事实伪装 fresh。
- pending invoice expected source versions 覆盖 bank detail source versions 与 `workbench_relation` source versions；relation 版本缺失或不匹配会触发 refresh。
- `oa_pending_payment:all` 在 refresh 链路中是 fan-out 控制 scope；默认 all 查询的 freshness proof 来自实际 rows/month scopes 与 active dirty/outbox 状态，不能等待全局 relation `all` proof。
- OA pending payment rows/filter-options/detail 在生产 SQL repository missing/stale 时 fail-closed，入队 `oa_pending_payment` refresh，不同步 live scan。

本轮不改运行时代码，只把该边界在 manifest/test 层加硬：

- `pending_invoice` 必须保持 `forbidden_bare_all` 与 `gateway_force_refresh_with_page_first_screen_scope`。
- `oa_pending_payment` 必须保持 `fan_out_command` 与标准 gateway force refresh。
- 两者保持独立 query owner、permission owner 和 repository port contract，避免待找发票 filter/source-version port 与 OA 待付款 row/detail/prune port 混用。

## 改动前影响分析

### 1. 模块范围

- 目标模块: `read-models`
- 关联页面模块: `pending-invoices`、`oa-pending-payments`
- 子边界: `pending_invoice`、`oa_pending_payment`
- 本次改动类型: manifest contract guard
- 是否改变业务行为: 否
- 是否改变 API response shape: 否
- 是否改变 SQL 查询或写入: 否
- 是否改变 worker refresh: 否
- 是否进入 Go / Fiber / Go Worker candidate: 否

### 2. 合同矩阵

| Contract | `pending_invoice` | `oa_pending_payment` | 本轮守卫 |
| --- | --- | --- | --- |
| scope type | `pending_invoice` | `oa_pending_payment` | manifest test |
| query owner | `PendingInvoiceReadModelService` | `OaPendingPaymentReadModelService` | manifest test |
| permission owner | `pending_invoices_api_session` | `oa_pending_payment_api_session` | manifest test |
| all scope | `forbidden_bare_all` | `fan_out_command` | manifest test |
| force refresh | page-first-screen scope | standard gateway force refresh | manifest test |
| repository ports | rows/filter-options/save/mark/source-version ports | rows/save/mark/prune/detail lookup ports | manifest test requires disjoint sets |

## Legacy 退役与污染防护

| Legacy / pollution risk | 当前状态 | 本轮处理 | 后续 |
| --- | --- | --- | --- |
| `pending_invoice:all` 裸 scope 污染 queue/readiness | scope policy 已拒绝 | manifest guard 锁定 `forbidden_bare_all` | legacy-read-path-removal slice 继续查旧 producer |
| pending invoice 首屏只刷新 shard、不刷新页面默认 aggregate | SLO smoke 已覆盖 page-first-screen scope | manifest guard 锁定 force refresh 合同 | 后续保持 SLO smoke |
| pending invoice relation source version 缺失仍 fresh | SQL runtime/API tests 已覆盖 stale enqueue | analysis 记录，不重复实现 | 后续 source-version 变更必须扩展业务测试 |
| `oa_pending_payment:all` 被当 queryable parent proof | 文档和 SQL runtime tests 已覆盖 fan-out/month proof | manifest guard 锁定 fan-out command | 后续 legacy read path slice 查旧 all-proof |
| 生产 repository missing 时 live scan | OA/pending API tests 已覆盖 fail-closed | analysis 记录，不改 runtime | 后续 route/server.py split 继续移除旧 fallback |

## 七类测试映射

| 类别 | 是否适用 | 本轮覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改规则、付款状态、relation 或 lifecycle 业务规则 |
| 2. Service-layer tests | 适用 | manifest guard 锁定 query owner、permission owner、repository port owner |
| 3. API contract tests | 不适用 | 无 HTTP shape 或 status code 变化；既有 API tests 继续覆盖 refreshing/fail-closed |
| 4. Read model/cache/background job tests | 适用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_pending_invoice_and_oa_payment_manifest_preserve_page_scope_contracts` 锁定 scope/force-refresh/port 合同 |
| 5. Frontend component and interaction tests | 不适用 | 无前端行为变化 |
| 6. End-to-end business-flow integration tests | 不适用 | 本轮不触发 import/OA sync/worker/write 链路 |
| 7. Existing feature regression tests | 适用 | 既有 pending invoice、OA pending payment、invoice usage collection SQL runtime、SLO smoke 和 refresh gateway tests 保持为后续必要验证集 |

## 环境与验证限制

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 是否需要真实 PostgreSQL: 否，本轮是 manifest/test guard。
- 是否需要真实 worker/outbox/readiness: 否。
- 是否会写生产数据: 否。
- 生产验证: 不适用。
- Secret handling: 未读取、未记录 secret。

## 状态机影响

- 全局 `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`: 本轮未新增、重命名或改变 workflow state/transition/guard，故不改全局状态机定义。
- `docs/modules/read-models/state-machine.md`: 不改变共享 read model 状态语义。
- `docs/modules/pending-invoices/state-machine.md`: 添加变更记录，说明本轮只是合同守卫加硬，不改变业务状态、UI 状态、read model 状态或 worker 状态。
- `docs/modules/oa-pending-payments/state-machine.md`: 添加变更记录，说明本轮只是合同守卫加硬，不改变业务状态、UI 状态、read model 状态或 worker 状态。

## 后续边界

下一步推进 `read-models:invoice-lifecycle-and-usage-contract`：

- 聚焦 invoice lifecycle、input invoice usage、output invoice collection 的 scoped incremental contract、relation source versions、direction-specific fan-out 和 production fail-closed。
- 继续优先 contract/guard/analysis，不做大规模 SQL 拆分、Go/Fiber 或 Go Worker 实现。
