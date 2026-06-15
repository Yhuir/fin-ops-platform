# Codebase Structure

**Analysis Date:** 2026-06-15

## Directory Layout

```text
fin-ops-platform/
├── AGENTS.md                     # Repo-local agent instructions and architectural constraints
├── README.md                     # Project overview, run commands, documentation map
├── ARCHITECTURE.md               # Repo-wide architecture overview
├── backend/                      # Python backend application
│   ├── README.md                 # Backend run/development notes
│   └── src/fin_ops_platform/
│       ├── app/                  # HTTP application, server handlers, route adapters, read facades
│       ├── services/             # Domain services, query services, write UoWs, workers, registries
│       └── postgres/             # PostgreSQL migrations and repository-related assets
├── web/                          # React + TypeScript + Vite frontend
│   ├── README.md                 # Frontend run/development notes
│   └── src/
│       ├── app/                  # Route registry and route host
│       ├── components/           # Shared and feature UI components
│       ├── contexts/             # Session, app status, overlay, page runtime contexts
│       ├── features/             # API clients, DTO mappers, frontend domain modules
│       ├── hooks/                # Shared React hooks
│       ├── pages/                # Route-level page components
│       └── test/                 # Frontend Vitest tests and API mocks
├── tests/                        # Backend unittest suite
├── docs/                         # Long-lived product, architecture, dev, ops, and module docs
│   ├── app-architecture/         # Current app runtime/page/read model architecture
│   ├── dev/                      # API contracts, local dev, testing, runtime development
│   ├── modules/turnover-ledger/  # Turnover-ledger module maintenance docs
│   ├── operations/               # Runtime/worker/deploy/monitoring docs
│   └── product-specs/            # Product/business specs
├── deploy/                       # OA deployment assets and environment examples
├── scripts/                      # Start, verify, deploy, and maintenance scripts
└── .planning/codebase/           # Generated codebase maps consumed by GSD planning/execution
```

## Directory Purposes

**`backend/src/fin_ops_platform/app/`:**
- Purpose: HTTP application boundary and thin route/read adapters.
- Contains: `server.py`, feature route adapters, read facades, application entry modules.
- Key files: `backend/src/fin_ops_platform/app/server.py`, `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`, `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`, `backend/src/fin_ops_platform/app/main.py`.

**`backend/src/fin_ops_platform/services/`:**
- Purpose: Business logic, read/query services, write UoWs, repositories/ports, runtime workers, app status registries.
- Contains: turnover relation/ledger services, write facade/UoW/adapters, SQL projection, refresh worker, source versions, runtime registries.
- Key files: `backend/src/fin_ops_platform/services/turnover_ledger_service.py`, `backend/src/fin_ops_platform/services/turnover_relation_service.py`, `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`, `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py`, `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`, `backend/src/fin_ops_platform/services/turnover_ledger_source_versions.py`.

**`backend/src/fin_ops_platform/postgres/`:**
- Purpose: PostgreSQL schema migrations and durable runtime/read model backing structures.
- Contains: migrations relevant to bank detail external turnover labels and settings/jobs.
- Key files: `backend/src/fin_ops_platform/postgres/migrations/0044_bank_detail_external_turnover_third_labels.sql`, `backend/src/fin_ops_platform/postgres/migrations/0005_tax_etc_turnover_settings_jobs.sql`.

**`web/src/pages/`:**
- Purpose: Route-level React screens.
- Contains: page orchestration components that own UI state and call feature API clients.
- Key files: `web/src/pages/TurnoverLedgerPage.tsx`.

**`web/src/components/turnoverLedger/`:**
- Purpose: Turnover-ledger page components.
- Contains: grouped table, extra drawer, export dialog.
- Key files: `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`, `web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx`, `web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx`.

**`web/src/features/turnoverLedger/`:**
- Purpose: Turnover-ledger frontend API client, mapper, and type contract.
- Contains: API request functions, snake_case-to-camelCase mappers, TypeScript DTOs.
- Key files: `web/src/features/turnoverLedger/api.ts`, `web/src/features/turnoverLedger/types.ts`.

