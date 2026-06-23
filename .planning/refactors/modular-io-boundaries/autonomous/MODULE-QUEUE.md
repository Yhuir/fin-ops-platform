# Autonomous Module Queue

**Purpose:** Ordered queue for unattended modular IO refactor execution.
**Rule:** Each item is a narrow boundary, not an entire product area.

| Order | Boundary | Status | Notes |
| ---: | --- | --- | --- |
| 1 | `bank-details:auto-tag-category-boundary` | production-evidence-deferred | Local contract/code guard/doc slice completed; real production DB/worker evidence deferred because no local PGSQL_URL or staging DB. |
| 2 | `read-models:manifest-and-boundary-inventory` | closed-autonomous | Manifest/owner/IO/state/event/permission/test inventory completed as analysis only; no behavior change. |
| 3 | `read-models:query-gateway-contract-and-status-parity` | closed-autonomous | Added code-level read model manifest and parity guard covering App Status registry, worker events, RabbitMQ dispatch and scope policy contracts; no runtime behavior change. |
| 4 | `read-models:refresh-gateway-force-refresh-and-operation-barrier` | closed-autonomous | Added manifest force refresh and operation barrier contract guards; no runtime behavior change. |
| 5 | `read-models:repository-port-and-sql-owner-split-plan` | closed-autonomous | Added manifest repository port contract owner map and guard tests; no SQL split yet. |
| 6 | `read-models:workbench-active-generation-contract` | closed-autonomous | Added manifest guard preserving Workbench active generation special-case contract. |
| 7 | `read-models:bank-detail-and-bank-account-balance-contract` | closed-autonomous | Added manifest guard keeping bank detail and bank account balance scope/repository/test contracts separate. |
| 8 | `read-models:pending-invoice-and-oa-pending-payment-contract` | closed-autonomous | Added manifest guard preserving pending invoice page-first-screen scope and OA pending payment fan-out contracts. |
| 9 | `read-models:invoice-lifecycle-and-usage-contract` | closed-autonomous | Added manifest guard preserving invoice lifecycle, input usage and output collection scoped incremental fan-out contracts and disjoint repository ports. |
| 10 | `read-models:cost-tax-ledger-summary-contract` | closed-autonomous | Added manifest guard preserving cost parent aggregate semantics, tax/turnover fan-out contracts and disjoint repository ports. |
| 11 | `read-models:search-and-no-oa-bank-batch-contract` | closed-autonomous | Added manifest guard preserving search partitioned index ownership and no-OA scoped incremental read-side contracts with disjoint repository ports. |
| 12 | `read-models:legacy-read-path-removal-guards` | closed-autonomous | Added static guard classifying direct read model refresh enqueue wrappers so new legacy producers cannot bypass gateway/scope policy unnoticed. |
| 13 | `reconciliation-workbench:amount-check-query-contract` | closed-autonomous | Added amount-check input priority guard proving explicit `reconciliation_amount` wins over legacy `detail_fields.明细金额合计` fallback; no runtime behavior change. |
| 14 | `batch-accounting:legacy-route-contract` | closed-autonomous | Added route handler static guard preventing GET repair/write/read-model scheduling and submit/withdraw direct relation write bypasses; no runtime behavior change. |
| 15 | `server-py:route-owner-inventory` | closed-autonomous | Added static inventory guard proving every existing `routes_*.py` owner is registered/imported/delegated from `server.py`; no runtime behavior change. |
| 16 | `go-hot-path:workbench-compute-admission` | pending | Admission review only for `workbench:matching-grouping-check`; no Go implementation until gates pass. |
| 17 | `go-hot-path:workbench-read-model-builder-admission` | pending | Admission review only for active generation / scoped incremental Go Worker candidate after read model contracts are stable. |
| 18 | `go-hot-path:import-parser-admission` | pending | Admission review only for parse/normalize/preview Go Processor candidate. |
| 19 | `go-hot-path:cost-summary-rollup-admission` | pending | Admission review only for summary/rollup candidate after cost read model contract is stable. |

## Status Values

- `pending`
- `in-progress`
- `closed-autonomous`
- `production-evidence-deferred`
- `deferred-module-failure`
- `deferred-scope-too-large`
- `go-candidate-deferred`
- `needs-human-production-gate`
