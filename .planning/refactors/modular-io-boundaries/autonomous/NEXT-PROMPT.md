# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:output-invoice-collection-repository-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:output-invoice-collection-repository-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `output_invoice_collection` is the sixth non-Go read model pilot.
- `OutputInvoiceCollectionReadModelRepositoryPort` exists and is wired for PostgreSQL state-store reads and projection save/mark/prune paths.
- `output_invoice_collection` is not locally closed. Freshness, force refresh, all fan-out/month proof, operation barrier and app-level helper classification remain open.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:output-invoice-collection-refresh-freshness-operation-barrier-audit`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-input-invoice-usage.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/output-invoice-collections/state-machine.md`
   - `docs/modules/output-invoice-collections/tests.md`
   - `docs/modules/output-invoice-collections/implementation-notes.md`
6. Read target code and tests:
   - `backend/src/fin_ops_platform/services/output_invoice_collection_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
   - `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
   - `backend/src/fin_ops_platform/services/output_invoice_collection_service.py`
   - `tests/test_invoice_usage_collection_sql_runtime.py`
   - `tests/test_output_invoice_collection_api.py`
   - `tests/test_read_model_architecture_guards.py`
7. Use CodeGraph for structural lookup before implementation edits.

## Boundary Scope

Target:

- Audit output collection fresh gates for rows, filter options, export and relation details.
- Confirm force refresh and operation barrier targets for lifecycle, receipt and red/blue relation writes.
- Confirm `output_invoice_collection:all` remains a fan-out control scope and all-query freshness proof comes from concrete month rows/scopes plus active dirty/outbox state.
- Classify retained app-level output projection helpers:
  - `Application.list_output_invoice_collection_scope_shards(...)`
  - `Application.mark_output_invoice_collection_scope_empty(...)`
  - `Application.rebuild_output_invoice_collection_read_model_scope(...)`
- Remove unused unsafe helpers if call graph and tests prove they are dead; otherwise quarantine them as compat-only/gateway-backed with owner, caller list, deletion condition and forbidden writes.
- Add or update tests for any removed/quarantined helper or freshness/operation-barrier gap found.
- Produce/update an analysis/accounting file.
- Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and module docs/tests as needed.

Forbidden:

- Do not change lifecycle write business rules, receipt numbering/history behavior, red/blue relation semantics, UI behavior, worker runtime, Go/Fiber/Go Worker or production state.
- Do not claim `output_invoice_collection` local closure unless every local support surface is accounted for.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `python3 -m py_compile` for changed backend/test files.
- Targeted unittest coverage for output freshness/helper behavior.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` if app wiring changes.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified output invoice collection freshness/helper audit slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
