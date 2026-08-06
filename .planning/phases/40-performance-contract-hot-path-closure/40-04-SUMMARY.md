---
phase: 40-performance-contract-hot-path-closure
plan: "04"
subsystem: runtime-contract-closure
tags: [runtime-workers, read-models, no-oa, candidate-handoff, regression-guards]

requires:
  - phase: 40-performance-contract-hot-path-closure
    plan: "01"
    provides: bounded HTTP evidence contract and measured/not_measured scale semantics
  - phase: 40-performance-contract-hot-path-closure
    plan: "02"
    provides: exact PostgreSQL result-equivalence proof for three set-based query hotspots
  - phase: 40-performance-contract-hot-path-closure
    plan: "03"
    provides: bounded import-row upsert and owner-guard rollback proof
provides:
  - exact six-required-worker and two-retained-read-model current runtime facts
  - negative guards for retired Search/no-OA derived runtime with positive canonical no-OA consumer proof
  - local application candidate c5557274bdc901c8137d6e2aeaae9036786ff216 and bounded release-gate risk handoff
affects: [40-08, runtime-workers, read-models, no-oa-bank-batches, release-gates]

tech-stack:
  added: []
  patterns: [exact registry inventory, deletion-first legacy contract retirement, local-only candidate handoff]

key-files:
  created:
    - .planning/phases/40-performance-contract-hot-path-closure/40-04-SUMMARY.md
  modified:
    - docs/architecture/persistence-and-read-models.md
    - docs/modules/runtime-workers/boundary-io.md
    - docs/modules/read-models/boundary-io.md
    - docs/modules/no-oa-bank-batches/boundary-io.md
    - docs/modules/imports-bank-transactions/boundary-io.md
    - docs/modules/imports-invoices/boundary-io.md
    - docs/operations/monitoring.md
    - tests/test_read_model_architecture_guards.py
    - tests/test_runtime_worker_registry.py
    - tests/test_no_oa_bank_batch_api.py
    - tests/test_no_oa_bank_batch_routes.py
    - tests/test_postgres_state_store_integration.py
    - .planning/phases/40-performance-contract-hot-path-closure/deferred-items.md

key-decisions:
  - "Treat oa-sync, workbench-matching, workbench, workbench-relation, import, and settings-maintenance as the exact required worker inventory; retain only workbench and workbench_relation read models."
  - "Keep canonical no-OA HTTP routes, BankFlow selection command, and Workbench internal-transfer command while rejecting projection/freshness/worker resurrection."
  - "Use c5557274bdc901c8137d6e2aeaae9036786ff216 as the exact local application candidate; do not push, deploy, or perform production writes."
  - "Do not claim a full-green release candidate while unrelated Phase 27 inventory and two browser motion gates remain red."

patterns-established:
  - "Retired runtime guards combine negative topology assertions with positive live-consumer proof so deletion cannot remove a canonical owner."
  - "Candidate handoffs distinguish application SHA, local correctness evidence, performance evidence bands, and external/unresolved release gates."

requirements-completed: []

duration: 41 min
completed: 2026-08-06
---

# Phase 40 Plan 04: Runtime Fact Closure and Local Candidate Handoff Summary

**Current facts now lock exactly six required workers and two retained read models, retire stale Search/no-OA projection claims, preserve every canonical no-OA consumer, and hand off exact local application candidate `c5557274bdc901c8137d6e2aeaae9036786ff216` with three unrelated non-green gates disclosed.**

## Performance

- **Duration:** 41 min
- **Started:** 2026-08-06T06:50:00Z
- **Completed:** 2026-08-06T07:31:34Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments

- Aligned all seven named long-term fact files to the exact runtime inventory: six required workers (`oa-sync`, `workbench-matching`, `workbench`, `workbench-relation`, `import`, `settings-maintenance`) and two retained read models (`workbench`, `workbench_relation`).
- Added negative guards proving Search and no-OA projection/freshness/worker runtime have no current registration, while positive guards preserve the canonical no-OA HTTP routes, BankFlow selection command, and Workbench internal-transfer command.
- Reproduced and retired the three 40-03 deferred integration tests that asserted already-removed `save_bank_flow_rule_batches`, legacy batch-page `total`, and `read_model.no_oa_bank_batch_rows` contracts; all 15 remaining state-store integration tests pass against disposable PostgreSQL.
- Aggregated the 40-01 bounded evidence/FinanceTable proof, 40-02 exact PostgreSQL result-equivalence proof, and 40-03 bounded import-row owner/rollback proof into one local application SHA.
- Preserved the remote boundary: local tracking `origin/main` remains `2fce06f98ceee1143c644b6d6de98ddfacc8beef` (last reflog update 2026-08-06T04:28:34+08:00), no `RELEASE.json` exists locally, and no push/deploy/production write command ran.

## Candidate Handoff

