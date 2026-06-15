# Legacy Entrypoints And Cleanup Gate

**Purpose:** Prevent old logic from polluting new page implementation while avoiding unsafe deletion of paths that may still be active.

## Cleanup Principle

Old logic should be removed when it is no longer an active production path. Unknown old logic must first be classified. Do not delete a path merely because it looks old.

Required sequence:

1. Inventory old route/service/repository/worker/client/docs references.
2. Classify each path as `canonical`, `transitional`, `dead`, or `unknown`.
3. Migrate active callers to the canonical boundary.
4. Add tests proving the canonical path works and the old path is no longer called.
5. Delete dead old code, stale tests, stale docs, and stale route/client references.
6. Run targeted verification and document residual risks.

## Known Transitional Areas

| Area | Current evidence | Risk | Page-phase action |
| --- | --- | --- | --- |
| `backend/src/fin_ops_platform/app/server.py` broad API dispatch | `server.py` still dispatches many `/api/workbench*`, bank details, pending invoices, invoice usage, output collections, no-OA, batch accounting, turnover ledger, ETC, settings, app health, tax, and cost paths. | New route modules may coexist with direct dispatch paths; changing only one boundary can leave old behavior active. | Identify canonical route owner before implementation. If extracting, migrate one endpoint family at a time with API tests. |
| Route module + `server.py` overlap | Files such as `routes_workbench.py`, `routes_tax.py`, `routes_cost_statistics.py`, `routes_pending_invoices.py`, `routes_oa_pending_payments.py`, `routes_output_invoice_collections.py`, `routes_no_oa_bank_batches.py`, `routes_turnover_ledger.py`, `routes_etc.py`, `routes_bank_details.py` exist while `server.py` still dispatches many matching paths. | Duplicate HTTP mapping, permissions, error shape, or response drift. | Page phase must map actual active dispatch path using code before editing contract. |
| Workbench relation legacy direct writes | `docs/modules/workbench-relations/README.md` notes prior direct pair relation mutations, persist helpers, and remaining server read/display/persist helpers. | Direct relation writes can bypass canonical command service, audit, idempotency, owner/version checks, and dirty scope fan-out. | Relation writes must use `WorkbenchRelationCommandService` / canonical UoW. Missing command service should fail fast, not fall back. |
| Legacy Workbench pair relation repository proxies | Workbench relation docs mention old `PostgresWorkbenchRepository.load_workbench_pair_relations` / `save_workbench_pair_relations` compatibility proxies. | Old repository paths can preserve stale relation semantics. | Do not add new dependencies. Delete only after caller inventory and relation regression tests. |
| Import legacy endpoints | Import docs and server dispatch include files/session APIs plus legacy `/imports/preview` and `/imports/confirm` style paths. | Shared import workflow can accidentally revive stale preview/confirm semantics. | Page phase must state which import API is canonical for bank/invoice/ETC mode and test preview stale/idempotency. |
| ETC legacy batch routes | ETC API client references legacy `/api/etc/batches*` behavior alongside business batch and reconciliation task APIs. | Old batch shape can drift from business batch source of truth. | Treat business batch/reconciliation task service as canonical unless page research proves otherwise. |
| Compatibility workers `search-pending` and `cost-tax` | Runtime worker registry keeps compatibility workers alongside focused workers. | New planning may rely on compatibility worker as canonical runtime. | Do not add new reliance; if registry changes, update worker/read model tests and ops docs. |
| Legacy app Mongo/GridFS/file paths | Global architecture notes legacy Mongo/GridFS paths remain for migration/rollback/shadow-read cases. | Old persistence can re-enter current facts or leak into export/import assumptions. | Page phases touching files/import/storage must identify current PostgreSQL/object-store boundary and migration-only paths. |
| Page-level stale/fresh bypasses | Older pages may still handle empty payloads or refreshing states inconsistently. | UI may show stale data as true empty results. | Page phase must verify API `read_model_status` and UI loading/refreshing/blocked behavior before UX work. |

## Classification Template For Page Phases

Use this exact classification before removing or bypassing old code:

```md
## Legacy Cleanup Gate

### Inventory

| Path | Kind | Current callers | Classification | Evidence |
| --- | --- | --- | --- | --- |
| `...` | route/service/repository/client/test/doc | `...` | canonical/transitional/dead/unknown | `...` |

### Canonical Boundary

- Route:
- Service:
- Repository / projection:
- Read model / worker:
- Audit / permission boundary:
- Operation barrier / affected scopes:

### Migration Plan

1. Add/confirm tests for canonical path.
2. Move callers from old path to canonical path.
3. Verify no active callers remain with `rg`/CodeGraph/tests.
4. Delete old path and stale docs/tests.
5. Run targeted verification.

### Blockers

- Unknown callers:
- Contract ambiguity:
- Missing test coverage:
```

## Removal Criteria

A path can be deleted only when all are true:

- No active runtime caller remains.
- No API client, route, service, worker, repository, or test imports it as production behavior.
- Canonical replacement has tests for success, permission, failure, stale/fresh, and regression where applicable.
- Docs no longer instruct future agents to use the old path.
- Deletion does not remove migration/rollback tooling still documented as operationally required.

## Red Flags

- "Fallback to old service if new service missing."
- "Read stale projection because it has rows."
- "Direct SQL dirty scope write from business service."
- "Direct Workbench pair mutation outside command service."
- "Frontend event emitted without backend lifecycle fan-out."
- "Old import endpoint kept for convenience without tests."
- "Compatibility worker treated as canonical worker."
- "Unknown path deleted because no one remembered using it."
