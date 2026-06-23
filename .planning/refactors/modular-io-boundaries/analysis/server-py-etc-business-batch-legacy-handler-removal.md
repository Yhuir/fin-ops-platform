# Server.py ETC Business Batch Legacy Handler Removal

**Date:** 2026-06-24
**Boundary:** `server-py:etc-business-batch-legacy-handler-removal`
**Status:** `implementation-closed`

## Previous State

- `autonomous/MODULE-QUEUE.md` selected `server-py:legacy-handler-extraction-implementation` as the first pending implementation boundary.
- `routes_etc.py` already owned the active `/api/etc/business-batches*` route behavior through `EtcBusinessBatchApiRoutes`.
- `server.py` still retained older private ETC business batch handlers that duplicated list/create/detail/import/oa/manual-status behavior.

## Selected Boundary

Remove only unused ETC business batch private handlers from `server.py` and add a static guard proving they cannot return.

Removed handlers:

- `Application._handle_api_etc_business_batches(...)`
- `Application._handle_api_etc_business_batch_create(...)`
- `Application._route_api_etc_business_batch(...)`
- `Application._handle_api_etc_business_import_preview(...)`
- `Application._handle_api_etc_business_import_confirm(...)`
- `Application._handle_api_etc_business_oa_draft(...)`
- `Application._handle_api_etc_business_manual_oa_status(...)`

Retained handlers:

- `Application._handle_api_etc_business_batches_route(...)`: thin HTTP/session/body wrapper delegating list/create to `EtcBusinessBatchApiRoutes`.
- `Application._route_api_etc_business_batch_v2(...)`: thin HTTP/path/body wrapper delegating source-files, import preview/confirm, OA draft and manual status to `EtcBusinessBatchApiRoutes`.
- `Application._handle_api_etc_business_oa_draft_revoke(...)`: still legacy because revoke has not yet been moved into `EtcBusinessBatchApiRoutes`.
- `Application._handle_api_etc_business_batch_delete(...)`: still legacy because delete/reset has Workbench relation preflight and read model side effects that need a separate boundary.

## Evidence

CodeGraph and literal search found the removed handlers were definition-only:

- The active dispatch for `/api/etc/business-batches` calls `_handle_api_etc_business_batches_route(...)`.
- The active dispatch for `/api/etc/business-batches/{id}...` calls `_route_api_etc_business_batch_v2(...)`.
- The removed handlers had no callers outside their own removed legacy route.
- Existing ETC module tests cover the active API contract surface.

## Impact Analysis

### 1. Module Scope

- Target module: `etc-tickets` and shared `server.py` route boundary.
- Module type: page module + shared route boundary.
- Change type: refactor / legacy removal.
- Business behavior change: no.
- API response shape change: no.
- Read model freshness semantic change: no.
- Permission/audit change: no.
- Go/Fiber/Go Worker candidate: no.

### 2. Backend Impact

| Layer | Impact | Files / symbols | Risk | Test |
| --- | --- | --- | --- | --- |
| route / HTTP mapping | yes | `server.py`, `EtcBusinessBatchApiRoutes` | accidental reintroduction of old handler path | static guard + active API tests |
| application service | no | `EtcBusinessBatchApplicationService` unchanged | no business rule change | existing tests |
| repository / SQL | no | none | no SQL change | not applicable |
| audit / permission | no | session still resolved in active wrappers | no permission change | existing ETC API tests |

### 3. Read Model / Worker Impact

No read model, dirty scope, outbox, worker, App Status, Redis or RabbitMQ behavior changed.

ETC import confirm, OA draft and manual status still reach `EtcBusinessBatchApplicationService` through `EtcBusinessBatchApiRoutes`, preserving existing link/freshness side effects owned by the application service dependencies.

### 4. Frontend Impact

No frontend files changed. Existing frontend API continues to call `/api/etc/business-batches*`.

### 5. Legacy Retirement / Contamination Control

| Legacy path | Current callers | Target state | Evidence | Guard |
| --- | --- | --- | --- | --- |
| removed ETC business-batch private handlers | none | removed | `rg` found definitions only before removal | `test_etc_business_batch_routes_do_not_keep_removed_legacy_handlers` |
| active list/create/detail/import/manual-status wrappers | `Application.handle_request` | thin HTTP/session/body wrapper | delegates to `EtcBusinessBatchApiRoutes` | same static guard |
| delete/reset handler | active delete path | compat-only shared boundary | kept for Workbench relation preflight and reset side effects | existing ETC summary relation boundary guard |
| OA draft revoke handler | active revoke path | compat-only shared boundary | kept as future extraction candidate | pending later slice |

The removed legacy path can no longer construct `EtcBusinessBatchActor` directly in `server.py`. Actor mapping for active list/create/detail/import/manual-status now stays in `EtcBusinessBatchApiRoutes._actor(...)`.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/etc-tickets/state-machine.md`
- `autonomous/STATE.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/NEXT-PROMPT.md`

Global workflow definition: unchanged. Existing `implementation-closed` slice label is sufficient.

ETC module state definition: unchanged. This slice deletes unreachable legacy handlers and does not alter business, UI, read model, worker, operation barrier, force refresh, permission or audit state definitions.

Success transition:

- `server-py:legacy-handler-extraction-implementation` -> `implementation-closed`
- Next pending boundary: `batch-accounting:legacy-route-implementation`

Defer/block transition:

- If active ETC tests failed due to API shape drift, this slice would be `deferred-module-failure`.
- If deletion required production writes or secrets, it would be `needs-human-production-gate`.
- Neither condition was triggered.

## Seven Test Categories

| Category | Applicable | Handling |
| --- | --- | --- |
| 1. Business core unit tests | no | No business rules, amount logic, state transitions or matching rules changed. |
| 2. Service-layer tests | indirect | Application service unchanged; route boundary guard proves server no longer bypasses route-owned actor mapping for removed paths. |
| 3. API contract tests | yes | Targeted ETC API tests protect active list/detail/scope/import/OA/manual-status behavior. |
| 4. Read model/cache/background job tests | indirect | No behavior change; existing ETC summary/delete guard remains for retained delete/reset path. |
| 5. Frontend component and interaction tests | no | No frontend change. |
| 6. End-to-end business-flow integration tests | indirect | Existing ETC backend flow tests cover active business-batches path. |
| 7. Existing feature regression tests | yes | Added static regression guard and ran targeted active ETC tests. |

## Verification Results

- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_business_batch_routes_do_not_keep_removed_legacy_handlers -v` passed.
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_etc_business_batch_scope_uses_session_dept_id tests.test_etc_backend.EtcApiTests.test_etc_business_batch_detail_returns_invoice_items_without_detection_fields tests.test_etc_backend.EtcApiTests.test_etc_business_batch_oa_draft_waits_for_manual_confirmation_without_detection_runtime tests.test_etc_backend.EtcApiTests.test_etc_business_manual_status_accepts_confirmation_pending_state -v` passed.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` passed.
- `bash scripts/verify.sh docs` passed.
- `git diff --check` passed.

## Production Evidence

No production validation is required for this slice because no runtime behavior, deployment config, database, worker, queue, readiness or file-system behavior changed.

## Next Prompt

`batch-accounting:legacy-route-implementation`
