# Read Model Turnover Ledger Freshness Barrier Audit

**Date:** 2026-06-24
**Boundary:** `read-models:turnover-ledger-refresh-freshness-operation-barrier-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`read-models:turnover-ledger-repository-port-extraction` implemented the narrow repository port and moved app query injection plus worker projection paths to that port. This audit checks whether turnover freshness, force refresh, operation barrier and legacy read/write contamination are sufficiently accounted for.

## Evidence Reviewed

- `TurnoverLedgerQueryService`
- `TurnoverLedgerReadModelRefreshService`
- `TurnoverLedgerSqlProjectionBuilder`
- `read_model_scope_policy.py`
- `read_model_manifest.py`
- `app_status_read_model_registry.py`
- `runtime_worker_registry.py`
- `Application._enqueue_turnover_ledger_read_model_refreshes(...)`
- `Application._clear_turnover_ledger_read_model_best_effort(...)`
- turnover API/UoW/read model refresh tests
- operation freshness barrier tests

## Local Support Evidence

- Query fresh gate: `TurnoverLedgerQueryService` reads SQL payload through `ReadModelQueryGateway` for `turnover_ledger:all`, checks expected source versions and enqueues refresh on miss/stale/source mismatch.
- Force refresh / scope policy: `DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY` registers `turnover_ledger` as `month_or_all`, so gateway-backed refresh calls normalize/validate month/all scopes.
- Worker / App Status registry: `turnover_ledger` exists in manifest, App Status read model registry and runtime worker registry with `turnover_ledger.read_model.refresh` and primary worker `turnover-ledger`.
- Projection source-version proof: `TurnoverLedgerSqlProjectionBuilder` refuses to save when Workbench relation context is not fresh, adds Workbench relation source versions to turnover source versions when available, and saves via the narrow port.
- Operation barrier proof: `OperationFreshnessBarrierService` blocks `turnover_ledger:all` when the current outbox event is failed even if readiness is fresh.
- Write response targets: turnover closure request boundary returns hard freshness targets for `turnover_ledger:all` and affected-month `workbench_relation` scopes.

## Implementation Gap

This audit cannot move `turnover_ledger` to local closure accounting.

Remaining app-owned helper contamination:

- `Application._enqueue_turnover_ledger_read_model_refreshes(...)` still owns turnover refresh producer behavior. It manually filters scopes before calling `ReadModelRefreshGateway.enqueue_many(...)` instead of being an explicit turnover producer boundary.
- `Application._clear_turnover_ledger_read_model_best_effort(...)` still clears turnover read model rows through broad `_workbench_sql_read_repository` instead of the turnover-specific repository port.
- Bank detail and turnover mutation wiring still receive these app helpers as callbacks, so old clear/refresh behavior remains coupled to `Application`.

The next boundary must extract this clear/refresh behavior behind an explicit turnover read model producer/maintenance port and wire callers to that boundary. It should preserve existing API/business behavior and keep non-transactional refresh behind `ReadModelRefreshGateway`.

## Seven-Category Test Decision

1. Business core unit tests: not applicable; this audit changes no turnover business rules.
2. Service-layer tests: applicable for the next implementation boundary; it must cover the new producer/clear boundary.
3. API contract tests: not applicable for this analysis slice; next implementation should add API tests only if response shape or error behavior changes.
4. Read model/cache/background job tests: applicable; existing turnover query/refresh tests are evidence, and next implementation should extend guards around refresh/clear producer behavior.
5. Frontend component and interaction tests: not applicable; no frontend behavior changed.
6. End-to-end business-flow integration tests: not applicable for analysis; implementation should avoid changing confirm/withdraw/tag-selection flows.
7. Existing feature regression tests: applicable; next implementation must guard that app-owned clear/enqueue helpers do not return as authoritative behavior.

## State Impact

- Queue item `142` moves to `analysis-closed`.
- Insert next boundary: `read-models:turnover-ledger-refresh-producer-clear-port-extraction`.
- `turnover_ledger` remains `implementation-gap-open`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Analysis-only slice. Required verification after documentation/state updates:

- `bash scripts/verify.sh docs`
- `git diff --check`

## Next Boundary

`read-models:turnover-ledger-refresh-producer-clear-port-extraction`
