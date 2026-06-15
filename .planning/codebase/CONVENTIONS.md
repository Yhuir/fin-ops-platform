# Coding Conventions

**Analysis Date:** 2026-06-15

## Naming Patterns

**Files:**
- Backend turnover-ledger modules use lowercase snake_case under `backend/src/fin_ops_platform/app/` and `backend/src/fin_ops_platform/services/`: `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`, `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`.
- Backend tests use `tests/test_<area>.py` with turnover-ledger names kept explicit: `tests/test_turnover_ledger_api.py`, `tests/test_turnover_ledger_uow_contract.py`, `tests/test_turnover_ledger_read_model_refresh.py`.
- Frontend feature code uses camelCase feature folders and PascalCase React files: `web/src/features/turnoverLedger/api.ts`, `web/src/features/turnoverLedger/types.ts`, `web/src/pages/TurnoverLedgerPage.tsx`, `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`.
- Frontend tests use PascalCase subject names with `.test.ts` or `.test.tsx`: `web/src/test/TurnoverLedgerApi.test.ts`, `web/src/test/TurnoverLedgerPage.test.tsx`.

**Functions:**
- Python functions and methods use snake_case and keyword-only parameters for service boundaries: `TurnoverLedgerWriteFacade.confirm_zero_difference_closure(...)` in `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`.
- Python route helpers and service adapters keep action names business-specific: `update_relation_extra`, `update_bank_row_tags_batch`, `withdraw_relation`.
- TypeScript functions use camelCase and expose frontend-friendly DTO names: `fetchTurnoverLedgerGrouped`, `saveTurnoverLedgerTagSelection`, `confirmTurnoverClosure` in `web/src/features/turnoverLedger/api.ts`.

**Variables:**
- Backend variables use snake_case and normalize external input before constructing commands: `normalized_bank_row_ids`, `normalized_months`, `normalized_expected_versions` in `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`.
- Frontend API variables use camelCase after mapping from backend snake_case: `selectedTagCodes`, `inactiveSelectedTagCodes`, `turnoverActionType` in `web/src/features/turnoverLedger/api.ts`.
- Test doubles use leading underscore class names in Python tests: `_QueueRecorder`, `_FailingQueueRecorder`, `_RecordingTurnoverLedgerUow` in `tests/test_turnover_ledger_api.py`.

**Types:**
- Python dataclasses use PascalCase and explicit type annotations: `TurnoverLedgerWriteCommand` in `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`.
- TypeScript API wire types use `Api...` prefixes and preserve snake_case field names at the boundary: `ApiTurnoverLedgerGroupedResponse`, `ApiTurnoverLedgerGroupedRow` in `web/src/features/turnoverLedger/api.ts`.
- TypeScript domain/UI types use `Turnover...` names and camelCase fields in `web/src/features/turnoverLedger/types.ts`.

## Code Style

**Formatting:**
- Python code uses standard four-space indentation, `from __future__ import annotations`, dataclasses where useful, and precise imports from `typing`: see `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`.
- TypeScript code uses two-space indentation, semicolons, double quotes, and trailing commas in multiline calls: see `web/src/features/turnoverLedger/api.ts` and `web/src/test/TurnoverLedgerPage.test.tsx`.
- Shell verification uses strict mode with `set -euo pipefail`: `scripts/verify.sh`.

**Linting:**
- No dedicated ESLint/Prettier config was detected in the project root or `web/`.
- TypeScript style is enforced indirectly by `npm run build` running `tsc -b` from `web/package.json`.
- Python style is enforced by conventions and tests rather than a detected Ruff/Black config.

## Import Organization

**Order:**
1. Python future imports, standard library imports, third-party imports, then `fin_ops_platform` imports, as in `tests/test_turnover_ledger_api.py`.
2. TypeScript value imports from libraries, then local context/page imports, then test helpers, as in `web/src/test/TurnoverLedgerPage.test.tsx`.
3. TypeScript type-only imports stay grouped with `import type { ... }` before value imports when mapping API DTOs, as in `web/src/features/turnoverLedger/api.ts`.

