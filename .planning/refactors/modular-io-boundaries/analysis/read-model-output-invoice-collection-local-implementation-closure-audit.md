# Read Model Output Invoice Collection Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:output-invoice-collection-local-implementation-closure-audit`
**Previous state:** `read-models:output-invoice-collection-relation-detail-production-repository-fail-closed` was `implementation-closed`.
**Result state:** `production-evidence-deferred`
**Module closure:** `not-module-closed`

## Scope

This slice accounts for local `output_invoice_collection` implementation support after the repository port, freshness/operation-barrier, app-level helper removal and relation-detail fail-closed slices.

This slice does not change runtime behavior. It does not claim global `output_invoice_collection` module closure because real PostgreSQL worker drain, App Status readiness, high-row HTTP/browser performance and production browser smoke evidence remain unavailable without local `PGSQL_URL`, staging database or approved production mutation.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-repository-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-refresh-freshness-operation-barrier-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-relation-detail-production-repository-fail-closed.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-input-invoice-usage.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/output-invoice-collections/README.md`
- `docs/modules/output-invoice-collections/state-machine.md`
- `docs/modules/output-invoice-collections/tests.md`
- `docs/modules/output-invoice-collections/implementation-notes.md`
- `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_read_model_detail_service.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_read_model_repository.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_service.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `tests/test_output_invoice_collection_api.py`
- `tests/test_invoice_usage_collection_sql_runtime.py`
- `tests/test_read_model_architecture_guards.py`
- `tests/test_read_model_manifest.py`
- `web/src/test/OutputInvoiceCollectionsPage.test.tsx`

CodeGraph was used before this accounting edit to inspect the output invoice collection read model / worker / projection surface. Literal searches then confirmed the remaining helper and detail references are either real worker/projection owners, tests, docs or the retained legacy/local detail query path.

## Accounting Result

### Repository Port

`OutputInvoiceCollectionReadModelRepositoryPort` is present and wired into PostgreSQL state-store reads and invoice usage collection projection save/mark/prune behavior. The manifest and tests require the output port to expose output-only methods, including `get_output_invoice_collection_row_by_row_id(...)` for detail rows, while excluding input usage, OA pending payment, pending invoice and Workbench relation source-version methods.

### Fresh Gates

Rows, filter options and export are fresh-gated by the output collection SQL read-model path. Missing repository, missing payload, schema stale, refresh status not fresh or source-version mismatch all enqueue `output_invoice_collection` refresh and return refreshing instead of returning stale rows as fresh.

Relation detail is now fresh-gated through `OutputInvoiceCollectionReadModelDetailService` in production SQL runtime. Missing SQL repository or missing detail lookup returns `202`/refreshing and enqueues `output_invoice_collection:all`; fresh SQL detail rows return the same relation-detail payload shape without calling the live query service.

### Source-Version Proof

`output_invoice_collection_source_versions()` remains the output collection expected source-version contract. Month-scoped Workbench relation source versions are added for concrete month scopes. The all-scope path remains a fan-out/query aggregate path and does not use global `workbench_relation:all` source versions as a false stale trigger.

### Scope Policy And Worker Fan-Out

`output_invoice_collection` is registered as month-or-all in `read_model_scope_policy.py`. `output_invoice_collection:all` remains a control scope that expands to concrete month shards through `InvoiceUsageCollectionReadModelRefreshService` and `InvoiceUsageCollectionSqlProjectionBuilder`.

Projection rebuild/list/mark/prune behavior is owned by `InvoiceUsageCollectionSqlProjectionBuilder` and the shared invoice-usage-collection worker family, not by `Application`.

### Operation Barrier

Lifecycle, reminder, red/blue relation and receipt mutations return `read_model_scope_keys` and `freshness_targets`. Frontend write-after-read flows prefer concrete month `output_invoice_collection:<YYYY-MM>` targets over fan-out-only `all` when concrete targets are available.

### Legacy / Live Path Classification

- `removed`: `Application.list_output_invoice_collection_scope_shards(...)`, `Application.mark_output_invoice_collection_scope_empty(...)` and `Application.rebuild_output_invoice_collection_read_model_scope(...)`.
- `implemented`: production SQL runtime rows/filter/export/detail fresh gates and refreshing/enqueue behavior.
- `compat-only`: `OutputInvoiceCollectionQueryService.row_relation_details(...)` remains for legacy/local non-production SQL runtime fallback. It must not write canonical facts, dirty scopes, outbox events, readiness, cache, App Status or new authoritative outputs.
- `out of read-model scope`: lifecycle fact writes, receipt numbering/history and red/blue relation business semantics remain owned by lifecycle/receipt services and were not changed in this accounting slice.

No new local implementation gap was found that must block the next non-Go read model pilot selection.

## State-Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/output-invoice-collections/state-machine.md`

No global or module state definition changed. This slice changes accounting only:

- `read-models:output-invoice-collection-local-implementation-closure-audit` moves from `pending` to `production-evidence-deferred`.
- `output_invoice_collection` remains `not-module-closed`; global closure is not claimed.
- Real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- Next boundary becomes `read-models:next-pilot-selection-after-output-invoice-collection`.
- Go hot-path admissions remain `blocked-by-prerequisite`.

## Seven Test Categories

1. Business core unit tests: not applicable for this accounting-only slice. No receipt, collection status, red/blue relation, status rule, amount or lifecycle business rule changed.
2. Service-layer tests: covered by prior output collection lifecycle, read-model detail service and repository port tests; no new service code changed.
3. API contract tests: covered by prior output collection rows and relation-detail fail-closed tests; no API shape changed.
4. Read model/cache/background job tests: covered by prior invoice usage collection SQL runtime, projection builder, manifest and architecture guard tests; no worker/cache behavior changed.
5. Frontend component and interaction tests: covered by prior OutputInvoiceCollectionsPage operation-barrier tests; no frontend behavior changed.
6. End-to-end business-flow integration tests: not newly applicable for this accounting-only slice. Existing Browser flows remain the current coverage, while real production worker drain remains deferred.
7. Existing feature regression tests: covered by prior output API/service/lifecycle/read-model regression tests; this slice only records closure accounting.

## Verification Plan

Because this slice changes only planning and module docs:

```bash
bash scripts/verify.sh docs
git diff --check
```

Runtime backend/frontend tests are not rerun in this slice because no runtime code or test code changed.

## Remaining Risks

- No local `PGSQL_URL` or staging database, so real PostgreSQL dirty/outbox/readiness and worker drain are not proved.
- No production write was performed; production evidence remains deferred.
- No high-row HTTP SLO, real browser performance or production App Status evidence is produced by this local accounting slice.
- `output_invoice_collection` is not globally closed; it is only locally accounted enough to continue to next non-Go pilot selection.

## Next Boundary

`read-models:next-pilot-selection-after-output-invoice-collection`
