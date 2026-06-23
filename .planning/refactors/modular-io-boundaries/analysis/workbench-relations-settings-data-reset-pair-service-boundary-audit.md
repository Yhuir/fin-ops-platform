# Workbench Relations - Settings Data Reset Pair Service Boundary Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:settings-data-reset-pair-service-boundary-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit `SettingsDataResetService(workbench_pair_relation_service=...)` and decide whether it is a legitimate reset boundary, a legacy broad service leak, or a candidate for an explicit port extraction.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-turnover-local-pair-snapshot-port-extraction.md`
- `docs/modules/settings/README.md`
- `docs/modules/settings/state-machine.md`
- `docs/modules/settings/tests.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/services/settings_data_reset_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_settings_data_reset_service.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Findings

`SettingsDataResetService` uses broad `workbench_pair_relation_service` for one reset-scoped responsibility:

- read the current pair relation snapshot for deletion counts;
- clear all pair relations for bank transaction and invoice resets through `state_store.save(...)`;
- preserve only non-OA relations during `reset_oa_and_rebuild`;
- save the filtered pair relation snapshot with `state_store.save_workbench_pair_relations(...)`.

This is not a normal relation command path and should not use `WorkbenchRelationCommandService`, because data reset intentionally clears or rewrites reset-scoped state. It is also not a read model refresh path. However, the current constructor still accepts broad pair service and lets the reset service know the full pair service surface.

## Decision

Do not mark the current state as locally closed.

Insert a narrow implementation slice before Go admission:

`workbench-relations:settings-data-reset-pair-snapshot-port-extraction`

Expected implementation:

- add an explicit settings data reset pair snapshot port;
- move snapshot/save details behind the port;
- keep reset filtering logic in `SettingsDataResetService` unless the implementation proves a smaller owner split is safer;
- prevent `SettingsDataResetService` from accepting broad `workbench_pair_relation_service`;
- preserve reset semantics, protected targets, deleted counts, read model cleanup and derived lifecycle fan-out.

## Existing Test Evidence

`tests/test_settings_data_reset_service.py` already covers the important reset relation semantics:

- bank reset clears `workbench_pair_relations`;
- invoice reset clears `workbench_pair_relations`;
- OA reset removes OA-derived pair relations;
- OA reset removes OA attachment invoice row relations;
- OA reset preserves pure bank-invoice pair relations.

The implementation slice should add a static guard proving settings reset no longer accepts broad pair service, then rerun the targeted settings reset tests above.

## Legacy Classification

- Current `SettingsDataResetService(workbench_pair_relation_service=...)`: legacy broad injection, not locally closed.
- Current pair relation reset behavior: legitimate settings reset boundary.
- Required next owner: explicit settings reset pair snapshot port.
- Go/Fiber/Go Worker: still blocked; this audit does not create performance evidence or Go admission readiness.

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:settings-data-reset-pair-service-boundary-audit`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:settings-data-reset-pair-snapshot-port-extraction`

## Seven Test Category Decision

1. Business core unit tests: not applicable for this audit-only slice; reset business behavior was not changed.
2. Service-layer tests: existing service tests identified for the next implementation slice.
3. API contract tests: not applicable for this audit-only slice; API shape was not changed.
4. Read model/cache/background job tests: not applicable for this audit-only slice; cleanup/fan-out behavior was not changed.
5. Frontend component and interaction tests: not applicable; no frontend code changed.
6. End-to-end business-flow integration tests: not applicable for this audit-only slice.
7. Existing feature regression tests: existing reset relation regression tests identified for the next implementation slice.

## Verification

```bash
git diff --check
bash scripts/verify.sh docs
```

## Completion Claim

Only this analysis slice is closed. `workbench_relation` remains `implementation-gap-open`, and settings data reset requires the explicit pair snapshot port implementation slice before local closure/defer accounting.