| Evidence band | Status | Evidence |
| --- | --- | --- |
| Local application candidate | exact | `c5557274bdc901c8137d6e2aeaae9036786ff216` |
| Current production baseline | measured | 40-01 preserves the existing named production evidence band and bounded HTTP report semantics. |
| Target-scale database/browser performance | not_measured | No isolated target-size database or production browser-capacity run was authorized; 40-08 remains the owner. |
| 40-01 targeted correctness | passed | 20 backend tool tests, 7 FinanceTable tests, lint/docs/diff evidence in 40-01. |
| 40-02 exact PostgreSQL equivalence | passed | 215 tests against disposable PostgreSQL; query-shape/version/result contracts passed. |
| 40-03 import-row owner/rollback | passed | Bounded 2,001-row query-count plus real idempotency/cross-owner transaction rollback proof. |
| 40-04 plan-owned correctness | passed | 65 architecture/registry/API/route tests and 15 full PostgreSQL state-store integration tests. |
| Repository full backend gate | failed outside scope | 3,956 tests ran; 1 Phase 27 coverage-matrix inventory drift failed, 55 skipped. |
| Frontend unit/build | passed | 75 files / 954 Vitest tests passed; production build completed. |
| Deterministic browser smoke | failed outside scope | 171 passed / 2 pre-existing shell/drawer motion timing failures. |
| Runtime/infra local gates | passed with bounded inputs | Disposable PostgreSQL runtime-check ready; infra-smoke 71 passed, 25 external-integration skips. |
| Production/external release evidence | not_measured | Authenticated HTTP, production browser, real RabbitMQ, recent-write audit, Workbench capacity/p99, push and deploy remain exclusive to 40-08. |

This is an exact local **application candidate**, not a full-green release candidate. Plan 40-08 must consume this SHA/working tree only after resolving or formally owning the three deferred unrelated gates and obtaining its target-scale/capacity evidence.

## Task Commits

1. **Task 1 RED: lock retired runtime and canonical no-OA contracts** - `7caa61442` (test)
2. **Task 1 GREEN: retire stale runtime facts and obsolete integration tests** - `c5557274b` (fix)

## Files Created/Modified

- `docs/architecture/persistence-and-read-models.md` - exact six-worker/two-read-model topology.
- `docs/modules/runtime-workers/boundary-io.md` - no independent legacy no-OA worker/projection.
- `docs/modules/read-models/boundary-io.md` - canonical no-OA boundary is direct, not a retained read model.
- `docs/modules/no-oa-bank-batches/boundary-io.md` - live route/BankFlow/Workbench consumers.
- `docs/modules/imports-bank-transactions/boundary-io.md` - direct-canonical visibility and fail-fast bounded batch capability.
- `docs/modules/imports-invoices/boundary-io.md` - only Workbench and Workbench relation remain read-model consumers.
- `docs/operations/monitoring.md` - retired Search/page refresh events are negative audit facts, not current runtime.
- `tests/test_read_model_architecture_guards.py` - stale-fact negatives and live no-OA consumer positives.
- `tests/test_runtime_worker_registry.py` - exact worker/manifest/App Status inventory.
- `tests/test_no_oa_bank_batch_api.py` - canonical DTO excludes projection/freshness metadata.
- `tests/test_no_oa_bank_batch_routes.py` - route fixture matches canonical DTO.
- `tests/test_postgres_state_store_integration.py` - removes exactly three tests for retired contracts.
- `.planning/phases/40-performance-contract-hot-path-closure/deferred-items.md` - closes 40-03 findings and records unrelated full-gate risks.

The production route and application service files named in the plan were audited read-only and were not modified.

## Decisions Made

- Runtime truth is derived from the active registry, manifest, App Status registry, and actual callers—not from migration/history/repair vocabulary.
- Migration, repair, rehydrate, domain job, and negative-audit references remain when they do not create a current runtime entry.
- Canonical no-OA ownership remains because server routing, BankFlow selection, and Workbench internal-transfer commands are real consumers; no alias, fallback, double-read, projection, or compatibility branch was added.
- Application rollback for 40-04 is limited to reverting `c5557274b` and `7caa61442`; this restores stale docs/tests but changes no production runtime code or schema. Earlier 40-01..03 production changes and the eventual release rollback remain under their own commits and 40-08 rollout control.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical regression integrity] Removed three obsolete PostgreSQL tests instead of restoring retired contracts**
- **Found during:** Task 1 GREEN verification and 40-03 deferred-item reconciliation.
- **Issue:** Three tests required deleted APIs/fields/projection writers and made the full integration file red despite production having one canonical path.
- **Fix:** Reproduced all three failures on disposable PostgreSQL, deleted exactly those three test methods, retained canonical route/command/Workbench coverage, and marked the 40-03 deferred items resolved.
- **Files modified:** `tests/test_postgres_state_store_integration.py`, `deferred-items.md`.
- **Commit:** `c5557274b`.

### Out-of-Scope Gate Discoveries

