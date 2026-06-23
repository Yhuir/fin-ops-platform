# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:pending-invoice-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:pending-invoice-local-implementation-closure-audit`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- `pending_invoice` was the active non-Go read model implementation pilot and is now locally accounted for.
- `PendingInvoiceReadModelRepositoryPort` is wired.
- Freshness/barrier audit is analysis-closed.
- Pending invoice scope policy now rejects unsupported expense/income filter groups at gateway validation.
- Income-status mutations now wait for `pending_invoice` operation barrier targets before refetching rows; backend response shape remains unchanged.
- Real pending_invoice PostgreSQL/worker/App Status/high-row/browser evidence remains deferred, so the module is not globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:next-pilot-selection-after-pending-invoice`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-workbench-relation.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-bank-detail.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pilot-gap-audit-and-contract-selection.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-repository-port-and-sql-owner-split-plan.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - module docs/tests/implementation notes for the top remaining candidate modules.
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
5. Use CodeGraph for top candidate service/route/read model impact before editing.
6. Update analysis/docs/state after verification.

## Boundary Scope

Target:

- Select the next non-Go read model implementation pilot after pending_invoice.
- Compare remaining candidates using current manifest contracts, module docs, tests, cross-page freshness value, blast radius, and existing local coverage.
- Decide the next first implementation boundary, preferably a narrow repository-port or owner-boundary extraction matching the successful bank_detail/workbench_relation/pending_invoice pattern.
- Insert the selected next implementation boundary before Go candidates.

Forbidden:

- Do not change pending invoice business rules, relation write behavior, status meanings or UI workflow.
- Do not broaden API shape without a separate API contract slice and tests proving existing clients remain compatible.
- Do not implement Go/Fiber/Go Worker.
- Do not mark any module globally closed.
- Do not rely on staging DB or local `PGSQL_URL`.

## Expected Output

- One verified next-pilot selection slice.
- Updated analysis/docs/state/queue/next prompt.
- No runtime tests unless code changes; otherwise docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified next-pilot selection slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the selected implementation boundary unless a hard stop gate is hit.
