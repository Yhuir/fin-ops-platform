# Read Model Main Wave 8 - Controlled Production Rollout and Evidence Sweep

Date: 2026-06-26
Branch: `main`
Deployed release: `main-18a0509f-20260626063245`
Deployed commit: `18a0509f3dca0649d1d7661293909c657853e91f`

## Result

Wave 8 closed the production rollout and direct read model freshness evidence for the current `main` release. It also validated one bounded production write/restore path through the Workbench relation business flow and a minimal DB restore because the selected sample had no business operation that could restore `cancelled -> active`.

This wave does not close public real-admin-token authenticated HTTP/SSE/browser proof. A secure Admin Token was not acquired in this execution, and no token was printed, hashed, encoded, persisted, copied into repo files, or stored in prompts/docs/log artifacts.

## Rollout Evidence

- Local `main` was clean and synced with `origin/main` before deployment.
- Local verification before deploy:
  - `PYTHONPATH=backend/src python3 -m unittest -q tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier tests.test_read_model_freshness tests.test_read_model_scope_contract tests.test_runtime_worker_read_model_refresh_scopes tests.test_write_operation_slo_audit tests.test_write_operation_e2e_smoke tests.test_runtime_sync_closure_gate tests.test_read_model_slo_smoke`
  - Result: 359 tests passed.
  - `bash scripts/verify.sh docs`
  - `git diff --check`
  - `npm run build` passed with the existing CSS minify/chunk-size warnings.
- Production rollout command: `./scripts/deploy-oa.sh`.
- Active release after rollout: `main-18a0509f-20260626063245`.
- Active production services:
  - `fin-ops.service`: active.
  - `fin-ops-rabbitmq-dispatcher.service`: active.
  - `fin-ops-worker@*.service`: 20 active units.
- Runtime readiness at `127.0.0.1:18001/health/ready`:
  - `status=ready`.
  - `runtime_release.consistent=true`.
  - `production_runtime_guard.consistent=true`.
  - Working directory and `PYTHONPATH` point at the deployed release.

## Read Model Evidence

Scope contract:

- Command: `finops-deploy-control read-model-scope-contract main-18a0509f-20260626063245 --json`.
- Result: `ok=true`, `violation_count=0`, `current_uncovered_outbox_failure_count=0`, `covered_historical_outbox_failure_count=0`.

Current production aggregate after sample restore and final recheck:

- `job.outbox_events`: `done=204319`.
- `job.read_model_dirty_scopes`: `done=188090`.
- `read_model.app_status_readiness`: `fresh=499`.
- Current readiness blockers: `0`.

Critical read model SLO smoke:

- Command: `read_model_slo_smoke --apply --critical-only --target-ms 5000 --timeout-seconds 120 --json`, executed with the production service runtime env and release `PYTHONPATH`.
- Result: `status=pass`, `planned_scope_count=15`, `result_count=15`, `failed_count=0`.
- Summary: enqueue-to-fresh `p50=469.186ms`, `p95=1958.911ms`, `p99=1958.911ms`, `max=1958.911ms`; handler `p95=1504.413ms`, `max=1504.413ms`.

Covered critical read model keys:

- `workbench`
- `workbench_relation`
- `bank_detail`
- `bank_account_balance`
- `pending_invoice`
- `search`
- `invoice_lifecycle`
- `input_invoice_usage`
- `output_invoice_collection`
- `oa_pending_payment`
- `cost_statistics`
- `tax_offset`
- `no_oa_bank_batch`
- `turnover_ledger`

## Production Write/Restore Evidence

Discovery found low-risk candidates for:

- `turnover`: 3 candidates.
- `workbench_relation`: 3 candidates.
- `no_oa_bank_batch`: 3 candidates.

Final evidenced mutating sample:

- Operation: `workbench_relation_withdraw`.
- Validation entry: business HTTP route/service/repository/queue path against the production database from a temporary server-local process bound only to `127.0.0.1:19081`.
- The temporary process used a local dev-session bypass only inside the subprocess; no systemd unit, public route, repo config, secret file, or production service configuration was changed.
- This proves the business route/service/repository/queue/read-model path against production data, but it does not prove real public Admin Token authentication.

Restore:

- The selected Workbench relation sample had no valid business operation for `cancelled -> active`.
- User-approved bounded DB restore protocol was used.
- Restore matched exactly one sample row by exact predicate, restored only the operation-before canonical status fields, and did not update readiness, dirty scopes, outbox, caches, or projections to fabricate freshness.
- Post-restore checks:
  - exact update row count was 1.
  - sample canonical status returned to `active`.
  - follow-up critical read model SLO smoke passed 15/15.
  - final aggregate showed all outbox/dirty scopes done and all App Status readiness fresh.

Write operation SLO audit:

- Command: `write_operation_slo_audit --operation workbench_relation_withdraw --lookback-hours 1 --target-ms 5000 --json`.
- Result: `status=pass`, `expectation_count=1`, `failed_expectation_count=0`, `missing_expectation_count=0`.
- `workbench_relation.read_model.refresh`: `sample_count=2`, latest dirty/event statuses `done`, `p95=2157.055ms`, `p99=2157.055ms`, `max=2157.055ms`.

## Limits And Next Gate

Closed in this wave:

- Current `main` deployed to production.
- Production worker/readiness/dirty/outbox facts are converged.
- Direct critical read model enqueue-to-fresh smoke passes for all planned critical scopes.
- Scope contract has no current violations.
- One Workbench relation write-operation audit and bounded sample restore path is proven.

Not closed in this wave:

- Secure Admin Token was not acquired.
- Public real-authenticated Admin Token API/SSE/browser proof was not executed.
- The full write-operation matrix is not yet proven under public real-authenticated production API/UI.
- Turnover and no-OA candidate samples were discovered but not used as final mutating closure samples.

Next wave should start with a secure Admin Token popup or secure credential manager lookup, then run public authenticated HTTP/SSE/browser proof and broader write-operation samples. If secure token input remains unavailable, continue all internal/SSH/business-command evidence that does not require printing or persisting secrets, but do not claim public authenticated closure.
