# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:output-invoice-collection-relation-detail-production-repository-fail-closed` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:output-invoice-collection-relation-detail-production-repository-fail-closed`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `output_invoice_collection` is the sixth non-Go read model pilot.
- `OutputInvoiceCollectionReadModelRepositoryPort` exists and is wired for PostgreSQL state-store reads and projection save/mark/prune paths.
- Output collection freshness/barrier/helper audit is locally implemented:
  - mutation responses expose `read_model_scope_keys` and `freshness_targets`;
  - frontend lifecycle, receipt and red/blue relation write-after-read flows prefer concrete month targets over fan-out-only `all`;
  - `output_invoice_collection:all` remains fan-out control scope;
  - unused `Application` output projection helpers were removed and guarded.
- Output collection relation detail production fail-closed support is locally implemented:
  - `OutputInvoiceCollectionReadModelDetailService` reads fresh SQL read-model rows for relation details;
  - production SQL runtime returns `202`/refreshing and enqueues `output_invoice_collection:all` when the SQL repository/detail lookup is unavailable;
  - relation detail no longer falls back to live query in production SQL runtime.
- `output_invoice_collection` is not globally closed. Local closure accounting and real PostgreSQL/worker/App Status/high-row/browser evidence remain open or deferred.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:output-invoice-collection-local-implementation-closure-audit`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-refresh-freshness-operation-barrier-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-input-invoice-usage.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/output-invoice-collections/state-machine.md`
   - `docs/modules/output-invoice-collections/tests.md`
   - `docs/modules/output-invoice-collections/implementation-notes.md`
6. Use CodeGraph for structural lookup before implementation or closure accounting edits.

## Boundary Scope

Target:

- Account for local `output_invoice_collection` implementation support after:
  - repository port extraction;
  - rows/filter/export/detail fresh gate and production fail-closed behavior;
  - source-version proof;
  - scope policy validation;
  - worker `all` fan-out/month shard behavior;
  - lifecycle/receipt/red relation operation barrier target contract;
  - app-level projection helper removal;
  - tests/docs coverage.
- Classify remaining output collection live/detail support after relation detail production fail-closed as implemented, compat-only, out of read-model scope, or requiring another narrow implementation slice.
- Decide whether local implementation support can move to `production-evidence-deferred` or whether another concrete local gap must be split before defer.
- Produce/update an analysis/accounting file.
- Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected module docs/tests.

Forbidden:

- Do not change lifecycle write business rules, receipt numbering/history behavior, red/blue relation semantics, UI behavior, worker runtime, Go/Fiber/Go Worker or production state.
- Do not claim `output_invoice_collection` globally closed unless every full closure requirement is proven.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `bash scripts/verify.sh docs`
- `git diff --check`
- Targeted backend/frontend tests only if local closure accounting changes runtime code or tests.

## Stop Condition

Complete one verified output invoice collection local implementation closure accounting slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
