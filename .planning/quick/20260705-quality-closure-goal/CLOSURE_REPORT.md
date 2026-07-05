# Quality Closure Report

Date: 2026-07-05

## Scope

Goal prompt: `.planning/quick/20260705-quality-closure-goal/GOAL_PROMPT.md`

This closure covers deterministic local Browser E2E, backend API/service/read-model/worker/permission tests, frontend component/build gates, documentation gates, production read-only validation, production read-model refresh apply, and one controlled reversible production write smoke.

This report does not claim the app is perfect. It records the scenarios that were modeled and executed, plus external risks and failed performance gates.

## Local Verification

| Gate | Result |
| --- | --- |
| Backend unittest discovery | Passed: `bash scripts/verify.sh backend`, 4062 tests, 25 explicit skips for missing local PostgreSQL/RabbitMQ/ticket-root samples |
| Python lint | Passed: `bash scripts/verify.sh lint` |
| Frontend unit/component/build | Passed: `bash scripts/verify.sh frontend`, 69 files / 802 tests, production build completed |
| Docs gate | Passed: `bash scripts/verify.sh docs` |
| Full deterministic Browser smoke | Passed: `cd web && npm run e2e:smoke`, 180 Chromium tests in 6.8m |
| Infra smoke with production preflight | Passed: 85 tests, 18 expected skips without local PostgreSQL/RabbitMQ/apply env |

Frontend build warnings remain visible:
- generated CSS selector warnings from Vite/esbuild
- one chunk-size warning for the main bundle

## Production Verification

| Gate | Result |
| --- | --- |
| Production admin AppHealth Browser smoke | Passed: 1 Chromium test, no mutating requests |
| Production authenticated HTTP SLO subset | Passed final sampled run: 9/9 probes, max p95 913.253ms |
| Production SSE smoke | Passed: 2 probes, max first event 969.364ms |
| SSH read-only discovery | Partial: core services active; failed units still include `finops-prune-runtime-queue-history.service`, `logrotate.service`, `clamd@scan.service`, and `systemd-fsck-disk.timer` |
| DB/readiness snapshot | Passed read-only: outbox/dirty all `done`, readiness all `fresh`; old heartbeat rows remain as historical cleanup risk |
| Read-model refresh apply | Failed performance: all 16 critical scopes converged, but 2 exceeded 5000ms |
| Controlled reversible write smoke | Failed post API performance: write and read-model SLO passed, but AppHealth post probe exceeded 1000ms |

## Production Write Smoke

Discovery was read-only and found:
- `workbench_relation_withdraw`: 1 safe candidate
- `turnover_manual_closure_or_withdraw`: 0 candidates
- `no_oa_bank_batch_withdraw`: 0 candidates

Apply executed one approved `workbench_relation_withdraw` under `FINOPS-WRITE-SMOKE-20260705-001`.

Observed:
- withdraw POST: 200, 2846.294ms
- write SLO audit: pass, `p95_enqueue_to_done_ms=879.533`
- post `workbench_groups`: pass, 228.69ms
- post `operations_app_health_dashboard`: fail, 2213.685ms against 1000ms scenario target
- post health: core services active, outbox/dirty `done`, readiness `fresh`, recent failed outbox/dirty counts `0`

The same scenario must not be rerun just to force a green result because the relation was already withdrawn.

## Performance Findings

| Priority | Finding | Evidence | Status |
| --- | --- | --- | --- |
| P1 | Production AppHealth dashboard post-write probe exceeded 1000ms | 2213.685ms after controlled Workbench withdraw | `performance-bug` |
| P1 | Production `bank_account_balance` read-model apply exceeded 5000ms | 7212.511ms enqueue-to-fresh | `performance-bug` |
| P1 | Production `bank_flow_rule_batch` read-model apply exceeded 5000ms | 7261.077ms enqueue-to-fresh; handler 7141.813ms | `performance-bug` |
| P2 | Production bank-flow-rule-batches sampled HTTP read initially returned stale then recovered | targeted rerun fresh in 531.202ms; final sampled run passed | monitor |
| P2 | Frontend build emits generated CSS selector warnings and chunk-size warning | `bash scripts/verify.sh frontend` passes but warns | build hygiene/perf follow-up |
| P2 | Failed system units on production host | prune runtime queue history, logrotate, clamd, fsck timer | ops follow-up |

## Bugs Fixed During Closure

- ETC ticket batch row now renders the external ETC batch id required by the business import fan-out assertion.
- Workbench `confirm-link` now avoids repeated live bank row detail rebuilds for bank-only live selections.
- Workbench special OA-bank relation grouping keeps documented personal-advance settlement and ETC batch OA-bank relations in paired groups without requiring invoice rows.
- Workbench facade row-type resolution preserves injected row-type fallback for minimal facade test fixtures.
- Multiple stale/wrong tests and harness barriers were corrected after triage rather than changing implementation to match invalid expectations.

## Coverage Categories

| Category | Status | Evidence |
| --- | --- | --- |
| Business core unit tests | Covered locally | backend full suite and targeted Workbench/ETC/cost/import tests |
| Service-layer tests | Covered locally | Workbench facade, grouping, audit, lifecycle, queue and read-model service tests |
| API contract tests | Covered locally | full backend suite plus no-OA/bank-flow, OA sync, cost statistics, auth guard, read-model contract harness |
| Read model/cache/worker tests | Covered locally; production performance failures found | local read-model/worker suites pass; production apply found 2 slow scopes |
| Frontend component and interaction tests | Covered locally | 802 Vitest tests and 180 Browser smoke tests pass |
| End-to-end business-flow integration tests | Covered locally; production write partial | Browser smoke covers imports, Workbench, fan-out, exports, permissions, stale/failure states; controlled production write found post-probe performance failure |
| Existing feature regression tests | Covered locally | backend full discovery, frontend full tests, E2E smoke, docs and lint gates pass |

## External Input / Risk Register

- `FIN_OPS_E2E_OA_TOKEN` is unavailable, so ordinary OA production route shell smoke remains `external_input_required`.
- Local/staging PostgreSQL and RabbitMQ URLs are unavailable; those integration tests are explicitly skipped locally and covered only through production SSH/read-only/apply evidence.
- Production route/API matrix is sampled, not exhaustive across every production data shape.
- Production controlled write covered exactly one approved reversible Workbench withdraw candidate; it does not prove every write operation is safe or fast.
- Concurrency races, third-party OA behavior, and future feature changes still require targeted tests when those areas change.

## Next Optimization Prompt

```text
/goal
Work in /Users/yu/Desktop/fin-ops-platform.

Optimize the production performance findings from .planning/quick/20260705-quality-closure-goal/CLOSURE_REPORT.md.

Use business/spec-first and Ponytail rules. Do not change behavior to force tests green. Focus only on confirmed bottlenecks:
1. AppHealth dashboard post-write probe: 2213.685ms vs 1000ms.
2. bank_account_balance read-model refresh apply: 7212.511ms vs 5000ms.
3. bank_flow_rule_batch read-model refresh apply: 7261.077ms vs 5000ms, handler 7141.813ms.

Required workflow:
- Read AGENTS.md and relevant module boundary docs.
- Reproduce locally if possible with deterministic tests or profiling fixtures.
- If production-only, use read-only SSH/DB inspection and existing runtime-smoke reports; do not print secrets.
- Add or update the smallest regression/performance tests that assert the confirmed contract.
- Modify implementation only after root cause is confirmed from code, docs, and metrics.
- Run targeted tests, then backend/lint/frontend/e2e smoke as needed.
- Do not rerun the already-consumed production Workbench withdraw scenario.
```
