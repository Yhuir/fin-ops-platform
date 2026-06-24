# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:next-pilot-selection-after-output-invoice-collection` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:next-pilot-selection-after-output-invoice-collection`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `invoice_lifecycle` is selected as the seventh non-Go read model implementation pilot.
- Reason: `invoice_lifecycle` is the shared upstream lifecycle state boundary for pending invoice, input invoice usage, output invoice collection, OA pending payment, tax offset, cost/search and import fan-out.
- No standalone `docs/modules/invoice-lifecycle/` module exists. Use `docs/modules/read-models/`, `docs/modules/domain-events-lifecycle/`, `docs/modules/pending-invoices/`, `docs/modules/input-invoice-usage/`, `docs/modules/output-invoice-collections/`, `docs/modules/oa-pending-payments/`, `docs/modules/tax-offset/`, and `docs/modules/imports-invoices/` as the relevant fact sources.
- `invoice_lifecycle` currently has manifest-listed repository methods but no narrow repository port; `InvoiceLifecycleReadFacade` and `InvoiceLifecycleSqlProjectionBuilder` still use broad read repository methods directly.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:invoice-lifecycle-repository-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile:
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
5. Read target planning evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-output-invoice-collection.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-and-usage-contract.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-repository-port-and-sql-owner-split-plan.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/domain-events-lifecycle/README.md`
   - `docs/modules/domain-events-lifecycle/tests.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/input-invoice-usage/README.md`
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/oa-pending-payments/README.md`
   - `docs/modules/tax-offset/README.md`
   - `docs/modules/imports-invoices/README.md`
6. Use CodeGraph for structural lookup before implementation edits.

## Boundary Scope

Target:

- Add `InvoiceLifecycleReadModelRepositoryPort`.
- Expose only manifest-listed methods:
  - `save_invoice_lifecycle_rows(...)`
  - `mark_invoice_lifecycle_scope(...)`
  - `get_invoice_lifecycle_rows_by_subject_ids(...)`
  - `get_invoice_lifecycle_rows_by_identity_keys(...)`
  - `list_invoice_lifecycle_rows(...)`
- Wire `InvoiceLifecycleReadFacade` and `InvoiceLifecycleSqlProjectionBuilder` through the narrow port.
- Inspect PostgreSQL state-store read wiring; if an invoice lifecycle SQL read repository property exists or is needed by existing construction, return the narrow port there. Do not create speculative wiring if there is no caller.
- Add a repository-port isolation test proving unrelated read model methods are not exposed.
- Update `READ_MODEL_MANIFEST["invoice_lifecycle"].repository_owner` if the port becomes the owner.
- Update modular IO analysis/state docs and read-models module docs/tests.

Forbidden:

- Do not change invoice lifecycle business rules, acquisition/certification/payment status semantics, payload shape, source-version semantics, worker event semantics, queue schema, API behavior, frontend behavior, Go/Fiber/Go Worker or production state.
- Do not create a broad service abstraction or split unrelated SQL methods.
- Do not claim `invoice_lifecycle` globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted py_compile for touched backend/test files.
- Targeted invoice lifecycle repository/facade/refresh/manifest tests.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified invoice lifecycle repository port extraction slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