**`web/src/features/operationBarrier/`:**
- Purpose: Frontend client for post-write read model freshness waits.
- Contains: barrier target types and polling helpers.
- Key files: `web/src/features/operationBarrier/api.ts`.

**`web/src/features/domainEvents.ts`:**
- Purpose: Same-browser finance domain refresh events.
- Contains: event constants and emit/listen helpers used by turnover-ledger and downstream pages.
- Key files: `web/src/features/domainEvents.ts`.

**`web/src/app/`:**
- Purpose: Frontend routing and page registration.
- Contains: page registry, router, route host.
- Key files: `web/src/app/pageRegistry.tsx`, `web/src/app/router.tsx`, `web/src/app/PageRouteHost.tsx`.

**`tests/`:**
- Purpose: Backend unit, API, UoW, read model, worker, and integration coverage.
- Contains: turnover-specific and cross-module Workbench/App Status tests.
- Key files: `tests/test_turnover_ledger_api.py`, `tests/test_turnover_ledger_uow_contract.py`, `tests/test_turnover_ledger_query_service.py`, `tests/test_turnover_ledger_read_model_refresh.py`, `tests/test_turnover_relation_service.py`, `tests/test_turnover_workbench_integration.py`, `tests/test_workbench_turnover_grouping.py`, `tests/test_runtime_worker_registry.py`.

**`web/src/test/`:**
- Purpose: Frontend component/API/domain event tests and API mocks.
- Contains: turnover page/API tests, domain event tests, shared mock API.
- Key files: `web/src/test/TurnoverLedgerPage.test.tsx`, `web/src/test/TurnoverLedgerApi.test.ts`, `web/src/test/domainEvents.test.ts`, `web/src/test/apiMock.ts`.

**`docs/modules/turnover-ledger/`:**
- Purpose: Module-level maintenance facts for external turnover management.
- Contains: entry doc, state machine, test matrix, implementation notes.
- Key files: `docs/modules/turnover-ledger/README.md`, `docs/modules/turnover-ledger/state-machine.md`, `docs/modules/turnover-ledger/tests.md`, `docs/modules/turnover-ledger/implementation-notes.md`.

**`docs/app-architecture/`:**
- Purpose: Current app runtime/page/read model architecture facts.
- Contains: page relationships, runtime ownership, docs maintenance rules.
- Key files: `docs/app-architecture/README.md`, `docs/app-architecture/pages.md`, `docs/app-architecture/runtime-and-ownership.md`.

**`docs/dev/`:**
- Purpose: API contracts, local development, testing, and runtime development guidance.
- Contains: API contract docs and verification entry points.
- Key files: `docs/dev/api-contracts.md`, `docs/dev/testing.md`, `docs/dev/runtime-development.md`, `docs/dev/index.md`.

**`docs/architecture/backend-refactor/`:**
- Purpose: Backend refactor direction and turnover-ledger discovery/write UoW planning.
- Contains: module refactor plans and turnover-ledger write boundary plans.
- Key files: `docs/architecture/backend-refactor/turnover-ledger-discovery.md`, `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`, `docs/architecture/backend-refactor/module-refactor-plan.md`.

## Key File Locations

**Entry Points:**
- `web/src/app/pageRegistry.tsx`: registers `/turnover-ledger` with page key `turnover-ledger`.
- `web/src/pages/TurnoverLedgerPage.tsx`: primary frontend page entry.
- `backend/src/fin_ops_platform/app/main.py`: backend CLI/application entry for checks and serving.
- `backend/src/fin_ops_platform/app/server.py`: backend HTTP dispatch and turnover handler wiring.

