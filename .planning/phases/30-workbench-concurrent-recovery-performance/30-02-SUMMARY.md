---
phase: 30-workbench-concurrent-recovery-performance
plan: "02"
subsystem: workbench
tags: [postgresql, active-generation, relation-preview, performance, tdd]

requires:
  - phase: 30-01
    provides: searched initial-page freshness gate and Phase 30 Workbench performance baseline
provides:
  - bounded active-generation row and OA attachment context reads for confirm/withdraw previews
  - preview-only selection DTO with generation proof, stable errors and hard input bounds
  - mechanical isolation between derived preview snapshots and canonical formal relation UoW
affects: [30-03, 30-04, reconciliation-workbench, workbench-relations, read-models]

tech-stack:
  added: []
  patterns:
    - preview-only bounded active-generation selection port
    - generation proof before and after selected-row reads
    - formal command isolation from derived preview DTOs

key-files:
  created: []
  modified:
    - backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
    - backend/src/fin_ops_platform/services/workbench_query_facade.py
    - backend/src/fin_ops_platform/services/workbench_write_facade.py
    - backend/src/fin_ops_platform/app/server.py
    - tests/test_workbench_sql_runtime.py
    - tests/test_workbench_write_characterization.py
    - tests/test_platform_runtime_boundary_guards.py

key-decisions:
  - "Reuse the existing generation/scope/row and generation/scope/zone/group indexes; EXPLAIN showed no migration or new index was justified."
  - "Bound preview input to 20 selected rows and 100 derived context rows, with missing, duplicate, non-fresh, cross-generation and drift states failing closed."
  - "Treat active-generation selection as a preview-only DTO; formal confirm/withdraw continue to re-read canonical facts, relation versions and idempotency inside the existing command/UoW."

patterns-established:
  - "Relation previews perform exactly one selection-port call per request; the port owns all bounded selected/context reads."
  - "Preview errors expose stable codes and safe Chinese messages, while request IDs remain available through the existing response header/timing path."

requirements-completed: [RELVIS-01, RELVIS-08, RMF-06, RMF-08]

duration: 31min
completed: 2026-07-26
---

# Phase 30 Plan 02: Bounded Relation Preview Selection Summary

**Confirm/withdraw previews now read only bounded active-generation rows and OA attachment context, while formal writes remain canonical command/UoW operations.**

## Performance

- **Duration:** 31 min
- **Started:** 2026-07-25T18:13:25Z
- **Completed:** 2026-07-25T18:44:13Z
- **Tasks:** 3
- **Files modified:** 17

### Same-fixture 10-run evidence

The disposable PostgreSQL fixture contained two month shards, 600 groups/1,800 active rows per month, active plus obsolete generations, and OA/bank/invoice/OA-attachment rows. Old and new measurements used the same scopes, versions, selected IDs, 2/6/20 sizes and warm-up rule. The legacy path operated on the equivalent materialized in-memory full payload because PostgreSQL snapshots intentionally retain only a metadata shell; it performed zero SQL but repeatedly deep-copied/scanned the complete payload.

| Scope / selection | Old confirm p50 / p95 | New confirm p50 / p95 | Old withdraw p50 / p95 | New withdraw p50 / p95 |
|---|---:|---:|---:|---:|
| month / 2 | 87.542 / 114.846 ms | 2.930 / 3.516 ms | 20.484 / 21.111 ms | 1.047 / 1.451 ms |
| month / 6 | 130.274 / 139.738 ms | 0.925 / 1.012 ms | 19.369 / 19.993 ms | 0.942 / 1.088 ms |
| month / 20 | 222.378 / 248.509 ms | 1.439 / 1.518 ms | 19.302 / 20.575 ms | 1.472 / 1.893 ms |
| all / 2 | 53.922 / 79.625 ms | 1.151 / 1.380 ms | 12.778 / 12.902 ms | 0.826 / 1.142 ms |
| all / 6 | 66.723 / 92.358 ms | 0.812 / 0.882 ms | 12.699 / 12.913 ms | 0.728 / 0.755 ms |
| all / 20 | 155.922 / 157.846 ms | 1.036 / 1.141 ms | 12.729 / 12.928 ms | 1.115 / 1.187 ms |

New measurements used a single transaction/connection, performed 10 warm runs per operation, issued a fixed six counted SQL calls per run in the benchmark harness, and performed zero complete payload copies/scans. The maximum new sample was 5.089 ms, comfortably below the preview-specific 3-second evidence target.

### EXPLAIN / index evidence

