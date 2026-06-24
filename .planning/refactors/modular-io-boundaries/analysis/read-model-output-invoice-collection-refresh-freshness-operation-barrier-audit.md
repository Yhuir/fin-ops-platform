# Read Model Output Invoice Collection Freshness / Operation Barrier Audit

**Date:** 2026-06-24
**Boundary:** `read-models:output-invoice-collection-refresh-freshness-operation-barrier-audit`
**Previous state:** `read-models:output-invoice-collection-repository-port-extraction` was `implementation-closed`.
**Result state:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Scope

This slice audited and closed the local freshness, force-refresh, all fan-out, operation-barrier and app-level projection-helper boundary for `output_invoice_collection`.

The slice did not attempt full `output_invoice_collection` module closure. Real PostgreSQL worker drain, App Status readiness, high-row HTTP SLO and browser smoke evidence remain unavailable in the current no-staging/no-local-`PGSQL_URL` environment.

## Evidence Reviewed

- `docs/modules/output-invoice-collections/README.md`
- `docs/modules/output-invoice-collections/state-machine.md`
- `docs/modules/output-invoice-collections/tests.md`
- `docs/modules/output-invoice-collections/implementation-notes.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `backend/src/fin_ops_platform/services/output_invoice_collection_read_model_repository.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_lifecycle_service.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_receipt_service.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_models.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
- `web/src/pages/OutputInvoiceCollectionsPage.tsx`
- `web/src/features/outputInvoiceCollections/api.ts`
- `web/src/components/outputInvoiceCollections/*`
- `tests/test_invoice_usage_collection_sql_runtime.py`
- `tests/test_output_invoice_collection_api.py`
- `tests/test_output_invoice_collection_lifecycle.py`
- `tests/test_read_model_architecture_guards.py`
- `web/src/test/OutputInvoiceCollectionsPage.test.tsx`

CodeGraph was used before edits to inspect the output collection freshness and projection-helper surface. Literal search confirmed the real worker/backfill paths depend on `InvoiceUsageCollectionSqlProjectionBuilder`, while the `Application` output projection helpers had no production callers.

## Findings

### Fresh Gates

- Rows, filter options and export continue to be fresh-gated through the output collection SQL read model path.
- Stale/missing/source-version mismatch remains `202`/refreshing and enqueue-backed; no live rows are returned as fresh.
- Relation detail remains a route-level live relation detail path and is not converted in this slice. It requires output collection read-session permission and does not publish or cache read model freshness. It should remain visible in the next local closure audit.

### Force Refresh / All Fan-Out

- `output_invoice_collection:all` remains a fan-out control scope.
- Worker expansion and backfill all-scope expansion continue to use `InvoiceUsageCollectionSqlProjectionBuilder.list_output_invoice_collection_scope_shards(...)`.
- Projection save/mark/prune paths remain on the `OutputInvoiceCollectionReadModelRepositoryPort` added in the prior slice.

### Operation Barrier

Concrete gap found:

- Lifecycle and receipt mutation routes committed facts and enqueued refresh, but responses did not include a stable `read_model_scope_keys` / `freshness_targets` contract.
- The frontend therefore fell back to the current visible query scope. On the default all-view this could wait on fan-out-only `all` instead of the concrete affected month, allowing cross-page stale-read bugs to survive.

Fix:

- Added `output_invoice_collection_freshness_metadata(row)` to generate the affected `output_invoice_collection:<YYYY-MM|all>` target.
- `OutputInvoiceCollectionLifecycleService` now returns freshness metadata for status, reminder, red/blue relation confirm and revoke.
- `OutputInvoiceCollectionReceiptService` now returns freshness metadata for create, void and reissue.
- Frontend API mapping now preserves mutation freshness metadata.
- `OutputInvoiceCollectionsPage` and related drawers now pass mutation response targets to the operation barrier and prefer concrete month scopes over fan-out-only `all`.

`revoke_red_invoice_relation(...)` remains `all` because the current service route deletes by relation id without a row/month lookup and enqueues `all`. Returning a concrete month here would lie about the actual enqueue scope.

