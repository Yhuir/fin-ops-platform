# Read Model Main Closure Reconciliation

日期：2026-06-26
目标：执行 `07-read-model-main-closure-controller.md`，完成所有页面 read model 读写闭环、dirty scope、freshness、operation barrier、前端刷新、旧链路剔除和生产证据闭环。

## 运行上下文

- 当前 main commit：`aa9b2232e261db2e4efe5776a7784705ab2e760d`
- 备份分支：`codex/backup-main-before-read-model-closure-20260626-050615`
- Admin Token：已通过安全弹窗采集到当前 controller shell 会话；未写入仓库、`.planning`、docs、日志或普通文件。
- CodeGraph：已运行 `codegraph_status`，索引状态正常：1065 files / 36644 nodes / 91657 edges。
- 当前 dirty files：`.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`，属于本次目标 prompt 更新。

## 事实源

- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- `backend/src/fin_ops_platform/services/read_model_freshness.py`
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/modules/*/boundary-io.md`
- `docs/app-architecture/pages.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/operations/runtime-worker-governance.md`

## 当前 Manifest / Worker 事实

- Manifest read model 数量：14。
- Required worker 数量：20。
- Worker registry 总 worker registration：21。
- Read model refresh event type：14。
- 29/29 个 `docs/modules/*/boundary-io.md` 已存在。
- CodeGraph trace 对 `confirm_link -> enqueue_read_model_refresh`、`confirm_paid -> enqueue_read_model_refresh`、`handle_closure_confirm_route -> enqueue_read_model_refresh` 未能解析直接静态路径，原因是 route -> service -> injected port/facade 的动态分发。这不是完成证据；后续 wave 必须用源码审计和 targeted tests 逐条证明 write API affected scopes / freshness targets / barrier targets。

## 与 2026-06-25 既有 GSD 结论的关系

- 既有 `read-model-main-local-owner-split-closure-audit-2026-06-25.md` 已确认：所有已知非 Workbench App Status read model 都完成本地 physical SQL owner split；Workbench 保留 active generation 例外。
- 既有 `read-model-main-production-equivalent-evidence-gap-2026-06-25.md` 和 `read-model-main-approval-gated-deploy-hard-stop-2026-06-25.md` 已确认：当时 PSCIP-L4 未闭合的主要原因是生产还在旧 release，且缺少 rollout approval。
- 本轮用户已批准 rollout、root SSH、生产样本、样本恢复和缺少业务恢复时的 bounded DB restore，因此旧的 `deploy-approval-required` 不再是审批阻塞。
- 本轮目标同时扩大：除了部署和生产 L4 证据，还必须闭合所有页面 read/write 操作的 freshness targets、operation barrier、frontend fresh reload 和旧链路剔除。因此不能直接从 2026-06-25 的 owner split 结论跳到 global closure。

## Closure Matrix

| Read model | Page/domain | Strategy | Worker | Query owner | Repository owner | Current PSCIP | Current status | Required closure action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `workbench` | 关联台 | active generation scoped publish | `workbench` | `WorkbenchQueryFacade` | `PostgresReadModelRepository.workbench` | L3 partial | active generation 例外已登记；仍存在 legacy API/read fallback 和 `server.py` 历史路径 | 证明所有 write API 返回/等待 workbench targets；删除或 hard-quarantine legacy workbench actions/read fallback；补生产 L4 |
| `workbench_relation` | 关系事实源 | scoped incremental distribution | `workbench-relation` | `WorkbenchRelationReadFacade` | `WorkbenchRelationReadModelRepositoryPort` | L3 partial | relation read facade/test 较完整；batch/turnover/workbench 写链路仍需逐条 targets 证明 | 统一 confirm/withdraw/submit/closure 后 affected scopes、barrier targets、前端等待；补生产样本 |
| `bank_detail` | 银行明细 | partitioned scoped incremental | `bank-detail` | `BankDetailsApplicationService` | `BankDetailReadModelRepositoryPort` | L3 partial | 查询 freshness 已覆盖；规则保存、分类确认/撤回、导入后刷新仍需全写链路闭环 | 写 API 必须统一返回 targets；前端规则保存/分类操作必须 barrier/fresh reload；补生产样本 |
| `bank_account_balance` | 银行账户余额 | partitioned scoped incremental / all-only | `bank-account-balance` | `BankDetailsApplicationService` | `BankAccountBalanceReadModelRepositoryPort` | L2/L3 partial | all-only 例外已登记；与 bank detail 写入影响关系需更明确 | 证明账户余额 read model 在银行明细导入/分类/规则变化后 dirty/outbox/readiness 收敛 |
| `pending_invoice` | 待找发票 | scoped incremental | `pending-invoice` + `search-pending` | `PendingInvoiceReadModelService` | `PendingInvoiceReadModelRepositoryPort` | L3 partial | page-first scope 和 forbidden bare all 已登记；规则更新和 attach confirm/batch confirm 写后闭环需增强 | 统一 write response targets；前端写后 barrier；生产样本确认/撤回 |
| `search` | 搜索 | partitioned scoped index | `search` + auxiliary lanes | Search read API | `SearchReadModelRepositoryPort` | L3 partial | producer convergence 文档显示 local closed、production evidence deferred | 证明所有 domain writes 的 search fan-out 通过 producer 且无 direct gateway 回流；补生产查询和延迟证据 |
| `invoice_lifecycle` | 发票生命周期 | scoped incremental | `invoice-lifecycle` + secondary | `InvoiceLifecycleReadFacade` | `InvoiceLifecycleReadModelRepositoryPort` | L3 partial | refresh/test 存在；各发票/导入/OA 写入影响域需全量 matrix | 生成 write -> lifecycle scopes 矩阵；补 API/worker/生产证据 |
| `input_invoice_usage` | 进项使用 | scoped incremental | `invoice-usage-collection` | `InputInvoiceUsageReadModelService` | `InputInvoiceUsageReadModelRepositoryPort` | L3 partial | rows/filter/export freshness 已覆盖；payment rules/OA reverse 写后 closure 需验证 | 写 API targets + 前端等待 + export non-fresh gate + 生产样本 |
| `output_invoice_collection` | 销项收款 | scoped incremental | `invoice-usage-collection` | `OutputInvoiceCollectionService` | `OutputInvoiceCollectionReadModelRepositoryPort` | L3 partial | rows/filter/export/receipt APIs 有 freshness 字段；部分 route 中仍有 explicit `read_model_status=fresh` overlay | 审计 overlay 是否 safe；统一 status/reminder/red invoice/receipt write targets；生产样本 |
| `oa_pending_payment` | OA 待付款 | scoped incremental | `invoice-usage-collection` | `OaPendingPaymentReadModelService` | `OaPendingPaymentReadModelRepositoryPort` | L3 partial | rows/filter/detail freshness 有测试；confirm/link/auto reconcile 写后 targets 需证明 | 写 API affected scopes + barrier + 前端 reload；生产可控样本 |
| `cost_statistics` | 成本统计 | partitioned scoped parent rollup | `cost-statistics` + `cost-tax` | `CostStatisticsQueryService` | `CostStatisticsReadModelRepositoryPort` | L3 partial | parent aggregate 例外已登记；父 scope 等待 child shard 的生产证据未闭合 | 生产 query plan/latency + parent/all scope readiness 证据；旧 fallback 删除 |
| `tax_offset` | 税金抵扣 | partitioned scoped incremental | `tax-offset` + `cost-tax` | `TaxOffsetQueryService` | `TaxOffsetReadModelRepositoryPort` | L3 partial | query gateway 合同存在；save plan / certified import 写后 closure 需增强 | 写 API targets、frontend wait、worker readiness、生产样本 |
| `no_oa_bank_batch` | 免 OA 批次 | scoped incremental | `no-oa-bank-batch` | `NoOaBankBatchApplicationService` | `NoOaBankBatchReadModelRepositoryPort` | L3 partial | submit/withdraw/tag selection route 存在 overlay；生产恢复样本需定义 | 统一 submit/withdraw/bulk write targets；前端 barrier；样本业务恢复或 bounded DB restore |
| `turnover_ledger` | 外部往来款 | partitioned scoped incremental | `turnover-ledger` | `TurnoverLedgerQueryService` | `TurnoverLedgerReadModelRepositoryPort` | L3 partial | closure/confirm/withdraw 有 freshness targets；仍有大量 `LegacyFallbackFacade` 可达 | 删除或 hard-quarantine turnover legacy fallback；统一 all writes targets；生产样本 |

结论：没有任何 read model 当前可声明 PSCIP-L4 global closure。所有 read model 至少需要生产证据；多数还需要 write API targets、frontend barrier/fresh reload 和 legacy path retirement。

## 模块分类

| Category | Modules / read models |
| --- | --- |
| `local-implementation-closed-production-evidence-needed` | `search`、部分 `cost_statistics`、部分 `tax_offset` |
| `needs-repository-physical-split` | `workbench` 仍依赖 `PostgresReadModelRepository.workbench` 和 shared `postgres_repositories/read_models.py` 历史边界 |
| `needs-refresh-producer-convergence` | `bank_detail`、`pending_invoice`、`invoice_lifecycle`、`input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`no_oa_bank_batch`、`turnover_ledger` 需逐条确认 producer owner 无 direct gateway 回流 |
| `needs-query-fresh-gate-convergence` | `workbench` legacy fallback、`output_invoice_collection` route overlay、frontend default `fresh` sites |
| `needs-operation-barrier-closure` | `workbench`、`workbench_relation`、`bank_detail`、`pending_invoice`、`oa_pending_payment`、`output_invoice_collection`、`tax_offset`、`no_oa_bank_batch`、`turnover_ledger` |
| `needs-frontend-freshness-closure` | `BatchAccountingPage`、`BankDetailsPage`、`ReconciliationWorkbenchPage`、`PendingInvoicesPage`、`NoOaBankBatchPage`、`TurnoverLedgerPage`、invoice usage/collection pages |
| `needs-legacy-removal` | `routes_legacy_workbench_actions.py`、`routes_etc_legacy_batches.py`、`server.py` legacy workbench/ETC/turnover fallback、`turnover_ledger_write_adapters.py` legacy fallback facades、legacy stale workbench payload fallback |
| `needs-worker-readiness-closure` | all 14 read models need production App Status/readiness/outbox drain evidence |
| `needs-write-operation-targets` | all page mutation APIs until proven otherwise |
| `needs-business-sample-validation` | all page mutation flows selected for production smoke |
| `needs-sample-restore-proof` | all production write samples; business inverse preferred, bounded DB restore allowed when inverse missing |

