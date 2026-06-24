# Read Model Next Pilot Selection After OA Pending Payment

**Date:** 2026-06-24
**Boundary:** `read-models:next-pilot-selection-after-oa-pending-payment`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

Select `input_invoice_usage` as the next non-Go read model implementation pilot after `bank_detail`, `workbench_relation`, `pending_invoice` and `oa_pending_payment`.

The next implementation boundary is:

`read-models:input-invoice-usage-repository-port-extraction`

This slice is planning and selection only. It does not change runtime code, API behavior, read model behavior, worker runtime, production state, or Go/Fiber/Go Worker admission.

## Why `input_invoice_usage`

`input_invoice_usage` is the strongest next pilot because it is the closest remaining read model to the just-completed `oa_pending_payment` work while still representing a separate user-facing stale-read risk:

- it shares the `invoice-usage-collection` worker and `InvoiceUsageCollectionSqlProjectionBuilder` with `oa_pending_payment` and `output_invoice_collection`;
- it consumes Workbench relation distribution and must surface OA/bank/invoice relationship evidence without private matching or live rebuilds;
- production rows, filter/export all-rows helpers and relation-details routes must use the SQL read model when PostgreSQL runtime is required;
- missing SQL repository, stale refresh status, schema/source mismatch or unavailable row payload must return refreshing/unavailable and enqueue through the unified refresh boundary instead of falling back to `InputInvoiceUsageQueryService` live scan;
- `input_invoice_usage:all` is fan-out control scope, so all-query freshness must be proven from actual month rows/scopes and active dirty/outbox state;
- existing tests already cover rows/detail read-model paths, source-version stale behavior, all-scope fan-out/prune behavior and invoice-usage collection projection runtime behavior.

The safest first slice is repository port extraction. It narrows the SQL read-model surface before touching OA reverse workflow, payment status rules, page UI, import preview paths, shared worker fan-out logic, or Go candidates.

## Candidate Comparison

| Candidate | Cross-page freshness value | Current structure | Risk | Decision |
| --- | --- | --- | --- | --- |
| `input_invoice_usage` | Very high. It consumes Workbench relation distribution and has user-visible OA/bank/invoice relationship evidence, relation details, filter/export all-rows helpers and payment status rules. | Manifest has a clear port contract; module docs define no-live-scan production behavior; tests cover read-model missing/stale/source mismatch, detail route and shared worker projection. | Shares `invoice-usage-collection` worker/projection with output/OA. Repository port extraction is narrow and reuses the OA pattern. | **Select as next pilot; first boundary is repository port extraction.** |
| `output_invoice_collection` | High. Relation-backed, export-sensitive, and downstream to tax/cost/search. | Has strong module docs and API tests. | Broader lifecycle, receipt, reminder, red/blue invoice and status-rule dependencies make it a wider first slice than input usage. | Defer until input usage port pattern is proven in the same shared worker family. |
| `invoice_lifecycle` | Very high shared dependency. | Has lifecycle projection/facade tests. | Central cross-page state module; changing it before the remaining page-level usage/collection ports would increase blast radius. | Defer. |
| `cost_statistics` | High performance and summary value. | Special parent aggregate and SLO history. | Performance-oriented with queryable parent aggregate semantics; Go admission remains blocked until modular IO prerequisites. | Defer. |
| `tax_offset` | Medium/high. | Has tax read model runtime tests and separate worker lane. | Depends on invoice lifecycle and cost-tax flows; less direct reuse from the just-finished invoice usage collection path. | Defer. |
| `turnover_ledger` | Medium/high. | Strong module docs and operation barrier rules. | Broad write UoW, Workbench relation, cost/search downstream and manual closure semantics make the first slice larger. | Defer. |
| `no_oa_bank_batch` | Medium/high. | Has application/read model refresh coverage. | Bankdetail subdomain with relation writes, lifecycle repair and batch status rules; broader than a read-only usage port first slice. | Defer. |
| `search` | High discoverability value. | Partitioned scoped index with multiple auxiliary workers. | Broad index semantics should follow page-specific source-version stabilization. | Defer. |
| `bank_account_balance` | Medium. | Bank-details adjacent read model with separate event/table contract. | Less cross-page stale relation risk than input usage and not the next natural continuation from invoice-usage collection. | Defer. |
| `workbench` | Very high. | Active generation special-case read model. | Must preserve atomic publish semantics and should not be mechanically converted to generic page read model patterns. | Defer. |

## Evidence

Planning evidence:

- `read-model-next-pilot-selection-after-workbench-relation.md` and `read-model-next-pilot-selection-after-pending-invoice.md` both ranked `input_invoice_usage` high but deferred it until the pending/OA patterns were proven.
- `read-model-oa-pending-payment-local-implementation-closure-audit.md` records the shared `invoice-usage-collection` worker/projection path as locally accounted for for OA pending payment, while keeping production evidence deferred and Go blocked.
- `READ_MODEL_MANIFEST["input_invoice_usage"]` defines a narrow scoped-incremental read model contract with `InputInvoiceUsageReadModelService` query owner, `PostgresReadModelRepository.input_invoice_usage` repository owner and `tests/test_input_invoice_usage_api.py` test owner.
- `04-IMPLEMENTATION-ROADMAP.md` still requires non-Go modular IO/read model implementation prerequisites before any Go hot-path admission.

