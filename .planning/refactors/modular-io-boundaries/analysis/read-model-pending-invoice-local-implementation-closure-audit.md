# Read Model Pending Invoice Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:pending-invoice-local-implementation-closure-audit`
**Slice status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`

## Goal

Audit whether the `pending_invoice` read model pilot has remaining local non-Go implementation gaps after repository port extraction, freshness/barrier audit, scope policy filter allowlist enforcement and mutation freshness barrier work.

This slice does not change runtime code.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-repository-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-refresh-freshness-operation-barrier-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-scope-policy-filter-allowlist.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-mutation-freshness-target-contract.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/pending-invoices/README.md`
- `docs/modules/pending-invoices/tests.md`
- `docs/modules/pending-invoices/implementation-notes.md`
- `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
- `backend/src/fin_ops_platform/services/pending_invoice_read_model_repository.py`
- `backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `tests/test_read_model_refresh_gateway.py`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_pending_invoice_api.py`
- `tests/test_pending_invoice_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `web/src/pages/PendingInvoicesPage.tsx`
- `web/src/test/PendingInvoicesPage.test.tsx`
- `web/src/test/PendingInvoicesRulesSaveTimeout.test.tsx`

CodeGraph was used to locate the active `PendingInvoiceReadModelService`, `SearchPendingSqlProjectionBuilder` and `ReadModelRefreshGateway` symbols before this audit.

## Local Closure Accounting

| Requirement | Evidence | Local status |
| --- | --- | --- |
| Narrow read-model repository port | `PendingInvoiceReadModelRepositoryPort` exposes only pending invoice read/model methods and is wired into app/worker/projection paths. | Accounted |
| Query fresh gate | `PendingInvoiceReadModelService.rows(...)` fail-closes on missing SQL payload, schema-stale rows and source-version mismatch; stale rows are marked `refreshing`, not fake fresh. | Accounted |
| Source-version proof | Expected versions include settings, parser/sync versions, bank detail source versions and workbench relation source versions when available. | Accounted |
| Refresh enqueue boundary | API miss/schema/source-version refreshes use `ReadModelRefreshGateway`; non-transactional refresh scope validation goes through scope policy registry. | Accounted |
| Scope policy | `pending_invoice` rejects bare `all`, bare month, unsupported direction and unsupported direction/filter combinations before durable queue enqueue. | Accounted |
| Worker expansion | `SearchPendingReadModelRefreshService` expands base scopes to month shards and delegates only month shards to projection rebuild. | Accounted |
| Projection write boundary | Pending invoice save/mark uses the pending invoice repository port; search index writes remain on the search repository. | Accounted |
| Operation barrier after writes | Rules, attach-existing and income-status writes wait on `pending_invoice` operation barrier targets before rows are treated as refreshed. | Accounted |
| Legacy contamination | Static guards keep old `server.py` pending invoice SQL helpers/manual audit/finalizer builders from returning and prevent pending invoice services from depending on Redis/RabbitMQ clients. | Accounted |
| Tests/docs | Relevant backend service/API/read model tests, frontend interaction tests, module docs and GSD analysis files are recorded. | Accounted |

## Retained Surfaces

| Surface | Classification | Reason |
| --- | --- | --- |
| `SearchPendingSqlProjectionBuilder.list_pending_invoice_scope_shards(...)` source SQL | retained source-fact enumeration | It enumerates source fact months from `app.bank_transactions`, not read-model rows. A future source-fact/provider port may extract it, but it is not a blocker for the pending invoice read-model repository port pilot. |
| Backend mutation responses without `freshness_targets` | retained current API contract | Existing `affectedMonths` plus current page direction/filter is enough for the page to build operation barrier targets. A uniform backend `freshness_targets` response should be a separate cross-page API contract slice if desired. |
| `search-pending` worker | compat auxiliary worker | Manifest keeps `pending-invoice` as primary and `search-pending` as auxiliary compatibility worker. It is not the only performance lane. |
| Manual invoice command service methods | legacy recovery/compat service surface | HTTP/UI new manual invoice entry points remain blocked by API/page tests and static guards; service methods preserve historical retry/recovery coverage. |

## Production Evidence Deferred

The local audit cannot prove real production PostgreSQL/worker/App Status/high-row/browser evidence because this autonomous plan must not depend on local `PGSQL_URL` or staging database and must not perform production writes without explicit approval.

Deferred evidence:

- real production `job.outbox_events` / `job.read_model_dirty_scopes` enqueue-to-done for `pending_invoice`;
- real `read_model.app_status_readiness` current-effective freshness for pending invoice scopes;
- real `pending-invoice` and `search-pending` worker drain;
- high-row pending invoice API p95/p99 and export row-limit behavior against production-sized data;
- authenticated browser smoke against production rows after a real write.

This is a soft gate only. It prevents global module closure, but it does not block the next local modular IO pilot.

## Decision

No new local non-Go implementation gap was found that must block the pending invoice pilot.

Set:

- `read-models:pending-invoice-local-implementation-closure-audit`: `production-evidence-deferred`
- module closure: `not-module-closed`
- Go hot-path admission: still `blocked-by-prerequisite`

Next executable boundary:

- `read-models:next-pilot-selection-after-pending-invoice`

The next boundary should compare remaining read model candidates using current manifest/module docs and pick the next non-Go pilot. The previous comparison suggests `oa_pending_payment` is a strong candidate, but the selection must be revalidated in its own slice rather than assumed here.

## Seven Test Category Decision

This slice is audit/accounting only and does not change runtime behavior.

1. Business core unit tests: not applicable; no business rules changed.
2. Service-layer tests: reviewed existing pending invoice service/read model coverage; no new service behavior changed.
3. API contract tests: reviewed existing pending invoice API contract coverage; no API shape changed.
4. Read model/cache/background job tests: reviewed scope policy, SQL runtime, worker refresh and manifest coverage.
5. Frontend component and interaction tests: reviewed existing pending invoice barrier interaction coverage.
6. End-to-end business-flow integration tests: not run; no runtime behavior changed in this audit slice.
7. Existing feature regression tests: reviewed existing regression inventory; no new runtime regression target was introduced.

## Verification

Required for this analysis-only slice:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only local pending invoice implementation support is accounted for. The `pending_invoice` module is not globally closed because production PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
