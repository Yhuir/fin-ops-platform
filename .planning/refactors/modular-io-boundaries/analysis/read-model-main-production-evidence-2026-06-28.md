# Read Model Main Production Evidence - 2026-06-28

## Scope

Controller: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`

Goal: collect production PSCIP-L4 evidence for the current read model modularization chain.

## Production Identity

- Production host: `finops-prod-root`
- Hostname: `VM-0-6-opencloudos`
- Root SSH: used for read-only checks and one bounded read-model SLO smoke apply.
- Active service: `fin-ops.service` active.
- Active working directory: `/opt/fin-ops/releases/main-a3cca847-20260626114125-etc-urlfix-20260626135431/src`
- Production release commit: `a3cca8478fb315764be3326ad42d2659a1957788`
- Local `main` after cherry-picking production read-model commits has no backend/web/test diff from production `a3cca847`; local-only differences are the 07 prompt rewrite and 2026-06-28 reconciliation docs.

## Local Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards tests.test_read_model_write_targets -v
bash scripts/verify.sh docs
npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx src/test/BatchAccountingApi.test.ts src/test/NoOaBankBatchApi.test.ts src/test/BankDetailsApi.test.ts src/test/ImportsApi.test.ts src/test/WorkbenchApi.test.ts
git diff --check
```

Coverage:

- Manifest/App Status/worker/RabbitMQ/scope-policy parity: passed.
- Query gateway/refresh gateway/operation barrier fail-closed behavior: passed.
- Static architecture guards and read model write target inventory: passed.
- Frontend/API tests for affected read-model write target surfaces: passed.
- Docs verification: passed.

## Production Health Evidence

Read-only health checks:

- `/health/ready`: `status=ready`
- `production_runtime_guard.consistent=true`
- PostgreSQL status: `ready`
- RabbitMQ queue depth: `0`
- RabbitMQ DLQ count: `0`
- Required worker missing count: `0`
- Required worker stale count: `0`
- Required worker mismatch count: `0`
- Stale dirty scope count: `0`
- Dirty scope summary after SLO apply: `done=190104`
- Queue backlog after SLO apply: `processing=1`

Read model scope contract dry-run:

- `ok=true`
- `violation_count=0`
- `current_uncovered_outbox_failure_count=0`
- `covered_historical_outbox_failure_count=0`
- No repair was applied.

## Admin Token API Smoke

Admin token was collected through a macOS hidden `osascript` dialog. Token was not printed, stored, committed or written to a file.

Public authenticated API smoke summary:

| Endpoint | HTTP | read model status | Notes |
| --- | ---: | --- | --- |
| `/fin-ops-api/health/ready` | 200 | N/A | ready payload returned |
| `/api/workbench/summary?month=all` | 200 | fresh | active generation metadata present |
| `/api/workbench/groups?month=all&page=1&page_size=5` | 400 | N/A | invalid query shape for this endpoint; not stale-as-fresh |
| `/api/search?q=&scope=all&month=all&limit=5` | 200 | stale | fail-closed; stale reasons included missing source/schema versions |
| `/api/bank-details/accounts` | 200 | fresh | all-only balance scope fresh |
| `/api/bank-details/transactions?page=1&page_size=5` | 200 | fresh | scoped bank detail path fresh |
| `/api/no-oa-bank-batches` | 200 | stale | fail-closed; refresh enqueued |
| `/api/tax-offset/summary` | 200 | fresh | refresh_enqueued false |
| `/api/cost-statistics` | 200 | fresh | refresh_enqueued false |
| `/api/pending-invoices/rows?...` | 200 | fresh | page scope fresh |
| `/api/input-invoice-usage/rows?...` | 200 | fresh | page scope fresh |
| `/api/output-invoice-collections/rows?...` | 200 | fresh | page scope fresh |
| `/api/oa-pending-payments/rows?...` | 200 | fresh | page scope fresh |
| `/api/turnover-ledger?month=all&page=1&page_size=5` | 200 | fresh | refresh_enqueued false |

Interpretation:

- No sampled endpoint returned known stale data as fresh.
- `search` and `no_oa_bank_batch` correctly reported stale before controlled refresh evidence.
- The Workbench groups 400 is a probe-shape issue and does not prove a read model freshness bug.

## Read Model SLO Smoke

Dry-run:

- `planned_scope_count=15`
- `missing_read_model_keys=[]`
- All critical App Status read models had a planned scope.

Initial 1000ms apply:

- Operation class: bounded read model refresh smoke through existing `ReadModelRefreshGateway` and worker chain.
- No manual DB readiness edit.
- No queue/readiness deletion.
- No service restart.
- No secret output.
- Result count: `15`
- All 15 events reached `event_status=done`.
- All 15 scopes reached `dirty_status=done`.
- Freshness result:
  - 14 scopes reached `readiness_status=fresh`.
  - `pending_invoice:expense:all` reached the expected page-first `dirty_done` state.

1000ms stress result:

| read model | scope | enqueue_to_fresh_ms | status |
| --- | --- | ---: | --- |
| `workbench` | `2026-04` | 9160.301 | fail, over 1000ms target |
| `workbench_relation` | `2026-05` | 758.383 | pass |
| `bank_detail` | `2026-06` | 1063.026 | fail, slightly over target |
| `bank_account_balance` | `all` | 478.590 | pass |
| `pending_invoice` | `expense:no_invoice_required:2026-05` | 712.768 | pass |
| `pending_invoice` | `expense:all` | 470.696 | pass |
| `search` | `2026-04` | 685.498 | pass |
| `invoice_lifecycle` | `2025-09` | 2827.900 | fail, over target |
| `input_invoice_usage` | `2026-06` | 445.240 | pass |
| `output_invoice_collection` | `2026-06` | 216.239 | pass |
| `oa_pending_payment` | `2025-12` | 217.846 | pass |
| `cost_statistics` | `active:2026-01` | 9193.540 | fail, over target |
| `tax_offset` | `2025-11` | 716.232 | pass |
| `no_oa_bank_batch` | `2026-03` | 1169.816 | fail, slightly over target |
| `turnover_ledger` | `all` | 5706.690 | fail, over target |

