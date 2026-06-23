# Read Model Next Pilot Selection After Workbench Relation

**Date:** 2026-06-24
**Boundary:** `read-models:next-pilot-selection-after-workbench-relation`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

Select `pending_invoice` as the next non-Go read model implementation pilot after `bank_detail` and `workbench_relation`.

The next implementation boundary is:

`read-models:pending-invoice-repository-port-extraction`

This slice is planning and selection only. It does not change runtime code, API behavior, read model behavior, workers, production state, or Go/Fiber/Go Worker admission.

## Why `pending_invoice`

`pending_invoice` is the best next pilot because it is the first user-visible page where the previous two pilots directly matter:

- `bank_detail` source versions affect pending invoice freshness.
- `workbench_relation` source versions affect pending invoice relation chips, paid/invoiced status and cross-page consistency.
- The module has a special scope contract: `expense|income:<filter>[:YYYY-MM]`; bare `all` is forbidden.
- The page has high user visibility and a known stale bug class: Workbench relation changes can leave pending invoice rows looking fresh when they are not.
- Existing tests already cover stale/missing/source mismatch, SQL repository behavior, filter options, relation source versions and no-sync-scan behavior.

The safest first slice is repository port extraction, matching the successful `bank_detail` and `workbench_relation` pattern. It narrows the read-model SQL surface before changing route/service behavior.

## Candidate Comparison

| Candidate | Cross-page freshness value | Current structure | Risk | Decision |
| --- | --- | --- | --- | --- |
| `pending_invoice` | Very high. Consumes bank detail and workbench relation source versions and drives a high-traffic page. | Has `PendingInvoiceReadModelService`, SQL projection, special scope policy, manifest contract and strong tests. | Special scope/filter semantics make broad migration risky, but repository port extraction is narrow. | **Select as next pilot; first boundary is repository port extraction.** |
| `oa_pending_payment` | High. Also consumes relation and OA facts. | Has service/read model docs and tests. | Heavier OA MySQL/payment-admitted/promotion dependencies. | Defer until pending invoice pattern is proven. |
| `input_invoice_usage` | High. Relation-backed and user-visible. | Strong relation facade docs and tests. | Shared `invoice-usage-collection` worker also owns output/OA pending projections; broader blast radius. | Defer. |
| `output_invoice_collection` | Medium/high. Relation-backed and export-sensitive. | Has module docs and tests. | Shares invoice-usage worker and all-scope relation freshness nuances. | Defer. |
| `invoice_lifecycle` | High shared dependency. | Has lifecycle read model tests. | Central invoice state module; better after pending invoice page port pattern. | Defer. |
| `search` | High discoverability value. | Has search-pending projection tests. | Index semantics are broad and should follow pending/relation facts. | Defer. |
| `cost_statistics` | High performance/summary value. | Has special parent aggregate contract. | Scope semantics are more complex and performance-oriented; Go admission still blocked. | Defer. |
| `tax_offset` | Medium/high. | Has tax read model tests. | Depends on invoice lifecycle and relation effects. | Defer. |
| `turnover_ledger` | Medium/high. | Relation source-version dependency and write adapters exist. | Recently touched workbench relation restore/closure surfaces; better after another page read model pilot. | Defer. |
| `no_oa_bank_batch` | Medium/high. | Has application/read model refresh tests. | Relation write/read dependencies are broader than pending invoice read port. | Defer. |

## Evidence

Planning evidence:

- `read-model-manifest-and-boundary-inventory.md` records `pending_invoice` as a special scoped incremental read model with `pending-invoice` primary worker and `search-pending` auxiliary worker.
- `read-model-pilot-gap-audit-and-contract-selection.md` deferred `pending_invoice` until `bank_detail` and `workbench_relation` became stable enough.
- `read-model-next-pilot-selection-after-bank-detail.md` again deferred `pending_invoice` specifically because it depended on bank detail and workbench relation source versions.
- `workbench-relations-final-local-implementation-closure-and-production-evidence-defer.md` records local `workbench_relation` implementation support as accounted for, while keeping production evidence deferred and Go blocked.

Module evidence:

