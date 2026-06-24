# Next Prompt

Continue after `production:read-model-full-user-scope-api-metadata-smoke-after-turnover-fixes`.

## Current State

- Branch: `dev`.
- Active production release is `dev-turnover-source-version-persistence-20260625` at git commit `8f525563e10972168014356ff410c4fc8456f377`.
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
- Row291 production convergence:
  - precheck mismatch `turnover_relation_snapshot_version_mismatch`, expected hash prefix `7c63fec7ba82c80c`, persisted hash prefix `198f5fd5f7ccbb8a`;
  - deployed `dev-turnover-source-version-persistence-20260625`;
  - first focused grouped GET exposed `read_model_status=refreshing`, `refresh_enqueued=true`, stale reason `turnover_relation_snapshot_version_mismatch`;
  - after worker convergence, persisted top-level and first-row hash prefixes both matched expected `7c63fec7ba82c80c`, mismatch reasons were empty;
  - post-convergence focused grouped GET returned HTTP `200`, `read_model_status=fresh`, `refresh_enqueued=false`, elapsed `67.957ms`;
  - final aggregate postcheck stayed `/health/ready=ready`, dirty `done=187061`, readiness `fresh=498`, outbox `done=202956`, dead letters none, no additional turnover dirty/outbox delta after recheck.
- Row292 full non-admin user-scope API smoke:
  - ran 37 non-admin `http_slo_probe.DEFAULT_API_PROBES` through target OA applicant credentials;
  - status `pass`;
  - failed probes `0`;
  - non-fresh probes `0`;
  - refresh-enqueued probes `0`;
  - pre/post aggregate dirty scopes `done=187061`, readiness `fresh=498`, read-model outbox `done=202956`, dead letters none;
  - recent turnover/no-OA dirty/outbox aggregates unchanged.
- Browser/admin/write probes and global/module closure remain open.

## Next Boundary

`planning:post-full-user-api-smoke-browser-admin-write-evidence-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row292 evidence if it is not already committed.
3. Reconcile remaining global closure gaps:
   - production browser evidence;
   - admin-scope API evidence;
   - write-flow evidence;
   - any remaining module-specific high-row/worker/readiness gap not covered by Rows245/257/291/292.
4. Select exactly one next bounded evidence boundary and write it to queue/state/next prompt.
5. Do not execute browser/admin/write commands in this planning boundary.

## Selection Criteria

- Prefer the smallest production evidence boundary that materially advances global closure.
- Browser/admin/write evidence must have a runbook before execution.
- Use existing target OA applicant credential seam only for user-scope; admin evidence requires an explicit existing non-secret admin seam or must be deferred/classified.

## Required Verification

- Planning analysis committed/pushed.
- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.

## Stop Gates

- Do not run browser, admin or write probes in this planning boundary.
- Do not print or store secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows or business identifiers.
- Do not claim module/global closure from selection alone.
