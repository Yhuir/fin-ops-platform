# Read Model Next Pilot Selection After Output Invoice Collection

**Date:** 2026-06-24
**Boundary:** `read-models:next-pilot-selection-after-output-invoice-collection`
**Previous state:** `read-models:output-invoice-collection-local-implementation-closure-audit` was `production-evidence-deferred`.
**Result state:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Scope

Select the next non-Go read model implementation pilot after `bank_detail`, `workbench_relation`, `pending_invoice`, `oa_pending_payment`, `input_invoice_usage` and `output_invoice_collection` have local implementation support accounted or deferred for production evidence.

This slice only selects the next pilot and first narrow boundary. It does not implement repository ports, change runtime code, run Go/Fiber/Go Worker admission, or claim any module closure.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/06-PILOT-SELECTION.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-manifest-and-boundary-inventory.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-pilot-gap-audit-and-contract-selection.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-input-invoice-usage.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-local-implementation-closure-audit.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`

CodeGraph was used before edits to inspect the remaining read model candidate surface. Targeted searches confirmed that `invoice_lifecycle` still has no narrow read-model repository port: `InvoiceLifecycleReadFacade` and `InvoiceLifecycleSqlProjectionBuilder` use the broad read repository methods directly.

## Candidate Comparison

| Candidate | Stale-read / cross-page risk | Existing evidence | First-slice feasibility | Decision |
| --- | --- | --- | --- | --- |
| `invoice_lifecycle` | Very high. It is the shared invoice state distribution boundary for pending invoice, input usage, output collection, OA pending payment, tax offset, cost/search and import fan-out. | Has manifest guard, read facade tests, refresh service tests, page integration tests, production SLO history and batch-save performance evidence. | High. First slice can add a narrow repository port around manifest-listed methods without changing lifecycle rules or payload shape. | **Select. First boundary: `read-models:invoice-lifecycle-repository-port-extraction`.** |
| `search` | High discoverability and cross-page fan-out value. | Has search-pending projection tests and manifest contract. | Medium. Index semantics are broad and should follow invoice lifecycle source stabilization. | Defer until after invoice lifecycle port/freshness accounting. |
| `cost_statistics` | High performance and summary value. | Has special parent aggregate contract and SLO history. | Medium/low. Queryable parent aggregate and performance work make it a wider first slice. | Defer; Go admission remains blocked. |
| `tax_offset` | Medium/high. It consumes invoice lifecycle and relation facts. | Has tax read model tests and Browser flow coverage. | Medium. Better after invoice lifecycle port/freshness is stable because tax state delegates certification state to lifecycle. | Defer. |
| `turnover_ledger` | Medium/high. Relation-backed and operation-barrier sensitive. | Strong module docs and tests. | Medium/low. Write UoW, Workbench relation, cost/search downstream and manual closure semantics make the first slice broader. | Defer. |
| `no_oa_bank_batch` | Medium/high. Relation-backed bank-batch read model. | Has application/read model refresh tests and manifest contract. | Medium. It is broader than a lifecycle repository-port first slice and depends on relation/bank facts. | Defer. |
| `bank_account_balance` | Medium. Bank details adjacent and already has separate manifest/storage contract. | Has tests and distinct event/table contract. | High, but lower immediate cross-page stale-read impact than invoice lifecycle. | Defer. |

## Selected Pilot

Select `invoice_lifecycle` as the next non-Go read model pilot.

Rationale:

- It is the next natural upstream after completing input/output/OA/pending page read models.
- It is the shared lifecycle state source that those pages must not privately recompute.
- Existing tests and production SLO notes provide enough guardrails for a narrow first implementation slice.
- The first slice is small: add `InvoiceLifecycleReadModelRepositoryPort`, wire facade/projection/state-store paths through it, and guard that unrelated read model methods are not exposed.

## First Implementation Boundary

`read-models:invoice-lifecycle-repository-port-extraction`

Expected first-slice scope:

- Add `InvoiceLifecycleReadModelRepositoryPort`.
- Expose only manifest-listed methods:
  - `save_invoice_lifecycle_rows(...)`
  - `mark_invoice_lifecycle_scope(...)`
  - `get_invoice_lifecycle_rows_by_subject_ids(...)`
  - `get_invoice_lifecycle_rows_by_identity_keys(...)`
  - `list_invoice_lifecycle_rows(...)`
- Wire `InvoiceLifecycleReadFacade` and `InvoiceLifecycleSqlProjectionBuilder` to the narrow port.
- If PostgreSQL state-store read wiring has an invoice lifecycle repository property, return the narrow port there; otherwise keep the slice limited and document the owner gap.
- Add a port isolation test proving input/output/OA/pending/search/cost/tax methods are not exposed.
- Preserve payload shape, lifecycle rules, source versions, worker event semantics, operation barrier behavior and API behavior.

## State-Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/read-models/tests.md`

No state definition changed. This slice only changes execution accounting:

- `read-models:next-pilot-selection-after-output-invoice-collection` moves from `pending` to `analysis-closed`.
- `read-models:invoice-lifecycle-repository-port-extraction` is inserted as the next `pending` boundary.
- Go candidates remain `blocked-by-prerequisite`.

## Seven Test Categories

1. Business core unit tests: not applicable for this analysis-only selection slice.
2. Service-layer tests: not applicable in this slice; the next implementation slice should add repository-port service/boundary tests.
3. API contract tests: not applicable in this slice; API shape must remain unchanged in the next slice.
4. Read model/cache/background job tests: applicable as planning evidence; next slice should extend invoice lifecycle read model refresh/facade or repository boundary tests.
5. Frontend component and interaction tests: not applicable for this selection slice.
6. End-to-end business-flow integration tests: not applicable for this selection slice.
7. Existing feature regression tests: applicable as planning evidence; next slice must rerun invoice lifecycle read facade, refresh and page integration regressions.

## Verification Plan

Because this slice changes only planning and docs:

```bash
bash scripts/verify.sh docs
git diff --check
```

Runtime backend/frontend tests are not required until the repository port extraction changes code.

## Next Boundary

`read-models:invoice-lifecycle-repository-port-extraction`
