# Module Contract - Output Invoice Collections

**Date:** 2026-06-24
**Worker:** T8 Module IO Contracts
**Status:** documentation/accounting closed
**Runtime behavior:** unchanged

## Module Basic Info

| Field | Content |
| --- | --- |
| Module key | `output-invoice-collections` |
| Module type | Page module |
| Route | `/output-invoice-collections` |
| Frontend entry | `web/src/pages/OutputInvoiceCollectionsPage.tsx`, `web/src/features/outputInvoiceCollections/api.ts` |
| Backend entry | `routes_output_invoice_collections.py`, output collection query/lifecycle/receipt services |
| Read model | `output_invoice_collection` |
| Docs entry | `docs/modules/output-invoice-collections/README.md` |
| Refactor status | Contracted locally; production evidence deferred |

## IO Contract Reconciliation

### Inputs

| Input | Contract |
| --- | --- |
| Rows query | Reads `output_invoice_collection` SQL read model; miss/stale/schema/source mismatch returns refreshing and enqueues refresh. |
| Filter-options query | Must be fresh together with rows before page empty/export states are allowed. |
| Relation detail query | Reads single SQL read-model detail row in production; repository/detail miss returns refreshing and enqueues `output_invoice_collection:all`. |
| Lifecycle write commands | Manual status, reminder, red/blue relation and receipt lifecycle writes use lifecycle/receipt services and transaction-bound refresh where applicable. |
| Operation barrier | Mutation response returns `read_model_scope_keys` and `freshness_targets`; frontend waits on concrete month target when available. |

### Outputs

| Output | Contract |
| --- | --- |
| Rows payload | Fresh SQL rows plus lifecycle overlay; stale rows must not be returned as fresh. |
| Filter-options payload | Must be fresh together with rows for page-level fresh. |
| Mutation result | Must include scope/freshness target for write-after-read synchronization. |
| Relation details | `kind=oa|bank|invoice` expands summaries from read model row; no production live rebuild on detail miss. |
| Receipt history | Real lifecycle facts only; no fabricated empty history. |

### State / Event Contract

- Page-level `fresh` requires both rows and filter-options fresh.
- Any `stale`, `missing`, `schema_mismatch`, `refreshing` or `unavailable` state from either rows or filter-options keeps the page in refresh diagnostics, disables export and blocks normal empty state.
- `output_invoice_collection:all` remains a fan-out command to month shards, not a standalone freshness proof.
- Lifecycle writes enqueue affected `output_invoice_collection` scope and rely on operation barrier before rows refetch.
- `relationStatus="candidate"` is display evidence only and cannot drive collected/confirmed status.

### Public / Internal Surfaces

Public surfaces:

- `OutputInvoiceCollectionsPage` through feature API only.
- Output collection rows/filter/detail/export/lifecycle/receipt routes.
- `OutputInvoiceCollectionReadModelRepositoryPort` and invoice usage collection refresh worker.
- Lifecycle and receipt services for write commands.

Internal-only surfaces:

- Production live query fallback for rows/filter-options/detail.
- App-level projection helpers for output collection rebuild/list/mark.
- Frontend inference from current page rows to generate global filter options.
- Direct dirty/outbox writes outside gateway or transaction-bound queue writer.

### Legacy Status

| Legacy path | Status | Constraint |
| --- | --- | --- |
| `OutputInvoiceCollectionQueryService.list_rows(...)` production fallback | `compat-only` | Allowed only legacy/local; forbidden in production SQL read-model runtime. |
| Relation detail live rebuild fallback | `compat-only` | Forbidden when production SQL repository/detail lookup is unavailable. |
| Page-level rows-only freshness | removed/guarded | Filter-options stale must keep page non-fresh. |
| App-level output projection helpers | removed/guarded | Projection owner remains worker/projection builder boundary. |

### Read Model Refresh / Force Refresh

- Non-transactional refresh uses `ReadModelRefreshGateway` and `output_invoice_collection` scope policy.
- Transactional lifecycle writes must enqueue affected scope in the same write boundary where configured.
- Force refresh follows the shared read-model gateway/runbook contract documented in `docs/modules/read-models/README.md`.
- Operation barrier prefers concrete month scope from mutation response; `all` is fallback only when month cannot be identified.

### Partitioned Scoped Incremental Target

`output_invoice_collection` uses scoped incremental month shards. The partition key is output invoice collection month scope; `all` is fan-out only. Builder owner is the invoice usage collection projection boundary. Current target is local Python worker; Go admission is not active.

## Test Contract

| Category | Applicability | Evidence |
| --- | --- | --- |
| 1. Business core unit tests | Applicable for collection/receipt rules | Existing output collection service/lifecycle tests; none changed by T8 docs. |
| 2. Service-layer tests | Applicable | Existing lifecycle, receipt, query and read model repository port tests. |
| 3. API contract tests | Applicable | Existing API tests cover rows/detail/export/lifecycle/receipt and mutation freshness targets. |
| 4. Read model/cache/background job tests | Applicable | `tests/test_invoice_usage_collection_sql_runtime.py`, runtime registry/App Status/readiness tests. |
| 5. Frontend component and interaction tests | Covered by T4 | `web/src/test/OutputInvoiceCollectionsPage.test.tsx` covers rows fresh + filter-options stale. |
| 6. E2E business-flow integration tests | Applicable for real flows | Existing Playwright flows cover collection status, receipt and red/blue relation fan-out; real infra drain remains deferred. |
| 7. Existing feature regression tests | Applicable | Existing module tests protect old rows/export/relation/detail/receipt behavior. |

## Files Updated By T8

- `docs/modules/output-invoice-collections/README.md`
- `docs/modules/output-invoice-collections/state-machine.md`
- `.planning/refactors/modular-io-boundaries/analysis/module-contract-output-invoice-collections.md`
- `.planning/refactors/modular-io-boundaries/parallel/handoffs/T8-module-io-contracts.md`

## Remaining Risk

No runtime verification beyond docs/diff checks is claimed by T8. Real PostgreSQL worker drain, App Status readiness, production browser and high-row evidence remain deferred.
