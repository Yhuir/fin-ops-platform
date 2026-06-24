# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:tax-offset-post-full-state-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:tax-offset-post-full-state-local-implementation-closure-audit`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- `tax_offset` is the eighth non-Go modular IO/read model pilot.
- `tax_offset` local implementation support is accounted for after:
  - repository port extraction;
  - freshness/barrier audit;
  - worker rebuild executor extraction;
  - derived lifecycle executor extraction;
  - cache warmup executor extraction;
  - full-state snapshot quarantine;
  - post-quarantine local closure audit.
- `tax_offset` is not globally closed. Real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:next-pilot-selection-after-tax-offset`

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
   - `.planning/ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md`
   - `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-post-full-state-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - candidate module docs for remaining implementation-gap-open read models, including `cost-statistics`, `turnover-ledger`, `no-oa-bank-batches`, `search` if present, and `bank-details`/`bank-account-balance` related docs as needed.
6. Use CodeGraph for structural lookup before selecting a pilot.

## Boundary Scope

Target:

- Select exactly one next non-Go modular IO/read model pilot from remaining implementation-gap-open candidates.
- Prefer the candidate with the highest stale-read/cross-page consistency risk and a narrow first implementation boundary.
- Use actual code and test evidence, not only queue notes.
- Consider at minimum:
  - `cost_statistics`;
  - `turnover_ledger`;
  - `no_oa_bank_batch`;
  - `search`;
  - `bank_account_balance` / bank details adjacent read model work.
- Compare candidates by:
  - user-visible stale-read risk;
  - canonical fact owner clarity;
  - existing read model freshness/status boundary;
  - worker/outbox/readiness contract;
  - legacy/live fallback risk;
  - narrow first slice availability;
  - test coverage and regression blast radius;
  - dependency order after `bank_detail`, `workbench_relation`, `pending_invoice`, `oa_pending_payment`, `input_invoice_usage`, `output_invoice_collection`, `invoice_lifecycle`, and `tax_offset`.
- Produce an analysis file documenting the selection and first narrow boundary.
- Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not run Go admission while non-Go modular IO/read model implementation-pending or implementation-gap-open work remains.
- Do not claim any module globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.
- Do not change business semantics, amount rules, status transitions, permissions, audit meaning, API shape, queue schema, Redis key/envelope contract or frontend behavior during this selection slice.

Expected verification:

- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified next-pilot selection slice, commit and push to `origin/dev`, then continue to the selected first implementation boundary unless a hard stop gate is hit.