## 旧代码污染清单

| Path / symbol | Risk | Required action |
| --- | --- | --- |
| `backend/src/fin_ops_platform/app/server.py` legacy workbench handlers and `read_model_status` default-fresh branches | Can route old read/write/readiness behavior around new owners | Move remaining behavior to route/service owners or hard-quarantine with static guards |
| `backend/src/fin_ops_platform/app/routes_legacy_workbench_actions.py` | Legacy workbench mutation API remains reachable through server routing | Delete or hard-quarantine from production normal path |
| `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py` | Legacy ETC batch path can still perform mutations and refresh events | Prove route is compat-only or migrate/delete |
| `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py` legacy fallback facades | Turnover write path can fall back to old module logic | Replace with explicit ports or hard-quarantine with tests |
| Workbench stale payload fallback in `server.py` | Stale payload could be served if guard weakens | Prove fail-closed or remove |
| Frontend default `readModelStatus || "fresh"` sites | Unknown/missing status can become fresh in UI | Replace with explicit unknown/refreshing handling where payload may omit status |
| Route overlays setting `read_model_status="fresh"` | Can mask underlying non-fresh rows/options | Verify only after fresh gate or replace with service payload status |

## 页面读写操作矩阵（初版）

| Page/module | Read APIs | Write APIs / operations | Expected targets | Current gap |
| --- | --- | --- | --- | --- |
| 关联台 | workbench list/groups/detail/summary/refresh-status/events | confirm/cancel/withdraw/exception/cash special/ignore/unignore | `workbench`, `workbench_relation`, downstream read models by domain | legacy actions and active generation exception need full target tests |
| 批量账务 | batch accounting list | submit/withdraw | `workbench_relation` changed months | frontend overlay exists; write API target contract needs global audit |
| 银行明细 | accounts/transactions/export/rules | rules save/reapply, category confirm/revoke/assign/clear, import effects | `bank_detail`, `bank_account_balance`, `search`, `pending_invoice` as applicable | rules and category operations need consistent freshness targets |
| 待找发票 | rows/filter/options/detail/export | attach existing confirm/batch confirm, rule update, income status update | `pending_invoice`, `workbench_relation`, `invoice_lifecycle`, `search` | broad write matrix not complete |
| 进项使用 | rows/filter/detail/relation/export | payment status rules, OA reverse draft/status flows | `input_invoice_usage`, `invoice_lifecycle`, `workbench_relation` | write target and frontend wait proof incomplete |
| OA 待付款 | rows/filter/details/relation | confirm paid, link bank transactions, auto reconcile | `oa_pending_payment`, `workbench_relation`, `bank_detail`, `turnover_ledger` as applicable | production sample and restore proof missing |
| 销项收款 | rows/filter/export/status/receipt/red relation | status/reminder/red relation/receipt settings/create/void/reissue | `output_invoice_collection`, `invoice_lifecycle`, `workbench_relation` | route overlay and write targets need audit |
| 成本统计 | month/explorer/project/export/transaction | no primary page write; affected by imports/OA/bank/relation/tax | `cost_statistics` month + parent scopes | production parent aggregate and query plan evidence missing |
| 税金抵扣 | month/summary/import job/certified imports | calculate/save plan/certified import confirm | `tax_offset`, `cost_statistics`, `invoice_lifecycle` | save/import write targets and frontend wait need proof |
| 免 OA 批次 | list/detail/tag selection | submit/withdraw/submit selection/bulk submit/update tags | `no_oa_bank_batch`, `workbench_relation`, `turnover_ledger` | sample restore proof and target matrix missing |
| 外部往来款 | list/grouped/export/relation/extra/tag selection | tag selection, relation extra, confirm/withdraw relation, closure confirm/withdraw, bank row tags | `turnover_ledger`, `workbench_relation`, selected months | legacy fallback facades reachable; must retire/quarantine |
| 系统状态 | App Status / health / operation barrier | force refresh/repair/smoke where exposed | all read models by scope | production evidence sweep not run |

