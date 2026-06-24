# Read Model Next Pilot Selection After Input Invoice Usage

**Date:** 2026-06-24
**Boundary:** `read-models:next-pilot-selection-after-input-invoice-usage`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

Select `output_invoice_collection` as the next non-Go read model implementation pilot after `bank_detail`, `workbench_relation`, `pending_invoice`, `oa_pending_payment`, and `input_invoice_usage`.

The next implementation boundary is:

`read-models:output-invoice-collection-repository-port-extraction`

This slice is planning and selection only. It does not change runtime code, API behavior, read model behavior, worker runtime, production state, or Go/Fiber/Go Worker admission.

## Why `output_invoice_collection`

`output_invoice_collection` is the strongest next pilot because it is the remaining page read model in the same `invoice-usage-collection` worker/projection family that just had OA pending payment and input usage tightened:

- it shares `InvoiceUsageCollectionReadModelRefreshService` and `InvoiceUsageCollectionSqlProjectionBuilder`;
- it has the same fan-out `all` versus month-shard freshness problem class as input usage and OA pending payment;
- it is user-visible and export-sensitive, with stale rows creating direct finance reporting risk;
- it overlays lifecycle facts, receipt facts, red/blue invoice relation facts and unified relation summaries before returning fresh rows;
- production PostgreSQL runtime already requires SQL read repository fail-closed behavior;
- current manifest has a clear repository port contract, but no `OutputInvoiceCollectionReadModelRepositoryPort` exists yet;
- `Application` still retains output app-level projection helper methods, so repository port extraction gives the next freshness/helper audit a narrower boundary.

The safest first slice is repository port extraction. It narrows the SQL read-model persistence surface before touching lifecycle writes, receipt workflows, red/blue relation behavior, frontend operation barriers, old app-level projection helpers, or Go candidates.

## Candidate Comparison

| Candidate | Cross-page freshness value | Current structure | Risk | Decision |
| --- | --- | --- | --- | --- |
| `output_invoice_collection` | Very high. It is relation-backed, export-sensitive, and downstream to tax/cost/search. | Manifest has a clear port contract; module docs define production no-live-scan behavior; tests cover stale/source mismatch/repository unavailable and Browser export/lifecycle flows. | Receipt, red/blue relation and lifecycle overlays make broad changes risky, but repository port extraction is narrow and reuses the input/OA pattern. | **Select as next pilot; first boundary is repository port extraction.** |
| `invoice_lifecycle` | Very high shared dependency. | Has lifecycle projection/facade tests and primary worker. | Central cross-page state module; better after the remaining invoice usage collection page is narrowed. | Defer. |
| `no_oa_bank_batch` | High. Bankdetail subdomain with relation-backed read model and write states. | Has application/read model refresh tests and operation barrier contract. | Write/read relation and lifecycle repair paths are broader than a read-only repository port first slice. | Defer. |
| `cost_statistics` | High performance/summary value. | Special parent aggregate and production SLO history. | Queryable parent aggregate semantics and performance focus make it a later shared-boundary/Go-admission candidate. | Defer. |
| `tax_offset` | Medium/high. | Dedicated worker and read model query gateway. | Depends heavily on invoice lifecycle and cost-tax flows; less direct reuse from invoice-usage collection. | Defer. |
| `turnover_ledger` | Medium/high. | Strong operation barrier and relation projection docs. | Broad write UoW, Workbench relation and cost/search downstream blast radius. | Defer. |
| `search` | High discoverability value. | Partitioned scoped index with auxiliary workers. | Broad index semantics should follow page-specific source-version stabilization. | Defer. |
| `bank_account_balance` | Medium. | Bank-details adjacent read model. | Lower immediate stale relation/export risk than output collection. | Defer. |
| `workbench` | Very high. | Active generation special-case read model. | Must preserve atomic publish; should not be mechanically converted through generic page-read-model slices. | Defer. |

## Evidence

Planning evidence:

- `read-model-next-pilot-selection-after-oa-pending-payment.md` deferred `output_invoice_collection` until the input usage pattern was proven in the same shared worker family.
- `read-model-input-invoice-usage-local-implementation-closure-audit.md` records local input usage support as accounted for while keeping real production evidence deferred and Go blocked.
- `READ_MODEL_MANIFEST["output_invoice_collection"]` defines a scoped incremental read model with `invoice-usage-collection` primary worker and a manifest-listed repository port contract.
- `04-IMPLEMENTATION-ROADMAP.md` still requires non-Go modular IO/read model implementation prerequisites before Go hot-path admission.

Module evidence:

