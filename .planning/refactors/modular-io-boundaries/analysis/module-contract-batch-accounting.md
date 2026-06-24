# Module Contract - Batch Accounting

**Date:** 2026-06-24
**Worker:** T8 Module IO Contracts
**Status:** documentation/accounting closed
**Runtime behavior:** unchanged

## Module Basic Info

| Field | Content |
| --- | --- |
| Module key | `batch-accounting` |
| Module type | Page module |
| Route | `/batch-accounting` |
| Frontend entry | Batch accounting page/features |
| Backend entry | `BatchAccountingApiRoutes`, `BatchAccountingService` |
| Read model | Uses batch accounting payload and `workbench_relation` for relation context |
| Docs entry | `docs/modules/batch-accounting/README.md` |
| Refactor status | Contracted locally; production evidence deferred |

## IO Contract Reconciliation

### Inputs

| Input | Contract |
| --- | --- |
| GET payload | Read-only route owner delegates to `BatchAccountingService.build_payload(...)`; no repair/write/read-model scheduling in GET. |
| Submit/withdraw | Must route relation writes through Workbench relation command service or explicit command port; direct pair mutation fallback is forbidden. |
| Legacy case id repair | Retained as test-observed compat repair behavior; no active app/service caller outside service definition per T5 evidence. |

### Outputs

| Output | Contract |
| --- | --- |
| List payload | Must preserve existing API shape and relation/read model diagnostics. |
| Submit/withdraw result | Must include affected scopes/freshness targets where relation/read model visibility changes. |
| Repair result | Compatibility repair must not become a hidden runtime caller without explicit owner/deletion decision. |

### State / Events

- Batch submit/withdraw relation state is canonical Workbench relation state, not a page-private fact.
- Read model non-fresh is a read-side diagnostic; mutation blocking must come from canonical write safety, permission/session, version/idempotency and DB/write model availability.
- Frontend events are refresh hints only.

### Public / Internal Surfaces

Public surfaces:

- Batch accounting page feature API.
- `BatchAccountingApiRoutes` for HTTP mapping.
- `BatchAccountingService` public query/command methods.
- Workbench relation command/read boundaries for relation effects.

Internal-only surfaces:

- Direct pair service mutation fallback.
- GET-side repair/write/read-model scheduling.
- Legacy repair callable from app/service runtime paths without explicit owner approval.

### Legacy Status

| Legacy path | Status | Constraint |
| --- | --- | --- |
| `BatchAccountingService.repair_legacy_case_id_collisions(...)` | test-observed compat repair | No active app/service caller outside service definition; do not delete or wire into runtime without owner/deletion condition. |
| Direct pair mutation fallback | removed/guarded in prior slices | Must not return in submit/withdraw production paths. |
| Old route-owned submit/withdraw side effects | extracted/guarded | Route owner keeps HTTP mapping; service/command boundaries own business effects. |

### Read Model Refresh / Force Refresh

- Batch accounting relation writes affect `workbench_relation` and downstream read models through Workbench relation command/durable queue contracts.
- Force refresh is not batch-accounting-specific; use shared read-model gateway/runbook contract if operationally required.
- Operation barrier targets must be returned/consumed by write paths when user-visible relation state changes.

### Partitioned Scoped Incremental Target

Batch accounting does not own a standalone App Status read model in the manifest. It consumes Workbench relation/read model contracts and must not introduce private unregistered read-model refresh or cache semantics.

## Test Contract

| Category | Applicability | Evidence |
| --- | --- | --- |
| 1. Business core unit tests | Applicable for submit/withdraw/repair rules | Existing batch accounting service/API tests. |
| 2. Service-layer tests | Applicable | Existing service and relation command boundary tests. |
| 3. API contract tests | Applicable | Batch accounting API tests preserve GET/submit/withdraw shape. |
| 4. Read model/cache/background job tests | Indirect | Relation effects covered through Workbench relation/read model tests. |
| 5. Frontend component and interaction tests | Applicable | Batch accounting page tests and Browser flow. |
| 6. E2E business-flow integration tests | Applicable | Submit/withdraw -> relation barrier -> bucket recovery flows. |
| 7. Existing feature regression tests | Applicable | T5 guard protects legacy repair quarantine; route guards protect no GET writes/direct pair bypass. |

## Handoff Evidence Consumed

- `T5-legacy-contamination.md`
- Existing batch-accounting modular IO analysis files.
- `docs/modules/batch-accounting/README.md`
- `docs/modules/batch-accounting/tests.md`

## Remaining Risk

Production submit/withdraw worker drain, relation readiness and browser smoke evidence remain deferred. Legacy repair deletion requires explicit finance owner/deletion condition.
