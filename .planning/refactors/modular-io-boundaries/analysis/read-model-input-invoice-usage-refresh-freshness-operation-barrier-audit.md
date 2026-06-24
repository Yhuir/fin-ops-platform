# Read Model Input Invoice Usage Freshness / Operation Barrier Audit

**Date:** 2026-06-24
**Boundary:** `read-models:input-invoice-usage-refresh-freshness-operation-barrier-audit`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit `input_invoice_usage` freshness, force-refresh, `all` fan-out, source-version proof, operation barrier and retained app-level helper surfaces after repository port extraction. Remove concrete legacy contamination only when call graph and tests prove the old path is unused.

This slice does not change API response shape, read model schema, worker event type, OA reverse workflow, target OA applicant credentials/token behavior, Workbench relation command behavior, payment status business rules, frontend behavior, Go/Fiber/Go Worker admission, or production state.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-input-invoice-usage-repository-port-extraction.md`
- `docs/modules/read-models/README.md`
- `docs/modules/input-invoice-usage/README.md`
- `docs/modules/input-invoice-usage/state-machine.md`
- `docs/modules/input-invoice-usage/tests.md`
- `backend/src/fin_ops_platform/services/input_invoice_usage_read_model_repository.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `web/src/pages/InputInvoiceUsagePage.tsx`
- `tests/test_invoice_usage_collection_sql_runtime.py`
- `tests/test_input_invoice_usage_api.py`
- `tests/test_read_model_architecture_guards.py`

CodeGraph was used before editing:

- `_get_input_invoice_usage_rows_from_sql_read_model(...)` is the SQL rows fresh gate in `Application`.
- `_get_input_invoice_usage_all_rows_from_sql_read_model(...)` delegates to the paged fresh-gated all-rows helper.
- `_enqueue_input_invoice_usage_read_model_refresh(...)` is called by SQL miss/stale/source-version paths, payment-rule invalidation, OA reverse invalidation and shared invoice-usage collection invalidation.
- `Application.rebuild_input_invoice_usage_read_model_scope(...)`, `Application.list_input_invoice_usage_scope_shards(...)` and `Application.mark_input_invoice_usage_scope_empty(...)` have no production callers. The active worker path uses `InvoiceUsageCollectionReadModelRefreshService` with `InvoiceUsageCollectionSqlProjectionBuilder`.

## Audit Findings

### Fresh Gate

`Application._get_input_invoice_usage_rows_from_sql_read_model(...)` remains the route-level SQL fresh gate:

- missing SQL repository in production SQL runtime returns `read_model_status=refreshing` and enqueues `api_sql_repository_unavailable`;
- repository miss enqueues `api_miss`;
- schema shape mismatch enqueues `api_schema_stale`;
- non-fresh `refresh_status` enqueues `api_stale`;
- source-version mismatch enqueues `api_source_versions_stale`;
- only fresh payloads receive `read_model_status=fresh`.

`_get_input_invoice_usage_all_rows_from_sql_read_model(...)` still pages through the same rows gate and returns `fresh` only when every page is fresh. Filter options and export continue to derive from this all-rows path.

### Source-Version Proof

`_input_invoice_usage_expected_source_versions(scope_key=...)` still builds the input usage base source versions and adds scoped `workbench_relation_source_versions` only for concrete month scopes. For `all`, `_workbench_relation_source_versions_from_repository(...)` returns `{}`, preserving the documented rule that all-query freshness is proven by child month rows/scopes and active dirty/outbox state, not by global `workbench_relation:all`.

### Scope Policy / Force Refresh

`ReadModelScopePolicyRegistry` registers `input_invoice_usage` with the month-or-all policy. Non-transactional refresh requests continue through `ReadModelRefreshGateway`, which applies scope policy normalization/validation/dedupe before durable queue enqueue.

### Worker Fan-Out / Month Proof

`InvoiceUsageCollectionReadModelRefreshService` treats non-month scopes, including `all`, as expansion scopes for `input_invoice_usage.read_model.refresh`. It delegates month discovery to `InvoiceUsageCollectionSqlProjectionBuilder.list_input_invoice_usage_scope_shards(...)`, prunes old month shards through `prune_input_invoice_usage_scope_shards(...)`, marks empty scopes through `mark_input_invoice_usage_scope_empty(...)`, enqueues concrete month shards through `ReadModelRefreshGateway.enqueue_many(...)`, and completes the parent dirty scope.

The active builder path is the owner for rebuild/list/mark/prune behavior.

### Operation Barrier

`InputInvoiceUsagePage` still waits for `operationBarrierTargets("input_invoice_usage", [query.month || "all"])` after payment status rule saves and OA reverse batch changes before reloading rows. Existing tests cover that rows are not reloaded until the barrier resolves.