- `docs/modules/pending-invoices/README.md` defines relation reads through `WorkbenchRelationReadFacade` / `workbench_relation` and relation writes through `WorkbenchRelationCommandService`.
- `docs/modules/pending-invoices/implementation-notes.md` records the prior relation source freshness gate fix for stale Workbench relation source versions.
- `docs/modules/read-models/README.md` states that pending invoice must compare `workbench_relation` source versions for the current filter/month scope and cannot use global `workbench_relation:all` as proof.

Code/test evidence:

- `PendingInvoiceReadModelService` currently takes a broad repository and dynamically calls:
  - `list_pending_invoice_rows`
  - `list_pending_invoice_filter_options`
  - `pending_invoice_source_summary`
- `PendingInvoiceSourceVersionsProvider` dynamically calls:
  - `pending_invoice_bank_detail_source_versions`
  - `pending_invoice_workbench_relation_source_versions`
- `SearchPendingSqlProjectionBuilder` writes pending invoice projection through:
  - `save_pending_invoice_rows`
  - `mark_pending_invoice_scope`
  - pending invoice scope shard listing behavior.
- `READ_MODEL_MANIFEST` already lists the pending invoice repository port contract, but no narrow `PendingInvoiceReadModelRepositoryPort` exists yet.
- `tests/test_search_pending_sql_runtime.py` already has focused tests for pending invoice SQL payload freshness, source version mismatch, filter options and repository behavior.

## Next Boundary Contract

`read-models:pending-invoice-repository-port-extraction` should:

- add a narrow `PendingInvoiceReadModelRepositoryPort`;
- expose only the pending invoice read-model methods required by the read service, source version provider and projection builder:
  - `list_pending_invoice_rows`
  - `list_pending_invoice_filter_options`
  - `pending_invoice_source_summary`
  - `pending_invoice_bank_detail_source_versions`
  - `pending_invoice_workbench_relation_source_versions`
  - `save_pending_invoice_rows`
  - `mark_pending_invoice_scope`
- decide during implementation whether `list_pending_invoice_scope_shards` belongs in the same port or a projection-only sub-port, based on current projection builder call sites;
- wire `PendingInvoiceReadModelService`, `PendingInvoiceSourceVersionsProvider` and `SearchPendingSqlProjectionBuilder` through the port where the app/worker currently passes the broad read model repository;
- add tests proving unrelated read model repository methods are not exposed through the port;
- preserve current payload shape, `read_model_status`, stale reasons, `expense|income:<filter>` scope semantics, filter options, export row limit and source version behavior;
- avoid changing pending invoice relation write behavior, UI behavior, worker runtime, Go/Fiber/Go Worker, or production state.

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `read-models:next-pilot-selection-after-workbench-relation`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:pending-invoice-repository-port-extraction`

## Seven Test Categories

This slice is analysis-only, so no runtime tests are added.

For the next implementation slice:

| Category | Applies? | Reason |
| --- | --- | --- |
| Business core unit tests | Not directly for repository port extraction; pending invoice status/filter business rules must remain covered by existing service tests. |
| Service-layer tests | Applies. Prove `PendingInvoiceReadModelService` and source version provider consume the narrow port without broad repository access. |
| API contract tests | Not directly unless route wiring changes; preserve rows/filter-options/export response shape. |
| Read model/cache/background job tests | Applies. Preserve freshness, source versions, scope semantics, save/mark behavior and no-sync-scan fallbacks. |
| Frontend component and interaction tests | Not directly; no UI behavior should change in the port extraction slice. |
| End-to-end business-flow integration tests | Not directly for the first port extraction; existing relation fan-out E2E remains regression evidence. |
| Existing feature regression tests | Applies. Keep stale source-version behavior, filter options, export limit and pending invoice rows shape unchanged. |

## Verification

Required for this analysis-only slice:

```bash
bash scripts/verify.sh docs
git diff --check
```

No application tests are required because runtime code is unchanged.

## Completion Claim

This slice only selects and queues the next pilot. It does not close `pending_invoice`, `workbench_relation`, `bank_detail`, the read model roadmap, or any Go hot-path gate.
