# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:pending-invoice-mutation-freshness-target-contract` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:pending-invoice-mutation-freshness-target-contract`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `pending_invoice` is the active non-Go read model implementation pilot.
- `PendingInvoiceReadModelRepositoryPort` is wired.
- Freshness/barrier audit is analysis-closed.
- Pending invoice scope policy now rejects unsupported expense/income filter groups at gateway validation.
- Income-status mutations now wait for `pending_invoice` operation barrier targets before refetching rows; backend response shape remains unchanged.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:pending-invoice-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-mutation-freshness-target-contract.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-scope-policy-filter-allowlist.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-refresh-freshness-operation-barrier-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-repository-port-extraction.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/pending-invoices/tests.md`
   - `docs/modules/pending-invoices/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
   - `backend/src/fin_ops_platform/services/pending_invoice_service.py`
   - `backend/src/fin_ops_platform/services/pending_invoice_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
   - `backend/src/fin_ops_platform/services/pending_invoice_rules_application_service.py`
   - `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
   - relevant frontend pending invoice operation barrier callers.
5. Use CodeGraph for pending invoice read model/service/route impact before editing.
6. Update analysis/docs/state after verification.

## Boundary Scope

Target:

- Audit `pending_invoice` local implementation support after repository port extraction, freshness/barrier audit, scope policy filter allowlist and mutation barrier slices.
- Decide whether local implementation support can be recorded as production-evidence-deferred, or whether another small non-Go implementation gap remains.
- Verify read boundary, refresh boundary, mutation barrier, scope policy, legacy contamination, docs and tests are accounted for.
- If a new local implementation gap is found and is narrow, insert it before Go candidates and execute it next; otherwise record closure/defer accounting and select the next non-Go read model pilot.

Forbidden:

- Do not change pending invoice business rules, relation write behavior, status meanings or UI workflow.
- Do not broaden API shape without a separate API contract slice and tests proving existing clients remain compatible.
- Do not implement Go/Fiber/Go Worker.
- Do not mark any module globally closed.
- Do not rely on staging DB or local `PGSQL_URL`.

## Expected Output

- One verified pending invoice local implementation closure audit/accounting slice.
- Updated analysis/docs/state/queue/next prompt.
- Targeted backend/frontend tests if behavior changes; otherwise document why analysis-only verification is sufficient.
- Docs verification and `git diff --check`; run targeted tests only if the audit changes behavior.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified pending invoice local implementation closure audit/accounting slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
