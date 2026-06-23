# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:pending-invoice-repository-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:pending-invoice-repository-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `pending_invoice` is the active non-Go read model implementation pilot.
- `PendingInvoiceReadModelRepositoryPort` now narrows rows, filter-options, source-version and projection save/mark repository access.
- Search index behavior remains on the search repository; pending invoice projection save/mark uses the pending invoice port.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:pending-invoice-refresh-freshness-operation-barrier-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-and-oa-pending-payment-contract.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/pending-invoices/tests.md`
   - `docs/modules/pending-invoices/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
   - `backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
   - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
   - `tests/test_search_pending_sql_runtime.py`
5. Produce/update an analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit pending invoice freshness, force-refresh, special scope and operation barrier behavior after repository port extraction.
- Confirm `expense|income:<filter>[:YYYY-MM]` scope handling still rejects bare `all` and preserves page-first-screen force refresh semantics.
- Classify whether remaining gaps are local implementation gaps, compat-only paths, or production evidence gaps.
- If a local gap remains, insert the next narrow implementation boundary before Go.

Forbidden:

- Do not change pending invoice business rules, status meanings, relation write behavior, API response shape or UI behavior unless the audit proves a narrow bug and tests cover it.
- Do not implement Go/Fiber/Go Worker.
- Do not mark any module globally closed.
- Do not rely on staging DB or local `PGSQL_URL`.

## Expected Output

- One verified audit/accounting slice.
- Updated queue/state/journal/next prompt.
- Targeted verification, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified pending invoice freshness/barrier audit slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
