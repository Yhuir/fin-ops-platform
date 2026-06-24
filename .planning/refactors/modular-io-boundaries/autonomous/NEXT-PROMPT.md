# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:turnover-ledger-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:turnover-ledger-local-implementation-closure-audit`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- `turnover_ledger` is the tenth non-Go read model implementation pilot.
- `TurnoverLedgerReadModelRepositoryPort` is implemented and wired into PostgreSQL state-store read wiring, app query injection and worker projection save paths.
- Turnover freshness/barrier evidence is locally accounted for: SQL fresh gate, month/all scope policy, manifest/App Status/worker registration, Workbench relation source-version proof and operation barrier targets.
- `TurnoverLedgerReadModelRefreshProducer` owns non-transactional turnover refresh enqueue and best-effort clear.
- Turnover refresh enqueue stays behind `ReadModelRefreshGateway` and the `turnover_ledger` scope policy.
- Turnover clear uses the turnover-specific repository port, not broad `_workbench_sql_read_repository`.
- Turnover local closure audit found no remaining local implementation gap.
- `turnover_ledger` is `production-evidence-deferred`, not globally closed.
- Real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- Remaining non-Go read model candidates include `no_oa_bank_batch`, `search` and `bank_account_balance`.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:next-pilot-selection-after-turnover-ledger`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile:
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-turnover-ledger-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-cost-statistics.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/no-oa-bank-batch/README.md`
   - `docs/modules/search/README.md`
   - any existing docs for `bank_account_balance` or bank account balance read model ownership
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
   - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
   - relevant tests for no-OA bank batch, search and bank account balance
6. Use CodeGraph for structural lookup before selecting the next pilot.

## Boundary Scope

Target:

- Compare remaining non-Go read model candidates: `no_oa_bank_batch`, `search`, and `bank_account_balance`.
- Choose exactly one next pilot based on current architecture risk, stale-read risk, user-visible impact, repository-port narrowness, freshness/operation-barrier gaps, worker/App Status contract, and test coverage.
- Produce or update one analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected module docs/tests as applicable.
- Insert the selected pilot's first narrow implementation boundary before Go/Fiber/Go Worker admission items.
- Keep Go/Fiber/Go Worker blocked unless no earlier modular IO/read model implementation-pending or implementation-gap-open work remains.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not start repository-port extraction in the same slice; this boundary is selection/accounting only unless state reconciliation finds a hard inconsistency.
- Do not change business rules, API shapes, worker event names, queue schema, Redis/cache behavior, permissions, audit meaning or frontend behavior.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted static/rg/CodeGraph evidence for the three candidate modules.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified next-pilot selection slice, commit and push to `origin/dev`, then continue to the selected first implementation boundary unless a hard stop gate is hit.
