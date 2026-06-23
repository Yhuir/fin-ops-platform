# Workbench Relations WorkbenchWriteFacade Post-Port Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:workbench-write-facade-post-port-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Re-audit WorkbenchWriteFacade after relation read/snapshot and cash special metadata mutation ports to decide whether remaining local gaps need more implementation before broader `workbench_relation` closure work.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-cash-special-metadata-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-cash-special-metadata-boundary-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-relation-read-snapshot-port-extraction.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_workbench_write_characterization.py`
- `tests/test_workbench_auth_context_idempotency.py`
- `tests/test_platform_runtime_boundary_guards.py`
- Text search for `WorkbenchWriteFacade(`, `_pair_relation_service`, `pair_relation_service=`, `relation_read_snapshot_port=` and `relation_special_metadata_mutation_port=`.

## Findings

- `WorkbenchWriteFacade` no longer stores broad `_pair_relation_service`.
- Direct pair service calls in `workbench_write_facade.py` are confined to:
  - `WorkbenchWriteRelationReadSnapshotPort`
  - `WorkbenchWriteRelationSpecialMetadataMutationPort`
- `Application._workbench_write_facade(...)` already injects both explicit ports.
- The only other `WorkbenchWriteFacade(...)` construction site is `tests/test_workbench_auth_context_idempotency.py::_new_facade(...)`.
- The constructor still accepts `pair_relation_service` only to build default ports when explicit ports are omitted.
- Keeping that broad constructor parameter leaves a path for future callers to instantiate the facade without declaring IO ports, which conflicts with the target boundary style even though the current production factory is already explicit.

## Decision

Next boundary:

`workbench-relations:workbench-write-facade-required-port-constructor`

Scope:

- Remove `pair_relation_service` from `WorkbenchWriteFacade.__init__`.
- Require explicit `relation_read_snapshot_port` and `relation_special_metadata_mutation_port`.
- Keep `WorkbenchWriteRelationReadSnapshotPort` and `WorkbenchWriteRelationSpecialMetadataMutationPort` as the only adapters that hold the pair relation service.
- Update `Application._workbench_write_facade(...)` and the test helper in `tests/test_workbench_auth_context_idempotency.py`.
- Strengthen the static guard so the facade constructor cannot re-accept `pair_relation_service`.

Not in scope:

- Do not change Workbench behavior, cash special behavior, relation writes, dirty scopes or read model refresh.
- Do not rewrite the ports into command service native commands in this slice.
- Do not declare `workbench_relation` closed.
- Do not implement Go/Fiber/Go Worker.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This audit closes only WorkbenchWriteFacade post-port local gap classification and selects the next narrow implementation boundary. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not changed in this audit slice | Next implementation should not change business rules. |
| Service-layer tests | Not changed in this audit slice | Next implementation should run Workbench facade/auth/idempotency and Workbench write characterization tests. |
| API contract tests | Not changed in this audit slice | No HTTP/API behavior changed. |
| Read model/cache/background job tests | Not changed in this audit slice | No scheduling behavior changed. |
| Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this analysis-only slice | No behavior changed. |
| Existing feature regression tests | Existing tests identified | Static boundary guard plus Workbench write/auth-context characterization are the target next-slice coverage. |

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only post-port WorkbenchWriteFacade local gap audit. It does not remove the constructor parameter, close `workbench_relation`, validate production PostgreSQL/worker evidence, or unblock Go/Fiber/Go Worker admission.
