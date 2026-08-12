---
phase: quick-260812-roj-workbench-generation-scope-generation-st
plan: "01"
subsystem: database
tags: [postgresql, workbench, retention, transactions, operations]
requires:
  - phase: existing-workbench-generation-runtime
    provides: active-generation repository, retention preview, CLI, and versioned prune helper
provides:
  - scope-isolated Workbench generation retention with independently committed chunks
  - dedicated CLI statement timeout and configurable delete batch size
  - versioned wrapper defaults, passthrough, logging, and focused regression coverage
affects: [workbench-read-model, runtime-maintenance, deployment-operations]
tech-stack:
  added: []
  patterns: [preview-owned bounded candidates, scope-stable chunking, one transaction per delete chunk]
key-files:
  created:
    - .planning/quick/260812-roj-workbench-generation-scope-generation-st/260812-roj-SUMMARY.md
  modified:
    - backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
    - backend/src/fin_ops_platform/tools/prune_workbench_generations.py
    - deploy/oa/bin/finops-prune-workbench-generations.sh
    - deploy/oa/env/fin-ops.common.env.example
    - deploy/oa/README.md
    - tests/test_workbench_sql_runtime.py
    - tests/test_deploy_runtime_examples.py
    - tests/test_postgres_connection.py
    - docs/architecture/module-boundaries/read-model-contracts.md
    - docs/modules/deploy/boundary-io.md
    - docs/modules/read-models/boundary-io.md
    - docs/modules/reconciliation-workbench/boundary-io.md
    - docs/modules/reconciliation-workbench/implementation-notes.md
    - docs/modules/reconciliation-workbench/tests.md
    - docs/operations/deployment.md
    - docs/operations/monitoring.md
    - docs/operations/runtime-worker-governance.md
key-decisions:
  - "Preview remains the sole candidate owner and is capped at 500 rows per run."
  - "Candidates retain preview order, are grouped by scope, and each 1..100-generation chunk commits independently."
  - "The maintenance connection receives its positive statement timeout before repository construction."
patterns-established:
  - "Destructive read-model retention groups candidates at the ownership boundary and never mixes scopes in a transaction."
  - "Maintenance wrapper policy logs non-secret batch and timeout values passed to the CLI."
requirements-completed: [QUICK-260812-ROJ]
duration: 5min
completed: 2026-08-12
---

# Quick Task 260812-roj: Workbench Generation Retention Summary

**Workbench generation retention now deletes bounded same-scope chunks in independent transactions, with a dedicated CLI statement timeout and versioned wrapper controls.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-08-12T12:14:33Z
- **Completed:** 2026-08-12T12:18:47Z
- **Tasks:** 2
- **Files modified:** 17 implementation/test/long-term-doc files, plus GSD state, plan, and this summary

## Accomplishments

- Capped a retention preview/run at 500 terminal `failed|superseded` candidates, grouped its stable rows by `scope_key`, normalized `delete_batch_size` to `1..100`, and committed every same-scope chunk in an independent transaction.
- Locked each chunk's generation metadata in deterministic id order and rechecked default tenant, scope, and terminal status before deleting child rows; `active|building` generations are skipped and `deleted_count` reflects actual metadata deletes.
- Preserved default dry-run, `keep_recent_generations_per_scope >= 1`, preview/final active-generation protection, the default tenant guard, and publish-path isolation.
- Added CLI `--delete-batch-size` and positive `--statement-timeout-seconds`; the default `60000` ms timeout is applied to the dedicated connection before repository construction.
- Added wrapper environment defaults and flag passthrough for batch size `1` and timeout `60` seconds, with non-secret policy logging.
- Updated the clean operations fact source with the bounded transaction and timeout contract.

## Task Commits

No commits were created. The executor was explicitly instructed not to stage or commit because the shared worktree contains unrelated user-owned edits.

## Files Created/Modified

- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` - Normalizes batch size, caps candidates at 500, groups by scope, and executes each chunk in its own transaction.
- `backend/src/fin_ops_platform/tools/prune_workbench_generations.py` - Adds CLI batch/timeout controls and applies the connection timeout before repository construction.
- `deploy/oa/bin/finops-prune-workbench-generations.sh` - Defines controlled environment defaults, logs them, and passes both CLI flags.
- `deploy/oa/env/fin-ops.common.env.example` and `deploy/oa/README.md` - Document the controlled batch/timeout environment contract.
- `tests/test_workbench_sql_runtime.py` - Covers scope/chunk transaction boundaries, normalization, candidate cap, dry-run/empty behavior, active/tenant guards, CLI defaults/custom values/order, positive timeout validation, and publish isolation.
- `tests/test_deploy_runtime_examples.py` - Covers wrapper defaults, passthrough, execution mode, and `keep_recent=1` regression.
- `tests/test_postgres_connection.py` - Proves the maintenance timeout override reaches PostgreSQL connection preparation.
- `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/reconciliation-workbench/boundary-io.md`, and `docs/modules/reconciliation-workbench/implementation-notes.md` - Record the read-model ownership, scope isolation, transaction, and maintenance boundaries.
- `docs/modules/deploy/boundary-io.md`, `docs/operations/deployment.md`, `docs/operations/monitoring.md`, and `docs/operations/runtime-worker-governance.md` - Record the versioned deployment/runtime batch, timeout, cap, timer/log troubleshooting, and publish-path contracts.
- `.planning/quick/260812-roj-workbench-generation-scope-generation-st/260812-roj-PLAN.md` - Records the locked design and test responsibilities.
- `.planning/quick/260812-roj-workbench-generation-scope-generation-st/260812-roj-SUMMARY.md` - Records execution evidence and risks.

## Tests Added or Changed

- **Category 1 — Business core unit:** batch bounds `1..100`, total candidate cap `500`, terminal-only candidates, stable per-scope grouping, `keep_recent >= 1`, and active/building/tenant deletion guards.
- **Category 2 — Service layer:** independent transaction entry/exit per chunk, deterministic metadata locking, later-batch failure with earlier commits preserved, no transaction for dry-run/empty candidates, and CLI connection → timeout → repository ordering.
- **Category 4 — Read model/cache/background job:** timer-owned generation retention and publish-path isolation; no worker, queue, or cache behavior was added.
- **Category 7 — Existing regression:** default dry-run, zero keep-days support, active-generation safety, wrapper active-release/execute defaults, and existing affected test modules.

The following categories were not applicable:

- **Category 3 — API contract:** no HTTP/API shape changed.
- **Category 5 — Frontend interaction:** no frontend files or user interaction changed.
- **Category 6 — End-to-end business flow:** production/database/deploy execution was explicitly prohibited; repository, CLI, and wrapper contract tests cover this maintenance path locally.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime tests.test_deploy_runtime_examples tests.test_postgres_connection tests.test_deploy_oa_script tests.test_platform_runtime_boundary_guards -q` — 486 passed; covers transactional commit/rollback/retry, terminal-status guards, scope-bound child deletes, candidate limits, timeout wiring, CLI, wrapper, deployment, and runtime-boundary regressions.
- `bash scripts/verify.sh lint` — PASS.
- `bash scripts/verify.sh docs` — PASS.
- `python3 -m compileall -q backend/src/fin_ops_platform/services/postgres_repositories/read_models.py backend/src/fin_ops_platform/tools/prune_workbench_generations.py` — PASS.
- `bash -n deploy/oa/bin/finops-prune-workbench-generations.sh` — PASS; syntax validation only, wrapper not executed.
- Scoped `git diff --check` for all owned implementation/test/doc/GSD files — PASS.

## Decisions Made

- Followed all locked decisions without introducing dependencies, schema, worker, queue, cache, retry fallback, post-publish cleanup, or `keep_recent=0` behavior.
- Merged the retention contract precisely into the pre-existing Workbench/read-model/deploy fact sources without reverting unrelated edits.

## Deviations from Plan

None in implementation. Workflow-only adjustments were required by direct instructions: the executor made no task commit and preserved the shared worktree while the root agent completed the exact long-term-document merge.

## Known Stubs

None introduced.

## Threat Flags

No unplanned security-relevant surface was introduced. The planned destructive repository boundary retains its candidate cap, scope isolation, tenant/active guards, positive statement timeout, and dry-run default.

## Remaining Risks

- No real PostgreSQL lock-wait/timeout behavior was exercised because database and production access were prohibited.
- The versioned wrapper was syntax-checked and text-contract tested but deliberately not executed.

## Self-Check: PASSED

- All owned implementation, test, operations-doc, and summary files exist.
- All reported local verification commands completed successfully.
- No files were staged or committed.

---
*Phase: quick-260812-roj-workbench-generation-scope-generation-st*
*Completed: 2026-08-12*
