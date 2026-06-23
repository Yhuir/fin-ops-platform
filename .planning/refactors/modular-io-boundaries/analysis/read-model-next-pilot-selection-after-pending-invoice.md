# Read Model Next Pilot Selection After Pending Invoice

**Date:** 2026-06-24
**Boundary:** `read-models:next-pilot-selection-after-pending-invoice`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

Select `oa_pending_payment` as the next non-Go read model implementation pilot after `bank_detail`, `workbench_relation` and `pending_invoice`.

The next implementation boundary is:

`read-models:oa-pending-payment-repository-port-extraction`

This slice is planning and selection only. It does not change runtime code, API behavior, read model behavior, worker runtime, production state or Go/Fiber/Go Worker admission.

## Why `oa_pending_payment`

`oa_pending_payment` is the strongest next pilot because it exercises the same stale-read class the refactor is meant to prevent, but on a different high-value page:

- it consumes Workbench relation distribution for completed OA rows;
- it owns a separate in-progress OA pending relation/bank-claim path;
- it depends on invoice lifecycle and invoice usage collection refresh;
- it has an existing `OaPendingPaymentReadModelService` fresh/source-version gate;
- it has detailed API/service/read model/frontend tests for completed and in-progress flows;
- previous pilot comparisons deferred it specifically until `bank_detail`, `workbench_relation` and `pending_invoice` patterns were proven.

The safest first boundary is repository port extraction. It narrows the read-model SQL surface before touching command flows, OA MySQL write-back, relation promotion, shared invoice-usage worker behavior or Go candidates.

## Candidate Comparison

| Candidate | Cross-page freshness value | Current structure | Risk | Decision |
| --- | --- | --- | --- | --- |
| `oa_pending_payment` | Very high. It combines completed OA projection, in-progress payment-admitted OA, Workbench relation, invoice lifecycle and pending bank claims. | Has `OaPendingPaymentReadModelService`, manifest contract, API tests, SQL runtime tests, frontend tests and `invoice-usage-collection` worker support. | Shared `InvoiceUsageCollectionSqlProjectionBuilder` and OA MySQL/payment-admitted dependencies make broad changes risky. A repository port slice is narrow. | **Select as next pilot; first boundary is repository port extraction.** |
| `input_invoice_usage` | High. Relation-backed page and shares invoice-usage worker. | Has read model service/tests. | Shares worker/projection with output/OA pending; less directly connected to pending invoice user-visible stale bug than OA pending payment. | Defer until OA repository port pattern is proven. |
| `output_invoice_collection` | Medium/high. Export-sensitive and relation-backed. | Has service/API tests and prior all-scope freshness fixes. | Shares invoice-usage worker and all-scope relation freshness nuances. | Defer. |
| `invoice_lifecycle` | Very high shared dependency. | Has lifecycle read facade/projection tests. | Central state module; changing it before another page-level pilot risks broad blast radius. | Defer. |
| `search` | High discoverability value. | Has search projection tests and `search` primary worker. | Search index is broad and should follow page-specific fact/source-version stabilization. | Defer. |
| `no_oa_bank_batch` | Medium/high. Relation-backed and has application/read model tests. | Has service/read model refresh coverage. | Relation write/read dependencies are broader and less directly sequenced from pending invoice than OA. | Defer. |
| `cost_statistics` | High performance/summary value. | Special parent aggregate and production SLO history. | More performance-oriented; Go admission remains blocked until modular IO prerequisites. | Defer. |
| `tax_offset` | Medium/high. | Has tax read model tests. | Depends on invoice lifecycle and relation effects; lower immediate stale-page value. | Defer. |
| `turnover_ledger` | Medium/high. | Strong test coverage and operation barrier work. | Broad write UoW/Workbench/cost/search blast radius; not the next read-model repository port pilot. | Defer. |

## Evidence

Planning evidence:

- `read-model-next-pilot-selection-after-workbench-relation.md` deferred `oa_pending_payment` until pending invoice pattern was proven.
- `read-model-pending-invoice-local-implementation-closure-audit.md` records pending invoice local implementation support as accounted for while keeping production evidence deferred.
- `read-model-repository-port-and-sql-owner-split-plan.md` lists the `oa_pending_payment` repository port contract.
- `04-IMPLEMENTATION-ROADMAP.md` requires non-Go read model implementation prerequisites before Go hot-path admission.

