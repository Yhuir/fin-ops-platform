# Post Shadow-Read Rehearsal Next Boundary Selection - 2026-06-25

**Boundary:** `planning:post-shadow-read-rehearsal-next-boundary-selection`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `production:workbench-read-model-high-row-query-plan-read-only-runbook`

## Goal

Reconcile Row255 shadow-read rehearsal evidence and select the next safe boundary that advances closure without relying on `local_pickle` as a production primary comparator.

This slice does not claim module or global closure.

## Inputs Reviewed

- `analysis/production-read-model-shadow-read-rehearsal-read-only-runbook-2026-06-25.md`
- `analysis/planning-post-public-page-shell-smoke-next-boundary-selection-2026-06-25.md`
- `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
- `analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`
- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
- Workbench read-model table/index references in migrations and tests surfaced by `rg`
- `autonomous/STATE.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

## Reconciled Row255 Evidence

Row255 proved:

- `/health/ready` stayed ready before and after.
- `run_shadow_read_rehearsal` is deployed and available.
- Production read-only guard can execute under runtime env without printing secrets.
- The tool output was redacted/hash-summary based.
- Direct root shell lacks DB config, which is expected outside the service runtime.

Row255 did not prove read-model closure:

- The selected `local_pickle` primary is not a comparable authoritative primary for current production PostgreSQL runtime.
- The PostgreSQL side contained data for relation, no-OA, cost and tax domains while `local_pickle` primary was missing those payloads.
- `pending_invoice_commands` failed on the `local_pickle` primary path.
- `workbench_read_models` hit a PostgreSQL statement timeout, which is a real high-row evidence gap.

## Candidate Boundary Review

| Candidate | Decision | Reason |
| --- | --- | --- |
| Retry `run_shadow_read_rehearsal` with `local_pickle` primary | Rejected | It would reproduce non-comparable primary mismatches and not advance closure. |
| Run `postgres` vs `postgres` shadow-read rehearsal | Rejected | It would be tautological and would not prove old-vs-new parity, API shape, browser behavior or high-row safety. |
| Authenticated API smoke retry | Rejected for now | Row252 already proved non-secret auth config is absent. |
| Browser data smoke | Deferred | Without auth/API data path, browser data smoke would not prove read-model closure. |
| New worker wave | Deferred | The open gap is production/runtime evidence and should stay T0-owned. |
| Workbench PostgreSQL-native high-row query plan/read-only diagnosis | Accepted | It directly targets the one concrete Row255 production gap: `workbench_read_models` statement timeout on high-row data. It can use read-only SQL under PostgreSQL user, collect counts/index/EXPLAIN/timeout classification, avoid payload rows and avoid auth secrets. |

## Selected Boundary

Select `production:workbench-read-model-high-row-query-plan-read-only-runbook`.

The next boundary must write and execute a bounded read-only production runbook that:

1. Uses `/health/ready` pre/post checks.
2. Uses `runuser -u postgres -- psql -d fin_ops` with `set default_transaction_read_only = on`, `begin read only` and `rollback`.
3. Collects only aggregate/high-row evidence:
   - active generation id and scope count;
   - row counts for `read_model.workbench_rows`, `read_model.workbench_group_rows`, `read_model.workbench_groups` by active generation and top scopes;
   - relevant index names/definitions or index scan stats;
   - bounded `EXPLAIN (FORMAT JSON)` or `EXPLAIN` for representative high-row Workbench queries without executing broad result fetches;
   - statement timeout classification for any probe that cannot complete.
4. Does not select payload columns, full rows, sensitive counterparty names, invoice details, tokens, cookies, DSNs or env values.
5. Performs no DB writes, queue/readiness mutation, deploy, restart, requeue, repair, replay or `--apply`.

## Why This Is The Highest-Risk Safe Next Step

- It follows the evidence: Row255's only PostgreSQL-side runtime gap was Workbench high-row timeout.
- Workbench is the largest row245 production surface: `workbench_group_rows`, `workbench_groups` and `workbench_rows` have high row counts.
- It does not depend on auth secrets, browser login or obsolete `local_pickle` parity.
- It can produce actionable production evidence for later API/browser/high-row closure or performance remediation without changing runtime behavior.

## State-Machine Impact

- Row255 remains `production-evidence-deferred`.
- Row256 closes as `planning-closed`.
- Row257 should be inserted as `pending`.
- No module closure changes to `closed`.
- Go admission remains blocked; this is evidence gathering, not Go admission.

## Docs Impact Assessment

Controller accounting only:

- Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `prompts/04-master-goal-controller.md`.

No module docs or long-term architecture docs change in this planning slice because no runtime behavior, API contract, worker contract or module state machine changes.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rules changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: still open and deferred until a non-secret auth path exists.
4. Read model/cache/background job tests: applicable to the next boundary as production read-only evidence; no local tests changed here.
5. Frontend component and interaction tests: still open; this planning slice does not exercise UI.
6. End-to-end business-flow integration tests: still open; this planning slice selects a lower-level read-model performance/evidence boundary first.
7. Existing feature regression tests: planning-only regression is covered by docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- secret scan over changed files
- `git diff --cached --check` after staging

No production command is executed in this planning slice.
