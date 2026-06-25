# server.py ETC reconciliation route owner residual audit

- Date: 2026-06-25
- Boundary: `server-py:etc-reconciliation-route-owner-residual-audit`
- Status: `analysis-closed`
- Module closure: `implementation-gap-open`
- Production: not used

## Scope

This slice audited the ETC/import/reconciliation routes still owned by `Application` after the existing ETC business-batch route owner extraction. It did not change runtime code or API behavior.

## Evidence Read

- `docs/modules/etc-tickets/README.md`
- `docs/modules/etc-tickets/tests.md`
- `docs/modules/imports-etc-invoices/README.md`
- `docs/modules/imports-etc-invoices/tests.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- CodeGraph context for `EtcBusinessBatchApiRoutes`, `Application` ETC/import/reconciliation handlers, and ETC backend tests.
- AST inventory of `backend/src/fin_ops_platform/app/server.py`.
- Static guard context in `tests/test_platform_runtime_boundary_guards.py`.

## Current Ownership Facts

Existing route owner:

- `backend/src/fin_ops_platform/app/routes_etc.py::EtcBusinessBatchApiRoutes` already owns `/api/etc/business-batches*` application-service delegation for list, create, detail, source files, import preview/confirm, OA draft creation, and manual OA status.
- `server.py` still owns session resolution, JSON/multipart loading, HTTP response mapping, and some compatibility/delete paths for ETC business batches.
- Static guard coverage already prevents removed ETC business batch legacy handlers from returning and requires the business-batch wrappers to delegate to `EtcBusinessBatchApiRoutes`.

Residual `Application` route groups:

- Reconciliation task group:
  - `_handle_api_etc_reconciliation_tasks`
  - `_handle_api_etc_reconciliation_ready_for_import`
  - `_handle_api_etc_reconciliation_task_create`
  - `_route_api_etc_reconciliation_task`
  - upload/text/source-file/item/confirm/reopen/refresh/delete subhandlers
- Task-aware import group:
  - `_handle_api_etc_import`
  - `_handle_api_etc_import_preview`
  - `_handle_api_etc_import_confirm`
  - import job/link/refresh helpers
- Legacy ETC invoice/batch group:
  - `_handle_api_etc_invoices`
  - `_handle_api_etc_batches`
  - `_handle_api_etc_batch_detail`
  - `_handle_api_etc_batch_delete`
  - draft/confirm-submitted/mark-not-submitted/revoke handlers

## Classification

`/api/etc/business-batches*` is already route-owned for the service-facing methods listed above. The remaining business-batch delete and OA draft revoke paths are not selected first because they still coordinate relation-summary cancellation, task cleanup, canonical invoice release, downstream refresh, and persistence helpers. Moving them before a narrower owner boundary would mix route extraction with side-effect service extraction.

`/api/etc/import/preview` and `/api/etc/import/confirm` are not selected first because they create or resume import jobs, enforce preview/session freshness, and fan out into task-scoped business batch creation, canonical invoice linking, and derived lifecycle refresh. This group should follow after the reconciliation task route surface is isolated, because it depends on task payload and task status contracts.

`/api/etc/batches*` legacy routes are not selected first because they intentionally bridge older UI/API shapes and business-batch compatibility payloads. They need a separate compat-only route-owner or removal/guard decision.

Selected next boundary:

`server-py:etc-reconciliation-task-route-owner-facade-extraction`

This is the safest first implementation slice because the route surface is cohesive and heavily covered by existing ETC backend tests, while the first extraction can be limited to a route facade that owns URL subrouting, JSON/multipart parsing decisions, structured route responses, and delegation to existing services/helpers. Heavy task-delete side effects can remain temporarily delegated to `Application` callbacks during the first slice, then be audited separately for service extraction.

## Required Implementation Shape

The next slice should add an explicit route owner, expected name:

- `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py::EtcReconciliationTaskApiRoutes`

Allowed first-slice behavior:

- Move `/api/etc/reconciliation-tasks*` route branching out of `Application`.
- Keep business semantics, payload shapes, status codes, and error codes unchanged.
- Inject explicit dependencies and callbacks rather than the whole `Application`.
- Reuse existing helpers for payload serialization and expected-version parsing if they are still app-owned, but pass them as named callables.
- Keep deletion side effects delegated through explicit callbacks such as task delete and imported-invoice delete until a later service-boundary slice.
- Add/extend static guards proving `server.py` delegates reconciliation task routing to the new route owner and does not reintroduce broad direct handler ownership.

Forbidden in the next slice:

- Do not change ETC task state machine semantics.
- Do not change `/api/etc/import/*` or `/api/etc/batches*` behavior.
- Do not move SQL or task deletion side-effect internals into a route class.
- Do not pass the whole `Application` into the new route owner.
- Do not use production browser/admin/write validation.

## Test Decision

This analysis slice changed no runtime behavior, so no runtime tests were added.

For the next implementation slice, applicable categories are:

1. Business core unit tests: existing ETC task tests should be rerun because route extraction must preserve task version/status validation.
2. Service-layer tests: applicable only if side-effect callbacks are touched; first slice should avoid service behavior changes.
3. API contract tests: required; rerun targeted `tests.test_etc_backend` ETC reconciliation route tests and add static guard coverage for delegation.
4. Read model/cache/background job tests: not directly applicable unless imported-invoice delete or task delete side effects move.
5. Frontend component/interaction tests: not directly applicable for a pure backend route-owner extraction.
6. End-to-end business-flow integration tests: targeted ETC backend integration tests apply because these routes feed import readiness.
7. Existing feature regression tests: required through existing ETC backend and platform runtime boundary guard tests.

## Next Prompt

Implement `server-py:etc-reconciliation-task-route-owner-facade-extraction`.

Start by reading this audit, `routes_etc.py`, `server.py` lines around the ETC reconciliation task handlers, `tests/test_etc_backend.py` ETC reconciliation route tests, and `tests/test_platform_runtime_boundary_guards.py`. Add a route owner for `/api/etc/reconciliation-tasks*` that owns subroute dispatch and delegates to existing services/helpers through explicit constructor dependencies. Keep behavior unchanged. Add or update static guard tests proving delegation and preventing broad app-owned reconciliation task route handlers from returning. Run targeted ETC backend tests plus platform boundary guard, docs verify, and diff checks.