Module evidence:

- `docs/modules/oa-pending-payments/README.md` defines the production read path through `OaPendingPaymentReadModelService` with no live scan pretending fresh when read model data is missing/stale.
- `docs/modules/oa-pending-payments/tests.md` already covers completed/in-progress views, auto reconcile, bank link, promotion, detail drawers, source-version freshness and frontend barrier behavior.
- `docs/modules/read-models/README.md` defines `oa_pending_payment:all` as a fan-out command while all-query freshness proof comes from actual month rows/scopes and dirty/outbox status.

Code evidence:

- `OaPendingPaymentReadModelService` dynamically consumes:
  - `list_oa_pending_payment_rows`
  - `get_oa_pending_payment_row_by_row_id`
  - `get_oa_pending_payment_row_by_oa_id`
  - `get_oa_pending_payment_row_by_bank_transaction_id`
  - `get_oa_pending_payment_row_by_invoice_id`
- `InvoiceUsageCollectionSqlProjectionBuilder` writes and maintains OA pending payment read model data through:
  - `save_oa_pending_payment_rows`
  - `mark_oa_pending_payment_scope`
  - `prune_oa_pending_payment_scope_shards`
- `READ_MODEL_MANIFEST["oa_pending_payment"]` already lists the exact repository port contract.
- Tests under `tests/test_oa_pending_payment_api.py` and `tests/test_invoice_usage_collection_sql_runtime.py` already protect read model freshness, source versions, scope fan-out and in-progress/completed behavior.

## Next Boundary Contract

`read-models:oa-pending-payment-repository-port-extraction` should:

- add a narrow `OaPendingPaymentReadModelRepositoryPort`;
- expose only the manifest-listed OA pending payment read-model methods:
  - `list_oa_pending_payment_rows`
  - `save_oa_pending_payment_rows`
  - `mark_oa_pending_payment_scope`
  - `prune_oa_pending_payment_scope_shards`
  - `get_oa_pending_payment_row_by_row_id`
  - `get_oa_pending_payment_row_by_oa_id`
  - `get_oa_pending_payment_row_by_bank_transaction_id`
  - `get_oa_pending_payment_row_by_invoice_id`
- wire `OaPendingPaymentReadModelService` and the OA pending payment parts of `InvoiceUsageCollectionSqlProjectionBuilder` through the port where the app/worker currently passes the broad read model repository;
- preserve completed/in-progress view behavior, read model response shape, detail response shape, source-version stale behavior, all fan-out/month shard behavior and pending relation cleanup behavior;
- add tests proving unrelated read model repository methods are not exposed through the port;
- avoid touching OA MySQL write-back, payment-admitted source adapter behavior, pending relation promotion, command service behavior, UI workflow, worker runtime or Go/Fiber/Go Worker.

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `read-models:next-pilot-selection-after-pending-invoice`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:oa-pending-payment-repository-port-extraction`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Categories

This slice is analysis-only, so no runtime tests are added.

For the next implementation slice:

| Category | Applies? | Reason |
| --- | --- | --- |
| Business core unit tests | Not directly for repository port extraction; OA payment status/write-back semantics must remain covered by existing service tests. |
| Service-layer tests | Applies. Prove `OaPendingPaymentReadModelService` consumes the narrow port and does not require unrelated repository methods. |
| API contract tests | Applies if app route wiring changes; preserve rows/filter-options/detail response shape and refreshing/fresh statuses. |
| Read model/cache/background job tests | Applies. Preserve all fan-out, month shard rebuild, save/mark/prune behavior and source-version stale behavior. |
| Frontend component and interaction tests | Not directly for the first port extraction unless response shape changes; UI behavior must remain unchanged. |
| End-to-end business-flow integration tests | Not directly for repository port extraction; existing deterministic flows remain regression evidence. |
| Existing feature regression tests | Applies. Keep completed/in-progress rows, details, filter options, operation barrier and source-version behavior unchanged. |

## Verification

Required for this analysis-only slice:

```bash
bash scripts/verify.sh docs
git diff --check
```

No application tests are required because runtime code is unchanged.

## Completion Claim

This slice only selects and queues the next pilot. It does not close `oa_pending_payment`, `pending_invoice`, the read model roadmap, or any Go hot-path gate.