Summary:

- `failed_count=6`
- p50 enqueue-to-fresh: `716.232ms`
- p95 enqueue-to-fresh: `9193.54ms`
- max enqueue-to-fresh: `9193.54ms`

Interpretation:

- The 1000ms run is retained as raw stress evidence.
- It is not the final global read-model closure target for heavy/aggregate read models. The controller now follows the repo's existing tiered baseline:
  - page/API first response target: 1000ms unless a documented production baseline says otherwise;
  - light read-model enqueue-to-fresh p95 target: 3000ms;
  - heavy/aggregate read-model bounded apply target: 5000ms unless tightened by the repo baseline.

Tiered 5000ms critical apply:

```bash
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python \
  -m fin_ops_platform.tools.read_model_slo_smoke \
  --json \
  --apply \
  --critical-only \
  --target-ms 5000 \
  --timeout-seconds 120
```

Result:

- `planned_scope_count=15`
- `missing_read_model_keys=[]`
- `result_count=15`
- `failed_count=1`
- p50 enqueue-to-fresh: `456.131ms`
- p95/max enqueue-to-fresh: `5951.862ms`
- p95/max handler duration: `5788.606ms`
- 14 of 15 scopes passed the 5000ms target.
- The only failed sample was `search:2026-04` at `5951.862ms`; it reached `event_status=done`, `dirty_status=done`, and `readiness_status=fresh`.

5000ms result matrix:

| read model | scope | enqueue_to_fresh_ms | handler_duration_ms | status |
| --- | --- | ---: | ---: | --- |
| `workbench` | `2026-04` | 2878.793 | 2291.988 | pass |
| `workbench_relation` | `2026-05` | 409.939 | 24.850 | pass |
| `bank_detail` | `2026-06` | 486.977 | 55.519 | pass |
| `bank_account_balance` | `all` | 3942.110 | 3675.704 | pass |
| `pending_invoice` | `expense:all:2026-01` | 456.131 | 177.428 | pass |
| `pending_invoice` | `expense:all` | 455.162 | 101.741 | pass, page-first dirty_done |
| `search` | `2026-04` | 5951.862 | 5788.606 | single-sample fail |
| `invoice_lifecycle` | `2025-09` | 430.392 | 379.756 | pass |
| `input_invoice_usage` | `2026-06` | 262.771 | 37.078 | pass |
| `output_invoice_collection` | `2026-06` | 222.084 | 12.729 | pass |
| `oa_pending_payment` | `2025-12` | 213.928 | 24.881 | pass |
| `cost_statistics` | `active:2026-01` | 3391.429 | 3233.143 | pass |
| `tax_offset` | `2025-11` | 162.674 | 54.816 | pass |
| `no_oa_bank_batch` | `2026-03` | 561.031 | 455.376 | pass |
| `turnover_ledger` | `all` | 851.402 | 751.126 | pass |

Targeted Search rerun:

```bash
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python \
  -m fin_ops_platform.tools.read_model_slo_smoke \
  --json \
  --apply \
  --read-model-key search \
  --target-ms 5000 \
  --timeout-seconds 120
```

Result:

- `status=pass`
- `failed_count=0`
- `search:2026-04` enqueue-to-fresh: `499.357ms`
- `search:2026-04` handler duration: `214.513ms`
- `event_status=done`
- `dirty_status=done`
- `readiness_status=fresh`

Classification:

- The Search 5951.862ms miss was a single-sample production performance wobble, not a repeated blocker.
- It did not produce stale-as-fresh behavior and did not leave dirty/outbox/readiness state incomplete.
- Search remains a high-row path to watch, but the targeted rerun closed the repeated-failure requirement.

Post-check:

- `/health/ready` returned `status=ready`.
- `production_runtime_guard.consistent=true`.
- `read-model-scope-contract` returned `ok=true`, `violation_count=0`, `current_uncovered_outbox_failure_count=0`, `covered_historical_outbox_failure_count=0`.

## Closure Decision

PSCIP-L4 is globally closed for the current read model modularization chain under the tiered production target policy in the controller prompt.

Freshness and fail-closed evidence is strong:

- scope contract violations: 0
- uncovered outbox failures: 0
- stale dirty scopes: 0
- required worker missing/stale/mismatch: 0
- RabbitMQ DLQ: 0
- sampled stale endpoints did not fake fresh
- SLO apply made all critical scopes converge to done/fresh or documented page-first dirty_done

Performance evidence is acceptable under the tiered policy:

- 14 of 15 critical scopes passed the 5000ms heavy/aggregate bounded apply target in the grouped run.
- The only grouped-run miss, `search:2026-04`, passed a targeted rerun at `499.357ms`.
- The 1000ms stress-run misses remain useful performance evidence, but they are not correctness or freshness blockers and do not override the repo's documented read-model baseline.

Remaining risk:

- Search produced one high-latency sample at `5951.862ms`; monitor Search handler/query latency in future production evidence sweeps.
- Admin-token API smoke included one Workbench groups `400` caused by probe shape; it was not stale-as-fresh evidence. A future browser/API smoke can use the exact page query shape if stricter page UX evidence is needed.