**Path Aliases:**
- No frontend path alias is used for turnover-ledger imports; use relative imports such as `../features/turnoverLedger/api` and `../pages/TurnoverLedgerPage`.
- Backend imports use installed package paths from `PYTHONPATH=backend/src`, for example `from fin_ops_platform.services.turnover_ledger_write_facade import TurnoverLedgerWriteFacade`.

## Error Handling

**Patterns:**
- Validate input at the service or route boundary and raise specific errors for invalid business fields. `TurnoverLedgerExtraValidationError` in `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` rejects missing relation ids, invalid decimals, invalid dates, and invalid rate types.
- Writes must fail rather than return best-effort success when dirty/outbox, queue, stale precondition, or command-service dependencies fail. This is protected by `tests/test_turnover_ledger_uow_contract.py` and `tests/test_turnover_ledger_api.py`.
- Stale writes use expected versions and idempotency keys, carried through `TurnoverLedgerWriteCommand.expected_versions`, `idempotency_key`, and `request_fingerprint` in `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`.
- Frontend stale state must block write actions instead of allowing local mutation. The expected behavior is documented in `docs/modules/turnover-ledger/tests.md` and tested in `web/src/test/TurnoverLedgerPage.test.tsx`.

## Logging

**Framework:** console / application-local logging

**Patterns:**
- Turnover-ledger tests emphasize observable API responses, dirty scopes, audit records, and operation barriers rather than asserting logs.
- Do not log secrets or raw environment values. `AGENTS.md` requires logging important failures without exposing sensitive data.
- For turnover-ledger writes, prefer audit/outbox facts over ad hoc log-only signaling: `TurnoverLedgerWriteFacade` in `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py` builds refresh requests that the UoW persists with the write.

## Comments

**When to Comment:**
- Use comments sparingly for contract history or non-obvious test intent. `tests/test_turnover_ledger_uow_contract.py` includes a short module comment explaining PF-P053/PF-P054 target contracts.
- Do not add comments that restate straightforward code. Normalize and validate with readable helper names instead.

**JSDoc/TSDoc:**
- Turnover-ledger frontend code does not rely on JSDoc for API contracts. Use explicit TypeScript types in `web/src/features/turnoverLedger/types.ts` and mapper tests in `web/src/test/TurnoverLedgerApi.test.ts`.

## Function Design

**Size:** Keep new functions focused on one boundary action. Route methods in `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` map HTTP-facing payloads; services in `backend/src/fin_ops_platform/services/` own business or persistence orchestration; frontend API functions in `web/src/features/turnoverLedger/api.ts` map one endpoint at a time.

**Parameters:** Use explicit keyword-only parameters for Python service methods that mutate state, including `actor_id`, `tenant_id`, `affected_months`, `expected_versions`, and `idempotency_key` as applicable. Do not pass the whole `Application` into turnover-ledger services.

**Return Values:** Return dictionaries or typed DTOs that include contract fields needed by the UI and tests. Mutation responses must preserve freshness/visibility fields such as `affected_months`, `freshness_targets`, `relation`, `row`, `extra`, and idempotency results when applicable.

## Module Design

**Exports:** Backend modules expose concrete service/facade classes and dataclasses directly from their files. Frontend modules export named API functions and shared types from `web/src/features/turnoverLedger/api.ts` and `web/src/features/turnoverLedger/types.ts`.

**Barrel Files:** No turnover-ledger barrel file pattern was detected. Import directly from the owning module.

## Backend Boundaries for Turnover-Ledger Work

**Routes and HTTP mapping:**
- Keep HTTP routing in `backend/src/fin_ops_platform/app/server.py` and turnover-specific route helpers in `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`.
- `server.py` should remain route/dependency assembly and HTTP mapping only, per `AGENTS.md`; do not add new business rules or SQL there.

