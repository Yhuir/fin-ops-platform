# Read Model Invoice Lifecycle Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:invoice-lifecycle-local-implementation-closure-audit`
**Previous state:** `read-models:invoice-lifecycle-derived-lifecycle-executor-port-extraction` was `implementation-closed`.
**Result state:** `production-evidence-deferred`
**Module closure:** `not-module-closed`

## Scope

Audit whether `invoice_lifecycle` local implementation support is accounted for after repository port extraction, freshness/barrier audit and explicit derived lifecycle executor extraction.

This slice is audit/accounting only. It does not change runtime code, invoice lifecycle business rules, payload shape, source-version semantics, worker event semantics, queue schema, API behavior, frontend behavior, Go/Fiber, Go Worker or production state.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-derived-lifecycle-executor-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-refresh-freshness-operation-barrier-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-repository-port-extraction.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/domain-events-lifecycle/README.md`
- `docs/modules/domain-events-lifecycle/implementation-notes.md`
- `docs/modules/domain-events-lifecycle/tests.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `backend/src/fin_ops_platform/services/invoice_lifecycle_read_facade.py`
- `backend/src/fin_ops_platform/services/invoice_lifecycle_read_model_repository.py`
- `backend/src/fin_ops_platform/services/invoice_lifecycle_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/invoice_lifecycle_sql_projection.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `tests/test_invoice_lifecycle_read_facade.py`
- `tests/test_invoice_lifecycle_read_model_refresh.py`
- `tests/test_invoice_lifecycle_derived_lifecycle_executor.py`
- `tests/test_operation_freshness_barrier.py`
- `tests/test_read_model_manifest.py`
- `tests/test_read_model_architecture_guards.py`
- `tests/test_input_invoice_usage_payment_rules.py`
- `tests/test_platform_runtime_boundary_guards.py`

CodeGraph was used before audit edits to inspect invoice lifecycle facade, refresh service, projection builder, repository port, worker and app wiring. Literal scans checked remaining invoice lifecycle references, direct queue SQL writes, app-owned helpers, live fallback terms and state-store exposure.

## Audit Findings

### Query and freshness boundary

- `InvoiceLifecycleReadFacade` remains the query owner.
- Facade reads go through `InvoiceLifecycleReadModelRepositoryPort`.
- `get_by_subject_ids(...)` and `get_by_invoice_identity_keys(...)` return non-fresh when rows or repository methods are unavailable and enqueue through `ReadModelRefreshGateway`.
- `list_by_month(...)` requires a concrete month; there is no page-facing queryable `invoice_lifecycle:all` read path.
- The only `read_model_status=fresh` repository lookups are classified in `tests/test_read_model_architecture_guards.py` as materialized fact lookups used by downstream freshness facades.

### Refresh, worker and all-scope behavior

- `InvoiceLifecycleReadModelRefreshService` rejects `Application` fallback dependencies.
- Worker wiring builds `InvoiceLifecycleSqlProjectionBuilder` and injects `RuntimeQueueRepository` into `InvoiceLifecycleReadModelRefreshService`.
- Non-month scopes such as `all` are fan-out commands. The refresh service lists month shards, enqueues concrete shards through `ReadModelRefreshGateway`, completes the original scope and does not publish a fake queryable parent `all` freshness proof.
- Source-version currentness is checked before and after rebuild before dirty scope completion.

### Repository and SQL ownership

- `InvoiceLifecycleReadModelRepositoryPort` exposes only manifest-listed lifecycle read-model methods.
- `InvoiceLifecycleSqlProjectionBuilder` uses the narrow port for lifecycle save/mark paths.
- `PostgresReadModelRepository` remains the SQL/table owner for `read_model.invoice_lifecycle_rows` and `read_model.invoice_lifecycle_scopes`.
- No `PostgresStateStore.invoice_lifecycle_sql_read_repository` property exists or is needed because no caller exists; avoiding a speculative state-store property remains correct.

### App/server helper and legacy contamination

- `Application._derived_lifecycle_invoice_lifecycle_executor(...)` has been removed and is guarded from returning.
- `Application._invoice_lifecycle_derived_lifecycle_executor(...)` is dependency assembly only; it builds `InvoiceLifecycleDerivedLifecycleExecutor` and injects a callback to `_enqueue_generic_read_model_refreshes("invoice_lifecycle", ...)`.
- `_enqueue_generic_read_model_refreshes(...)` uses `ReadModelRefreshGateway`; it does not directly SQL-write `job.outbox_events` or `job.read_model_dirty_scopes`.
- `_enqueue_input_invoice_usage_payment_rules_refreshes(...)` legitimately fans out `invoice_lifecycle:all` after payment-status rules change and is covered by `tests/test_input_invoice_usage_payment_rules.py`.
- Import-state changed scheduling legitimately fans out invoice lifecycle refresh after import state mutation; it also uses the generic gateway-backed helper.
- No remaining app-owned invoice lifecycle implementation helper was found that requires extraction before local closure/defer accounting.

### Manifest, operation barrier and deployment registration

- `read_model_manifest.py` registers `invoice_lifecycle` with `scope_type="invoice_lifecycle"`, event `invoice_lifecycle.read_model.refresh`, primary worker `invoice-lifecycle`, auxiliary worker `invoice-lifecycle-secondary`, `gateway_force_refresh`, `app_status_registry_target` and the expected repository port contract.
- `runtime_worker_registry.py`, deploy env examples and RabbitMQ dispatcher examples include the invoice lifecycle worker/event registrations.
- `tests/test_operation_freshness_barrier.py` proves an exact month lifecycle target is not blocked by another month pending outbox.

## Closure Decision

Local implementation support is accounted for after:

- repository port extraction
- freshness/force-refresh/operation-barrier audit
- explicit derived lifecycle executor extraction
- worker/manifest/App Status registration evidence
- legacy/app-owned helper classification
- targeted unit/static/manifest/barrier tests

The module is **not globally closed** because real PostgreSQL/worker/App Status/high-row/browser evidence is unavailable in the current environment. The correct state is `production-evidence-deferred`, with `Module Closure = not-module-closed`.

## State-Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/domain-events-lifecycle/state-machine.md`

