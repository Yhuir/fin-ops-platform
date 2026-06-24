# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:output-invoice-collection-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:output-invoice-collection-local-implementation-closure-audit`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- `output_invoice_collection` is the sixth non-Go read model pilot.
- `OutputInvoiceCollectionReadModelRepositoryPort` is wired for PostgreSQL state-store reads and projection save/mark/prune paths.
- Output collection rows/filter/export/detail freshness behavior is locally accounted for:
  - production SQL runtime rows/filter/export miss/stale/schema/source-version mismatch returns refreshing and enqueues refresh;
  - production SQL runtime relation detail uses `OutputInvoiceCollectionReadModelDetailService`;
  - missing SQL repository/detail lookup returns `202`/refreshing and enqueues `output_invoice_collection:all`;
  - legacy/local non-production mode may still use `OutputInvoiceCollectionQueryService.row_relation_details(...)` as compat-only read support.
- Output collection mutation operation barrier behavior is locally accounted for:
  - lifecycle, reminder, red/blue relation and receipt mutations expose `read_model_scope_keys` / `freshness_targets`;
  - frontend flows prefer concrete month targets over fan-out-only `all`;
  - `output_invoice_collection:all` remains a fan-out control scope.
- Output collection app-level projection helpers were removed from `Application`; worker projection ownership remains in `InvoiceUsageCollectionSqlProjectionBuilder` / `InvoiceUsageCollectionReadModelRefreshService`.
- `output_invoice_collection` is not globally closed. Real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:next-pilot-selection-after-output-invoice-collection`

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
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/06-PILOT-SELECTION.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-manifest-and-boundary-inventory.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pilot-gap-audit-and-contract-selection.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-input-invoice-usage.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-local-implementation-closure-audit.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
6. Use CodeGraph for structural lookup before any implementation or accounting edits.

## Boundary Scope

Target:

- Select the next non-Go read model pilot from remaining implementation-gap-open manifest candidates.
- Compare remaining candidates by:
  - user-visible stale-read/cross-page risk;
  - read model repository-port gap;
  - freshness/source-version proof gap;
  - force-refresh and operation-barrier gap;
  - legacy contamination risk;
  - test coverage readiness;
  - ability to execute a narrow first slice without staging DB or local `PGSQL_URL`.
- Candidate pool should include remaining read-model modules that are not locally accounted yet, such as `invoice_lifecycle`, `no_oa_bank_batch`, `cost_statistics`, `tax_offset`, `turnover_ledger`, `search`, `bank_account_balance`, and any manifest entry whose implementation migration remains open.
- Produce/update an analysis file for the pilot selection.
- Insert the selected first narrow implementation boundary before Go candidates in `MODULE-QUEUE.md`.
- Update `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected read-model docs.

Forbidden:

- Do not select Go/Fiber/Go Worker while non-Go modular IO/read model implementation-gap-open work remains.
- Do not implement the selected pilot in this selection slice unless the queue already contains the implementation boundary and the selection slice has been committed.
- Do not claim any module globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `bash scripts/verify.sh docs`
- `git diff --check`
- Runtime backend/frontend tests only if runtime code or tests change.

## Stop Condition

Complete one verified next-pilot-selection slice, commit and push to `origin/dev`, then continue to the selected first implementation boundary unless a hard stop gate is hit.
