# Reconciliation Workbench Amount-check Query Contract

**日期:** 2026-06-23
**Boundary:** `reconciliation-workbench:amount-check-query-contract`
**状态:** `closed-autonomous`
**范围:** 锁定 Workbench 金额核对输入优先级合同；不改 runtime 行为、不改 API shape、不改 SQL、不改 worker、不改前端、不进入 Go/Fiber 或 Go Worker。

## 执行结论

本轮审阅了关联台模块文档、read model 状态机、Go hot-path carve-out 计划、前序 read model legacy guard analysis，并用 CodeGraph/代码搜索确认金额核对链路：

- `WorkbenchWriteFacade` 通过注入的 `amount_check_for_rows_by_type` 调用金额核对边界。
- `Application._amount_check_for_rows_by_type(...)` 持有 HTTP app 层适配，实际委托 `WorkbenchAmountCheckService.check(...)`。
- `WorkbenchQueryService` 和 Workbench SQL projection 已在 OA row payload 中暴露 `reconciliation_amount`。
- `WorkbenchAmountCheckService` 当前合同为：显式 `reconciliation_amount` 优先；只有缺少显式字段时，才允许使用旧 read model 的 `detail_fields.明细金额合计` fallback。

本轮新增测试锁定：当新 query/read payload 已有显式 `reconciliation_amount` 时，旧 `detail_fields.明细金额合计` 即使存在且不同，也不能覆盖新字段，避免旧 read model fallback 污染新链路。

## 模块 IO 合同

| 项 | 合同 |
| --- | --- |
| 输入 | Workbench preview/confirm 所选 group 的 OA、银行流水、发票 rows，由 query/read boundary 或 live row resolver 提供。 |
| 输出 | `amount_check` payload，包括 `status`、`direction`、`oa_total`、`bank_total`、`invoice_total`、`amount_delta`、`requires_note`、`mismatch_fields`。 |
| 状态 | 本轮不改变 business/UI/read model/worker 状态；仅增加 amount-check 输入优先级回归合同。 |
| 事件 | 本轮不新增事件；confirm/withdraw 仍由既有 relation write + operation barrier 链路触发。 |
| read model contract | `reconciliation_amount` 是新 query/read payload 的核对金额字段；旧 `detail_fields.明细金额合计` 只作缺字段兼容 fallback。 |
| force refresh contract | 不适用；本轮不触发 read model refresh，不改变 refresh gateway 或 dirty scope。 |
| operation barrier contract | 不变；confirm/withdraw submit 继续等待操作级 `workbench_relation` barrier。 |
| canonical facts | 金额核对不是 canonical fact owner；canonical relation 仍是 `app.workbench_pair_relations`，OA/bank/invoice 事实归各自模块。 |
| shared fact owner | Workbench 只消费 rows 与 relation facts；不得把旧 read model fallback 提升为 canonical amount fact。 |
| 权限 | 不变；无新增权限分支。 |
| 审计 | 不变；amount mismatch note/audit 仍由既有确认链路处理。 |
| public surface | `amount_check` response contract 保持兼容。 |
| internal-only surface | `WorkbenchAmountCheckService._oa_reconciliation_amount(...)` 的优先级属于内部合同，由测试保护。 |
| allowed dependencies | Query/read payload 字段、direction helper、Decimal normalization、既有 Workbench write facade callable。 |
| forbidden dependencies | 禁止前端重算金额核对；禁止旧 `detail_fields` fallback 覆盖显式 `reconciliation_amount`；禁止为了兼容旧 read model 改写 canonical amount。 |
| legacy retirement/quarantine | 旧 `detail_fields.明细金额合计` fallback 仍保留为 compat-only，删除条件是生产 active generation 和所有 query payload 均证明长期输出 `reconciliation_amount`。 |
| test contract | `test_explicit_reconciliation_amount_wins_over_legacy_detail_mismatch_fields` 锁定新字段优先级；既有测试继续覆盖显式字段、旧 fallback、unknown invoice direction 与 mismatch note。 |
| docs impact | 更新关联台 tests、implementation notes、state-machine 变更记录；全局状态机定义不变。 |

## 改动前影响分析

### 1. 模块范围