## High-Efficiency Wave Plan

1. **Wave 1: Static guard and mutation target inventory**
   - Add/strengthen tests that detect frontend default-fresh patterns, route-level `read_model_status=fresh` overlays, and reachable legacy read model fallbacks.
   - Generate a source-backed write API target inventory for all page mutations.
   - Acceptance: guard tests fail on current reachable old/default-fresh patterns or report exact allowlist.

2. **Wave 2: Operation barrier/write response convergence**
   - Batch update write APIs to return `freshness_targets` / affected scopes / job/version where missing.
   - Batch update frontend mutations to use `GlobalOperationOverlay` and fresh reload.

3. **Wave 3: Legacy path retirement**
   - Delete or hard-quarantine legacy workbench, ETC and turnover fallback paths.
   - Move remaining logic to explicit service/repository ports.

4. **Wave 4: Query fresh gate and projection owner cleanup**
   - Remove stale-as-fresh route overlays and shared repository leakage.
   - Ensure every read API fail-closes or returns refreshing/blocked.

5. **Wave 5: Worker/readiness and production tooling**
   - Run baseline unit tests, SLO smokes, readiness probes and production evidence scripts.
   - Select low-risk production samples; use business inverse restore or bounded DB restore protocol.

6. **Wave 6: Global closure audit**
   - Re-run full test suite subset, docs verification, production evidence sweep, and update all module docs/state logs.

## Immediate Next Prompt

Start Wave 1 with focus on static guard + write target inventory:

- Inspect existing guard tests in `tests/test_read_model_architecture_guards.py`, `tests/test_platform_runtime_boundary_guards.py`, frontend tests, and operation barrier tests.
- Add or strengthen tests for:
  - frontend defaulting missing/unknown read model status to fresh outside explicitly safe initial local placeholders;
  - route/service `read_model_status=fresh` assignments that do not come from fresh gate or projection owner;
  - reachable `routes_legacy_workbench_actions.py`, `routes_etc_legacy_batches.py`, and turnover legacy fallback facades on normal production paths;
  - write API response payloads missing `freshness_targets` / affected scopes for page mutations.
- Do not yet run production mutations; finish local guard/inventory first.