**Configuration / Registries:**
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`: registers worker instance `turnover-ledger`.
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`: registers app status domain `turnover_ledger`.
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`: registers read model `turnover_ledger`.
- `web/src/app/pageRegistry.tsx`: route/page metadata for frontend shell and sidebar derivation.

**Turnover Backend Core Logic:**
- `backend/src/fin_ops_platform/services/turnover_relation_service.py`: relation states, manual closure rules, withdraw rules, audit snapshot.
- `backend/src/fin_ops_platform/services/turnover_ledger_service.py`: ledger/grouped row construction from bank rows, categories, relations, extras, and selected tags.
- `backend/src/fin_ops_platform/services/turnover_ledger_extra_service.py`: persisted extra fields and validation.
- `backend/src/fin_ops_platform/services/bank_turnover_tag_semantics.py`: external turnover tag semantics.

**Turnover Backend Read Path:**
- `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`: read facade boundary.
- `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`: route adapter read methods and grouped compatibility.
- `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`: SQL read model freshness gate.
- `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py`: SQL projection rebuild.
- `backend/src/fin_ops_platform/services/turnover_ledger_source_versions.py`: source version payload.

**Turnover Backend Write Path:**
- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`: write commands and refresh fan-out.
- `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`: transaction/idempotency/dirty-outbox UoW.
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`: request-boundary facades, ports, stale preconditions, Workbench pair port, fallback builders.
- `backend/src/fin_ops_platform/app/server.py`: HTTP handler methods that call the request-boundary facades.

**Turnover Worker / Runtime:**
- `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`: runtime event handler for projection refresh.
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`: worker registration and manifest metadata.
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`: domain-to-worker/read-model relationship.
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`: read model readiness definition.

**Turnover Frontend:**
- `web/src/features/turnoverLedger/api.ts`: API functions and DTO mappers.
- `web/src/features/turnoverLedger/types.ts`: frontend contract types.
- `web/src/pages/TurnoverLedgerPage.tsx`: page logic, pre-write fresh/rebind, operation overlay.
- `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`: grouped ledger table.
- `web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx`: relation extra drawer.
- `web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx`: export preview/download dialog.

**Cross-Module Frontend Impact:**
- `web/src/features/domainEvents.ts`: events `turnoverRelationUpdated`, `workbenchRelationUpdated`, `turnoverLedgerExtraUpdated`.
- `web/src/pages/CostStatisticsPage.tsx`: listens to turnover relation updates.
- `web/src/features/operationBarrier/api.ts`: operation freshness barrier used after turnover writes.

**Testing:**
- `tests/test_turnover_ledger_api.py`: API contracts and request/response behavior.
- `tests/test_turnover_ledger_uow_contract.py`: UoW transaction, idempotency, rollback, dirty/outbox contracts.
- `tests/test_turnover_ledger_query_service.py`: query service freshness/read model behavior.
- `tests/test_turnover_ledger_read_facade.py`: read facade behavior.
- `tests/test_turnover_ledger_read_model_refresh.py`: worker refresh handler/projection behavior.
- `tests/test_turnover_relation_service.py`: business core relation rules.
- `tests/test_turnover_ledger_service.py`: ledger/grouping rules.
- `tests/test_turnover_ledger_extra_service.py`: extra validation/persistence rules.
- `tests/test_turnover_ledger_export_service.py`: export preview/download rows.
- `tests/test_turnover_workbench_integration.py`: manual closure + Workbench relation integration.
- `tests/test_workbench_turnover_grouping.py`: Workbench grouping regression.
- `web/src/test/TurnoverLedgerPage.test.tsx`: page interactions, stale guards, operation overlay, closure fresh/rebind, drawer/export.
- `web/src/test/TurnoverLedgerApi.test.ts`: frontend API mapper contract.
- `web/src/test/domainEvents.test.ts`: frontend domain event contract.

## Naming Conventions

