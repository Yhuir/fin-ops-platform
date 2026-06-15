<!-- refreshed: 2026-06-15 -->
# Architecture

**Analysis Date:** 2026-06-15

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                 React Page / Route Layer                    │
├──────────────────┬──────────────────┬───────────────────────┤
│ Turnover page    │ Grouped table    │ Extra/export dialogs  │
│ `web/src/pages/TurnoverLedgerPage.tsx`                      │
│ `web/src/components/turnoverLedger/`                        │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                 Frontend API / Event Layer                  │
│ `web/src/features/turnoverLedger/api.ts`                    │
│ `web/src/features/turnoverLedger/types.ts`                  │
│ `web/src/features/domainEvents.ts`                          │
│ `web/src/features/operationBarrier/api.ts`                  │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                HTTP Mapping / Route Boundary                │
│ `backend/src/fin_ops_platform/app/server.py`                │
│ `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`│
│ `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py` │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│             Domain Services / Write UoW / Read Facade       │
│ `services/turnover_ledger_query_service.py`                 │
│ `services/turnover_ledger_write_facade.py`                  │
│ `services/turnover_ledger_write_uow.py`                     │
│ `services/turnover_relation_service.py`                     │
│ `services/turnover_ledger_service.py`                       │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│        PostgreSQL Facts, Durable Queue, SQL Read Model      │
│ `PostgresStateStore` / read repositories                    │
│ `job.outbox_events`, `job.read_model_dirty_scopes`          │
│ `read_model.turnover_ledger_*` via SQL repository methods   │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Runtime Worker Plane                     │
│ `services/turnover_ledger_read_model_refresh.py`            │
│ `services/turnover_ledger_sql_projection.py`                │
│ `services/runtime_worker_registry.py`                       │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Turnover page | Owns filters, loading/error/stale UI, tag drawer, manual closure drawer, extra drawer, export dialog, operation overlay, and domain-event emission. | `web/src/pages/TurnoverLedgerPage.tsx` |
| Grouped table | Renders grouped summary rows and real `flow_rows`; action callbacks must use real bank row identifiers, not summary rows. | `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx` |
| Extra drawer | Renders relation detail, extra fields, confirm/withdraw affordances, and permission-disabled state. | `web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx` |
| Export dialog | Previews formal XLSX export columns and downloads blob responses. | `web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx` |
| Frontend API mapper | Maps snake_case API payloads to typed camelCase UI models and calls turnover endpoints. | `web/src/features/turnoverLedger/api.ts` |
| Frontend types | Defines the page contract for rows, groups, extras, tag selection, closure, mutation responses, and operation barrier targets. | `web/src/features/turnoverLedger/types.ts` |
| HTTP server | Routes `/api/turnover-ledger*`, parses query/body, maps errors/status codes, and wires facades/builders. | `backend/src/fin_ops_platform/app/server.py` |
| Route adapter | Provides route-level methods for list/detail/extra/confirm/export and grouped compatibility normalization. | `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` |
| Read facade | Keeps read handlers behind a small facade for list/export/detail/extra reads. | `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py` |
| Query service | Reads `turnover_ledger` SQL read model through `ReadModelQueryGateway`; enqueues missing/stale refresh and only uses legacy payload when PostgreSQL read model is not required. | `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py` |
| Ledger service | Builds legacy/grouped turnover rows from bank transactions, effective categories, relation snapshot, selected tags, and extras. | `backend/src/fin_ops_platform/services/turnover_ledger_service.py` |
| Relation service | Owns business rules for suggested/deterministic/confirmed/withdrawn relations and manual zero-difference closure validation. | `backend/src/fin_ops_platform/services/turnover_relation_service.py` |
| Write facade | Creates command objects for tag selection, bank-row tag batch, extra save, confirm, manual closure, and withdraw; declares affected read model refresh requests. | `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py` |
| Write UoW | Runs stale preconditions, idempotency reservation/replay, mutation handler, dirty/outbox enqueue, and transaction commit atomically. | `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py` |
| Write adapters | Binds PostgreSQL/local ports, stale precondition ports, Workbench pair port, legacy fallback adapters, and request-boundary facades. | `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py` |
| SQL projection | Rebuilds turnover read model rows for scope `all` or month-like scopes and persists via read repository. | `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py` |
| Worker handler | Consumes `turnover_ledger.read_model.refresh`, rebuilds projection, and completes dirty scope. | `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py` |
| Source versions | Computes freshness source versions from schema versions, relation snapshot, extras, tag selection, category snapshot, auto-tag rules, and OA projection sync. | `backend/src/fin_ops_platform/services/turnover_ledger_source_versions.py` |
| Runtime registry | Registers `turnover-ledger` worker and maps it to `turnover_ledger` read model/scope/event. | `backend/src/fin_ops_platform/services/runtime_worker_registry.py` |
| App status registries | Registers `turnover_ledger` domain and read model for global runtime status. | `backend/src/fin_ops_platform/services/app_status_domain_registry.py`, `backend/src/fin_ops_platform/services/app_status_read_model_registry.py` |

