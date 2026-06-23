# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:next-pilot-selection-after-workbench-relation` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:next-pilot-selection-after-workbench-relation`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `pending_invoice` is selected as the next non-Go read model implementation pilot.
- `pending_invoice` depends on both `bank_detail` and `workbench_relation` source versions and has special `expense|income:<filter>[:YYYY-MM]` scope semantics.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:pending-invoice-repository-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-workbench-relation.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-repository-port-and-sql-owner-split-plan.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-and-oa-pending-payment-contract.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/pending-invoices/tests.md`
   - `docs/modules/pending-invoices/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
   - `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `tests/test_search_pending_sql_runtime.py`
5. Produce/update an analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add a narrow `PendingInvoiceReadModelRepositoryPort` or equivalent narrow port.
- Expose only pending invoice read-model methods needed by the read service, source-version provider and projection builder:
  - `list_pending_invoice_rows`
  - `list_pending_invoice_filter_options`
  - `pending_invoice_source_summary`
  - `pending_invoice_bank_detail_source_versions`
  - `pending_invoice_workbench_relation_source_versions`
  - `save_pending_invoice_rows`
  - `mark_pending_invoice_scope`
- Decide whether `list_pending_invoice_scope_shards` belongs in the same port or a projection-only sub-port based on current call sites.
- Wire `PendingInvoiceReadModelService`, `PendingInvoiceSourceVersionsProvider` and `SearchPendingSqlProjectionBuilder` through the port where the app/worker currently passes the broad read model repository.
- Add tests proving unrelated read model repository methods are not exposed through the port.
- Preserve current payload shape, `read_model_status`, stale reasons, filter options, export row limit, source version behavior and scope semantics.

Forbidden:

- Do not change pending invoice business rules, status meanings, relation write behavior, API response shape or UI behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not mark any module globally closed.
- Do not rely on staging DB or local `PGSQL_URL`.

## Expected Output

- One verified `read-models:pending-invoice-repository-port-extraction` implementation slice.
- Updated tests for the narrow port and affected service/projection behavior.
- Updated queue/state/journal/next prompt.
- Targeted verification, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified pending invoice repository port extraction slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