**Files:**
- Backend turnover modules use `snake_case` with prefix `turnover_ledger_` or `turnover_relation_`: `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`.
- Backend route adapters use `routes_<feature>.py`: `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`.
- Frontend route pages use `PascalCasePage.tsx`: `web/src/pages/TurnoverLedgerPage.tsx`.
- Frontend feature API/types use lowercase feature directory plus `api.ts` / `types.ts`: `web/src/features/turnoverLedger/api.ts`.
- Frontend feature components use `PascalCase.tsx` under a feature component directory: `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`.
- Tests mirror feature names: `tests/test_turnover_ledger_api.py`, `web/src/test/TurnoverLedgerPage.test.tsx`.

**Directories:**
- Backend feature/domain code belongs in `backend/src/fin_ops_platform/services/`; HTTP-only mapping belongs in `backend/src/fin_ops_platform/app/`.
- Frontend page orchestration belongs in `web/src/pages/`; reusable feature UI pieces belong in `web/src/components/turnoverLedger/`.
- Frontend API contract code belongs in `web/src/features/turnoverLedger/`.
- Long-lived module facts belong in `docs/modules/turnover-ledger/`.

**Symbols:**
- Backend classes use `PascalCase`: `TurnoverLedgerWriteFacade`, `TurnoverLedgerWriteUnitOfWork`, `TurnoverRelationService`.
- Backend functions/methods use `snake_case`: `confirm_zero_difference_closure`, `rebuild_turnover_ledger_read_model_scope`.
- Backend constants use `UPPER_SNAKE_CASE`: `TURNOVER_LEDGER_REFRESH_EVENT_TYPE`, `TURNOVER_LEDGER_SCOPE_TYPE`.
- Frontend React components use `PascalCase`: `TurnoverLedgerGroupedTable`.
- Frontend functions/hooks use `camelCase`: `fetchTurnoverLedgerGrouped`, `waitForOperationFreshness`.
- Frontend types use `PascalCase`: `TurnoverLedgerGroupedResponse`, `TurnoverRelationMutationResponse`.

## Where to Add New Code

**New Turnover Page Behavior:**
- Primary code: `web/src/pages/TurnoverLedgerPage.tsx`.
- Reusable UI component: `web/src/components/turnoverLedger/`.
- API/client contract: `web/src/features/turnoverLedger/api.ts`, `web/src/features/turnoverLedger/types.ts`.
- Tests: `web/src/test/TurnoverLedgerPage.test.tsx`, `web/src/test/TurnoverLedgerApi.test.ts`.

**New Turnover Read API Field:**
- Backend DTO source: `backend/src/fin_ops_platform/services/turnover_ledger_service.py` or `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py`.
- Read facade/route compatibility: `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`.
- Frontend mapper/type: `web/src/features/turnoverLedger/api.ts`, `web/src/features/turnoverLedger/types.ts`.
- Contract docs: `docs/dev/api-contracts.md`, and if state/UI impact changes, `docs/modules/turnover-ledger/state-machine.md`.
- Tests: `tests/test_turnover_ledger_api.py`, `tests/test_turnover_ledger_query_service.py`, `web/src/test/TurnoverLedgerApi.test.ts`, `web/src/test/TurnoverLedgerPage.test.tsx`.

**New Turnover Business Rule:**
- Primary code: `backend/src/fin_ops_platform/services/turnover_relation_service.py` for relation validity/state changes.
- Ledger presentation: `backend/src/fin_ops_platform/services/turnover_ledger_service.py`.
- Tag semantics: `backend/src/fin_ops_platform/services/bank_turnover_tag_semantics.py` if the rule is category/tag semantics.
- Tests: `tests/test_turnover_relation_service.py`, `tests/test_turnover_ledger_service.py`, and API/UoW tests if exposed through endpoints.

**New Turnover Write Operation:**
- Command/fan-out: `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`.
- Atomic transaction behavior: `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`.
- Ports/request boundaries/stale preconditions: `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`.
- HTTP mapping only: `backend/src/fin_ops_platform/app/server.py` and, if route-adapter method is needed, `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`.
- Frontend call: `web/src/features/turnoverLedger/api.ts`.
- Tests: `tests/test_turnover_ledger_uow_contract.py`, `tests/test_turnover_ledger_api.py`, relevant business service tests, and `web/src/test/TurnoverLedgerPage.test.tsx`.