### Legacy / App-Level Helper Classification

Removed from `Application`:

- `list_output_invoice_collection_scope_shards(...)`
- `mark_output_invoice_collection_scope_empty(...)`
- `rebuild_output_invoice_collection_read_model_scope(...)`

Classification:

- `removed`: no production callers found; the real worker/backfill/projection path uses `InvoiceUsageCollectionSqlProjectionBuilder`.
- Forbidden writes: old app-level helpers must not write read-model rows, scope status, dirty scopes, outbox events, readiness, cache, App Status or canonical facts.
- Deletion condition: satisfied by no production caller evidence plus architecture guard coverage.

Guard:

- `ReadModelArchitectureGuardTests.test_output_invoice_collection_app_level_projection_helpers_do_not_return` prevents these helpers from returning to `server.py`.

## State-Machine Impact

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md` reviewed; no global state definition change is required.
- `docs/modules/output-invoice-collections/state-machine.md` updated with the mutation response freshness contract and app-level helper removal.
- `autonomous/MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `prompts/04-master-goal-controller.md` must record this boundary as `implementation-closed`.

## Seven Test Categories

1. Business core unit tests: applicable. Lifecycle/receipt semantics are protected by existing and updated lifecycle tests; no business rule change was made.
2. Service-layer tests: applicable. Updated lifecycle tests assert mutation responses carry concrete freshness metadata while preserving enqueue scope.
3. API contract tests: applicable. Updated output collection API tests assert mutation routes return `read_model_scope_keys` and `freshness_targets`.
4. Read model/cache/background job tests: applicable. Existing invoice usage collection SQL runtime tests protect builder fan-out/save/mark/prune; architecture guard prevents removed app-level projection helpers from returning.
5. Frontend component and interaction tests: applicable. Updated page tests assert red relation and receipt creation wait on concrete `2026-05` operation barrier targets before reloading.
6. End-to-end business-flow integration tests: partially applicable. This slice did not run browser E2E; existing E2E covers output collection lifecycle flows, while operation-barrier target specificity is covered by Vitest.
7. Existing feature regression tests: applicable. Targeted API, lifecycle, architecture and frontend tests preserve previous lifecycle/receipt/red relation behavior while adding freshness metadata.

## Verification

Verification executed during the slice:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/output_invoice_collection_models.py backend/src/fin_ops_platform/services/output_invoice_collection_lifecycle_service.py backend/src/fin_ops_platform/services/output_invoice_collection_receipt_service.py tests/test_output_invoice_collection_lifecycle.py tests/test_output_invoice_collection_api.py tests/test_read_model_architecture_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards.ReadModelArchitectureGuardTests.test_output_invoice_collection_app_level_projection_helpers_do_not_return tests.test_output_invoice_collection_lifecycle.OutputInvoiceCollectionLifecycleTests.test_manual_status_and_reminder_overlay_rows_and_enqueue_month_scope tests.test_output_invoice_collection_lifecycle.OutputInvoiceCollectionLifecycleTests.test_receipts_are_idempotent_and_history_is_real tests.test_output_invoice_collection_api.OutputInvoiceCollectionApiTests.test_lifecycle_write_routes_overlay_rows_and_create_real_receipt_history -v
cd web && npm test -- --run src/test/OutputInvoiceCollectionsPage.test.tsx -t "waits for output invoice collection barrier"
cd web && npm run build
PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_lifecycle tests.test_output_invoice_collection_api tests.test_read_model_architecture_guards -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
cd web && npm test -- --run src/test/OutputInvoiceCollectionsPage.test.tsx
bash scripts/verify.sh docs
git diff --check
```

## Remaining Risks

- No local `PGSQL_URL` or staging database, so real PostgreSQL dirty/outbox/readiness and worker drain are not proved.
- No production write was performed; production evidence remains deferred.
- Output collection local implementation closure still requires a separate accounting slice before selecting another pilot or Go candidate.
- Relation detail remains a route-level read-session live detail path and must be explicitly accounted for in the local closure audit.

## Next Boundary

`read-models:output-invoice-collection-local-implementation-closure-audit`
