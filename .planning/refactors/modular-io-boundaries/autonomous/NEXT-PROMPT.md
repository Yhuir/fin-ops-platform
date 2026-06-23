# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:pending-invoice-scope-policy-filter-allowlist` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:pending-invoice-scope-policy-filter-allowlist`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `pending_invoice` is the active non-Go read model implementation pilot.
- `PendingInvoiceReadModelRepositoryPort` is wired.
- Freshness/barrier audit is analysis-closed.
- Pending invoice scope policy now rejects unsupported expense/income filter groups at gateway validation.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:pending-invoice-mutation-freshness-target-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-scope-policy-filter-allowlist.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-refresh-freshness-operation-barrier-audit.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/pending-invoices/tests.md`
   - `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
   - `backend/src/fin_ops_platform/services/pending_invoice_service.py`
   - `backend/src/fin_ops_platform/services/pending_invoice_rules_application_service.py`
   - `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
   - relevant frontend pending invoice operation barrier callers.
5. Use CodeGraph for mutation response impact before editing.
6. Update analysis/docs/state after verification.

## Boundary Scope

Target:

- Audit pending invoice mutation responses and frontend callers for rules update, attach-existing confirm and income-status updates.
- Decide whether the production-grade contract should add `freshness_targets` to these responses or document the current page-local refresh/barrier contract.
- If adding targets is safe and narrow, implement with tests; otherwise close as analysis with the next narrower implementation boundary.

Forbidden:

- Do not change pending invoice business rules, relation write behavior, status meanings or UI workflow.
- Do not broaden API shape without tests proving existing clients remain compatible.
- Do not implement Go/Fiber/Go Worker.
- Do not mark any module globally closed.
- Do not rely on staging DB or local `PGSQL_URL`.

## Expected Output

- One verified mutation freshness target contract slice.
- Updated analysis/docs/state/queue/next prompt.
- Targeted backend/frontend tests if behavior changes.
- `python3 -m py_compile` for touched backend/test files, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified mutation freshness target contract slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
