# Workbench Relations - Server Case ID Allocation Relation Read Owner Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:server-case-id-allocation-relation-read-owner-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit `_next_workbench_relation_case_id(...)`, which still reads `self._workbench_pair_relation_service.snapshot()` directly to avoid allocating a `CASE-AUTO-*` id that is already active.

This is an analysis/accounting slice only. It does not change runtime behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-retained-oa-supplemental-relation-read-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-server-precondition-local-implementation-closure-audit.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `tests/test_workbench_write_characterization.py`
- `tests/test_workbench_v2_api.py`
- CodeGraph/text search for `_next_workbench_relation_case_id`, `next_case_id`, `CASE-AUTO-0001`, and case id collision behavior.

## Findings

`_next_workbench_relation_case_id(...)` is the only app-level auto relation case id allocator passed into `WorkbenchWriteFacade`.

The current behavior is intentional:

- `WorkbenchWriteFacade.confirm_link(...)` uses `case_id or self._next_case_id()`.
- The app allocator snapshots active pair relations and builds a used case id set.
- It repeatedly calls `WorkbenchOverrideService._next_case_id()` until it finds an unused id.
- This was introduced to avoid production confirm-link failures where generated `CASE-AUTO-0001` already existed in active relations.

The boundary problem is also real:

- `server.py` still knows relation snapshot shape (`pair_relations` keys).
- The allocator mixes application wiring, relation read ownership and override-service id generation.
- The snapshot read should move behind an explicit case-id allocation service/port, not another generic relation read port.

## Decision

Do not mark `workbench_relation` closed.

Do not run Go admission.

Queue the next narrow implementation boundary:

`workbench-relations:server-case-id-allocation-service-extraction`

Expected implementation shape:

- Add `WorkbenchRelationCaseIdAllocator`.
- Constructor dependencies:
  - `relation_snapshot_provider`
  - `next_case_id`
- Method:
  - `next_case_id() -> str`
- Move relation snapshot parsing and collision avoidance into that service.
- Keep `Application._next_workbench_relation_case_id(...)` as a thin delegate or replace the facade injection with the allocator method.
- Add static guard coverage proving app no longer parses `pair_relations` inside `_next_workbench_relation_case_id(...)`.
- Run existing case-id collision characterization tests.

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:server-case-id-allocation-relation-read-owner-audit`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:server-case-id-allocation-service-extraction`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no behavior changed in this audit.
2. Service-layer tests: not applicable; no code changed.
3. API contract tests: not applicable; no HTTP contract changed.
4. Read model/cache/background job tests: not applicable; no read model behavior changed.
5. Frontend component and interaction tests: not applicable; no frontend code changed.
6. End-to-end business-flow integration tests: not applicable for this analysis-only slice.
7. Existing feature regression tests: not run because this slice only records ownership analysis.

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this audit slice is closed. `workbench_relation` remains `implementation-gap-open`.
