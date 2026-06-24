# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:search-repository-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:search-repository-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `search` is the twelfth non-Go read model pilot.
- `SearchReadModelRepositoryPort` now owns manifest-listed `search_index(...)` and `save_search_index_rows(...)`.
- `PostgresStateStore.search_sql_read_repository` and `SearchPendingSqlProjectionBuilder.rebuild_search_index_scope(...)` use the narrow port.
- `search` remains `implementation-gap-open` because app-owned fresh gate, source-version, enqueue, rebuild and invalidation helpers still need audit/extraction.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:search-freshness-helper-boundary-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-no-oa-bank-batch.md`
   - `docs/modules/search/README.md`
   - `docs/modules/search/state-machine.md`
   - `docs/modules/search/tests.md`
   - `docs/modules/search/implementation-notes.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
   - `backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/search_read_model_repository.py`
   - `tests/test_search_pending_sql_runtime.py`
   - `tests/test_search_api.py`
6. Use CodeGraph for `_get_search_payload_from_sql_read_model`, `_search_index_expected_source_versions`, `_enqueue_search_read_model_refresh`, `rebuild_search_index_scope`, `_build_search_index_rows_for_month`, and `_invalidate_search_read_model_scopes`.

## Boundary Scope

Target:

- Audit remaining app-owned search helper surfaces after repository port extraction.
- Classify each helper as dependency assembly, removable, compat-only, or implementation gap:
  - `Application._get_search_payload_from_sql_read_model(...)`
  - `Application._search_index_expected_source_versions(...)`
  - `Application._enqueue_search_read_model_refresh(...)`
  - `Application.rebuild_search_index_scope(...)`
  - `Application._build_search_index_rows_for_month(...)`
  - `Application._invalidate_search_read_model_scopes(...)`
- If a concrete implementation gap is found, split and execute the first narrow extraction/quarantine boundary.
- If only dependency assembly remains, record evidence without claiming global module closure.

Forbidden:

- Do not change search ranking, query filters, group context, response shape, permission behavior, worker event names, scope policy, queue schema, Redis/cache behavior or frontend behavior unless a verified gap requires it and tests are updated.
- Do not implement Go/Fiber/Go Worker.
- Do not mark `search` or any module globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted search tests when code changes:
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` when Python imports/manifests change.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified search freshness/helper audit or split and execute the first concrete implementation gap, commit and push to `origin/dev`, then continue to the next safe search boundary unless a hard stop gate is hit.