**Business services:**
- Put turnover business rules in `backend/src/fin_ops_platform/services/turnover_relation_service.py`, `backend/src/fin_ops_platform/services/turnover_ledger_service.py`, and `backend/src/fin_ops_platform/services/turnover_ledger_extra_service.py`.
- Preserve rules documented in `docs/modules/turnover-ledger/README.md`: external turnover tag eligibility, same-group real bank flow rows, at least one income and one expense, zero difference, same counterparty/semantic group, manual closure, withdrawal, extra validation, and internal-transfer exclusion.

**Write orchestration:**
- Use `TurnoverLedgerWriteFacade` and `TurnoverLedgerWriteUnitOfWork` for tag-selection, bank-row-tags batch, extra, confirm, and withdraw writes: `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`, `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`.
- Dirty/outbox refresh requests must be in the same write transaction for PostgreSQL-backed writes. Do not write `job.outbox_events` or `job.read_model_dirty_scopes` directly from business services.
- Manual closure and withdraw paths involving Workbench relations must delegate to `WorkbenchRelationCommandService`; missing command service is a fail-fast error, not a fallback to direct pair mutation.

**Read model and worker:**
- Query grouped turnover-ledger reads through `TurnoverLedgerQueryService` and `ReadModelQueryGateway`: `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`.
- Rebuild projection logic belongs in `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py` and `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`.
- Register worker/domain status changes in `backend/src/fin_ops_platform/services/runtime_worker_registry.py`, `backend/src/fin_ops_platform/services/app_status_domain_registry.py`, and `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`.

## Frontend Patterns for Turnover-Ledger Work

**API mapping:**
- Keep snake_case to camelCase conversion in `web/src/features/turnoverLedger/api.ts`; components should consume camelCase domain types from `web/src/features/turnoverLedger/types.ts`.
- Add mapper coverage in `web/src/test/TurnoverLedgerApi.test.ts` whenever endpoint fields, error shapes, or freshness fields change.

**Page and components:**
- Page orchestration belongs in `web/src/pages/TurnoverLedgerPage.tsx`.
- Reusable UI pieces belong in `web/src/components/turnoverLedger/`, including `TurnoverLedgerGroupedTable.tsx`, `TurnoverLedgerExtraDrawer.tsx`, and `TurnoverLedgerExportDialog.tsx`.
- Preserve loading, empty, error, stale, permission-disabled, drawer/dialog, filtering, grouped table, and export states in component tests.

**Operation barrier:**
- tag-selection, extra, manual closure confirm, and withdraw must use `GlobalOperationOverlayProvider` and wait for operation barrier freshness through `web/src/features/operationBarrier/api.ts`.
- Manual closure submit must wait for `turnover_ledger:all` fresh, reload grouped payload, rebind selected flow rows by original bank row ids, submit latest `categoryVersion` expected versions, then wait for backend `freshness_targets` before reload and cross-page refresh events.
- Domain events in `web/src/features/domainEvents.ts` are browser refresh hints only; do not treat `turnoverRelationUpdated`, `workbenchRelationUpdated`, or `turnoverLedgerExtraUpdated` as consistency facts.

## Docs Impact

**Required pre-read:**
- Read `docs/modules/README.md` and `docs/modules/turnover-ledger/README.md` before any turnover-ledger change.
- Also read `docs/modules/turnover-ledger/tests.md` for test scope and `docs/modules/turnover-ledger/state-machine.md` for state/freshness behavior.

**When to update docs:**
- Update `docs/modules/turnover-ledger/README.md`, `docs/modules/turnover-ledger/tests.md`, or `docs/modules/turnover-ledger/state-machine.md` when page behavior, API shape, DTO fields, permissions, read model status, worker/dirty scope behavior, domain events, operation barrier behavior, or validation rules change.
- Update long-term facts only when their facts change: product rules in `docs/product-specs/bank-turnover-and-no-oa.md`, API contract in `docs/dev/api-contracts.md`, runtime/worker operations in `docs/operations/runtime-worker-governance.md`, and app page architecture in `docs/app-architecture/pages.md`.
- For pure internal test refactors or implementation-only fixes with unchanged boundaries, state `docs 不适用` in the final implementation response.

---

*Convention analysis: 2026-06-15*
