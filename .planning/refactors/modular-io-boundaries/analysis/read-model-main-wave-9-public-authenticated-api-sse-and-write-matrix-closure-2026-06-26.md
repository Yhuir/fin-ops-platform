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
