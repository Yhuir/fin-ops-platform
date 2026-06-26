# Read Model Main Wave 9 - Public Authenticated API/SSE and Write Matrix Closure

Date: 2026-06-26
Branch: `main`

## Current Result

Wave 9 is in progress. The first production write-matrix evidence pass found turnover/workbench/no-OA write samples could execute and restore, but turnover-related write-operation SLO still had long-tail failures caused by broad `all` refresh targets on normal month-addressable write paths. This file records the local code closure for that root cause before the next deploy/production retest.

This is not a global closure claim. Production public authenticated API/SSE/browser proof and the full write matrix still require post-deploy evidence.

## Root Cause

Turnover relation and manual closure writes already know their affected months, but normal write targets still included broad scopes:

- `turnover_ledger:all`
- `workbench:all`
- `workbench_relation:all`
- `cost_statistics` and `search` requests carrying raw `all`

Those targets forced fan-out or parent aggregate paths during ordinary writes and caused write-after-read freshness SLO long tails. The manifest already classifies `turnover_ledger:all` as fan-out command semantics, so using it as the default normal write target violated the intended Partitioned + Scoped + Incremental Projection contract.

## Local Fix

- `TurnoverLedgerWriteFacade` now uses affected month scope keys for:
  - bank-row-tags batch;
  - relation confirm;
  - manual zero-difference closure confirm;
  - relation withdraw.
- `TurnoverLedgerConfirmRequestBoundaryFacade` returns affected `turnover_ledger:<month>` targets plus affected `workbench_relation:<month>` targets for manual closure visibility.
- `TurnoverLedgerPage` waits for affected `turnover_ledger:<month>` scopes before manual closure fresh rebind; it falls back to `all` only when no selected row month can be parsed.
- `all` remains available only for fan-out/global/unknown-month exception paths, such as cash closure withdraw where the affected months are not known until the handler returns.

## Docs Updated

- `docs/modules/turnover-ledger/state-machine.md`
- `docs/modules/turnover-ledger/boundary-io.md`
- `docs/modules/turnover-ledger/tests.md`
- `docs/modules/turnover-ledger/implementation-notes.md`
- `docs/modules/read-models/implementation-notes.md`

## Verification So Far

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest -q tests.test_turnover_ledger_api tests.test_turnover_ledger_uow_contract tests.test_read_model_write_targets
```

Result: 224 tests passed.

```bash
npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx
```

Result: 35 tests passed.

```bash
PYTHONPATH=backend/src python3 -m unittest -q tests.test_turnover_ledger_api tests.test_turnover_ledger_uow_contract tests.test_read_model_write_targets tests.test_write_operation_slo_audit tests.test_slo_tool_defaults tests.test_read_model_manifest tests.test_runtime_worker_read_model_refresh_scopes tests.test_operation_freshness_barrier
```

Result: 298 tests passed.

## Open Production Evidence

Still required after commit/deploy:

- Deploy the turnover write-target narrowing to production.
- Re-run critical read model SLO smoke.
- Re-run controlled turnover/workbench/no-OA write-operation samples through business logic.
- Restore samples through business inverse when available; use the preapproved bounded DB restore protocol only when no business restore path exists and operation-before snapshot + exact predicate + transaction safety + post-restore verification are established.
- Re-check dirty/outbox/readiness aggregate and public/server-local API freshness.
- Do not claim full PSCIP-L4/global closure until the write matrix and public authenticated evidence are complete.

## Production Retest After Turnover Scope Narrowing

Release `main-28569b0b-20260626102452` deployed successfully from commit
`28569b0bacd8f03052928ee06db7da5e145ea92e`.

Post-deploy read-model evidence:

- scope contract: `ok=true`, `violation_count=0`;
- critical `read_model_slo_smoke --apply --critical-only --target-ms 5000`: 15/15 passed, enqueue-to-fresh p95/max `1963.289ms`;
- DB aggregate after smoke: no non-done outbox rows, no non-done dirty scopes, `read_model.app_status_readiness fresh=499`.

Controlled write evidence:

- `turnover-withdraw-turnover_rel_36266274e9235566` used the external turnover page relation withdraw endpoint and returned HTTP `409` with `turnover_closure_withdraw_requires_workbench`; the relation stayed `confirmed`, version `1`, event count `1`, with no dirty/outbox mutation. This is correct contract behavior for turnover relations that have been upgraded into a complete Workbench relation.
- `workbench-withdraw-turnover:turnover_rel_89e8fb47e3ffce91` used the Workbench business endpoint `POST /api/workbench/actions/withdraw-link`. The write step succeeded, but write-operation SLO failed: Workbench, Workbench Relation, Bank Detail, Pending Invoice, Cost Statistics and Search scopes eventually completed but exceeded the 5s target; the Workbench post API probe returned `read_model_status=refreshing`.
- The selected Workbench sample had no business `cancelled -> active` restore path. The pre-approved bounded DB restore protocol was used: one `app.workbench_pair_relations` row and case-local `app.workbench_pair_relation_history` were restored from the operation-before snapshot using exact `case_id='turnover:turnover_rel_89e8fb47e3ffce91'` predicates. No readiness, dirty scope, outbox or cache row was modified to fake fresh state.
- Post-restore canonical check matched the operation-before state: active, version `1`, `withdrawn_at is null`, history count `6`.
- Post-restore critical read-model refresh reached fresh state, but `workbench:2026-01` enqueue-to-fresh was `9508.538ms`, exceeding 5s. Queue inspection showed remaining non-done items were `workbench.read_model.refresh` aggregate-only `workbench:all` events with `aggregate_only=true` and repeated parent scope sets.

## Additional Local Fix In Progress

The second root cause is not a stale-as-fresh correctness bug; it is Workbench parent aggregate queue amplification:

- month shard refresh publishes correctly;
- aggregate-only `workbench:all` parent refreshes are valid and must remain;
- but aggregate-only parent refreshes were deduped by source version in multiple enqueue paths, producing multiple pending low-priority parent events instead of coalescing into one pending aggregate event with merged `parent_scope_keys`.

Local code fix:

- `RuntimeQueueRepository.enqueue_workbench_all_aggregate_refresh(...)` now provides a Workbench-specific coalescing enqueue path with stable dedupe key `workbench.read_model.refresh:workbench:all:aggregate`, merged `parent_scope_keys`, max `source_version`, retained `reason`, and stable priority/trace handling.
- `WorkbenchReadModelRefreshService` uses the coalescing enqueue path when available and falls back to the old generic enqueue only for compatibility.
- `PostgresWorkbenchRelationRepository` transaction-side aggregate helper uses the same stable aggregate dedupe key and merges `parent_scope_keys` instead of creating source-version-specific pending parent events.

Local verification added/passed:

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_queue.py tests/test_workbench_relation_repository.py tests/test_write_operation_slo_audit.py tests/test_read_model_slo_smoke.py -q
```

Result: 96 tests passed.

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_enqueues_low_priority_all_aggregate_after_month_publish tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_uses_coalescing_all_aggregate_enqueue_when_available tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_can_enqueue_aggregate_without_legacy_enqueue_method tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_expands_all_into_month_shards tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_completes_all_after_aggregate_only_event tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_completes_all_when_aggregate_publish_is_confirmed_despite_self_dirty_status tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_aggregate_only_all_scope_defers_when_parent_generation_is_inconsistent -q
```

Result: 7 tests passed.

This still is not global closure. The coalescing fix must be committed, deployed, and retested with production critical SLO plus the Workbench turnover write sample.
