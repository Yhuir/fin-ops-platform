# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:oa-pending-payment-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:oa-pending-payment-local-implementation-closure-audit`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- `oa_pending_payment` was the fourth non-Go read model implementation pilot after `bank_detail`, `workbench_relation`, and `pending_invoice`.
- `OaPendingPaymentReadModelRepositoryPort` is wired for rows/detail and projection save/mark/prune paths.
- Workbench relation source-version lookup for OA pending payment uses the Workbench relation port.
- OA pending payment rows/filter-options/detail freshness gates return refreshing/unavailable on missing/stale/source mismatch and enqueue through `ReadModelRefreshGateway`.
- OA pending payment `all` refresh is fan-out control scope; worker expansion enqueues concrete month shards and prunes orphan shards.
- Frontend write-after-read operation barrier selection prefers concrete month scopes over fan-out-only `all` when mutation responses return both.
- Unused app-level OA pending payment rebuild/list/mark/live helpers were removed from `Application`.
- Local OA pending payment implementation support is accounted for, but real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:next-pilot-selection-after-oa-pending-payment`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile:
   - `.planning/ROADMAP.md`
   - `.planning/refactors/README.md`
   - `.planning/refactors/modular-io-boundaries/README.md`
   - `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
5. Read the completed pilot closure audits:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-service-factory-collaborator-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-final-local-implementation-closure-and-production-evidence-defer.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-oa-pending-payment-local-implementation-closure-audit.md`
6. Read current read model contracts and remaining candidates:
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `docs/modules/input-invoice-usage/README.md`
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/cost-statistics/README.md`
   - `docs/modules/tax-offset/README.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - relevant tests/docs for the selected candidate.
7. Use CodeGraph for candidate structural context before writing analysis.

## Boundary Scope

Target:

- Compare remaining read model candidates after `oa_pending_payment` local accounting.
- Select exactly one next non-Go read model implementation pilot.
- Prefer the candidate with the highest stale-read/cross-page risk, clear IO boundary, manageable first implementation slice, and existing test leverage.
- Produce an analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and `NEXT-PROMPT.md`.
- Insert the first narrow implementation boundary for the selected candidate before Go candidates.
- Keep all Go/Fiber/Go Worker admissions blocked unless documented prerequisites are actually satisfied.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not declare any module globally closed.
- Do not rely on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.
- Do not start a broad global cleanup.

Expected output:

- One candidate-selection analysis slice.
- Queue/state updated so the selected pilot's first narrow implementation boundary is next.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the selected pilot's first implementation boundary if safe.

## Stop Condition

Complete one verified non-Go read model pilot selection slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
