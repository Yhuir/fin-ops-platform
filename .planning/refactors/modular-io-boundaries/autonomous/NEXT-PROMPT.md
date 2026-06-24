# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:next-pilot-selection-after-input-invoice-usage` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:next-pilot-selection-after-input-invoice-usage`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `input_invoice_usage` local implementation support is accounted for, but real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- `output_invoice_collection` is selected as the next non-Go read model pilot.
- Selection reason: it is the remaining invoice-usage-collection page read model, shares the worker/projection family with input usage and OA pending payment, and has high stale-read/export/lifecycle risk.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:output-invoice-collection-repository-port-extraction`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-input-invoice-usage.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-input-invoice-usage-local-implementation-closure-audit.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/output-invoice-collections/state-machine.md`
   - `docs/modules/output-invoice-collections/tests.md`
   - `docs/modules/output-invoice-collections/implementation-notes.md`
6. Read target code and tests:
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/postgres_state_store.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
   - `backend/src/fin_ops_platform/services/output_invoice_collection_service.py`
   - `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
   - `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
   - `backend/src/fin_ops_platform/app/worker.py`
   - `tests/test_invoice_usage_collection_sql_runtime.py`
   - `tests/test_output_invoice_collection_api.py`
7. Use CodeGraph for structural lookup before implementation edits.

## Boundary Scope

Target:

- Add `OutputInvoiceCollectionReadModelRepositoryPort`.
- Expose only the manifest-listed output invoice collection read-model methods:
  - `list_output_invoice_collection_rows`
  - `save_output_invoice_collection_rows`
  - `mark_output_invoice_collection_scope`
  - `prune_output_invoice_collection_scope_shards`
- Wire PostgreSQL state-store output collection read repository and the output-collection portions of `InvoiceUsageCollectionSqlProjectionBuilder` through the narrow port.
- Add or update tests proving unrelated read model repository methods are not exposed through the output port.
- Preserve rows/filter-options/export/detail response shape, `read_model_status`, stale reasons, source-version proof, `all` fan-out/month shard behavior, lifecycle overlay behavior, receipt facts and red/blue relation behavior.
- Produce/update an analysis/accounting file.
- Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and module docs/tests as needed.

Forbidden:

- Do not change lifecycle write behavior, receipt service behavior, red/blue relation commands, UI behavior, worker runtime, Go/Fiber/Go Worker or production state.
- Do not remove output app-level projection helpers in this repository-port slice unless implementation proves a concrete unused unsafe helper and the removal remains narrow; otherwise leave helper removal for the following freshness/helper audit.
- Do not declare `output_invoice_collection` globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `python3 -m py_compile` for changed backend/test files.
- Targeted unittest coverage for the new port and existing output SQL runtime/API behavior.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` if app wiring changes.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified output invoice collection repository port extraction slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
