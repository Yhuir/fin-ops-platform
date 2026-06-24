# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:next-pilot-selection-after-no-oa-bank-batch` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:next-pilot-selection-after-no-oa-bank-batch`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `no_oa_bank_batch` local implementation support is accounted for but not globally closed; real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- `search` is selected as the twelfth non-Go read model pilot.
- `bank_account_balance` remains a later implementation-gap-open candidate.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:search-repository-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-no-oa-bank-batch.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-and-no-oa-bank-batch-contract.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-manifest-and-boundary-inventory.md`
   - `docs/modules/search/README.md`
   - `docs/modules/search/state-machine.md`
   - `docs/modules/search/tests.md`
   - `docs/modules/search/implementation-notes.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
   - `backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
   - `tests/test_search_pending_sql_runtime.py`
   - `tests/test_search_api.py`
   - `tests/test_read_model_manifest.py`
6. Use CodeGraph for `search_index`, `save_search_index_rows`, `SearchPendingSqlProjectionBuilder`, `_get_search_payload_from_sql_read_model`, and `_search_sql_read_repository` before editing.

## Boundary Scope

Target:

- Add a narrow `SearchReadModelRepositoryPort` exposing only manifest-listed `search_index(...)` and `save_search_index_rows(...)`.
- Wire `/api/search` SQL read model access and `SearchPendingSqlProjectionBuilder.rebuild_search_index_scope(...)` through the narrow port.
- Update manifest repository owner to the new port if the port becomes the application/projection owner.
- Add or update tests proving the port does not expose unrelated read model methods and search behavior still reads/saves through the expected boundary.
- Update search/read-model module docs and autonomous state files.

Forbidden:

- Do not change search ranking, query filters, group context, response shape, permission behavior, worker event names, scope policy, queue schema, Redis/cache behavior or frontend behavior.
- Do not remove app-owned search helpers in this slice unless call graph proves they are unused after port wiring; helper quarantine should be a follow-up boundary.
- Do not implement Go/Fiber/Go Worker.
- Do not mark `search` or any module globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted search tests, at minimum:
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified `search` repository port extraction slice, commit and push to `origin/dev`, then continue to the next search freshness/helper audit boundary unless a hard stop gate is hit.
