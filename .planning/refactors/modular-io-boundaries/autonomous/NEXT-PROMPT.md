# Next Prompt

Continue after `production:no-oa-bank-batches-api-stale-read-only-diagnosis`.

## Current State

- Branch: `dev`.
- Row281 used only read-only root SSH/deployed PostgreSQL metadata. It did not call production API endpoints, print payload rows, print secrets, enqueue/requeue/refresh/rebuild/repair/replay, deploy, restart or mutate DB/readiness/queue state.
- Row281 initially hit several read-only compatibility issues before final evidence:
  - `PostgresStateStore` required deployed `data_dir`.
  - deployed `default_data_dir` import path is `fin_ops_platform.services.state_store`.
  - deployed `AppSettingsService` requires `project_costing_service`, so final diagnosis used `PostgresStateStore.load_app_settings()` plus deployed constants.
  - `read_model.app_status_readiness` uses `scope_type`, not `domain`.
  - simplified pair-relation snapshot reconstruction was rejected; final evidence used `WorkbenchPairRelationService.from_snapshot(store.load_workbench_pair_relations()).snapshot()` to match `NoOaPairRelationSnapshotPort.snapshot_version()`.
- Final Row281 evidence:
  - Probe scope: `month=2026-06`, `bucket=unsubmitted`.
  - Summary scope row count: `8`.
  - Detail scope row count: `8`.
  - Status distribution: `draft/unsubmitted=8`.
  - Detail row source-version hash: `36cab6e37ef9aede`.
  - Exact base expected hash: `12a6a240c94fcc71`.
  - Optional-detail expected hash: `36cab6e37ef9aede`.
  - Optional `bank_detail_source_versions` hash: `0673e51b28166cb9`.
  - Optional `workbench_relation_source_versions` hash: `18ffe677bd6f1aa2`.
  - Exact expected `pair_relation_snapshot_version` prefix: `d35b81698abdd031`.
  - Base expected mismatch: `0` rows across summary/detail/combined API comparison.
  - Optional-detail expected mismatch: `0` rows across summary/detail/combined API comparison.
  - Dirty `no_oa_bank_batch:all`: `done`, latest `2026-06-25 06:11:30.097589+08`.
  - Outbox `no_oa_bank_batch.read_model.refresh` last 24h: `done`, count `3`, latest `2026-06-25 06:11:30.105523+08`.
  - App Status readiness `no_oa_bank_batch:all`: `fresh`, latest `2026-06-25 06:11:30.101741+08`.
  - Dead letters in last 7d: none.
- Row280's `no_oa_bank_batches` API stale result is classified as stale persisted rows before its GET-triggered refresh, now cleared by the completed refresh.
- No code fix, repair, rebuild, requeue or manual refresh is justified from Row281 evidence.
- Module/global closure remains open.

## Next Boundary

`production:no-oa-bank-batches-focused-api-freshness-recheck`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Acquire the direct-dev write lease before editing:
   - `mkdir /tmp/fin-ops-dev-write.lock`
4. Read:
   - `analysis/production-no-oa-bank-batches-api-stale-read-only-diagnosis-2026-06-25.md`
   - `analysis/production-read-model-focused-user-scope-api-metadata-resmoke-runbook-2026-06-25.md`
   - `backend/src/fin_ops_platform/tools/http_slo_probe.py`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
5. Write a bounded runbook/evidence file under `analysis/` before any production API command.

## Recheck Scope

Run a focused authenticated production API metadata recheck for `no_oa_bank_batches` only, reusing the Row280 in-process target OA applicant credential seam without printing/storing credentials, tokens, cookies, env values, response bodies or payload rows.

Target expectation:

- `no_oa_bank_batches` returns HTTP `200`;
- `read_model_status=fresh`;
- `refresh_enqueued_count=0`;
- p95 remains under the existing API smoke target;
- no full user-scope, browser, admin or write probes run unless this focused no-OA recheck passes cleanly.

## Stop Gates

- Stop if `/health/ready` is unavailable or not ready.
- Stop if no safe target OA applicant auth path is available without printing/storing secrets.
- Stop if focused `no_oa_bank_batches` still reports `stale`, `missing`, `refreshing`, `schema_mismatch`, `failed` or any refresh enqueue.
- Stop if pre/post dirty/outbox/readiness/dead-letter checks are not clean.
- Do not run browser/admin/write probes in this boundary.
- Do not claim module/global closure from this focused API recheck alone.
