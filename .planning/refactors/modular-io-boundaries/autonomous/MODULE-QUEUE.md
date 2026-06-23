# Autonomous Module Queue

**Purpose:** Ordered queue for unattended modular IO refactor execution.
**Rule:** Each item is a narrow boundary, not an entire product area.

| Order | Boundary | Status | Notes |
| ---: | --- | --- | --- |
| 1 | `bank-details:auto-tag-category-boundary` | production-evidence-deferred | Local contract/code guard/doc slice completed; real production DB/worker evidence deferred because no local PGSQL_URL or staging DB. |
| 2 | `reconciliation-workbench:amount-check-query-contract` | pending | Narrow workbench contract; avoid full workbench rewrite. |
| 3 | `pending-invoices:read-side-contract` | pending | Read model/detail/drawer contract first; avoid rule write expansion. |
| 4 | `oa-pending-payments:read-side-and-relation-contract` | pending | Builds on pending invoice/OA projection read-side evidence. |
| 5 | `batch-accounting:legacy-route-contract` | pending | Route/server.py extraction candidate. |
| 6 | `read-model-refresh-gateway:force-refresh-and-freshness-registry` | pending | Shared refresh, force refresh, freshness proof, scope policy and operation barrier registry after pilot evidence. |
| 7 | `server-py:route-owner-inventory` | pending | Inventory and small route ownership hardening only; no broad rewrite. |
| 8 | `go-hot-path:workbench-compute-admission` | pending | Admission review only for `workbench:matching-grouping-check`; no Go implementation until gates pass. |
| 9 | `go-hot-path:workbench-read-model-builder-admission` | pending | Admission review only for active generation / scoped incremental Go Worker candidate. |
| 10 | `go-hot-path:import-parser-admission` | pending | Admission review only for parse/normalize/preview Go Processor candidate. |
| 11 | `go-hot-path:cost-summary-rollup-admission` | pending | Admission review only for summary/rollup candidate after cost read model contract is stable. |

## Status Values

- `pending`
- `in-progress`
- `closed-autonomous`
- `production-evidence-deferred`
- `deferred-module-failure`
- `deferred-scope-too-large`
- `go-candidate-deferred`
- `needs-human-production-gate`