No workflow, module, business, read model or worker state definition changed. This slice advances one queue item:

- `read-models:invoice-lifecycle-local-implementation-closure-audit`: `pending` -> `production-evidence-deferred`
- Module closure is `not-module-closed`
- Next boundary becomes `read-models:next-pilot-selection-after-invoice-lifecycle`
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`

## Seven Test Categories

1. Business core unit tests: not applicable. This audit changes no lifecycle policy or business rule.
2. Service-layer tests: applicable as evidence through invoice lifecycle facade, refresh and derived executor tests; no new service code changed in this slice.
3. API contract tests: not applicable. No HTTP behavior changed.
4. Read model/cache/background job tests: applicable as evidence through invoice lifecycle refresh, manifest and operation barrier tests; no new read model behavior changed in this slice.
5. Frontend component and interaction tests: not applicable. No frontend behavior changed.
6. End-to-end business-flow integration tests: not required for this audit-only slice; existing page integration and derived lifecycle tests remain the referenced evidence.
7. Existing feature regression tests: applicable as evidence through previously run invoice lifecycle, operation barrier, manifest, input usage payment-rules and static guard tests.

## Verification

This slice is documentation/accounting only. Runtime targeted tests were not rerun because no runtime code changed after commit `c415c04b`; the audit references the already recorded executor/facade/refresh/barrier/manifest tests from the immediately preceding implementation slices.

Required verification for this slice:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Remaining Risk

- No local `PGSQL_URL` or staging database is available, so real PostgreSQL worker/readiness/App Status/high-row/browser evidence remains unavailable.
- Historical operations docs still show invoice lifecycle worker latency/queue long-tail observations; performance optimization remains a later Go/admission topic after more module IO contracts are stable.
- `invoice_lifecycle` is not globally closed.

## Next Boundary

`read-models:next-pilot-selection-after-invoice-lifecycle`
