# Workbench Relations - Settings Data Reset Pair Snapshot Port Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:settings-data-reset-pair-snapshot-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Remove broad Workbench pair service injection from `SettingsDataResetService` by extracting an explicit reset-scoped pair snapshot/save port.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-settings-data-reset-pair-service-boundary-audit.md`
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

## Change Summary

- Added `SettingsDataResetPairSnapshotPort`.
- `SettingsDataResetService` now accepts `workbench_pair_snapshot_port` instead of `workbench_pair_relation_service`.
- Pair relation snapshot reads and filtered snapshot saves now go through the explicit port.
- `Application._initialize_runtime_services(...)` wraps `_workbench_pair_relation_service.snapshot` and `state_store.save_workbench_pair_relations` in `SettingsDataResetPairSnapshotPort`.
- Added a static guard proving `SettingsDataResetService` no longer accepts broad pair service.

## Preserved Semantics

- Bank transaction reset still clears Workbench pair relations through the existing reset snapshot.
- Invoice reset still clears Workbench pair relations through the existing reset snapshot.
- OA reset still removes OA-derived pair relations and preserves pure bank-invoice pair relations.
- Deleted counts, protected targets, API response shape, read model cleanup, derived lifecycle fan-out and reset job behavior are unchanged.

## Legacy Classification

- Removed from `SettingsDataResetService`: broad `workbench_pair_relation_service` constructor/storage dependency.
- New explicit owner: `SettingsDataResetPairSnapshotPort`.
- Still open:
  - final local workbench relation closure/defer accounting;
  - production PostgreSQL/worker/App Status/high-row/browser evidence, because no local `PGSQL_URL` or staging DB exists.

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:settings-data-reset-pair-snapshot-port-extraction`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:local-implementation-closure-and-production-evidence-defer`

## Seven Test Category Decision

1. Business core unit tests: not applicable; reset business rules and relation filtering rules were not changed.
2. Service-layer tests: covered by targeted settings data reset tests for bank reset, invoice reset, OA reset removal and non-OA relation preservation.
3. API contract tests: not applicable; API response shape and job contract were not changed.
4. Read model/cache/background job tests: covered indirectly by reset service tests preserving read model cleanup; broader worker evidence remains deferred.
5. Frontend component and interaction tests: not applicable; no frontend code changed.
6. End-to-end business-flow integration tests: not applicable for this narrow dependency extraction; reset flow behavior was not changed.
7. Existing feature regression tests: covered by targeted reset relation regressions and static guard.

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/settings_data_reset_service.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_settings_data_reset_pair_snapshot_uses_explicit_port -v
PYTHONPATH=backend/src python3 -m unittest tests.test_settings_data_reset_service.SettingsDataResetServiceTests.test_reset_bank_transactions_keeps_invoices_and_protects_form_data_db tests.test_settings_data_reset_service.SettingsDataResetServiceTests.test_reset_invoices_clears_tax_certified_records tests.test_settings_data_reset_service.SettingsDataResetServiceTests.test_reset_oa_and_rebuild_preserves_pure_bank_invoice_pair_relation tests.test_settings_data_reset_service.SettingsDataResetServiceTests.test_reset_oa_and_rebuild_removes_pair_relation_containing_expense_row tests.test_settings_data_reset_service.SettingsDataResetServiceTests.test_reset_oa_and_rebuild_removes_pair_relation_containing_attachment_invoice_row -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this implementation slice is closed. `workbench_relation` remains `implementation-gap-open`.
