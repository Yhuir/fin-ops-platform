# Next Prompt

Continue after `production:no-oa-bank-batches-api-stale-reasons-sanitized-probe`.

## Current State

- Branch: `dev`.
- Row283 collected only sanitized API freshness metadata from authenticated user-scope `GET /api/no-oa-bank-batches?month=2026-06&bucket=unsubmitted&page=1&page_size=200`.
- Row283 did not print response payload rows, `summary`, `batches`, batch IDs, transaction IDs, account names, counterparties, credentials, tokens, cookies, passwords or env values.
- Row283 production stale reason:
  - HTTP `200`.
  - elapsed `221.667ms`.
  - `read_model_status=stale`.
  - `read_model_stale_reasons=["workbench_read_model_schema_version_mismatch"]`.
  - `refresh_enqueued=true`.
  - `refresh_reason=api_no_oa_source_versions_stale`.
- The GET-triggered no-OA refresh converged:
  - `/health/ready`: ready.
  - dirty scopes: `done=187057`.
  - readiness: `fresh=498`.
  - read-model outbox: `done=202952`.
  - recent no-OA outbox last hour: `done=3`, latest `2026-06-25 06:33:15.765409+08`.
  - recent no-OA dirty last hour: `all/done=3`, latest `2026-06-25 06:33:15.75908+08`.
  - read-model dead letters: none.
- Root cause:
  - no-OA API expected source versions used `Application._workbench_matching_source_versions()`, which emits legacy `WORKBENCH_READ_MODEL_SCHEMA_VERSION`.
  - no-OA read-model refresh worker writes rows using SQL projection contract `WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION`.
  - This drift caused `workbench_read_model_schema_version_mismatch`.
- Local fix implemented:
  - `Application._no_oa_bank_batch_workbench_source_versions()` returns the same Workbench matching source-version fields but overrides `workbench_read_model_schema_version` to `WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION`.
  - `_no_oa_bank_batch_application_service()` now uses that no-OA-specific provider.
  - Added `NoOaBankBatchReadModelRefreshTests.test_no_oa_api_source_versions_use_sql_workbench_schema_version`.
  - Updated `docs/modules/no-oa-bank-batches/tests.md`.
- Verification already run:
  - `PYTHONPATH=backend/src pytest -q tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests::test_no_oa_api_source_versions_use_sql_workbench_schema_version`
  - `PYTHONPATH=backend/src pytest -q tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_workbench_integration.py`
  - `PYTHONPATH=backend/src pytest -q tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_no_oa_source_version_helpers_stay_out_of_application`
- The fix is local only. It has not been committed/deployed yet unless the latest git history shows otherwise.
- Full user-scope API, browser/admin/write and global/module closure remain open.

## Next Boundary

`production:no-oa-source-version-provider-fix-deploy-and-convergence`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. If the current local fix is uncommitted, finish verification, update evidence files, commit and push to `origin/dev`.
3. Write a bounded production deploy/convergence runbook under `analysis/` before any deploy command.
4. Deploy the current `dev` commit using the repository production deploy entrypoint.
5. Post-deploy, run focused authenticated `no_oa_bank_batches` API metadata probe only.

## Deploy/Convergence Scope

Deploy the no-OA API source-version provider fix, then prove:

- active release points to the new git commit;
- `/health/ready` is ready;
- dirty scopes are done;
- readiness is fresh;
- read-model outbox is done;
- read-model dead letters are empty;
- focused `no_oa_bank_batches` API probe returns HTTP `200`, `read_model_status=fresh`, `refresh_enqueued_count=0`, p95 under `1000ms`.

## Stop Gates

- Do not deploy if local tests or docs verification fail.
- Do not deploy if worktree contains unrelated unstaged/staged changes.
- Do not print secrets, env values, tokens, cookies, response bodies or payload rows.
- Do not run broad user-scope/browser/admin/write probes in the deploy boundary.
- If the focused no-OA probe still reports stale or enqueues refresh after deploy, stop and collect only sanitized stale reasons/postcheck evidence.
- Do not claim module/global closure from deploy/focused no-OA convergence alone.