- `docs/modules/output-invoice-collections/README.md` requires production rows to prefer SQL read model, return refreshing on miss/stale/schema/source mismatch or missing SQL repository, and avoid live scan fallback when PostgreSQL runtime is required.
- `docs/modules/output-invoice-collections/README.md` defines `output_invoice_collection:all` as a fan-out control scope whose page freshness proof comes from actual rows/month scopes and active dirty/outbox state.
- `docs/modules/output-invoice-collections/tests.md` already covers API fresh/stale, repository unavailable, Browser export, lifecycle writes, receipt create/void/reissue, red/blue relation fan-out and read-export permissions.
- `docs/modules/read-models/README.md` requires relation-backed page read models to include Workbench relation source versions and prevents fan-out-only `all` scopes from pretending fresh.

Code evidence:

- CodeGraph and literal search show `InvoiceUsageCollectionSqlProjectionBuilder` still writes output rows/scopes through broad `PostgresReadModelRepository` methods:
  - `save_output_invoice_collection_rows`
  - `mark_output_invoice_collection_scope`
  - `prune_output_invoice_collection_scope_shards`
- `backend/src/fin_ops_platform/app/server.py` reads output rows through `_get_output_invoice_collection_rows_from_sql_read_model(...)` and still has app-level output projection helpers:
  - `list_output_invoice_collection_scope_shards(...)`
  - `mark_output_invoice_collection_scope_empty(...)`
  - `rebuild_output_invoice_collection_read_model_scope(...)`
- No narrow `output_invoice_collection_read_model_repository.py` port exists yet.
- `tests/test_output_invoice_collection_api.py` and `tests/test_invoice_usage_collection_sql_runtime.py` already provide regression leverage for SQL read-model freshness, repository unavailable, output projection save/mark/prune and Browser-facing API shape.

## Next Boundary Contract

`read-models:output-invoice-collection-repository-port-extraction` should:

- add a narrow `OutputInvoiceCollectionReadModelRepositoryPort`;
- expose only the manifest-listed output invoice collection read-model methods:
  - `list_output_invoice_collection_rows`
  - `save_output_invoice_collection_rows`
  - `mark_output_invoice_collection_scope`
  - `prune_output_invoice_collection_scope_shards`
- wire PostgreSQL state-store output collection read repository and the output-collection portions of `InvoiceUsageCollectionSqlProjectionBuilder` through the narrow port where they currently pass the broad read model repository;
- preserve rows/filter-options/export/detail response shape, `read_model_status`, stale reasons, source-version proof, `all` fan-out/month shard behavior, lifecycle overlay behavior, receipt facts and red/blue relation behavior;
- add tests proving unrelated read model repository methods are not exposed through the port;
- avoid touching lifecycle writes, receipt service behavior, red/blue relation commands, UI behavior, worker runtime, Go/Fiber/Go Worker or production state.

The following should remain later slices unless repository extraction exposes a concrete gap:

- output fresh/operation-barrier/helper audit;
- unused app-level output projection helper removal or quarantine;
- relation detail fail-closed parity review;
- production evidence defer accounting.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/output-invoice-collections/state-machine.md`

No global or module state definition changed. This slice only changes autonomous queue/accounting.

The transition is slice-only:

- Previous queue item: `read-models:next-pilot-selection-after-input-invoice-usage`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:output-invoice-collection-repository-port-extraction`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Categories

This slice is analysis-only, so no runtime tests are added.

For the next implementation slice:

| Category | Applies? | Reason |
| --- | --- | --- |
| Business core unit tests | Not directly for repository port extraction; receipt, collection status and red/blue relation business rules must remain unchanged and covered by existing tests. |
| Service-layer tests | Applies. Prove output collection read-model consumers can use a narrow port without broad repository access. |
| API contract tests | Applies if route/state-store wiring changes; preserve rows/filter-options/export/detail response shapes and refreshing/fresh statuses. |
| Read model/cache/background job tests | Applies. Preserve save/mark/prune, all fan-out, month shard rebuild, source-version stale behavior and no-live-scan production behavior. |
| Frontend component and interaction tests | Not directly for the first port extraction unless response shape or operation barrier targets change; UI behavior must remain unchanged. |
| End-to-end business-flow integration tests | Not directly for repository port extraction; lifecycle, receipt and red/blue relation flows stay unchanged. |
| Existing feature regression tests | Applies. Keep rows, lifecycle overlays, receipt history, export, relation fields, source-version proof and projection builder behavior unchanged. |

## Verification

Required for this analysis-only slice:

```bash
bash scripts/verify.sh docs
git diff --check
```

No application tests are required because runtime code is unchanged.

## Completion Claim

This slice only selects and queues the next pilot. It does not close `output_invoice_collection`, `input_invoice_usage`, the read model roadmap, or any Go hot-path gate.