## Pattern Overview

**Overall:** Route-to-service architecture with command/UoW writes, SQL read model queries, durable outbox refresh, and React page-level orchestration.

**Key Characteristics:**
- Reads prefer `turnover_ledger` SQL read model through `ReadModelQueryGateway` in `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`.
- Writes go through `TurnoverLedgerWriteFacade` and `TurnoverLedgerWriteUnitOfWork`, not direct route mutation.
- Manual closure and withdraw also affect Workbench relation facts through `TurnoverLedgerWorkbenchPairPort` in `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`.
- Freshness truth is PostgreSQL durable queue/readiness: `job.outbox_events`, `job.read_model_dirty_scopes`, and app status readiness, not browser events.
- Frontend operation completion requires API success plus operation barrier freshness through `web/src/features/operationBarrier/api.ts`.

## Layers

**Page Layer:**
- Purpose: Own turnover-ledger UI state and user interactions.
- Location: `web/src/pages/TurnoverLedgerPage.tsx`, `web/src/components/turnoverLedger/`.
- Contains: filters, family tabs, grouped table, tag selection, manual closure selection, extra drawer, export preview/download, permission gating.
- Depends on: `web/src/features/turnoverLedger/api.ts`, `web/src/features/operationBarrier/api.ts`, `web/src/features/domainEvents.ts`.
- Used by: route registry entry in `web/src/app/pageRegistry.tsx`.

**Frontend API Contract Layer:**
- Purpose: Keep backend snake_case contract isolated from UI models.
- Location: `web/src/features/turnoverLedger/api.ts`, `web/src/features/turnoverLedger/types.ts`.
- Contains: request functions, DTO mappers, blob download handling, read model status fields, mutation response fields.
- Depends on: `web/src/features/apiClient.ts`.
- Used by: `web/src/pages/TurnoverLedgerPage.tsx` and tests in `web/src/test/TurnoverLedgerApi.test.ts`.

**HTTP Mapping Layer:**
- Purpose: Map HTTP request/response shape, auth/session actor, errors, file responses, and request-boundary facades.
- Location: `backend/src/fin_ops_platform/app/server.py`, `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`.
- Contains: handlers for `/api/turnover-ledger`, `/tag-selection`, `/bank-row-tags/batch`, `/relations/{id}`, `/relations/{id}/extra`, `/relations/confirm`, `/closures/confirm`, `/relations/{id}/withdraw`, `/export-preview`, `/export`.
- Depends on: turnover services, write facade builders, read facade, route adapter.
- Used by: local/dev server entry in `backend/src/fin_ops_platform/app/main.py` through `Application`.

**Business Service Layer:**
- Purpose: Own turnover relation and ledger business rules independent of HTTP.
- Location: `backend/src/fin_ops_platform/services/turnover_relation_service.py`, `backend/src/fin_ops_platform/services/turnover_ledger_service.py`, `backend/src/fin_ops_platform/services/turnover_ledger_extra_service.py`, `backend/src/fin_ops_platform/services/bank_turnover_tag_semantics.py`.
- Contains: category semantics, group construction, manual zero-difference closure validation, relation statuses, extra field validation.
- Depends on: bank transaction category/effective category services, import transactions, app settings tag selection, relation/extras snapshots.
- Used by: route adapter, SQL projection builder, write ports.

**Write Boundary Layer:**
- Purpose: Keep mutations atomic, idempotent, stale-checked, auditable, and connected to durable refresh.
- Location: `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`.
- Contains: command shape, refresh requests, transaction context, stale preconditions, idempotency store integration, dirty/outbox enqueue, Workbench pair port delegation.
- Depends on: explicit repository/port dependencies, not `Application`.
- Used by: request-boundary facades created in `backend/src/fin_ops_platform/app/server.py`.