- Month row detail used `workbench_rows_generation_scope_row_uidx`; group detail used `workbench_groups_generation_scope_zone_group_uidx`.
- Month `row_id=ANY` bulk lookup returned 3 rows with 10 shared-buffer hits, 0 reads and 0.103 ms execution.
- All-scope generation-set lookup performed a two-shard nested loop whose inner scans both used `workbench_rows_generation_scope_row_uidx`; it returned 3 rows with 19 shared-buffer hits, 0 reads and 0.197 ms execution.
- No migration, index, cache, queue, worker or second read-model owner was added.

## Accomplishments

- Added a set-based repository/query-facade port that binds selected rows and OA attachment context to one expected active generation or generation-set and rechecks freshness/version after reading.
- Migrated only `preview_confirm_link` and `preview_withdraw_link` to one bounded selection call and removed their full-payload, live-row, repeated alias and withdraw-row scan paths.
- Preserved preview-only `group_type=selection` output and the formal `paired/unpaired` page model.
- Proved formal confirm/withdraw never consume preview selection by installing an exploding preview callable while canonical command/UoW tests still pass.
- Added stable preview error codes/safe messages plus request timing and `X-Request-ID` coverage.

## Task Commits

Each task was committed atomically:

1. **Task 1: Characterize row/group detail, indexes and formal canonical boundary** - `1d119fd39` (`test`)
2. **Task 2: Add preview-only bounded bulk read** - `6d5be5d0d` (`feat`)
3. **Task 3: Migrate only confirm/withdraw preview** - `177790a29` (`perf`)

Additional AGENTS-required contract documentation:

- `90abd4d97` - document bounded preview I/O, formal isolation and benchmark evidence

## TDD Gate Compliance

- RED: `1d119fd39` added failing repository-port and preview-wiring guards; both failed before implementation while the formal isolation negative test passed.
- GREEN: `6d5be5d0d` added the bounded repository/query port; `177790a29` completed preview wiring and made the full targeted suite pass.
- REFACTOR: preview-only dead operation-projection/fallback code was removed in the Task 3 commit; no separate behavior-neutral refactor commit was necessary.

## Files Created/Modified

- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` - bounded generation-bound selected-row and OA attachment context queries.
- `backend/src/fin_ops_platform/services/workbench_query_facade.py` - preview selection validation and stable result/error mapping.
- `backend/src/fin_ops_platform/services/workbench_read_model_version.py` - selection/context limits and typed preview selection failure.
- `backend/src/fin_ops_platform/services/workbench_write_facade.py` - one selection call per confirm/withdraw preview; formal methods unchanged.
- `backend/src/fin_ops_platform/app/routes_workbench_actions.py` - confirm preview consumes the standard write result contract.
- `backend/src/fin_ops_platform/app/server.py` - injects the query port and records preview request ID/timing.
- `tests/test_workbench_sql_runtime.py` - bounded SQL shape, attachment context and missing-row fail-closed coverage.
- `tests/test_workbench_stale_write_contract.py` - version-drift and oversized-input contracts.
- `tests/test_workbench_write_characterization.py` - formal isolation, one-call preview boundary and stable error/request ID coverage.
- `tests/test_workbench_auth_context_idempotency.py` - withdraw preview one-call boundary, alias/grouping and formal regressions.
- `tests/test_platform_runtime_boundary_guards.py` - AST guards against preview full scans and formal preview dependency.
- `tests/app_test_support.py` - local-state test adapter for the production selection contract.
- `docs/architecture/module-boundaries/read-model-contracts.md` - long-term bounded preview/fact-source contract.
- `docs/modules/reconciliation-workbench/boundary-io.md` - reconciliation Workbench preview I/O boundary.
- `docs/modules/reconciliation-workbench/tests.md` - tests, benchmark and EXPLAIN evidence.
- `docs/modules/workbench-relations/boundary-io.md` - formal relation isolation contract.
- `docs/modules/read-models/boundary-io.md` - active-generation selection ownership and bounds.

## Decisions Made

- Existing indexes are sufficient. Schema work was rejected because measured month/all plans already use the generation-bound unique indexes with zero disk reads.
- A 20-row selected bound and 100-row derived context bound are enforced in both the query boundary and repository trust boundary.
- OA attachment context is read from the same active generation set and never from `workbench:all`, a cache payload, live rebuild or shared `workbench_relation` projection.
- Formal submit never accepts the preview DTO. Actor/tenant, preview identity, relation version, audit, idempotency and canonical UoW behavior remain authoritative.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added explicit relation preview resource bounds**
- **Found during:** Task 2
- **Issue:** The existing generic row normalizer deduplicated inputs but did not enforce a relation-action upper bound, while the threat model requires bounded untrusted row IDs.
- **Fix:** Added 20 selected-row and 100 context-row limits at the facade/repository boundaries, with stable fail-closed errors.
- **Files modified:** `workbench_read_model_version.py`, `workbench_query_facade.py`, `read_models.py`
- **Verification:** Oversized input is rejected before repository I/O; 2/6/20 selection tests and benchmark pass.
- **Committed in:** `6d5be5d0d`

**2. [Rule 2 - AGENTS.md contract maintenance] Updated affected module/read-model documentation**
- **Found during:** Task 3 closeout
- **Issue:** The new preview I/O port changes reconciliation-workbench, workbench-relations and read-model boundary/test contracts.
- **Fix:** Updated all affected `boundary-io.md`, long-term read-model contract and module test evidence.
- **Files modified:** five files under `docs/architecture/module-boundaries/` and `docs/modules/`
- **Verification:** `bash scripts/verify.sh docs` passed.
- **Committed in:** `90abd4d97`

---

**Total deviations:** 2 auto-fixed (2 Rule 2)
**Impact on plan:** Both changes enforce the stated security/resource boundary and repository documentation rules; no feature, schema or infrastructure scope was added.

## Issues Encountered

- The default framework Python did not expose Ruff as a module, while the repository already had Ruff in the Miniconda toolchain. The required lint command passed with `PATH=/opt/miniconda3/bin:$PATH`; no dependency was installed.
- The first disposable database URL omitted a host and was rejected by the migration safety checker. The explicit test database was recreated through the accepted localhost URL, fully migrated, verified and dropped after use.

## Known Stubs

None. No placeholder, mock or empty production data source was introduced.

## Threat Flags

None. The new database read surface is the preview trust boundary already covered by T-30-02-02, T-30-02-04 and T-30-02-05; no endpoint, auth path, schema or write boundary was added.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime tests.test_workbench_write_characterization tests.test_workbench_relation_command_service tests.test_workbench_uow_contract tests.test_workbench_idempotency_contract tests.test_workbench_stale_write_contract tests.test_platform_runtime_boundary_guards` — 538 passed.
- Task 3 facade/API/formal/UoW/idempotency/boundary slice — 433 passed.
- `PATH=/opt/miniconda3/bin:$PATH bash scripts/verify.sh lint` — passed.
- `bash scripts/verify.sh docs` — passed.
- Real disposable PostgreSQL month/all selection smoke and EXPLAIN/BUFFERS — passed; database `fin_ops_test_30_02` dropped and confirmed absent.
- Whole-repo scan — preview legacy scan calls are guarded at zero; formal command/UoW files contain no `relation_preview_selection`; non-preview `_resolve_live_rows_direct` callers remain.
- Per instruction, pytest, the unrelated 183-browser suite, full CI, deploy and push were not run.

## Test Coverage Categories

1. **Business core unit tests — applicable:** amount/group/alias semantics and invalid/missing/duplicate selection paths are covered.
2. **Service-layer tests — applicable:** repository/query/write facade ownership, generation drift and one-call behavior are covered.
3. **API contract tests — applicable:** stable error code/message, conflict status and request ID are covered.
4. **Read model/cache/background jobs — applicable in part:** active-generation freshness/proof and no-cache/no-queue behavior are covered; no worker behavior changed.
5. **Frontend interaction tests — not applicable:** no frontend files or UI behavior changed.
6. **End-to-end business-flow integration — applicable:** confirm/withdraw preview-to-formal regression slices preserve the canonical command/UoW path; no browser rerun was required for unchanged frontend.
7. **Existing feature regression — applicable:** relation command, UoW, idempotency, stale-write, grouping, V2 API and retained non-preview live-row callers are covered.

## User Setup Required

None - no dependency, environment variable, migration or external service configuration was added.

## Next Phase Readiness

- Plan 30-03 can build on a bounded relation preview path with measured local headroom and no schema debt.
- No correctness or implementation blocker remains. Production concurrent latency remains the later Phase 30 verification scope; this plan intentionally made no deploy or production claim.

## Self-Check: PASSED

- All files listed in `key-files` and the plan summary exist.
- Task commits `1d119fd39`, `6d5be5d0d`, `177790a29`, and `90abd4d97` are present in git history.

---
*Phase: 30-workbench-concurrent-recovery-performance*
*Completed: 2026-07-26*