**New Turnover Read Model Source or Scope:**
- Source version: `backend/src/fin_ops_platform/services/turnover_ledger_source_versions.py`.
- Query/freshness handling: `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`.
- Projection rebuild: `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py`.
- Worker handling: `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`.
- Registry updates: `backend/src/fin_ops_platform/services/runtime_worker_registry.py`, `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`, `backend/src/fin_ops_platform/services/app_status_domain_registry.py`.
- Tests: `tests/test_turnover_ledger_query_service.py`, `tests/test_turnover_ledger_read_model_refresh.py`, `tests/test_runtime_worker_registry.py`, `tests/test_app_status_overview_service.py`.

**New Workbench Interaction From Turnover:**
- Use/extend ports in `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`.
- Keep Workbench command ownership in Workbench relation services; do not write Workbench relation facts directly from `backend/src/fin_ops_platform/app/server.py`.
- Tests: `tests/test_turnover_workbench_integration.py`, `tests/test_workbench_turnover_grouping.py`, `tests/test_turnover_ledger_uow_contract.py`.

**New Operation Overlay / Freshness Target:**
- Backend mutation response target fields: `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py` and request-boundary facade in `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`.
- Frontend target handling: `web/src/pages/TurnoverLedgerPage.tsx`, `web/src/features/operationBarrier/api.ts`.
- Tests: `web/src/test/TurnoverLedgerPage.test.tsx`, `web/src/test/OperationBarrierApi.test.ts`.

**New Domain Event Usage:**
- Event constant/helper: `web/src/features/domainEvents.ts`.
- Active page listener: use `useActiveFinanceDomainEvent` in the affected page, such as `web/src/pages/CostStatisticsPage.tsx`.
- Tests: `web/src/test/domainEvents.test.ts`.
- Rule: domain events are refresh hints only; backend dirty/outbox/read model freshness remains the fact source.

**New Documentation for Turnover Changes:**
- Module docs: `docs/modules/turnover-ledger/README.md`, `docs/modules/turnover-ledger/state-machine.md`, `docs/modules/turnover-ledger/tests.md`.
- Page/runtime architecture docs: `docs/app-architecture/pages.md`, `docs/app-architecture/runtime-and-ownership.md`.
- API contracts: `docs/dev/api-contracts.md`.
- Product/business facts: `docs/product-specs/bank-turnover-and-no-oa.md`.
- Runtime/worker operations: `docs/operations/runtime-worker-governance.md`, `docs/operations/monitoring.md`.

## Special Directories

**`.planning/codebase/`:**
- Purpose: Generated codebase maps for GSD planner/executor.
- Generated: Yes.
- Committed: Project-dependent; update only through mapping tasks.

**`.runtime/`:**
- Purpose: Local runtime data, backups, generated files, and PostgreSQL-related local artifacts.
- Generated: Yes.
- Committed: No for runtime contents; do not use as source of architecture facts.

**`.worktrees/`:**
- Purpose: Local git worktrees for parallel development.
- Generated: Yes.
- Committed: No as project source. Ignore for main-codebase maps unless explicitly scoped.

**`fixtures/`:**
- Purpose: Local manual validation samples.
- Generated: Mixed.
- Committed: Only curated fixtures; automated tests should not depend on real business files.

**`deploy/`:**
- Purpose: OA deployment assets, systemd/env examples, deployment documentation.
- Generated: No for tracked deploy assets; environment files may contain secrets and must not be read if secret-like.
- Committed: Yes for templates/assets, not secrets.

**`docs/`:**
- Purpose: Long-lived facts for product, architecture, development, operations, and module ownership.
- Generated: No for curated docs.
- Committed: Yes.

---

*Structure analysis: 2026-06-15*
