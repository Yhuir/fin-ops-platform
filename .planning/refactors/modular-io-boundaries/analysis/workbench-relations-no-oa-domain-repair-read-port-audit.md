# Workbench Relations No-OA Domain Repair Read Port Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:no-oa-domain-repair-read-port-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit the remaining `NoOaBankBatchService` pair relation service dependency after the no-OA application snapshot port extraction, and decide the next narrow boundary for domain repair/read migration.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-no-oa-pair-service-boundary-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-no-oa-application-pair-snapshot-port-extraction.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `docs/modules/no-oa-bank-batches/README.md`
- `docs/modules/no-oa-bank-batches/state-machine.md`
- `docs/modules/no-oa-bank-batches/tests.md`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
- `tests/test_no_oa_bank_batch_service.py`
- `tests/test_no_oa_bank_batch_application_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for `NoOaBankBatchService`, `WorkbenchPairRelationService`, `active_relations_for_row_ids`, and no-OA relation command boundaries.

## Findings

The remaining no-OA domain pair service dependency is concentrated and still semantically active. It is not safe to delete without a replacement port.

`NoOaBankBatchService` still stores `_pair_relation_service` for three related reasons:

1. Month-scoped rebuilds pass the same relation dependency into a scoped child service in `_build_batches_for_month_scope(...)`.
2. Submitted no-OA relation repair checks canonical relation state before issuing command-service-backed repair writes in `_repair_submitted_no_oa_relation_consistency(...)`.
3. Public stale/submitted projection and withdraw eligibility call `_has_active_no_oa_relation(...)`, which reads the active relation by case id.

The write side is already command-service gated:

- `_confirm_no_oa_relation(...)` requires `relation_command_service` and delegates to `confirm_relation(...)`.
- `_cancel_no_oa_relation(...)` requires `relation_command_service` and delegates to `cancel_relation(...)`.
- Existing static guard `test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback` prevents direct `_pair_relation_service.create_active_relation`, `.cancel_relation`, or `.record_history` fallback from returning.

The read side still calls the broad pair relation service directly:

- `_repair_submitted_no_oa_relation_consistency(...)`
  - `get_active_relation_by_case_id(relation_case_id)` determines whether the submitted batch already has a matching no-OA active relation.
  - `active_relations_for_row_ids(row_ids)` identifies non-no-OA blocking relations before repair.
  - `active_relations_for_row_ids(row_ids)` also finds stale no-OA relations that should be cancelled through the command service.
- `_has_active_no_oa_relation(...)`
  - `get_active_relation_by_case_id(relation_case_id)` determines whether a stale batch should be presented as submitted and withdrawable.

The current `_ForbiddenRelationReadVisitor` allows exactly these domain service methods and no longer allows direct pair reads inside `NoOaBankBatchApplicationService`.

## Classification

| Surface | Current classification | Target classification | Notes |
| --- | --- | --- | --- |
| `NoOaBankBatchService._pair_relation_service` constructor dependency | broad legacy read dependency | replace with explicit no-OA relation read/repair port | Still needed for repair/projection until the port exists. |
| `_repair_submitted_no_oa_relation_consistency(...)` relation reads | compat-only repair read path | move reads behind port | Writes must stay command-service backed. |
| `_has_active_no_oa_relation(...)` relation read | compat-only projection/withdraw guard | move read behind port | Must preserve stale-as-submitted public behavior. |
| `_build_batches_for_month_scope(...)` dependency forwarding | support wiring | forward the new port | Scoped child service must share the same read/repair port. |
| `_confirm_no_oa_relation(...)` / `_cancel_no_oa_relation(...)` | canonical command write path | keep | No direct pair write fallback allowed. |

## Decision

The next boundary should be:

`workbench-relations:no-oa-domain-repair-read-port-extraction`

Scope:

- Introduce an explicit no-OA relation read/repair port for the domain service.
- Port methods should cover:
  - active no-OA relation by case id.
  - active relations for row ids.
  - active relation matching/submitted batch helper if needed to keep domain code narrow.
- Inject the port into `NoOaBankBatchService` and `from_snapshot(...)`.
- Forward the port into month-scoped child services.
- Preserve `_confirm_no_oa_relation(...)` and `_cancel_no_oa_relation(...)` as command-service-backed writes.
- Preserve `test_stale_batch_with_active_no_oa_relation_stays_in_submitted_bucket`.
- Preserve submitted relation repair and stale relation cancellation tests.
- Strengthen `tests/test_platform_runtime_boundary_guards.py` so `NoOaBankBatchService` no longer directly stores or calls `_pair_relation_service` after extraction.

Not in scope for the next slice:

- Do not change no-OA batch status semantics.
- Do not change submit, withdraw, internal transfer, dirty scope, read model refresh or API payloads.
- Do not migrate application snapshot/persist/rollback again.
- Do not implement Go/Fiber/Go Worker.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/no-oa-bank-batches/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice classifies remaining no-OA domain relation read/repair dependencies and selects the next implementation boundary. `workbench_relation` remains `implementation-gap-open`.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not changed in this audit slice. Next implementation slice must keep no-OA status/projection behavior covered. |
| Service-layer tests | Not changed in this audit slice. Next implementation slice should run `tests.test_no_oa_bank_batch_service` and targeted no-OA application/API tests. |
| API contract tests | Not applicable. No HTTP/API shape changed. |
| Read model/cache/background job tests | Not applicable. No refresh, dirty scope, cache or worker behavior changed. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this analysis-only slice. |
| Existing feature regression tests | Existing service tests and static guards were inspected; next implementation must strengthen guards to forbid direct pair reads in the domain service. |

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the no-OA domain repair/read dependency audit. It does not remove `NoOaBankBatchService._pair_relation_service`, close `workbench_relation`, classify ETC or WorkbenchWriteFacade relation dependencies, validate production PostgreSQL/worker evidence, or unblock Go admission.
