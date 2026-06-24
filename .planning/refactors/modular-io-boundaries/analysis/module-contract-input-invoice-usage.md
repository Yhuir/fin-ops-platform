# Module Contract - Input Invoice Usage

**Date:** 2026-06-24
**Worker:** T8 Module IO Contracts
**Status:** documentation/accounting closed
**Runtime behavior:** unchanged

## Module Basic Info

| Field | Content |
| --- | --- |
| Module key | `input-invoice-usage` |
| Module type | Page module |
| Route | `/input-invoice-usage` |
| Frontend entry | `web/src/pages/InputInvoiceUsagePage.tsx`, `web/src/features/inputInvoiceUsage/api.ts` |
| Backend entry | input invoice usage routes/services, `InputInvoiceUsageReadModelService`, `InvoiceUsageCollectionSqlProjectionBuilder` |
| Read model | `input_invoice_usage` |
| Docs entry | `docs/modules/input-invoice-usage/README.md` |
| Refactor status | Contracted locally; production evidence deferred |

## IO Contract Reconciliation

### Inputs

| Input | Contract |
| --- | --- |
| Rows query | Reads `input_invoice_usage` SQL read model; production SQL runtime must fail closed to refreshing on repository/view/source/schema miss. |
| Filter-options query | Same page-level freshness contract as rows; cannot be treated as an optional fresh-independent helper for empty/export state. |
| Relation detail query | Reads single row payload from `read_model.input_invoice_usage_rows`; non-fresh or repository unavailable returns refreshing and enqueues refresh. |
| OA reverse commands | Write local batch state and, for relation facts, must use `WorkbenchRelationCommandService` rather than page-private relation writes. |
| Operation barrier | Mutation success waits on returned/derived `input_invoice_usage` freshness target before rows refresh. |

### Outputs

| Output | Contract |
| --- | --- |
| Rows payload | `read_model_status=fresh` plus rows/pagination before normal empty state or export is allowed. |
| Filter-options payload | Must be fresh together with rows for page-level fresh. |
| Relation detail payload | Uses existing summaries/invoice relations from one read-model row; no live full rebuild in detail route. |
| OA reverse result | Local batch state is not relation truth; relation writes fan out through `workbench_relation` and `input_invoice_usage` refresh. |

### State / Event Contract

- Page-level `fresh` requires both rows and filter-options fresh.
- Any `stale`, `missing`, `schema_mismatch`, `refreshing` or `unavailable` state from either rows or filter-options keeps the page in refresh diagnostics, disables export and blocks normal empty state.
- `input_invoice_usage:all` remains a fan-out command to month shards, not a standalone freshness proof.
- Relation evidence comes from `WorkbenchRelationReadFacade`; candidate relation evidence never drives paid/confirmed calculations.

### Public / Internal Surfaces

Public surfaces:

- `InputInvoiceUsagePage` through feature API only.
- Input usage API routes for rows, filter-options, export, relation details and OA reverse.
- `InputInvoiceUsageReadModelRepositoryPort` and registered read model worker/producer boundaries.
- `WorkbenchRelationReadFacade` for linked/candidate relation evidence.

Internal-only surfaces:

- Live query fallback as production fresh source.
- Page-local inference from currently displayed rows to build filter-options or relation facts.
- Direct pair relation mutation for OA reverse relation facts.
- Detail route full live rebuild.

### Legacy Status

| Legacy path | Status | Constraint |
| --- | --- | --- |
| `InputInvoiceUsageQueryService.list_rows(...)` production fallback | `compat-only` | Allowed only legacy/local; forbidden when production SQL read model is required. |
| Detail live rebuild fallback | `compat-only` | Forbidden for production repository-unavailable path. |
| Page-level rows-only freshness | removed/guarded | Filter-options stale must keep page non-fresh. |

### Read Model Refresh / Force Refresh

- Non-transactional refresh uses `ReadModelRefreshGateway` and the `input_invoice_usage` scope policy.
- `all` refresh fans out to current month shards and prunes orphan month shards.
- Force refresh follows the shared read-model gateway/runbook contract documented in `docs/modules/read-models/README.md`.
- Operation barrier target is `input_invoice_usage:<month|all>` depending on write context; rows reload must not happen before barrier completion for mutating flows.

### Partitioned Scoped Incremental Target

`input_invoice_usage` uses scoped incremental month shards. The partition key is input invoice usage month scope; `all` is fan-out only. Builder owner is the invoice usage collection projection boundary. Current target is local Python worker; Go admission is not active.

## Test Contract

| Category | Applicability | Evidence |
| --- | --- | --- |
| 1. Business core unit tests | Applicable for OA reverse/payment status changes | Existing input usage OA reverse and freshness tests; none changed by T8 docs. |
| 2. Service-layer tests | Applicable | Existing input usage service/read model/detail tests cover relation context and read-model boundaries. |
| 3. API contract tests | Applicable | Existing API tests cover rows/filter/detail/export/OA reverse and production fail-closed detail. |
| 4. Read model/cache/background job tests | Applicable | `tests/test_invoice_usage_collection_sql_runtime.py`, read model manifest/gateway tests. |
| 5. Frontend component and interaction tests | Covered by T4 | `web/src/test/InputInvoiceUsagePage.test.tsx` covers rows fresh + filter-options stale. |
| 6. E2E business-flow integration tests | Applicable for real flows | Existing Playwright flow covers rows, OA reverse and relation fan-out; real infra drain remains deferred. |
| 7. Existing feature regression tests | Applicable | Existing module tests protect old rows/export/relation/OA reverse behavior. |

## Files Updated By T8

- `docs/modules/input-invoice-usage/README.md`
- `docs/modules/input-invoice-usage/state-machine.md`
- `.planning/refactors/modular-io-boundaries/analysis/module-contract-input-invoice-usage.md`
- `.planning/refactors/modular-io-boundaries/parallel/handoffs/T8-module-io-contracts.md`

## Remaining Risk

No runtime verification beyond docs/diff checks is claimed by T8. Real PostgreSQL worker drain, App Status readiness, production browser and high-row evidence remain deferred.
