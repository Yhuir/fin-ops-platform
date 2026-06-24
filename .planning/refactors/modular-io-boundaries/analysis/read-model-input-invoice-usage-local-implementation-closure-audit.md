# Read Model Input Invoice Usage Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:input-invoice-usage-local-implementation-closure-audit`
**Slice status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`

## Goal

Audit whether the `input_invoice_usage` read model pilot has remaining local non-Go implementation gaps after repository port extraction, freshness/operation-barrier audit, unused app-level projection helper removal, and the relation-detail production fail-closed fix.

This slice does not change runtime code. It closes only local implementation accounting for the current pilot and records production evidence as deferred.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-input-invoice-usage-repository-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-input-invoice-usage-refresh-freshness-operation-barrier-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-input-invoice-usage-relation-detail-production-repository-fail-closed.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/input-invoice-usage/README.md`
- `docs/modules/input-invoice-usage/state-machine.md`
- `docs/modules/input-invoice-usage/tests.md`
- `docs/modules/input-invoice-usage/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/input_invoice_usage_read_model_repository.py`
- `backend/src/fin_ops_platform/services/input_invoice_usage_read_model_detail_service.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
- `tests/test_invoice_usage_collection_sql_runtime.py`
- `tests/test_input_invoice_usage_api.py`
- `tests/test_read_model_architecture_guards.py`

CodeGraph was used before this audit to inspect `InputInvoiceUsageReadModelDetailService`, `InputInvoiceUsageReadModelRepositoryPort`, `InvoiceUsageCollectionSqlProjectionBuilder`, `InvoiceUsageCollectionReadModelRefreshService`, and remaining `Application` input usage surfaces. Literal `rg` checks were then used for route/helper names and removed legacy projection helper names.

## Local Closure Accounting

| Requirement | Evidence | Local status |
| --- | --- | --- |
| Narrow read-model repository port | `InputInvoiceUsageReadModelRepositoryPort` exposes input usage rows/detail/save/mark/prune only and is wired into PostgreSQL state-store reads plus worker projection save/mark/prune paths. | Accounted |
| Query fresh gate | `Application._get_input_invoice_usage_rows_from_sql_read_model(...)` fail-closes in production SQL runtime when repository/payload/schema/source versions are missing or stale; filter options and export all-rows path page through the same fresh gate. | Accounted |
| Relation detail fresh gate | `InputInvoiceUsageReadModelDetailService` reads single-row detail payload by `row_id`; production SQL runtime missing repository now returns `202`/refreshing and enqueues `input_invoice_usage:all` instead of falling back to live rebuild. | Accounted |
| Source-version proof | `Application._input_invoice_usage_expected_source_versions(...)` composes base input usage source versions with Workbench relation scope versions only for concrete month scopes; `all` does not depend on global `workbench_relation:all`. | Accounted |
| Scope policy and force refresh | `ReadModelScopePolicyRegistry` keeps `input_invoice_usage` on the month-or-all contract; non-transactional enqueue goes through `ReadModelRefreshGateway`. | Accounted |
| Worker fan-out | `InvoiceUsageCollectionReadModelRefreshService` expands fan-out `all` scopes through `InvoiceUsageCollectionSqlProjectionBuilder.list_input_invoice_usage_scope_shards(...)`, prunes orphan month shards, enqueues concrete months and completes the parent dirty scope. | Accounted |
| Projection write boundary | `InvoiceUsageCollectionSqlProjectionBuilder.rebuild_input_invoice_usage_read_model_scope(...)` writes input usage rows/scope readiness through `InputInvoiceUsageReadModelRepositoryPort`. | Accounted |
| Operation barrier after writes | Input usage payment-rule and OA reverse frontend flows wait for `input_invoice_usage` operation barrier targets before reloading rows; backend mutation invalidation routes to the read model refresh gateway. | Accounted |
| Legacy contamination | Unused app-level `list_input_invoice_usage_scope_shards(...)`, `mark_input_invoice_usage_scope_empty(...)` and `rebuild_input_invoice_usage_read_model_scope(...)` were removed and guarded from returning. | Accounted |
| Tests/docs | API, runtime, architecture guard, frontend and Browser coverage are recorded in module docs; this audit updates GSD accounting and local evidence. | Accounted |

## Retained Surfaces

| Surface | Classification | Reason |
| --- | --- | --- |
| `Application._handle_api_input_invoice_usage_rows(...)` | HTTP mapping / route fresh gate | It maps query, response status and errors. In production SQL runtime, stale/missing SQL read model returns refreshing rather than live scan. Local/legacy fallback remains development compatibility. |
| `Application._handle_api_input_invoice_usage_filter_options(...)` | HTTP mapping / all-rows fresh gate consumer | It derives filter options from the same fresh-gated rows path when SQL read model is available; local/legacy fallback remains only outside required SQL runtime. |
| `Application._input_invoice_usage_export_service(...)` and `_load_input_invoice_usage_export_page(...)` | export dependency assembly / fresh-gated page loader | Export preview/download pages through `_get_input_invoice_usage_rows_from_sql_read_model(...)`; production SQL runtime unavailable/stale paths return refreshing via the fresh gate before live fallback can execute. |
| `Application._get_input_invoice_usage_rows_from_sql_read_model(...)` | route read-model fresh gate | Current HTTP SQL read boundary; it enqueues through `ReadModelRefreshGateway` on miss/stale/source mismatch and only labels payload fresh after schema and source proof pass. |
| `Application._get_input_invoice_usage_all_rows_from_sql_read_model(...)` | route all-query fresh gate | It pages through the same rows fresh gate and stops on refreshing, so all-query filter/export helpers cannot aggregate stale rows as fresh. |
| `Application._get_input_invoice_usage_relation_details_from_sql_read_model(...)` | route detail fresh gate | It delegates to `InputInvoiceUsageReadModelDetailService`; production missing repository is now fail-closed. |
| `Application._input_invoice_usage_expected_source_versions(...)` | source-version provider | It is still used by route fresh gates and keeps the `all` relation-version exception local to the input usage boundary. Moving it to a service/provider is optional future cleanup, not a blocking local gap. |
| `Application._enqueue_input_invoice_usage_read_model_refresh(...)` | gateway-backed producer wrapper | It delegates to `ReadModelRefreshGateway.enqueue_one("input_invoice_usage", ...)`; it does not direct-SQL write dirty scopes, outbox, readiness, cache or App Status. |
| `Application._invalidate_input_invoice_usage_oa_reverse_read_models(...)` | mutation side-effect wrapper | It maps OA reverse affected scopes to the gateway-backed wrapper and persists Workbench pair relations; OA reverse command semantics are unchanged. |
| `Application._input_invoice_usage_scope_keys_for_import_preview(...)` and `_input_invoice_usage_scope_keys_for_import_file_session(...)` | import lifecycle scope calculator | These derive impacted month scopes from import facts and feed shared invalidation; they are not read-model rebuild or SQL write paths. |
| `Application._invalidate_invoice_usage_collection_read_model_scopes(...)` | shared invoice usage invalidation helper | It normalizes lifecycle/import scopes and calls the gateway-backed wrappers for input usage, output collection and OA pending payment. It is shared boundary plumbing, not an input usage legacy projection path. |

## Production Evidence Deferred

The autonomous plan must not depend on local `PGSQL_URL` or a staging database, and automatic runs must not perform production writes or secret reads. Therefore this slice cannot prove real production evidence for:

- production `job.outbox_events` / `job.read_model_dirty_scopes` enqueue-to-done for `input_invoice_usage`;
- current-effective `read_model.app_status_readiness` for input usage scopes;
- real `invoice-usage-collection` worker drain for `input_invoice_usage:all` fan-out and concrete month shards;
- production App Status evidence for the input invoice usage page;
- high-row rows/filter/export/detail API p95/p99 against production-sized data;
- authenticated browser smoke after a real write affecting input usage.

This is a soft gate. It prevents global module closure, but it does not block the next local modular IO pilot.

## Decision

No additional local non-Go implementation gap was found after the relation-detail fail-closed fix.

Set:

- `read-models:input-invoice-usage-local-implementation-closure-audit`: `production-evidence-deferred`
- module closure: `not-module-closed`
- Go hot-path admission: still `blocked-by-prerequisite`

Insert the next executable boundary before Go candidates:

- `read-models:next-pilot-selection-after-input-invoice-usage`

The next boundary should compare remaining read model candidates using current manifest/module docs and pick the next non-Go pilot. It must not start Go/Fiber/Go Worker admission.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/input-invoice-usage/state-machine.md`

No state definition changes are needed. This slice changes execution accounting only; it does not add or alter business, UI, read model or worker states.

## Seven Test Category Decision

This slice is audit/accounting only and does not change runtime behavior.

1. Business core unit tests: not applicable; no payment, OA reverse, relation, invoice lifecycle or amount rule changed.
2. Service-layer tests: reviewed existing input usage service/read model detail/repository port coverage; no service behavior changed.
3. API contract tests: reviewed existing rows/filter/export/detail fail-closed and fresh-detail coverage; no API shape changed.
4. Read model/cache/background job tests: reviewed invoice usage collection SQL runtime coverage for repository port, fan-out, prune, source versions and refresh handler behavior.
5. Frontend component and interaction tests: reviewed existing operation-barrier, refreshing/error/detail/export coverage; no frontend behavior changed.
6. End-to-end business-flow integration tests: not run; no runtime behavior changed in this audit slice.
7. Existing feature regression tests: reviewed existing regression inventory; no new runtime regression target was introduced.

## Verification

Required for this analysis-only slice:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only local `input_invoice_usage` implementation support is accounted for. The module is not globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
