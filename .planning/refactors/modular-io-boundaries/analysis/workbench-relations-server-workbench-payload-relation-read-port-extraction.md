# Workbench Relations Server Workbench Payload Relation Read Port Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:server-workbench-payload-relation-read-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move Workbench page payload/live-row active relation reads in `server.py` behind an explicit relation read port without changing relation writes, repair/precondition reads, source-version snapshot reads, transaction-persist behavior, rollback behavior, API response shape or frontend behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-relation-read-helper-boundary-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph/text search for payload/live-row relation read helpers.

## Changes

- Added `WorkbenchPayloadRelationReadPort`.
- Added `WorkbenchRelationCommandService.get_active_relation_by_row_id(...)` as a read-only command-boundary method.
- Added `Application._workbench_payload_relation_read_port(...)` to construct the payload read port from `WorkbenchRelationCommandService(require_fresh_relations=False)`.
- Moved active relation reads behind the payload read port in:
  - `_apply_pair_relations_to_payload(...)`
  - `_supplement_missing_active_pair_relation_rows(...)`
  - `_relation_for_group(...)`
  - `_resolve_live_rows_direct(...)`
- Added static guard coverage proving the four extracted helpers no longer read `_workbench_pair_relation_service` directly.

## Legacy Path Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| Workbench payload/live-row active relation reads | explicit-port extracted | Four payload/live-row helpers use `WorkbenchPayloadRelationReadPort`. |
| Repair/precondition relation reads | implementation gap retained | `_sync_oa_invoice_offset_auto_pair_relations(...)`, `_repair_active_relations_with_oa_attachment_context(...)`, `_expand_confirm_link_row_ids_for_existing_context(...)`, and `_auto_pair_conflicts_with_manual_relation(...)` remain separate. |
| Source-version snapshot reads | next implementation candidate | `_no_oa_bank_batch_source_versions(...)` and `_workbench_read_model_source_versions(...)` still read relation snapshot directly for freshness versioning. |
| Transaction-persist snapshot reads | retained canonical transaction persistence | `_persist_workbench_pair_relations_in_transaction(...)` remains unchanged. |
| Rollback/local persistence snapshots | retained later cleanup surfaces | Exception rollback, batch callback, whole-state persistence and case-id allocation remain unchanged. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice closes only Workbench payload/live-row relation read port extraction. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Decision |
| --- | --- | --- |
| Business core unit tests | Applies indirectly | Existing Workbench payload tests cover missing active relation rows and active relation context preservation. |
| Service-layer tests | Applies | Static guard and command-service-backed port verify service boundary movement. |
| API contract tests | Applies | Targeted Workbench API tests verify payload behavior remains stable. |
| Read model/cache/background job tests | Not changed | No read model, cache, dirty scope, outbox, App Status or worker behavior changed. |
| Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| End-to-end business-flow integration tests | Not added for this narrow boundary | Existing Workbench API tests cover the affected server-side business paths. |
| Existing feature regression tests | Applies | Existing Workbench V2 API regression tests and static guard prevent behavior drift and broad pair service reintroduction in extracted helpers. |

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_payload_relation_read_port.py backend/src/fin_ops_platform/services/workbench_relation_command_service.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_workbench_payload_relation_reads_use_payload_read_port -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_pair_relation_application_supplements_missing_active_oa_rows tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_includes_active_relation_rows_for_selected_oa_context -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_falls_back_to_underlying_live_row_services_when_group_payload_is_missing_selected_rows -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the Workbench payload/live-row relation read port extraction. It does not close `workbench_relation`, remove source-version snapshot reads, remove repair/precondition reads, validate production PostgreSQL/worker evidence, or unblock Go/Fiber/Go Worker admission.

## Next Boundary

`workbench-relations:server-source-version-relation-snapshot-provider-extraction`