- 目标模块: `reconciliation-workbench`
- 子边界: amount-check query/compute input priority contract
- 本次改动类型: regression test + docs/state accounting
- 是否改变业务行为: 否
- 是否改变 API response shape: 否
- 是否改变 SQL 查询或写入: 否
- 是否改变 read model refresh: 否
- 是否改变 worker: 否
- 是否进入 Go / Fiber / Go Worker candidate: 否

### 2. Legacy 分类

| Path | 分类 | owner | 删除条件 | 禁止事项 |
| --- | --- | --- | --- | --- |
| `detail_fields.明细金额合计` amount fallback | compat-only legacy read model fallback | Workbench amount-check owner | 所有 active generation/query payload 均稳定输出 `reconciliation_amount` 并有生产 evidence | 不得覆盖显式 `reconciliation_amount`；不得成为 canonical amount fact |
| `Application._amount_check_for_rows_by_type` | app adapter wrapper | Workbench route/application owner | route owner extraction 后可迁到 route module adapter | 不得直接写 relation/read model/outbox |

## State Machine Impact

- 全局工作流状态: `AutonomousContinue`，当前执行状态为 `autonomous-continue-after-legacy-read-path-removal-guards`。
- 选中边界进入前状态: `reconciliation-workbench:amount-check-query-contract` 为 `pending`。
- 已审阅状态机文件:
  - `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
  - `docs/modules/reconciliation-workbench/state-machine.md`
  - `docs/modules/read-models/state-machine.md`
- 全局状态机定义: definition unchanged。本轮未新增、重命名或改变 workflow state、transition、guard、stop/defer condition 或 completion criterion；只推进单个 queue boundary 从 `pending` 到 `closed-autonomous`。
- 模块状态机定义: definition unchanged。本轮新增输入优先级测试并追加变更记录，不改变业务状态、UI 状态、read model 状态、worker 状态、operation barrier 状态、force-refresh 状态、permission 状态或 legacy-retirement 状态定义。
- 成功流转: `pending` -> `closed-autonomous`，自动执行状态更新为 `autonomous-continue-after-workbench-amount-check-query-contract`。
- defer/block 流转: 若发现 amount-check 新字段优先级需要业务行为变更或生产写验证，应记录 `deferred-module-failure` 或 `needs-human-production-gate`。本轮未触发。
- 完成时必须更新: 本 analysis、`tests/test_workbench_amount_check_service.py`、关联台 tests/implementation notes/state-machine、`autonomous/STATE.md`、`autonomous/MODULE-QUEUE.md`、`autonomous/JOURNAL.md`、`autonomous/NEXT-PROMPT.md`。

## 七类测试映射

| 类别 | 是否适用 | 本轮覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 适用 | `test_explicit_reconciliation_amount_wins_over_legacy_detail_mismatch_fields` 覆盖金额核对输入优先级，防止旧 fallback 导致 false mismatch。 |
| 2. Service-layer tests | 适用 | 同一 service 测试直接覆盖 `WorkbenchAmountCheckService` 合同；无 repository/queue side effect。 |
| 3. API contract tests | 不适用 | 无 HTTP/API shape 变化；既有 Workbench v2 mismatch note tests 继续保护 API 行为。 |
| 4. Read model/cache/background job tests | 间接适用 | 本轮不改 read model refresh；测试锁定新 read/query payload 字段优先于旧 read model fallback。 |
| 5. Frontend component and interaction tests | 不适用 | 无前端行为变化，前端仍消费后端 `amount_check`。 |
| 6. End-to-end business-flow integration tests | 不适用 | 本轮是窄 contract guard，不触发 relation 写入、worker 或跨页面 fan-out。 |
| 7. Existing feature regression tests | 适用 | 既有显式 `reconciliation_amount`、旧 fallback、mismatch note、directional bank total 回归继续作为验证集合。 |

## 环境与验证限制

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 是否需要真实 PostgreSQL: 否，本轮只加 service-level contract guard 和文档状态。
- 是否需要真实 worker/outbox/readiness: 否。
- 是否会写生产数据: 否。
- 生产验证: 不适用。
- 敏感凭据处理: 未读取、未记录凭据。

## 后续边界

下一步推进 `batch-accounting:legacy-route-contract`：

- 聚焦批量账务旧 route/server.py 写链路、Workbench relation fan-out、权限和 read model refresh 边界。
- 只做窄范围 route/contract guard 或 analysis，不做全量 server.py 拆分，不进入 Go/Fiber 实现。
