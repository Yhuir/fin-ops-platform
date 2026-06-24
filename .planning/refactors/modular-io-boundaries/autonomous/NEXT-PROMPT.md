# Next Prompt

Continue after `production:turnover-ledger-relation-snapshot-source-version-mismatch-diagnosis`.

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
- Browser/admin/write probes and global/module closure remain open.

## Next Boundary

`read-models:turnover-ledger-refresh-source-version-persistence-contract-fix`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row289 evidence if it is not already committed.
3. Read turnover ledger module docs before code edits:
   - `docs/modules/turnover-ledger/README.md`;
   - `docs/modules/turnover-ledger/tests.md`;
   - `docs/modules/turnover-ledger/implementation-notes.md`.
4. Inspect local code around:
   - `TurnoverLedgerSqlProjectionBuilder.rebuild_turnover_ledger_read_model_scope`;
   - `TurnoverLedgerReadModelRepositoryPort.save_turnover_ledger_rows`;
   - PostgreSQL turnover ledger repository save/list methods;
   - worker handler/readiness marking for `turnover_ledger.read_model.refresh`;
   - tests covering source-version persistence and App Status freshness.
5. Implement the smallest fix so completed turnover refresh persists current source versions or cannot mark readiness fresh while persisted row source versions are stale.

## Implementation Scope

- Preserve turnover ledger business grouping and API response shape.
- Reuse the existing source-version provider, projection builder, repository port, read model gateway and worker/readiness boundaries.
- Do not add broad fallback code or duplicate SQL ownership.
- Add focused regression coverage for source-version persistence/freshness proof.

## Required Verification

- Run targeted turnover projection/repository/worker tests relevant to the fix.
- Run `bash scripts/verify.sh docs`.
- Run `git diff --check` and `git diff --cached --check`.
- Commit/push local fix and select a separate deploy/convergence boundary.

## Stop Gates

- Do not run production deploy or API smoke in this boundary.
- Do not change turnover business semantics, grouping, manual closure/withdraw/tag-selection behavior or Workbench relation writes.
- Do not claim module/global closure from local fix/tests alone.
