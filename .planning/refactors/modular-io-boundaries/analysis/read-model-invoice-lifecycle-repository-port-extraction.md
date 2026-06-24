# Read Model Invoice Lifecycle Repository Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:invoice-lifecycle-repository-port-extraction`
**Previous state:** `read-models:next-pilot-selection-after-output-invoice-collection` was `analysis-closed`.
**Result state:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Scope

Add the first narrow implementation boundary for the `invoice_lifecycle` read model pilot.

This slice only extracts and wires a repository port. It does not change invoice lifecycle business rules, lifecycle status semantics, payload shape, source-version semantics, worker event semantics, queue schema, API behavior, frontend behavior, Go/Fiber, Go Worker, or production state.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/prompts/04-master-goal-controller.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-output-invoice-collection.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-and-usage-contract.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-repository-port-and-sql-owner-split-plan.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/domain-events-lifecycle/README.md`
- `docs/modules/domain-events-lifecycle/tests.md`
- `docs/modules/pending-invoices/README.md`
- `docs/modules/input-invoice-usage/README.md`
- `docs/modules/output-invoice-collections/README.md`
- `docs/modules/oa-pending-payments/README.md`
- `docs/modules/tax-offset/README.md`
- `docs/modules/imports-invoices/README.md`
- `backend/src/fin_ops_platform/services/invoice_lifecycle_read_facade.py`
- `backend/src/fin_ops_platform/services/invoice_lifecycle_sql_projection.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `tests/test_invoice_lifecycle_read_facade.py`
- `tests/test_invoice_lifecycle_read_model_refresh.py`
- `tests/test_read_model_manifest.py`

CodeGraph was used before runtime edits to inspect invoice lifecycle facade, SQL projection, repository and test entry points.

## Implementation

Added `InvoiceLifecycleReadModelRepositoryPort` with only the manifest-listed methods:

- `save_invoice_lifecycle_rows(...)`
- `mark_invoice_lifecycle_scope(...)`
- `get_invoice_lifecycle_rows_by_subject_ids(...)`
- `get_invoice_lifecycle_rows_by_identity_keys(...)`
- `list_invoice_lifecycle_rows(...)`

Wiring changes:

- `InvoiceLifecycleReadFacade` now calls lifecycle row lookups through the narrow port.
- The facade keeps the original repository method-availability check against the supplied repository source before calling the port, so missing-method behavior remains `unavailable` rather than turning into an AttributeError or a fake missing row state.
- `InvoiceLifecycleSqlProjectionBuilder` now accepts an optional `invoice_lifecycle_read_model_repository` and uses the narrow port for lifecycle save/mark operations.
- `InvoiceLifecycleSqlProjectionBuilder` keeps the broad `PostgresReadModelRepository` only for existing shared collaborators that are outside this repository-port slice, including Workbench relation facade and pending invoice projection builder dependencies.

State-store wiring was inspected. There is no existing `invoice_lifecycle_sql_read_repository` property or caller. Per the prompt's anti-speculation rule, this slice did not add a new state-store property solely for symmetry.

## Legacy / Pollution Classification

| Surface | Classification | Result |
| --- | --- | --- |
| `InvoiceLifecycleReadFacade` direct broad repository method calls | migrated | Reads now go through `InvoiceLifecycleReadModelRepositoryPort`. |
| `InvoiceLifecycleSqlProjectionBuilder` direct `save_invoice_lifecycle_rows(...)` call | migrated | Save path now goes through `InvoiceLifecycleReadModelRepositoryPort`. |
| `InvoiceLifecycleSqlProjectionBuilder` direct `mark_invoice_lifecycle_scope(...)` call | migrated | Empty-scope mark path now goes through `InvoiceLifecycleReadModelRepositoryPort`. |
| `PostgresStateStore` invoice lifecycle SQL read property | not-applicable | No existing property or caller was found; no speculative state-store API was added. |
| `PostgresReadModelRepository` SQL owner methods | retained SQL owner | SQL/table knowledge remains in repository; this slice creates a consumer port, not a file split. |

Old paths in this slice do not write canonical facts, dirty scopes, outbox events, readiness, cache, App Status or new authoritative outputs outside the new port.

## State-Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/read-models/state-machine.md`

No workflow, module, business, read model or worker state definition changed. This slice advances one queue item:

- `read-models:invoice-lifecycle-repository-port-extraction`: `pending` -> `implementation-closed`
- Module closure remains `implementation-gap-open`
- Next boundary becomes `read-models:invoice-lifecycle-refresh-freshness-operation-barrier-audit`
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`

## Seven Test Categories

1. Business core unit tests: not applicable. No lifecycle policy, payment, collection, acquisition, certification, amount, relation or status transition rule changed.
2. Service-layer tests: applicable and covered by `tests/test_invoice_lifecycle_read_facade.py::InvoiceLifecycleReadModelRepositoryPortTests::test_port_excludes_unrelated_read_model_methods`.
3. API contract tests: not applicable. No route, status code, response shape, permission or frontend API contract changed.
4. Read model/cache/background job tests: applicable and covered by invoice lifecycle facade, refresh service and manifest tests. This slice specifically guards the read-model repository port boundary.
5. Frontend component and interaction tests: not applicable. No frontend code or visible behavior changed.
6. End-to-end business-flow integration tests: not applicable for this repository-port-only slice. Cross-page lifecycle fan-out remains a later freshness/barrier audit target.
7. Existing feature regression tests: applicable and covered by existing invoice lifecycle facade, refresh service and manifest tests.

## Verification

Ran:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/invoice_lifecycle_read_model_repository.py backend/src/fin_ops_platform/services/invoice_lifecycle_read_facade.py backend/src/fin_ops_platform/services/invoice_lifecycle_sql_projection.py tests/test_invoice_lifecycle_read_facade.py tests/test_invoice_lifecycle_read_model_refresh.py tests/test_read_model_manifest.py
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_lifecycle_read_facade tests.test_invoice_lifecycle_read_model_refresh tests.test_read_model_manifest -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Remaining Risk

- No local `PGSQL_URL` or staging database is available, so real PostgreSQL worker/readiness/App Status/high-row/browser evidence remains unavailable.
- This slice does not prove lifecycle freshness, force refresh, fan-out `all`, source-version proof, operation barrier behavior or legacy live/rebuild fallback absence. Those are the next audit boundary.
- `invoice_lifecycle` is not globally closed.

## Next Boundary

`read-models:invoice-lifecycle-refresh-freshness-operation-barrier-audit`
