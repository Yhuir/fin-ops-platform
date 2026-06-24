# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:next-pilot-selection-after-turnover-ledger` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:next-pilot-selection-after-turnover-ledger`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `turnover_ledger` local implementation support is accounted for after repository port, freshness/barrier audit and refresh producer/clear extraction, but real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- `no_oa_bank_batch` is selected as the eleventh non-Go read model implementation pilot.
- Selection rationale: `no_oa_bank_batch` has the highest remaining page-level stale-read risk because it combines draft/submitted/withdrawn lifecycle, Bank Detail dependency, Workbench relation adjacency, public snapshot persistence, operation barrier requirements and cleanup of legacy exception states.
- Target verification fixed a stale no-OA refresh-service constructor keyword: `NoOaBankBatchReadModelRefreshService` now passes `pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(...)` to match the current application service contract.
- `search` remains a later candidate because it is a shared index with primary and compatibility worker lanes (`search`, `search-pending`, `search-secondary`, `search-tertiary`) and no standalone frontend route.
- `bank_account_balance` remains a later candidate because it is user-visible but currently a Bank Details supporting read model with a narrower scope.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:no-oa-bank-batch-repository-state-store-boundary-audit`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-turnover-ledger.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-and-no-oa-bank-batch-contract.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/state-machine.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `docs/product-specs/bank-turnover-and-no-oa.md`
   - `docs/app-architecture/runtime-and-ownership.md`
   - `docs/operations/runtime-worker-governance.md`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
   - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
   - `backend/src/fin_ops_platform/services/postgres_state_store.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
   - `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
   - `tests/test_no_oa_bank_batch_read_model_refresh.py`
   - `tests/test_no_oa_bank_batch_application_service.py`
   - `tests/test_no_oa_bank_batch_workbench_integration.py`
6. Use CodeGraph for structural lookup before selecting any implementation boundary.

## Boundary Scope

Target:

- Audit no-OA read model repository/state-store/public-snapshot/refresh-worker ownership.
- Classify all relevant surfaces as explicit boundary, compat-only, removed candidate or blocked-by-human-gate.
- Decide the first implementation extraction after the audit:
  - narrow `NoOaBankBatchReadModelRepositoryPort`;
  - refresh projection/state-store boundary extraction;
  - public snapshot persistence quarantine;
  - or a smaller prerequisite split.
- Produce or update one analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected module docs/tests as applicable.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not start repository-port extraction in this audit slice unless the audit proves the slice is already too small and safe; default stop condition is a documented next implementation boundary.
- Do not change business rules, API shapes, worker event names, queue schema, Redis/cache behavior, permissions, audit meaning or frontend behavior.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted static/rg/CodeGraph evidence for no-OA read model ownership.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_read_model_refresh tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_workbench_integration -v`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified no-OA repository/state-store boundary audit slice, commit and push to `origin/dev`, then continue to the selected first implementation boundary unless a hard stop gate is hit.
