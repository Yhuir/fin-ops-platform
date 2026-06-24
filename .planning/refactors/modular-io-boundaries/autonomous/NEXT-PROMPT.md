# Next Prompt

Continue after `read-models:turnover-ledger-refresh-source-version-persistence-contract-fix`.

## Current State

- Branch: `dev`.
- Active production release is `dev-turnover-grouped-metadata-20260625` at git commit `2dbacf9f6054baabe7084fc87b87511a49bbdb95`.
- Row285 full user-scope API metadata smoke passed 37/37 probes, but aggregate postcheck showed one hidden `turnover_ledger:all` refresh enqueue.
- Row286 focused diagnosis proved live grouped turnover GET returned no top-level read-model metadata while creating one `turnover_ledger.read_model.refresh` / `turnover_ledger:all` dirty scope.
- Row287 local fix changed `TurnoverLedgerApiRoutes._flat_payload_to_grouped(...)` so SQL/read-model top-level metadata is preserved while legacy `rows` is removed and grouped fields are overwritten.
- Row288 deployed that fix and focused authenticated `GET /api/turnover-ledger?view=grouped&page=1&page_size=50` now exposes metadata:
  - HTTP `200`;
  - `read_model_status=refreshing`;
  - `read_model_scope_key=all`;
  - `read_model_stale_reasons=["turnover_relation_snapshot_version_mismatch"]`;
  - `refresh_enqueued=true`;
  - `refresh_reason=source_version_mismatch`;
  - elapsed `110.729ms`;
  - group count `20`;
  - pagination page `1`, page size `50`, total `20`.
- Row288 postcheck stayed clean:
  - `/health/ready=ready`;
  - dirty scopes `done=187060`;
  - readiness `fresh=498`;
  - read-model outbox `done=202955`;
  - read-model dead letters none;
  - latest turnover outbox/dirty done at `2026-06-25 07:07:13+08`.
- Row289 read-only diagnosis:
  - API expected source versions and SQL projection provider source versions agree;
  - current expected/projection `turnover_relation_snapshot_version` hash prefix is `7c63fec7ba82c80c`;
  - persisted turnover read-model top-level and first-row `turnover_relation_snapshot_version` hash prefix is `198f5fd5f7ccbb8a`;
  - top-level and first-row mismatch reasons are both `turnover_relation_snapshot_version_mismatch`;
  - repository payload still says `read_model_status=fresh`;
  - App Status readiness remains `fresh=498`, dirty/outbox done and dead letters none.
- Row290 local fix:
  - `TurnoverLedgerSqlProjectionBuilder.rebuild_turnover_ledger_read_model_scope(...)` now captures source versions before `_collect_rows(ledger_service)`;
  - this prevents `TurnoverLedgerService.list_grouped_ledger()` / `rebuild_from_bank_rows(...)` in-memory relation rebuild side effects from changing the version persisted by the worker;
  - new test `test_projection_source_versions_are_captured_before_relation_rebuild_side_effects`;
  - verification passed: turnover refresh `9 passed`, turnover query/read-facade/API `148 passed`, `31 subtests passed`, compileall passed.
- Browser/admin/write probes and global/module closure remain open.

## Next Boundary

`production:turnover-ledger-source-version-persistence-fix-deploy-and-convergence`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row290 implementation if it is not already committed.
3. Write a bounded production deploy/convergence runbook under `.planning/refactors/modular-io-boundaries/analysis/production-turnover-ledger-source-version-persistence-fix-deploy-and-convergence-2026-06-25.md` before any production command.
4. Precheck active release, `/health/ready`, dirty/readiness/outbox/dead-letter aggregates and current turnover persisted source-version mismatch.
5. Deploy current `origin/dev` with the standard `./scripts/deploy-oa.sh --release-name ...` path.
6. Run focused authenticated grouped turnover metadata re-smoke only.
7. Run read-only persisted source-version comparison after the probe/refresh convergence.

## Production Expectations

- Focused grouped turnover response should expose metadata.
- Expected clean result after deploy/convergence: HTTP 200, `read_model_status=fresh`, `refresh_enqueued=false`, no `turnover_relation_snapshot_version_mismatch`, and persisted top-level/row-level `turnover_relation_snapshot_version` hash matching API expected.
- If a refresh is still enqueued, it must be visible and postcheck must classify convergence.

## Required Verification

- Runbook committed/pushed before deploy if it changes repository files.
- Deployment release and git commit recorded.
- Focused metadata probe and persisted source-version comparison recorded with sanitized metadata only.
- Postcheck health/dirty/readiness/outbox/dead-letter evidence recorded.
- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Do not broaden into full user-scope API, browser, admin or write probes in this boundary.
- Do not print or store secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows or business identifiers.
- Do not manually repair, direct-SQL mutate, mark readiness or run broad refresh/replay outside the runbook.
- Do not claim module/global closure from this deploy/convergence alone.