**Read Model / Worker Layer:**
- Purpose: Materialize and serve turnover grouped ledger without hot-path recomputation when PostgreSQL read model is required.
- Location: `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`, `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py`, `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`.
- Contains: source version comparison, missing/stale enqueue, projection rebuild, dirty scope completion.
- Depends on: read repository, runtime queue repository, source version provider.
- Used by: read facade and runtime worker process.

**Runtime Status Layer:**
- Purpose: Make turnover read model/worker state visible in App Status and prevent green status without readiness proof.
- Location: `backend/src/fin_ops_platform/services/runtime_worker_registry.py`, `backend/src/fin_ops_platform/services/app_status_domain_registry.py`, `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`.
- Contains: domain key `turnover_ledger`, route `/turnover-ledger`, worker `turnover-ledger`, read model key `turnover_ledger`, event type `turnover_ledger.read_model.refresh`.
- Depends on: runtime monitoring repository and worker heartbeat/readiness facts.
- Used by: app health endpoints in `backend/src/fin_ops_platform/app/server.py` and shell status UI.

## Data Flow

### Primary Read Path

1. Page registers route `/turnover-ledger` through `web/src/app/pageRegistry.tsx`.
2. `web/src/pages/TurnoverLedgerPage.tsx` calls `fetchTurnoverLedgerGrouped(...)` in `web/src/features/turnoverLedger/api.ts`.
3. API client requests `GET /api/turnover-ledger?view=grouped&page=...&page_size=...`.
4. `backend/src/fin_ops_platform/app/server.py` parses query in `_handle_api_turnover_ledger(...)` and calls `TurnoverLedgerReadFacade.list_ledger(...)`.
5. `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py` delegates to `TurnoverLedgerApiRoutes.list_ledger(...)`.
6. `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` delegates grouped reads to `TurnoverLedgerQueryService.list_ledger(...)` when a query service is bound.
7. `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py` loads SQL read model with `ReadModelQueryGateway` for scope type `turnover_ledger`, scope key `all`.
8. Fresh payload returns grouped rows; stale/missing payload returns status and enqueues refresh through runtime queue.
9. `web/src/features/turnoverLedger/api.ts` maps `read_model_status`, `read_model_stale_reasons`, `groups`, `flow_rows`, `summary_row`, and pagination to camelCase.
10. `web/src/pages/TurnoverLedgerPage.tsx` shows data, stale warning, loading, empty, or error state.

### Manual Zero-Difference Closure Write Path

1. User selects multiple same-group `flow_rows` in `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`.
2. Before submit, `web/src/pages/TurnoverLedgerPage.tsx` waits for `turnover_ledger:all` fresh via `waitForOperationFreshness(...)`, reloads grouped ledger, and rebinds selected `sourceBankRowId` values to latest `flowRows`.
3. Page sends `POST /api/turnover-ledger/closures/confirm` through `confirmTurnoverClosure(...)` in `web/src/features/turnoverLedger/api.ts`.
4. `backend/src/fin_ops_platform/app/server.py` maps the request to `TurnoverLedgerClosureRequestBoundaryFacade` from `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`.
5. `TurnoverLedgerWriteFacade.confirm_zero_difference_closure(...)` creates action `turnover_relation_zero_difference_closure` with refresh requests for `turnover_ledger`, `workbench`, `workbench_relation`, `cost_statistics`, and `search`.
6. `TurnoverLedgerWriteUnitOfWork.run(...)` checks expected versions, reserves idempotency, runs the handler, enqueues dirty/outbox refresh events, and commits.
7. Handler calls `relation_repository.confirm_zero_difference_closure(...)` and `workbench_pair_port.create_turnover_manual_closure(...)` in one transaction.
8. API returns relation, Workbench pair relation, affected months, and freshness targets.
9. Page holds global operation overlay, waits for returned targets to become fresh, reloads grouped ledger, then emits `turnoverRelationUpdated` and `workbenchRelationUpdated` from `web/src/features/domainEvents.ts`.

### Relation Extra Save Path

