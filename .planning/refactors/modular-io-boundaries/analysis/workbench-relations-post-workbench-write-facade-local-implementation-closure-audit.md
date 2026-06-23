# Workbench Relations Post-WorkbenchWriteFacade Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:post-workbench-write-facade-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Re-audit broader `workbench_relation` local implementation gaps after `WorkbenchWriteFacade` stopped accepting broad `pair_relation_service`, and select the next smallest safe boundary before any production-evidence defer or Go admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/prompts/04-master-goal-controller.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-required-port-constructor.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-post-port-local-implementation-closure-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `backend/src/fin_ops_platform/services/etc_batch_invoice_link_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_turnover_ledger_uow_contract.py`
- CodeGraph context for remaining `workbench_relation` local gaps.
- Text search for `pair_relation_service`, `_workbench_pair_relation_service`, `WorkbenchPairRelationService`, `WorkbenchRelationCommandService`, `WorkbenchRelationReadFacade`, and `TurnoverLedgerWorkbenchPairPort`.

## Findings

- Planning state is consistent: the first pending queue item is this audit boundary, the last completed boundary is `workbench-relations:workbench-write-facade-required-port-constructor`, and Go hot-path candidates remain `blocked-by-prerequisite`.
- `WorkbenchWriteFacade` no longer stores or accepts broad `pair_relation_service`; production and test construction now inject explicit read/snapshot and special metadata mutation ports.
- ETC repair/link/migration services are not the next highest-risk local gap:
  - `historical_etc_repair_service.py`, `historical_etc_business_batch_migration_service.py`, and `existing_etc_batch_link_service.py` use `WorkbenchRelationCommandService` methods and are covered by an existing static guard that forbids direct pair fallback.
  - `EtcBatchInvoiceLinkService` persists ETC batch invoice membership through its own repository and does not hold pair relation service.
- Remaining broad pair service references in `server.py` include several intentionally retained explicit adapter/recovery boundaries, such as command repository adapter construction, rollback restore service construction, no-OA snapshot port construction, settings data reset snapshot handling, and read-only/snapshot route helpers.
- The next smallest unsafe-looking surface is turnover:
  - `Application._turnover_ledger_closure_write_facade(...)` and `_turnover_ledger_withdraw_write_facade(...)` still pass `pair_relation_service=self._workbench_pair_relation_service` into turnover primary builders.
  - `Application._turnover_ledger_closure_legacy_fallback_facade(...)` and `_turnover_ledger_withdraw_legacy_fallback_facade(...)` still pass broad pair service into legacy fallback facades.
  - `TurnoverLedgerConfirmPrimaryWriteFacadeBuilder` and `TurnoverLedgerWithdrawPrimaryWriteFacadeBuilder` still pass broad pair service into `TurnoverLedgerWorkbenchPairPort`.
  - `TurnoverLedgerWorkbenchPairPort` still accepts and stores `pair_relation_service`, even though writes already fail fast when `WorkbenchRelationCommandService` is unavailable and current tests use blocking pair-service fakes to prove write paths must not fall back to pair writes.
  - `TurnoverLedgerWorkbenchPairPort.assert_turnover_manual_closure_withdrawable(...)` still has a pair-service read fallback when `relation_facade` cannot provide the active relation. This keeps a broad old read surface alive inside the turnover relation write port.
- `TurnoverLedgerLocalClosureConnection` still uses pair service for local transaction snapshot/rollback persistence. That is a separate rollback/snapshot boundary and should not be removed in the same slice as the port constructor cleanup.

## Decision

Next boundary:

`workbench-relations:turnover-workbench-pair-port-required-command-constructor`

Scope:

- Remove `pair_relation_service` from `TurnoverLedgerWorkbenchPairPort.__init__`.
- Make turnover Workbench pair port rely on explicit command service and relation facade boundaries only.
- Remove the pair-service fallback read path inside `TurnoverLedgerWorkbenchPairPort`.
- Update primary builder and legacy fallback facade construction so they no longer pass broad pair service into `TurnoverLedgerWorkbenchPairPort`.
- Keep builder-level `pair_relation_service` only where it is still required for local transaction snapshot/rollback via `TurnoverLedgerLocalClosureConnection`.
- Preserve turnover confirm/withdraw behavior, relation command service writes, freshness/read-model behavior, API response shape, and local rollback semantics.
- Strengthen/static guard the port so it cannot re-accept or store broad pair service.

Not in scope:

- Do not remove `TurnoverLedgerLocalClosureConnection` pair snapshot rollback behavior in this slice.
- Do not change turnover relation business rules, amount rules, affected month scope rules, dirty outbox behavior, or operation barrier behavior.
- Do not change ETC behavior.
- Do not declare `workbench_relation` closed.
- Do not implement Go/Fiber/Go Worker.

## Legacy Path Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| `WorkbenchWriteFacade.__init__(pair_relation_service=...)` | removed | Previous slice removed the broad constructor parameter. |
| ETC repair/link/migration direct pair fallback | already removed/guarded | Existing guard rejects `pair_relation_service` and `_pair_relation_service` in ETC repair/link/migration services. |
| `TurnoverLedgerWorkbenchPairPort(pair_relation_service=...)` | next implementation gap | Port still accepts/stores broad pair service and has a read fallback. |
| Turnover builder `pair_relation_service` for local rollback connection | retained for later classification | Local transaction connection snapshots and restores pair relation state; separate rollback/snapshot boundary. |
| `WorkbenchRelationCommandRepositoryAdapter` pair service usage | explicit command repository adapter | Required adapter currently owns in-memory snapshot merge/apply behavior. |
| rollback restore services using `replace_pair_relation_service` | explicit rollback boundary | Existing guards require these services for rollback recovery paths. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice updates progress/accounting only. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Decision |
| --- | --- | --- |
| Business core unit tests | Not changed in this audit slice | Next implementation should not change turnover amount, mode, state transition, permission, or idempotency rules. |
| Service-layer tests | Not changed in this audit slice | Next implementation should run turnover UoW contract tests covering `TurnoverLedgerWorkbenchPairPort`. |
| API contract tests | Not changed in this audit slice | No HTTP/API behavior changed. |
| Read model/cache/background job tests | Not changed in this audit slice | No dirty scope, outbox, freshness or barrier behavior changed. |
| Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this analysis-only slice | No behavior changed. |
| Existing feature regression tests | Existing tests identified | Static boundary guard plus turnover UoW/workbench integration tests are the target next-slice coverage. |

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the post-WorkbenchWriteFacade local implementation closure audit. It does not close `workbench_relation`, does not remove turnover broad pair service usage, does not validate production PostgreSQL/worker evidence, and does not unblock Go/Fiber/Go Worker admission.

## Next Boundary

`workbench-relations:turnover-workbench-pair-port-required-command-constructor`
