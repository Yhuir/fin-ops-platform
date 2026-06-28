# Read Model Main Final Closure Report - 2026-06-28

## Scope

Controller: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`

Objective: close Read Model modularization on `main` while keeping read models as modular PSCIP systems. This is not the Direct API removal task.

Authoritative detail files:

- Reconciliation matrix: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-28.md`
- Production evidence: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-evidence-2026-06-28.md`

## Git State

- Branch: `main`
- Backup branch: `codex/backup-main-before-read-model-closure-20260628-190532`
- Production release commit: `a3cca8478fb315764be3326ad42d2659a1957788`
- Local `main` read-model runtime code has no `backend/`, `web/` or `tests/` diff from production `a3cca847`; local-only closure changes are prompt/report docs.

## Closure Matrix

| read model | scope type | PSCIP status | production evidence |
| --- | --- | --- | --- |
| `workbench` | `workbench` | L4 equivalent, active generation exception | fresh/done, 5000ms grouped pass |
| `workbench_relation` | `workbench_relation` | L4 | fresh/done, 5000ms grouped pass |
| `bank_detail` | `bank_detail` | L4 | fresh/done, 5000ms grouped pass |
| `bank_account_balance` | `bank_account_balance` | L4 equivalent, all-only exception | fresh/done, 5000ms grouped pass |
| `pending_invoice` | `pending_invoice` | L4 equivalent, page-first exception | fresh/done plus documented `dirty_done` page-first scope |
| `search` | `search` | L4 with latency-watch risk | grouped run had one 5951.862ms miss; targeted rerun passed at 499.357ms |
| `invoice_lifecycle` | `invoice_lifecycle` | L4 | fresh/done, 5000ms grouped pass |
| `input_invoice_usage` | `input_invoice_usage` | L4 | fresh/done, 5000ms grouped pass |
| `output_invoice_collection` | `output_invoice_collection` | L4 | fresh/done, 5000ms grouped pass |
| `oa_pending_payment` | `oa_pending_payment` | L4 | fresh/done, 5000ms grouped pass |
| `cost_statistics` | `cost_statistics` | L4 equivalent, shard plus parent aggregate exception | fresh/done, 5000ms grouped pass |
| `tax_offset` | `tax_offset` | L4 | fresh/done, 5000ms grouped pass |
| `no_oa_bank_batch` | `no_oa_bank_batch` | L4 | fresh/done, 5000ms grouped pass |
| `turnover_ledger` | `turnover_ledger` | L4 | fresh/done, 5000ms grouped pass |

## Evidence Summary

Local verification passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards tests.test_read_model_write_targets -v
bash scripts/verify.sh docs
npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx src/test/BatchAccountingApi.test.ts src/test/NoOaBankBatchApi.test.ts src/test/BankDetailsApi.test.ts src/test/ImportsApi.test.ts src/test/WorkbenchApi.test.ts
git diff --check
```

Production evidence passed:

- `/health/ready`: ready.
- `production_runtime_guard.consistent=true`.
- Read model scope contract: `ok=true`, `violation_count=0`.
- Current uncovered outbox failure count: 0.
- Covered historical outbox failure count: 0.
- Dirty/outbox/readiness converged after bounded SLO apply.
- Required worker missing/stale/mismatch counts were 0 in collected health evidence.
- Admin-token API smoke used a hidden prompt; token was not printed or stored.
- Sampled stale endpoints did not fake fresh.
- `read_model_slo_smoke --apply --critical-only --target-ms 5000` passed 14/15 in the grouped run; the single Search miss passed targeted rerun.

## Closure Decision

The Read Model modularization task is closed under PSCIP-L4 for all current App Status read models, with explicit exception semantics for Workbench, bank account balance, pending invoice and cost statistics.

No known stale-as-fresh path remains in the collected local and production evidence.

## Residual Risk

- Search had one production grouped-run high-latency sample at `5951.862ms`; targeted rerun passed at `499.357ms`. Keep Search in future production SLO watches.
- The Workbench groups admin API smoke used an invalid probe shape and returned 400. It did not show stale-as-fresh; stricter browser/page evidence can use the exact page query shape later.
- The current production release commit does not include local prompt/report documentation commits, but it does include equivalent read-model runtime code.