1. `web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx` edits interest/payment/note fields.
2. `web/src/pages/TurnoverLedgerPage.tsx` calls `saveTurnoverRelationExtra(...)`.
3. `backend/src/fin_ops_platform/app/server.py` routes to relation extra request-boundary facade.
4. `TurnoverLedgerWriteFacade.update_relation_extra(...)` normalizes extra and creates a `turnover_relation_extra_changed` refresh request for `turnover_ledger`.
5. `TurnoverLedgerWriteUnitOfWork.run(...)` saves extra through `extra_repository.save_extra(...)` and enqueues dirty/outbox in the same transaction.
6. Frontend waits operation barrier for `turnover_ledger` and emits `turnoverLedgerExtraUpdated` only as same-browser refresh hint.

### Tag Selection Path

1. `GET /api/turnover-ledger/tag-selection` reads `AppSettingsService.get_turnover_ledger_tag_selection_payload()` in `backend/src/fin_ops_platform/app/server.py`.
2. `PUT /api/turnover-ledger/tag-selection` goes through `TurnoverLedgerWriteFacade.update_tag_selection(...)`.
3. The write facade uses `AppSettingsService.normalize_turnover_ledger_tag_selection_update(...)`, saves settings through a settings port, writes audit, and enqueues `turnover_ledger` refresh with reason `turnover_ledger_tag_selection_changed`.

### Bank Row Tag Batch Path

1. `web/src/features/turnoverLedger/api.ts` posts `POST /api/turnover-ledger/bank-row-tags/batch`.
2. `TurnoverLedgerWriteFacade.update_bank_row_tags_batch(...)` applies category updates through `bankdetail_port.apply_turnover_category_updates(...)`.
3. Refresh requests include `bank_detail` month scopes, `workbench` month scopes, and `turnover_ledger:all`.

### Read Model Refresh Worker Path

1. Dirty/outbox rows are written to PostgreSQL by `TurnoverLedgerDirtyOutboxWriter` via write adapters.
2. Runtime worker `turnover-ledger` is registered in `backend/src/fin_ops_platform/services/runtime_worker_registry.py`.
3. Worker consumes `turnover_ledger.read_model.refresh` events.
4. `TurnoverLedgerReadModelRefreshService.handle_runtime_event(...)` validates event type, scope type `turnover_ledger`, and scope key.
5. `TurnoverLedgerSqlProjectionBuilder.rebuild_turnover_ledger_read_model_scope(...)` rebuilds rows with source versions and calls `save_turnover_ledger_rows(...)`.
6. Handler calls `complete_read_model_refresh(...)` on the queue repository.
7. App Status reads readiness/dirty/outbox/worker state through registries and runtime monitoring.

**State Management:**
- Backend canonical state lives in PostgreSQL facts/settings/relation/extras/category snapshots and Workbench relation facts.
- `turnover_ledger` SQL read model is a projection and must not be treated as write truth.
- Frontend state is page-local; `PageRouteHost` unmounts inactive pages, and domain events only prompt refresh in the same browser session.
- Operation overlay state in `web/src/contexts/GlobalOperationOverlayContext.tsx` blocks user continuation until operation barrier targets are fresh.

## Key Abstractions

**Turnover Relation:**
- Purpose: Canonical relation between external turnover bank rows, including suggested/deterministic/confirmed/withdrawn state.
- Examples: `backend/src/fin_ops_platform/services/turnover_relation_service.py`, `tests/test_turnover_relation_service.py`.
- Pattern: In-memory/domain service with snapshot persistence ports and SQL adapters.

**Grouped Ledger Row:**
- Purpose: UI/read model representation that separates `summary_row`, real `flow_rows`, `allocation_lots`, and compatibility rows.
- Examples: `backend/src/fin_ops_platform/services/turnover_ledger_service.py`, `web/src/features/turnoverLedger/types.ts`, `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`.
- Pattern: Read DTO; write operations must use `flow_rows[*].source_bank_row_id`.

**Write Command:**
- Purpose: Mutation envelope with action name, scope keys, refresh requests, expected versions, idempotency, actor, tenant, and payload.
- Examples: `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`.
- Pattern: Command object passed into UoW.

**Write Unit of Work:**
- Purpose: One transaction for stale preconditions, idempotency, mutation, dirty/outbox enqueue, and idempotency commit.
- Examples: `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`, `tests/test_turnover_ledger_uow_contract.py`.
- Pattern: Dependency-injected ports; no HTTP or `Application` dependency.

