# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:search-app-rebuild-helper-quarantine` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:search-app-rebuild-helper-quarantine`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `search` is the twelfth non-Go read model pilot.
- `SearchReadModelRepositoryPort` owns manifest-listed `search_index(...)` and `save_search_index_rows(...)`.
- `Application.rebuild_search_index_scope(...)` and `_build_search_index_rows_for_month(...)` were removed; rebuild ownership stays in `SearchPendingSqlProjectionBuilder`.
- `search` remains `implementation-gap-open` because `/api/search` fresh/stale/miss payload assembly, expected source-version proof, refresh enqueue and invalidation helpers still live in `Application`.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:search-query-freshness-service-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-freshness-helper-boundary-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-app-rebuild-helper-quarantine.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-repository-port-extraction.md`
   - `docs/modules/search/README.md`
   - `docs/modules/search/state-machine.md`
   - `docs/modules/search/tests.md`
   - `docs/modules/search/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/search_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
   - `tests/test_search_pending_sql_runtime.py`
   - `tests/test_search_api.py`
6. Use CodeGraph for `_get_search_payload_from_sql_read_model`, `_search_index_expected_source_versions`, `_enqueue_search_read_model_refresh`, and `_invalidate_search_read_model_scopes`.

## Boundary Scope

Target:

- Move `/api/search` SQL fresh/stale/miss payload assembly out of `Application` into an explicit search query/freshness service.
- Move or inject expected source-version proof dependencies into that service without making the service depend on the whole `Application`.
- Keep refresh enqueue behind `ReadModelRefreshGateway`; the app may assemble the gateway or callback, but should not own search freshness logic.
- Preserve `/api/search` response shape, status code behavior, source-version stale reasons and enqueue reasons.
- Add service/API/architecture tests proving the route delegates freshness logic and no live scan/fake fresh behavior returns.

Forbidden:

- Do not change search ranking, query filters, group context, response shape, permission behavior, worker event names, scope policy, queue schema, Redis/cache behavior or frontend behavior unless a verified gap requires it and tests are updated.
- Do not implement Go/Fiber/Go Worker.
- Do not mark `search` or any module globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest -v`
- Relevant platform boundary guard tests.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified search query/freshness service extraction slice, commit and push to `origin/dev`, then continue to the next safe search boundary unless a hard stop gate is hit.
