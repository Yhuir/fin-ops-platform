# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:next-pilot-selection-after-oa-pending-payment` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:next-pilot-selection-after-oa-pending-payment`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `input_invoice_usage` is selected as the fifth non-Go read model implementation pilot after `bank_detail`, `workbench_relation`, `pending_invoice` and `oa_pending_payment`.
- `input_invoice_usage` shares the `invoice-usage-collection` worker/projection family with `oa_pending_payment` and `output_invoice_collection`.
- The module has high stale-read/cross-page risk because rows, filter/export helpers and relation-details display Workbench relation-backed OA/bank/invoice evidence.
- Production PostgreSQL runtime must not fall back to `InputInvoiceUsageQueryService` live scan when the SQL read model repository/view/payload/source versions are missing or stale.
- `input_invoice_usage:all` remains a fan-out control scope; all-query freshness proof must come from concrete month rows/scopes and active dirty/outbox state.
- No runtime code changed in the selection slice.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:input-invoice-usage-repository-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile:
   - `.planning/ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
5. Read target docs:
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/input-invoice-usage/README.md`
   - `docs/modules/input-invoice-usage/state-machine.md`
   - `docs/modules/input-invoice-usage/tests.md`
   - `docs/modules/input-invoice-usage/implementation-notes.md`
6. Read target code/tests:
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
   - `backend/src/fin_ops_platform/services/input_invoice_usage_service.py`
   - `backend/src/fin_ops_platform/services/input_invoice_usage_read_model_detail_service.py`
   - `backend/src/fin_ops_platform/services/postgres_state_store.py`
   - `tests/test_input_invoice_usage_api.py`
   - `tests/test_invoice_usage_collection_sql_runtime.py`
7. Use CodeGraph for structural lookup before implementation edits.

## Boundary Scope

Target:

- Add a narrow `InputInvoiceUsageReadModelRepositoryPort`.
- Expose only input usage read-model methods from the manifest:
  - `list_input_invoice_usage_rows`
  - `save_input_invoice_usage_rows`
  - `mark_input_invoice_usage_scope`
  - `prune_input_invoice_usage_scope_shards`
  - `get_input_invoice_usage_row_by_row_id`
- Decide during implementation whether `list_input_invoice_usage_scope_shards` belongs in the same port or a projection-only helper port, based on current worker fan-out call sites.
- Wire PostgreSQL state-store input usage read repository and the input-usage portions of `InvoiceUsageCollectionSqlProjectionBuilder` through the narrow port where they currently pass the broad read model repository.
- Add or update tests proving unrelated read model repository methods are not exposed through the port.
- Preserve rows/filter-options/export/detail response shape, `read_model_status`, stale reasons, source-version proof, `all` fan-out/month shard behavior, payment-status rule source version behavior and relation-detail payload shape.

Forbidden:

- Do not change OA reverse draft creation, OA credential/token flows, Workbench relation command behavior, payment status business rules, UI behavior, worker runtime, Go/Fiber/Go Worker or production state.
- Do not declare `input_invoice_usage` or any other module globally closed.
- Do not rely on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.
- Do not start broad shared `PostgresReadModelRepository` splitting.

Expected output:

- One narrow implementation slice.
- Analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and `NEXT-PROMPT.md`.
- Updated module docs/tests matrix if the implementation changes ownership evidence.
- Targeted Python tests for input usage API/projection behavior plus docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified `input_invoice_usage` repository port extraction slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