**ReadModelQueryGateway:**
- Purpose: Fresh/stale/missing/source mismatch gate for read model reads.
- Examples: `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`, `backend/src/fin_ops_platform/services/read_model_query_gateway.py`.
- Pattern: Read gateway with enqueue-on-stale/missing.

**Source Versions:**
- Purpose: Detect whether turnover read model matches current facts and schemas.
- Examples: `backend/src/fin_ops_platform/services/turnover_ledger_source_versions.py`.
- Pattern: Stable version payload derived from schema versions and fact snapshots.

**Operation Barrier Target:**
- Purpose: Frontend waits for backend runtime facts to become fresh after writes.
- Examples: `web/src/features/operationBarrier/api.ts`, `web/src/pages/TurnoverLedgerPage.tsx`.
- Pattern: Post-write read-side convergence barrier; does not replace backend write safety.

## Entry Points

**Frontend Route:**
- Location: `web/src/app/pageRegistry.tsx`
- Triggers: Browser navigation to `/turnover-ledger`.
- Responsibilities: Lazy-load `web/src/pages/TurnoverLedgerPage.tsx` with page key `turnover-ledger`.

**Turnover Page:**
- Location: `web/src/pages/TurnoverLedgerPage.tsx`
- Triggers: Route mount, filter changes, drawer actions, export actions, domain events.
- Responsibilities: Query grouped ledger, manage local UI state, perform pre-write freshness waits, call API client, emit refresh events.

**HTTP API:**
- Location: `backend/src/fin_ops_platform/app/server.py`
- Triggers: `/api/turnover-ledger*` requests.
- Responsibilities: Request parsing, permission/actor mapping, facade dispatch, error mapping, JSON/blob response.

**Route Adapter:**
- Location: `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
- Triggers: Server handler calls.
- Responsibilities: Delegate list/detail/extra/export/confirm operations to services and normalize grouped payloads.

**Read Model Worker:**
- Location: `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`
- Triggers: `turnover_ledger.read_model.refresh` runtime queue events.
- Responsibilities: Validate event, rebuild projection, complete dirty scope.

**Runtime Worker Registration:**
- Location: `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- Triggers: Runtime worker manifest/health discovery.
- Responsibilities: Register `turnover-ledger`, event types, env examples, read model key, and scope type.

## Architectural Constraints

- **Threading:** Backend request handling and service objects are Python process-local; `TurnoverRelationService` uses `RLock` for in-memory snapshots in `backend/src/fin_ops_platform/services/turnover_relation_service.py`, while production writes must use PostgreSQL transaction boundaries.
- **Global state:** `backend/src/fin_ops_platform/app/server.py` wires many services and still owns legacy handler methods; new turnover business rules belong in `backend/src/fin_ops_platform/services/`, not new private server methods.
- **Read model truth:** `turnover_ledger` read model status must come from `ReadModelQueryGateway`, durable queue, and readiness. Do not return stale/missing payload as fresh in `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`.
- **Worker boundary:** Workers must not depend on `Application`, Flask/HTTP response objects, cookies, headers, or auth modules. Use `TurnoverLedgerReadModelRefreshService` and `TurnoverLedgerSqlProjectionBuilder`.
- **Write boundary:** Write services must receive explicit dependencies such as repository, queue, store, settings provider, stale precondition port, and Workbench pair port. Do not inject the whole `Application`.
- **Workbench relation boundary:** Manual closure and withdraw must delegate to Workbench relation command service through `TurnoverLedgerWorkbenchPairPort`; do not directly mutate Workbench pair relation snapshots from route code.
- **Bank detail boundary:** `/api/turnover-ledger/bank-row-tags/batch` is a Turnover API that writes Bank Detail facts via a port and fans out refresh. Do not implement a parallel Bank Detail write path in the page.
- **Frontend facts:** `turnoverRelationUpdated`, `workbenchRelationUpdated`, and `turnoverLedgerExtraUpdated` in `web/src/features/domainEvents.ts` are refresh hints only; they are not cross-page consistency facts.
- **Secrets:** `.env*`, credential, key, and secret files are not read or quoted. Environment existence may be noted only outside source maps when needed.

## Anti-Patterns

### Summary Row As Write Input

