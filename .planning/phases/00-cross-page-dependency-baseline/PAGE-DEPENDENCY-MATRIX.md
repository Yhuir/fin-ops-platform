# Page Dependency Matrix

**Purpose:** Identify upstream/downstream page dependencies before page-level implementation planning.

## Dependency Groups

| Group | Pages | Why grouped |
| --- | --- | --- |
| Import source facts | 银行流水导入, 发票导入, ETC发票导入 | These pages create or queue canonical source facts consumed by most business pages. They share import workflow/services and can affect many read models. |
| Workbench relation core | 关联台, 银行明细, 批量账务, 免OA流水批量处理, 外部往来款管理 | These pages create/read relation facts and bank transaction categories; stale relation projections affect multiple downstream views. |
| Invoice lifecycle and tax | 待找发票, 进项发票使用情况, OA待付款核对, 销项发票收款情况, 税金抵扣 | These pages share invoice lifecycle, invoice usage/collection read models, and tax/cost downstream effects. |
| ETC chain | ETC发票导入, ETC票据管理, 关联台, 税金抵扣, 成本统计 | ETC import/business batch state becomes invoice/workbench/tax/cost facts. |
| Analytics and status | 成本统计, 系统状态, 设置 | Cost reads many upstream facts; App Health observes all runtime domains; settings reset and project scope changes can invalidate broad state. |

## Page-Level Matrix

| Page | Upstream dependencies | Downstream consumers | Strong coupling | Minimum smoke after page change |
| --- | --- | --- | --- | --- |
| 银行流水导入 | import workflow, bank account mapping, import worker | 银行明细, 关联台, 待找发票, 成本统计, 搜索, App Health | Import source facts | Import preview/confirm, bank detail list, workbench refresh, cost statistics stale/fresh, App Status import worker |
| 发票导入 | import workflow, invoice normalization, import worker | 关联台, 待找发票, 进项/销项/OA发票页面, 税金抵扣, 成本统计, 搜索 | Import source facts, invoice lifecycle | Invoice import preview/confirm, invoice lifecycle refresh, tax offset, pending invoice, App Status |
| ETC发票导入 | ETC reconciliation task, zip parser/filter, import worker | ETC票据, 关联台, 税金抵扣, 成本统计, 搜索 | Import source facts, ETC chain | ETC preview/confirm, ETC business batch, workbench summary, tax/cost stale/fresh |
| 关联台 | bank/OA/invoice/ETC facts, workbench active generation, relation facts | 银行明细, 待找发票, 发票使用/收款, 批量账务, 往来款, 成本统计, 搜索 | Workbench relation core | confirm/withdraw, active generation, relation read model, downstream relation consumers |
| 银行明细 | bank import, tags, relation facts, no-OA, category rules | 关联台, 待找发票, 免OA, 往来款, 成本统计, 搜索 | Workbench relation core | bank detail stale/fresh, tag writes, workbench matching, no-OA candidate effects |
| 批量账务 | workbench relation read model, bank/OA facts | 关联台, 银行明细, 成本统计, 搜索; relation projections for other pages | Workbench relation core | relation read model status, submit/withdraw, operation barrier, workbench/bank/cost smoke |
| 免OA流水批量处理 | bank details, auto tag rules, relation facts | 关联台, 银行明细, 成本统计, 搜索 | Workbench relation core | batch submit/withdraw, no-OA read model, workbench relation, bank detail, cost |
| 外部往来款管理 | bank details, workbench pair relation, turnover read model | 关联台, 成本统计, 搜索 | Workbench relation core | relation confirm/closure/withdraw, turnover read model, workbench relation, cost |
| 待找发票 | bank/invoice/OA facts, pending invoice rules, invoice lifecycle | 关联台, 税金抵扣, 成本统计, 搜索 | Invoice lifecycle and tax | rows/filter/options, attach existing invoice, income status, lifecycle fan-out |
| 进项发票使用情况 | invoice lifecycle, bank/OA facts, payment status rules | 税金抵扣, 成本统计, 搜索, OA reverse flows | Invoice lifecycle and tax | rows, export, detail drawers, payment rules, OA reverse writes |
| OA待付款核对 | OA sync, bank/invoice facts, invoice lifecycle | 关联台, 发票生命周期, 成本/税金 through relation effects | Invoice lifecycle and tax, OA integration | rows/detail, OA sync dependency, stale/fresh, permissions |
| 销项发票收款情况 | output invoices, bank transactions, receipts, invoice lifecycle | 税金抵扣, 成本统计, 搜索 | Invoice lifecycle and tax | rows, receipt/collection writes, red invoice relations, output read model |
| 税金抵扣 | invoice lifecycle, certified import, output/input invoice usage | 成本统计/search indirectly through tax facts and cache | Invoice lifecycle and tax | tax offset read model, certified import, month cache, invoice lifecycle stale/fresh |
| ETC票据管理 | ETC import, business batch state, OA draft/manual status | 关联台, 税金抵扣, 成本统计, 搜索 | ETC chain | business batch create/update/delete, OA draft, workbench summary, tax/cost |
| 成本统计 | bank, invoice, workbench relation, tax, project scope, no-OA, turnover, ETC | Analytics/output only, but broad regression signal | Analytics/status | month/all scopes, export, explorer, project/transaction detail, App Status cost domain |
| 设置 | app settings, OA credentials, project scope, data reset | All pages on reset/settings/project changes | Analytics/status, security | permissions/admin, data reset, project sync, read model invalidation, App Health |
| 系统状态 | runtime registries, workers, queue, dependencies, read model readiness | Observability only, but validates all pages | Analytics/status | app health snapshot, stream, operations dashboard, registry consistency |

## Strong Dependency Rules

- Workbench relation changes are never page-local. Plan relation writes with Workbench, relation read model, bank detail, cost, search, and affected invoice pages in mind.
- Import workflow changes are never single-page until proven otherwise. `ImportWorkflowPage` and import services are shared.
- Invoice lifecycle changes must consider pending invoices, input invoice usage, OA pending payments, output collections, tax offset, cost statistics, and search.
- Settings reset and project scope changes are cross-system changes and require App Health plus affected read model verification.
- Cost statistics is a downstream aggregate and should be used as a smoke target for many upstream business writes.

## Parallel Work Guidance

Safe parallel work requires all of the following:

- Threads are in separate worktrees or write only separate page phase directories.
- Shared files such as `.planning/ROADMAP.md`, `.planning/STATE.md`, registry files, shared import workflow, Workbench relation services, and lifecycle service are not edited concurrently without coordination.
- Each page phase lists upstream and downstream smoke targets before implementation.
- If two pages both touch Workbench relation, import workflow, invoice lifecycle, App Status, or settings reset, treat them as the same dependency group rather than independent work.
