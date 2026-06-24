# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:input-invoice-usage-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:input-invoice-usage-local-implementation-closure-audit`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- `input_invoice_usage` local implementation support is accounted for:
  - `InputInvoiceUsageReadModelRepositoryPort` owns rows/detail/save/mark/prune access.
  - PostgreSQL state-store read wiring returns the narrow port.
  - `InvoiceUsageCollectionSqlProjectionBuilder` owns input usage projection rebuild/list/mark/prune behavior.
  - rows/filter/export/detail SQL read paths are fresh-gated and enqueue refresh through `ReadModelRefreshGateway` on miss/stale/source-version mismatch.
  - production SQL runtime relation detail returns `202`/refreshing and enqueues `input_invoice_usage:all` when the SQL detail repository is unavailable.
  - unused app-level input usage projection helpers were removed from `Application`.
  - retained `Application` surfaces are route fresh gates, source-version providers, gateway-backed wrappers, import scope calculators, dependency assembly or mutation side-effect wrappers.
- Real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- `input_invoice_usage` is not globally closed.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:next-pilot-selection-after-input-invoice-usage`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile:
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
5. Read recent read model pilot selection and closure evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-workbench-relation.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-pending-invoice.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-oa-pending-payment.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-input-invoice-usage-local-implementation-closure-audit.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
   - `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
6. Read candidate module docs for remaining read model pages before selecting:
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/output-invoice-collections/tests.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `docs/modules/cost-statistics/README.md`
   - `docs/modules/cost-statistics/tests.md`
   - `docs/modules/tax-offset/README.md`
   - `docs/modules/tax-offset/tests.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/tests.md`
7. Use CodeGraph for structural lookup before editing planning files.

## Boundary Scope

Target:

- Compare remaining read model candidates and select the next non-Go pilot.
- Prefer a candidate that reuses already proven patterns and still reduces high stale-read/cross-page risk.
- Likely high-priority candidates include `output_invoice_collection` because it shares the invoice-usage-collection worker/projection family with `input_invoice_usage` and `oa_pending_payment`, but the selection must be revalidated from current manifest/docs/code.
- Produce an analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- Add the first narrow implementation boundary for the selected pilot, usually repository port extraction unless analysis proves another smaller prerequisite.
- Do not implement runtime code in the selection slice.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not run Go admission while non-Go read model candidates remain.
- Do not declare any module globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected output:

- One next-pilot selection analysis file.
- Updated queue/state/journal/next prompt/main controller prompt.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified next-pilot selection slice, commit and push to `origin/dev`, then continue to the selected pilot's first narrow implementation boundary unless a hard stop gate is hit.