This slice did not change frontend target selection. `input_invoice_usage` still differs from OA pending payment: mutation responses currently do not expose a concrete month-plus-all target list to choose from, so the current visible query scope remains the frontend target.

### Legacy Helper Classification

| Surface | Classification | Decision |
| --- | --- | --- |
| `Application.list_input_invoice_usage_scope_shards(...)` | removed | No production callers; active fan-out owner is `InvoiceUsageCollectionSqlProjectionBuilder`. |
| `Application.mark_input_invoice_usage_scope_empty(...)` | removed | No production callers; active empty-scope owner is `InvoiceUsageCollectionSqlProjectionBuilder` with `InputInvoiceUsageReadModelRepositoryPort`. |
| `Application.rebuild_input_invoice_usage_read_model_scope(...)` | removed | No production callers; it performed app-level live query rebuild/save outside the active worker builder boundary. |
| `Application._get_input_invoice_usage_rows_from_sql_read_model(...)` | retained route fresh gate | It is still the current HTTP SQL read-model fresh gate and enqueues through `ReadModelRefreshGateway`. |
| `Application._get_input_invoice_usage_all_rows_from_sql_read_model(...)` | retained route fresh gate | It only returns fresh after every paged rows payload is fresh. |
| `Application._get_input_invoice_usage_relation_details_from_sql_read_model(...)` | retained route detail fresh gate | It delegates to `InputInvoiceUsageReadModelDetailService` and uses gateway-backed refresh enqueue. |
| `Application._enqueue_input_invoice_usage_read_model_refresh(...)` | retained gateway-backed wrapper | It is a thin app-level wrapper around `ReadModelRefreshGateway.enqueue_one(...)`. |
| `Application._input_invoice_usage_expected_source_versions(...)` | retained source-version helper | Current route fresh gates depend on it; local closure accounting should later decide whether to move it to a service/provider. |
| `Application._invalidate_input_invoice_usage_oa_reverse_read_models(...)` | retained mutation side-effect wrapper | It enqueues through the gateway-backed wrapper and persists Workbench pair relations; broader OA reverse side-effect ownership remains outside this slice. |

## Implementation

Removed unused app-level projection helpers from `backend/src/fin_ops_platform/app/server.py`:

- `Application.list_input_invoice_usage_scope_shards(...)`
- `Application.mark_input_invoice_usage_scope_empty(...)`
- `Application.rebuild_input_invoice_usage_read_model_scope(...)`

Added `tests/test_read_model_architecture_guards.py::ReadModelArchitectureGuardTests.test_input_invoice_usage_app_level_projection_helpers_do_not_return` to prevent these old helpers from returning.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/input-invoice-usage/state-machine.md`

No state definition changes are required. This slice removes unused Application-level helper code and records freshness/barrier evidence; it does not change business, UI, read model or worker state definitions.

Transition:

- Previous queue item: `read-models:input-invoice-usage-refresh-freshness-operation-barrier-audit`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:input-invoice-usage-local-implementation-closure-audit`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Category Decision

1. Business core unit tests: not directly applicable; payment status rules, OA reverse state, relation semantics and invoice lifecycle rules are unchanged.
2. Service-layer tests: applicable as architecture/service-boundary guard; added a static guard proving app-level projection helpers do not return.
3. API contract tests: applicable as regression; existing input usage API tests continue to cover rows/detail/filter/export freshness and response shape. No API shape changed.
4. Read model/cache/background job tests: applicable; existing invoice-usage collection SQL runtime tests cover all-scope fan-out, source-version mismatch, projection save/mark/prune, orphan shard cleanup and refresh handler behavior. This slice adds a guard against the removed app-level projection helper returning.
5. Frontend component and interaction tests: not directly applicable; no frontend behavior or operation barrier target selection changed.
6. End-to-end business-flow integration tests: not directly applicable for unused helper removal; OA reverse and payment-rule flows are unchanged.
7. Existing feature regression tests: applicable; targeted architecture guard plus existing input usage runtime/API coverage preserve current boundaries.

## Verification

Verification run for this slice:

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_read_model_architecture_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards.ReadModelArchitectureGuardTests.test_input_invoice_usage_app_level_projection_helpers_do_not_return -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_refresh_handler_expands_all_scopes_and_completes_with_source_version tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_prunes_invoice_usage_collection_scope_shards tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_all_scope_uses_rows_when_month_relation_versions_differ tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_relation_details_use_input_invoice_usage_read_model_row_without_live_rebuild -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only the input usage freshness/barrier/helper audit and unused app-level projection helper removal slice is closed. `input_invoice_usage` remains implementation-gap-open because local closure/defer accounting, production PostgreSQL/worker/App Status/high-row/browser evidence, and any future service/provider ownership migration still need later slices.
