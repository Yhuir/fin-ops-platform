# Workbench Relations Workbench Matching Pair Service Boundary Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:workbench-matching-pair-service-boundary-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit broad `WorkbenchPairRelationService` reads in Workbench matching/orchestration and select the next smallest safe boundary without changing matching, grouping, candidate, refresh, relation write or API behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-turnover-workbench-pair-port-required-command-constructor.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py`
- `backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_workbench_matching_orchestrator.py`
- `tests/test_workbench_reconciliation_engine.py`
- CodeGraph context for matching/orchestrator relation reads.
- Text search for `WorkbenchMatchingOrchestrator`, `WorkbenchReconciliationEngine`, `pair_relation_service`, `_pair_relation_service`, `list_active_relations`, and `active_relations_for_row_ids`.

## Findings

- `WorkbenchMatchingOrchestrator` still imports `WorkbenchPairRelationService`, accepts `pair_relation_service`, stores `_pair_relation_service`, and passes it into `WorkbenchReconciliationEngine` when decision-store mode is active.
- In legacy candidate mode, `WorkbenchMatchingOrchestrator._active_pair_relation_row_ids(...)` calls `list_active_relations()` to suppress rows already held by active confirmed relations. This is a canonical active relation read used as matching-only candidate context; it is not a relation write and not a read model distribution read.
- `WorkbenchReconciliationEngine` still imports `WorkbenchPairRelationService`, accepts `pair_relation_service`, stores `_pair_relation_service`, and uses:
  - `list_active_relations()` in `_active_pair_relation_row_ids(...)` to suppress held rows and identify two-pane relations that can be extended to three-pane completion.
  - `active_relations_for_row_ids(...)` in `_auto_complete_two_pane_relations(...)` to find the single active relation that a paired decision may upgrade through `WorkbenchRelationCommandService.confirm_relation(..., replace_existing=True)`.
- `WorkbenchRelationCommandService` already exposes `list_active_relations()` and `active_relations_for_row_ids(...)`, so a narrow read port can delegate through the command boundary without inventing new relation semantics.
- A direct rewrite to `WorkbenchRelationReadFacade` is not a safe first implementation slice because matching needs canonical active relation rows and auto-completion uses active relation identity and before-relation snapshots, not downstream distribution payloads.
- The next implementation slice should preserve current behavior by extracting an explicit matching relation read port, not by changing matching logic or using read model distribution as a source of truth.

## Decision

Next boundary:

`workbench-relations:workbench-matching-relation-read-port-extraction`

Scope:

- Add an explicit matching relation read port for canonical active relation reads used by `WorkbenchMatchingOrchestrator` and `WorkbenchReconciliationEngine`.
- Move `list_active_relations()` and `active_relations_for_row_ids(...)` usage behind that port.
- Update `Application` wiring to inject the port, preferably backed by existing `WorkbenchRelationCommandService` read methods.
- Keep matching candidate suppression, decision generation, auto-completion, dirty scope, read model invalidation and API behavior unchanged.
- Add or strengthen static guard coverage so matching/orchestrator classes no longer accept or store broad `pair_relation_service`.

Not in scope:

- Do not change matching rules, grouping, candidate generation, auto-completion semantics, dirty scopes, read model refresh, relation writes, API response shape or frontend behavior.
- Do not convert matching compute to Go/Fiber.
- Do not declare `workbench_relation` closed.

## Legacy Path Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| `WorkbenchMatchingOrchestrator(pair_relation_service=...)` | next implementation gap | Constructor still accepts/stores broad pair service. |
| `WorkbenchReconciliationEngine(pair_relation_service=...)` | next implementation gap | Constructor still accepts/stores broad pair service. |
| Matching held-row suppression via `list_active_relations()` | canonical active relation read | Needed to avoid proposing candidates for held rows. |
| Auto-completion lookup via `active_relations_for_row_ids(...)` | canonical active relation read/precondition | Needed to upgrade exactly one two-pane relation through command service. |
| `WorkbenchRelationCommandService.list_active_relations()` / `active_relations_for_row_ids(...)` | existing narrow command-boundary read methods | Suitable backing for next extraction without changing semantics. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This audit closes only matching/orchestrator pair-service classification and selects the next narrow implementation boundary. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Decision |
| --- | --- | --- |
| Business core unit tests | Not changed in this audit slice | Next implementation should preserve matching suppression and auto-completion business behavior. |
| Service-layer tests | Not changed in this audit slice | Next implementation should run matching orchestrator and reconciliation engine tests. |
| API contract tests | Not changed in this audit slice | No HTTP/API behavior changed. |
| Read model/cache/background job tests | Not changed in this audit slice | No dirty scope, outbox, read model or worker behavior changed. |
| Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this analysis-only slice | No behavior changed. |
| Existing feature regression tests | Existing tests identified | `tests/test_workbench_matching_orchestrator.py` and `tests/test_workbench_reconciliation_engine.py` are the target regression surface for the next slice. |

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the Workbench matching pair-service boundary audit. It does not remove broad pair service from matching/orchestrator, close `workbench_relation`, validate production PostgreSQL/worker evidence, or unblock Go/Fiber/Go Worker admission.

## Next Boundary

`workbench-relations:workbench-matching-relation-read-port-extraction`
