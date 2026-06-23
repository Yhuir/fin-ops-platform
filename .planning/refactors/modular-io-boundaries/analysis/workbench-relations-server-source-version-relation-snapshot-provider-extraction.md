# Workbench Relations Server Source Version Relation Snapshot Provider Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:server-source-version-relation-snapshot-provider-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move relation snapshot version reads used by Workbench/no-OA read model freshness source versions behind an explicit provider while preserving exact `pair_relation_snapshot_version` values and response payload shape.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-workbench-payload-relation-read-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-relation-read-helper-boundary-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_read_model_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph/text search for `_no_oa_bank_batch_source_versions`, `_workbench_read_model_source_versions`, `pair_relation_snapshot_version`, `snapshot_version`, and `_workbench_pair_relation_service.snapshot`.

## Changes

- Added `WorkbenchRelationSourceVersionProvider`.
- Added `Application._workbench_relation_source_version_provider(...)`.
- Moved direct relation snapshot version reads behind the provider in:
  - `_no_oa_bank_batch_source_versions(...)`
  - `_workbench_read_model_source_versions(...)`
- Preserved `WorkbenchReadModelService.snapshot_version(...)` as the hash implementation.
- Added unit coverage proving provider output matches `WorkbenchReadModelService.snapshot_version(snapshot)`.
- Added static guard coverage proving source-version helpers no longer direct-read `_workbench_pair_relation_service.snapshot`.

## Legacy Path Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| Source-version relation snapshot reads | explicit-provider extracted | No-OA and Workbench source-version helpers use `WorkbenchRelationSourceVersionProvider`. |
| Payload/live-row relation reads | already extracted | Covered by `WorkbenchPayloadRelationReadPort`. |
| Transaction-persist snapshot reads | retained canonical transaction persistence | `_persist_workbench_pair_relations_in_transaction(...)` remains unchanged. |
| Rollback/local persistence snapshots | retained later cleanup surfaces | Exception rollback, batch callback, whole-state persistence and case-id allocation remain unchanged. |
| Repair/precondition relation reads | next audit candidate | Remaining direct active relation reads are write-adjacent and need separate classification. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice closes only source-version relation snapshot provider extraction. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Decision |
| --- | --- | --- |
| Business core unit tests | Not applicable | No business matching/write rules changed. |
| Service-layer tests | Applies | Added provider unit test preserving snapshot hash behavior. |
| API contract tests | Not changed | App check verifies startup/route wiring; no HTTP response shape changed. |
| Read model/cache/background job tests | Applies | This slice touches read model source-version freshness inputs; provider unit/static guard coverage preserves exact hash contract. |
| Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| End-to-end business-flow integration tests | Not added for this narrow provider extraction | No cross-module runtime behavior changed. |
| Existing feature regression tests | Applies | Static guard prevents source-version helpers from reintroducing direct pair service snapshot reads. |

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_relation_source_version_provider.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_workbench_relation_source_version_provider.py
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_source_version_provider tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_source_versions_use_relation_source_version_provider -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only source-version relation snapshot provider extraction. It does not close `workbench_relation`, remove repair/precondition reads, remove rollback/local persistence snapshots, validate production PostgreSQL/worker evidence, or unblock Go/Fiber/Go Worker admission.

## Next Boundary

`workbench-relations:server-repair-precondition-relation-read-port-audit`