- Phase 27 coverage history still lists removed frontend export `workbench/api.ts#unignoreWorkbenchRow`, causing one backend inventory test failure.
- Responsive OA shell animation frame p95 and right-drawer close travel caused two deterministic Playwright failures.
- Per scope rules these were recorded, not fixed or retried. They do not touch any 40-04 runtime-fact/no-OA file or invalidate its targeted acceptance slice.

**Total deviations:** 1 approved Rule-2 test-contract retirement; 3 unrelated gate failures deferred.

## TDD Gate Compliance

- RED commit `7caa61442` produced exactly two planned failures: stale long-term runtime facts and the route fixture's retired `read_model_status` field.
- GREEN commit `c5557274b` passed 65 target tests and docs verification.
- The Rule-2 PostgreSQL retirement was included in GREEN after each obsolete contract failure was reproduced independently.

## Tests

- **Business core unit:** Not applicable; no amount, state-transition, classification, permission, or financial business rule changed.
- **Service layer:** Applicable; registry/manifest exactness and canonical no-OA application response behavior are protected by architecture and registry tests.
- **API contract:** Applicable; no-OA list/route tests assert canonical response fields and reject retired freshness/projection metadata while preserving live routes.
- **Read model/cache/background job:** Applicable; exact six-worker/two-read-model topology, retired Search/no-OA runtime, and active App Status keys are guarded.
- **Frontend component/interaction:** Not applicable to the implementation diff; no frontend source changed. The full frontend suite/build nevertheless passed.
- **End-to-end business flow:** Not applicable to the implementation diff; no new cross-module flow was introduced. Existing deterministic no-OA/BankFlow/Workbench flows passed in the 171-test browser majority.
- **Existing feature regression:** Applicable; live no-OA HTTP, BankFlow selection, Workbench command consumers, canonical DTO, and full remaining PostgreSQL store contracts are protected.

## Verification

- `PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_read_model_architecture_guards.py tests/test_runtime_worker_registry.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_routes.py` — 65 passed.
- `bash scripts/verify.sh docs` — passed.
- Disposable PostgreSQL full `tests/test_postgres_state_store_integration.py` — 15 passed; database dropped by trap.
- `bash scripts/verify.sh lint` — passed.
- `bash scripts/verify.sh all` — backend ran 3,956 tests and stopped at 1 unrelated Phase 27 inventory failure (55 skipped); therefore the compound gate is not green.
- `bash scripts/verify.sh frontend` — 75 files / 954 tests passed; production build passed with existing generated CSS minifier warnings.
- `bash scripts/verify.sh e2e` — 171 passed / 2 unrelated motion failures.
- `FIN_OPS_APP_STORAGE_BACKEND=postgres FIN_OPS_POSTGRES_DATABASE_URL=postgresql://localhost/fin_ops_test_40_04_runtime bash scripts/verify.sh runtime-check` after migrations — ready; disposable database dropped by trap.
- `bash scripts/verify.sh infra-smoke` — 71 passed, 25 skipped; external production/RabbitMQ inputs correctly reported unavailable and no apply ran.
- `git diff --check` — passed.
- Remote/release review — `origin/main` unchanged; no push, deploy, release metadata write, or production mutation.

## Deferred Issues

- Full-green candidate status is blocked by the three unrelated gate failures recorded in `deferred-items.md`.
- Target-scale database/browser performance and Workbench capacity/p99 remain `not_measured` until 40-08 performs the authorized release gate.

## Known Stubs

None. Scanned changed code/tests/docs contain no unwired UI, mock-only production data source, TODO/FIXME, or placeholder implementation. Empty values in test fixtures and direct-canonical empty-response assertions are intentional contracts.

## Security

- T-40-04-01: positive caller assertions preserve the live no-OA route owner and Workbench command path.
- T-40-04-02: exact registry/manifest/App Status assertions prevent stale Search/no-OA topology tampering.
- T-40-04-03: candidate SHA, command outcomes, measured bands, remote ref, and no-mutation boundary are recorded explicitly.
- No new endpoint, authentication path, file-access pattern, schema, queue event, worker, cache, dependency, or trust boundary was introduced; no threat flag is required.

## User Setup Required

None for the local closure. Production credentials, real infrastructure inputs, approval ticket, target-scale database, and release authority remain intentionally absent and belong to 40-08.

## Next Phase Readiness

- 40-08 can consume application candidate `c5557274bdc901c8137d6e2aeaae9036786ff216` and all passed 40-01..04 targeted evidence.
- 40-08 must not call this candidate full-green until the Phase 27 inventory drift and two browser motion gates are resolved or explicitly accepted by their owners.
- 40-08 remains the sole owner of Workbench capacity/p99, production authenticated evidence, push, deploy, and application rollback execution.

## Self-Check: PASSED

- All created/modified closure files exist and both task commits resolve in git history.
- Candidate SHA, remote tracking ref, verification counts, deferred failures, and no-mutation boundary were checked against command output.
- Stub/threat-surface scan found no incomplete implementation or new security-relevant surface.

---
*Phase: 40-performance-contract-hot-path-closure*
*Completed: 2026-08-06*
