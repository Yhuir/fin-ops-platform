# Next Prompt

Continue the user-authorized `main-read-model-closure` run from Wave 10.

## Current State

- Branch: `main`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260628-190532`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest reconciliation: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-28.md`.
- Latest production evidence: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-evidence-2026-06-28.md`.
- Production release commit: `a3cca8478fb315764be3326ad42d2659a1957788`.
- Local `main` contains production read-model runtime code plus the updated 07 prompt/report docs; backend/web/test diff versus production `a3cca847` is empty.
- Do not implement Go, Go Fiber or Go Worker.
- Do not print or persist secrets.

## Evidence Already Collected

Local checks passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards tests.test_read_model_write_targets -v
bash scripts/verify.sh docs
npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx src/test/BatchAccountingApi.test.ts src/test/NoOaBankBatchApi.test.ts src/test/BankDetailsApi.test.ts src/test/ImportsApi.test.ts src/test/WorkbenchApi.test.ts
git diff --check
```

Production evidence already collected:

- `/health/ready` status ready.
- scope contract dry-run ok, violation count 0.
- uncovered outbox failure count 0.
- stale dirty scope count 0.
- required worker missing/stale/mismatch counts 0.
- RabbitMQ queue depth 0 and DLQ 0.
- Admin-token API smoke used hidden dialog; token was not printed or stored.
- Sampled stale endpoints did not fake fresh.
- `read_model_slo_smoke --apply --critical-only` made all 15 planned scopes reach `done/fresh` or documented pending-invoice page-first `dirty_done`.

## Current Blocker

PSCIP-L4 is blocked only by production SLO performance.

Failed 1000ms enqueue-to-fresh target:

| read model | scope | enqueue_to_fresh_ms |
| --- | --- | ---: |
| `workbench` | `2026-04` | 9160.301 |
| `bank_detail` | `2026-06` | 1063.026 |
| `invoice_lifecycle` | `2025-09` | 2827.900 |
| `cost_statistics` | `active:2026-01` | 9193.540 |
| `no_oa_bank_batch` | `2026-03` | 1169.816 |
| `turnover_ledger` | `all` | 5706.690 |

## Wave 10 Objective

Close production SLO performance for the six failing scopes without changing read model architecture semantics.

Do this as one macro-wave:

1. Diagnose whether latency is queue/poll/coalescing overhead, worker handler duration, SQL builder hot path, broad scope choice, or parent aggregate behavior.
2. Prefer one shared fix if the root cause is shared queue/worker timing.
3. Otherwise fix only the high-impact family hot spots:
   - Workbench active generation refresh.
   - Cost statistics parent/shard refresh.
   - Turnover ledger all-scope refresh.
   - Invoice lifecycle refresh.
   - Near-threshold bank detail and no-OA refresh.
4. Do not manually write readiness fresh.
5. Do not delete queue/readiness rows to make evidence pass.
6. Do not broaden scope to Direct API removal.
7. Do not edit canonical facts prompt files.

## Required First Steps

1. Run:

```bash
git status --short --branch
```

There may be unrelated canonical facts prompt files dirty in the worktree. Do not stage or modify them for this read-model wave.

2. Collect targeted production diagnostics with root SSH:

- recent worker logs for the six read models;
- handler duration samples if present;
- App Status/dirty/outbox/readiness aggregate after the failed SLO run;
- existing API performance samples for the six read models;
- query-plan or SQL timing evidence only if it does not print sensitive payload.

3. Implement the smallest code change that addresses the measured bottleneck.

4. Run local targeted tests and the shared gates.

5. Push `main` only after local verification is green.

6. Deploy only through `./scripts/deploy-oa.sh` or an already active equivalent release path. No ad hoc production patching.

7. Re-run production:

```bash
read-model-scope-contract --json
read_model_slo_smoke --json --apply --critical-only --target-ms 1000 --timeout-seconds 120
```

8. Update:

- `.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-evidence-2026-06-28.md`
- `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
- this `NEXT-PROMPT.md`

Continue automatically unless a precise hard stop is reached.
