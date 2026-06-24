# Next Prompt

Continue after `read-models:turnover-ledger-grouped-query-metadata-boundary-fix`.

## Current State

- Branch: `dev`.
- Active production release before the next deploy remains `dev-no-oa-source-version-480d2d0e-20260625` at git commit `d117b4519284db00c0fa88bdf7faaa938a5b1f69`.
- Row285 full user-scope API metadata smoke passed 37/37 probes, but aggregate postcheck showed one hidden `turnover_ledger:all` refresh enqueue.
- Row286 focused diagnosis proved live grouped turnover GET returned no top-level read-model metadata while creating one `turnover_ledger.read_model.refresh` / `turnover_ledger:all` dirty scope.
- Row287 local fix changed `TurnoverLedgerApiRoutes._flat_payload_to_grouped(...)` so SQL/read-model top-level metadata is preserved while legacy `rows` is removed and grouped fields are overwritten.
- Row287 tests added:
  - `test_get_turnover_ledger_grouped_preserves_fresh_sql_read_model_metadata`;
  - `test_get_turnover_ledger_grouped_preserves_stale_sql_refresh_metadata`.
- Row287 verification passed:
  - targeted turnover grouped/query tests: `10 passed`;
  - broader `tests/test_turnover_ledger_api.py tests/test_turnover_ledger_query_service.py tests/test_turnover_ledger_read_facade.py`: `148 passed`, `31 subtests passed`;
  - compileall passed;
  - docs and diff checks passed before commit.
- Browser/admin/write probes and global/module closure remain open.

## Next Boundary

`production:turnover-ledger-grouped-metadata-fix-deploy-and-resmoke`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and `origin/dev` contains the Row287 commit.
2. Write a bounded pre-operation runbook under `.planning/refactors/modular-io-boundaries/analysis/production-turnover-ledger-grouped-metadata-fix-deploy-and-resmoke-2026-06-25.md` before any production command.
3. Precheck, without printing secrets or payload rows:
   - active release and release git commit;
   - `/health` and `/health/ready`;
   - dirty scope status counts;
   - App Status readiness status counts;
   - read-model outbox status counts;
   - read-model dead-letter counts;
   - recent `turnover_ledger` outbox/dirty latest timestamps.
4. Deploy the latest `dev` commit with `./scripts/deploy-oa.sh --release-name <bounded-turnover-grouped-metadata-release>`.
5. Run only focused authenticated user-scope metadata re-smoke for `GET /api/turnover-ledger?view=grouped&page=1&page_size=50` through the existing target OA applicant credential seam, with no secrets, response bodies, payload rows or business identifiers printed.
6. Postcheck the same aggregate health/dirty/readiness/outbox/dead-letter and recent turnover outbox/dirty evidence.

## Resmoke Expectations

- Focused grouped turnover response must expose top-level metadata keys, including at least `read_model_status` and `refresh_enqueued`.
- If production is fresh, expected result is HTTP 200, `read_model_status=fresh`, `refresh_enqueued=false`, and no aggregate turnover enqueue delta.
- If production still enqueues, response metadata must make that visible (`refresh_enqueued=true` and reason/stale metadata where available), and the aggregate delta must be classified.
- Do not run full user-scope API smoke until the focused turnover grouped probe and aggregate postcheck are understood.

## Required Verification

- Production runbook committed/pushed before deploy if it changes repository files.
- Deployment release recorded with release name and git commit.
- Focused metadata probe result recorded with sanitized metadata only.
- Postcheck result recorded and committed/pushed.

## Stop Gates

- Do not broaden into full user-scope, browser, admin or write probes in this boundary.
- Do not print or store tokens, cookies, passwords, env values, response bodies, payload rows or business identifiers.
- Do not manually refresh, requeue, repair, replay, mark readiness, or directly mutate DB state unless a new runbook is written for that separate operation.
- Do not claim module/global closure from this deploy/re-smoke alone.