Module evidence:

- `docs/modules/input-invoice-usage/README.md` requires production rows, filter/export helpers and relation details to use SQL read model data and to avoid live scan fallback when SQL runtime is required.
- `docs/modules/input-invoice-usage/README.md` also defines `input_invoice_usage:all` as fan-out to month shards, with all-query freshness proven from actual rows/month scopes and active dirty/outbox status.
- `docs/modules/read-models/README.md` requires relation-backed page read models to include `workbench_relation` source versions and prevents fan-out-only `all` scopes from pretending fresh.
- `docs/modules/output-invoice-collections/README.md` shows the output candidate is important but broader because it layers lifecycle facts, receipt lifecycle, status rules and downstream tax/cost dependencies on top of the same shared worker family.

Code evidence:

- CodeGraph identified `InvoiceUsageCollectionSqlProjectionBuilder` as the shared worker projection owner for `input_invoice_usage`, `output_invoice_collection` and `oa_pending_payment`.
- `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py` still writes input usage rows through the broad `PostgresReadModelRepository` methods:
  - `save_input_invoice_usage_rows`
  - `mark_input_invoice_usage_scope`
  - `prune_input_invoice_usage_scope_shards`
  - `list_input_invoice_usage_scope_shards`
- `backend/src/fin_ops_platform/app/server.py` still wires `_input_invoice_usage_sql_read_repository` from `state_store.input_invoice_usage_sql_read_repository` and reads it from input usage rows/filter/export/detail helpers.
- No narrow `input_invoice_usage_read_model_repository.py` port exists yet.
- `tests/test_input_invoice_usage_api.py` and `tests/test_invoice_usage_collection_sql_runtime.py` already provide useful regression leverage for SQL read-model detail reads, repository unavailable behavior, source-version stale behavior, all-scope fan-out/pruning and shared projection builder behavior.

## Next Boundary Contract

`read-models:input-invoice-usage-repository-port-extraction` should:

- add a narrow `InputInvoiceUsageReadModelRepositoryPort`;
- expose only the manifest-listed input invoice usage read-model methods:
  - `list_input_invoice_usage_rows`
  - `save_input_invoice_usage_rows`
  - `mark_input_invoice_usage_scope`
  - `prune_input_invoice_usage_scope_shards`
  - `get_input_invoice_usage_row_by_row_id`
- decide during implementation whether `list_input_invoice_usage_scope_shards` belongs in the same port or a projection-only helper port, based on current worker fan-out call sites;
- wire PostgreSQL state-store input usage read repository and the input-usage portions of `InvoiceUsageCollectionSqlProjectionBuilder` through the narrow port where they currently pass the broad read model repository;
- preserve rows/filter-options/export/detail response shape, `read_model_status`, stale reasons, source-version proof, `all` fan-out/month shard behavior, payment-status rule source version behavior and relation-detail payload shape;
- add tests proving unrelated read model repository methods are not exposed through the port;
- avoid touching OA reverse draft creation, OA credential/token flows, Workbench relation command behavior, payment status business rules, UI behavior, worker runtime, Go/Fiber/Go Worker or production state.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/input-invoice-usage/state-machine.md`

No global or module state definition changed. This slice only changes autonomous queue/accounting.

The transition is slice-only:

- Previous queue item: `read-models:next-pilot-selection-after-oa-pending-payment`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:input-invoice-usage-repository-port-extraction`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Categories

This slice is analysis-only, so no runtime tests are added.

For the next implementation slice:

| Category | Applies? | Reason |
| --- | --- | --- |
| Business core unit tests | Not directly for repository port extraction; payment status and OA reverse business rules must remain unchanged and covered by existing tests. |
| Service-layer tests | Applies. Prove input usage read-model consumers can use a narrow port without broad repository access. |
| API contract tests | Applies if route/state-store wiring changes; preserve rows/filter-options/export/detail response shapes and refreshing/fresh statuses. |
| Read model/cache/background job tests | Applies. Preserve save/mark/prune, all fan-out, month shard rebuild, source-version stale behavior and no-live-scan production behavior. |
| Frontend component and interaction tests | Not directly for the first port extraction unless response shape or operation barrier targets change; UI behavior must remain unchanged. |
| End-to-end business-flow integration tests | Not directly for repository port extraction; relation and OA reverse flows stay unchanged. |
| Existing feature regression tests | Applies. Keep rows, detail drawer, filter/export behavior, source-version proof and projection builder runtime behavior unchanged. |

## Verification

Required for this analysis-only slice:

```bash
bash scripts/verify.sh docs
git diff --check
```

No application tests are required because runtime code is unchanged.

## Completion Claim

This slice only selects and queues the next pilot. It does not close `input_invoice_usage`, `oa_pending_payment`, the read model roadmap, or any Go hot-path gate.