**What happens:** A grouped `summary_row` or aggregate row is used as the selected bank row for manual closure.
**Why it's wrong:** Summary rows do not represent real bank transactions and can create invalid closure evidence.
**Do this instead:** Use `flow_rows[*].source_bank_row_id` and latest `categoryVersion` from `web/src/pages/TurnoverLedgerPage.tsx` after fresh reload/rebind.

### Direct Route Mutation

**What happens:** `backend/src/fin_ops_platform/app/server.py` or `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` directly mutates relations, extras, settings, dirty scopes, or Workbench relation facts.
**Why it's wrong:** It bypasses stale preconditions, idempotency, transactionality, audit, rollback, and durable outbox.
**Do this instead:** Add command behavior to `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py` and ports/UoW behavior in `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py` / `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`.

### Freshness Bypass

**What happens:** A page or route reads SQL projection rows directly and treats them as fresh when source versions are stale or readiness is missing.
**Why it's wrong:** Users may confirm/withdraw against obsolete bank categories, relations, or Workbench state.
**Do this instead:** Read through `TurnoverLedgerQueryService` and `ReadModelQueryGateway` in `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`; expose `read_model_status` and stale reasons to `web/src/pages/TurnoverLedgerPage.tsx`.

### Deterministic Means Confirmed

**What happens:** `deterministic` candidates are treated as active closure or Workbench paired facts.
**Why it's wrong:** Deterministic only means the system found a unique zero-difference candidate; it is not manual closure.
**Do this instead:** Only `confirmed` manual relations written by `confirm_zero_difference_closure` and Workbench pair port create bank-only Workbench relation facts.

### Browser Event As Consistency Mechanism

**What happens:** Another page relies on frontend domain events as proof that read models have refreshed.
**Why it's wrong:** Events are same-browser hints and can be missed; backend read model convergence is asynchronous.
**Do this instead:** Wait for `/api/operation-barrier/status` through `web/src/features/operationBarrier/api.ts`, then reload the target read boundary.

## Error Handling

**Strategy:** Fail fast on invalid contracts, stale preconditions, unsupported worker events, permission errors, idempotency conflicts, and invalid business state; return displayable business messages through HTTP.

**Patterns:**
- `TurnoverRelationValidationError` in `backend/src/fin_ops_platform/services/turnover_relation_service.py` carries business error codes for invalid closure/relation operations.
- `TurnoverLedgerWritePreconditionError` in `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py` maps stale expected-version failures to structured HTTP payloads in `backend/src/fin_ops_platform/app/server.py`.
- `TurnoverLedgerReadModelRefreshService.handle_runtime_event(...)` rejects unsupported event types and missing/wrong scope.
- `web/src/features/turnoverLedger/api.ts` treats HTML responses as proxy/deploy errors through shared API client behavior.
- `web/src/pages/TurnoverLedgerPage.tsx` maps detail disappearance to user-facing refresh guidance.

## Cross-Cutting Concerns

**Logging:** Backend write UoW includes action names and non-sensitive actor/tenant/action metadata in outbox payloads from `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`; operational audit scenarios are documented in `docs/operations/monitoring.md`.

**Validation:** Business validation belongs in `backend/src/fin_ops_platform/services/turnover_relation_service.py`, extra validation in `backend/src/fin_ops_platform/services/turnover_ledger_extra_service.py` and route adapter helpers, tag selection normalization in `AppSettingsService`, and frontend pre-submit validation in `web/src/pages/TurnoverLedgerPage.tsx`.

**Authentication:** Routes resolve actor/session in `backend/src/fin_ops_platform/app/server.py`; services do not read cookies or headers directly.

**Authorization:** Frontend uses `useSessionPermissions()` in `web/src/pages/TurnoverLedgerPage.tsx` to disable writes, while backend APIs still enforce permissions and stale/idempotency checks.

**Read Model / Worker Governance:** `turnover_ledger` domain must stay registered in `backend/src/fin_ops_platform/services/app_status_domain_registry.py`, `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`, and `backend/src/fin_ops_platform/services/runtime_worker_registry.py` whenever its read model/worker/event contract changes.

**Documentation:** Turnover changes must update `docs/modules/turnover-ledger/README.md`, `docs/modules/turnover-ledger/state-machine.md`, and `docs/modules/turnover-ledger/tests.md` when page/API/state/read model/worker facts change; long-lived API changes must update `docs/dev/api-contracts.md`.

---

*Architecture analysis: 2026-06-15*
