# Next Prompt

Continue after `production:turnover-ledger-grouped-metadata-fix-deploy-and-resmoke`.

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
- Browser/admin/write probes and global/module closure remain open.

## Next Boundary

`production:turnover-ledger-relation-snapshot-source-version-mismatch-diagnosis`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Commit/push Row288 evidence if it is not already committed.
3. Write a bounded read-only runbook under `.planning/refactors/modular-io-boundaries/analysis/production-turnover-ledger-relation-snapshot-source-version-mismatch-diagnosis-2026-06-25.md` before any production command.
4. Inspect code contracts locally before production queries:
   - turnover ledger expected source-version provider;
   - `TurnoverLedgerQueryService` / `ReadModelQueryGateway` mismatch helper usage;
   - Workbench relation snapshot/source-version provider used by turnover ledger.
5. Run only read-only production metadata queries needed to compare expected vs persisted source versions and App Status/read-model facts.

## Diagnosis Scope

- Diagnose `turnover_relation_snapshot_version_mismatch`.
- Compare deployed expected turnover relation snapshot source versions with current row/source-version metadata and Workbench relation snapshot facts.
- Determine whether the mismatch is stale persisted rows, API expected-source drift, worker writer-source drift, or an aggregate/readiness-vs-row-level proof gap.
- Do not issue authenticated API probes unless a later runbook explicitly chooses that as a separate step.

## Required Verification

- Runbook/evidence committed and pushed after the read-only diagnosis.
- Health/dirty/readiness/outbox/dead-letter postcheck stays clean.
- Next boundary selected from evidence.

## Stop Gates

- Do not run full user-scope, browser, admin or write probes in this boundary.
- Do not print or store tokens, cookies, passwords, env values, response bodies, payload rows or business identifiers.
- Do not manually refresh, requeue, repair, replay, mark readiness, or directly mutate DB state unless a new runbook is written for that separate operation.
- Do not claim module/global closure from diagnosis alone.
