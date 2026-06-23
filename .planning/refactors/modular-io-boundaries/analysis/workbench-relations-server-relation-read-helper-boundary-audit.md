# Workbench Relations Server Relation Read Helper Boundary Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:server-relation-read-helper-boundary-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit remaining direct `Application._workbench_pair_relation_service` read/snapshot call sites in `server.py`, classify legacy surfaces, and select the next smallest safe extraction boundary without changing runtime behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-matching-relation-read-port-extraction.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for remaining relation read helpers.
- Text search for `_workbench_pair_relation_service`, `list_active_relations`, `active_relations_for_row_ids`, `get_active_relation_by_row_id`, `snapshot`, and `snapshot_case_ids`.

## Direct Call Site Inventory

| Function | Direct calls | Classification | Next action |
| --- | --- | --- | --- |
| `_next_workbench_relation_case_id(...)` | `snapshot()` | case-id allocation snapshot read | Later explicit case-id allocator/snapshot port; not part of page payload read extraction. |
| `_apply_workbench_exception_application(...)` | `snapshot()` | exception write rollback snapshot | Later exception rollback snapshot owner cleanup; current rollback restore service already owns restore. |
| `_batch_accounting_routes(...)` | `snapshot` callback injection | explicit route rollback callback | Compat callback already delegated to rollback restore service; not the next highest-risk read path. |
| `_no_oa_bank_batch_source_versions(...)` | `snapshot()` | read model source-version fact read | Later source-version provider extraction; do not mix with page payload reads. |
| `_workbench_read_model_source_versions(...)` | `snapshot()` | read model source-version fact read | Later source-version provider extraction; do not mix with page payload reads. |
| `_persist_state(...)` | `snapshot()` | legacy whole-state persistence | Compat/local persistence surface; not a user-facing read model boundary. |
| `_persist_workbench_pair_relations_in_transaction(...)` | `snapshot_case_ids(...)`, `snapshot()` | transactional persistence snapshot | Already repository-backed transaction persist path; leave separate from read helper cleanup. |
| `_supplemental_retained_oa_row_ids(...)` | `list_active_relations()` | OA retention support read | Later OA retention/read port candidate. |
| `_apply_pair_relations_to_payload(...)` | `get_active_relation_by_row_id(...)` | Workbench page payload relation enrichment | Next implementation candidate. |
| `_supplement_missing_active_pair_relation_rows(...)` | `list_active_relations()` | Workbench page payload missing-row supplementation | Next implementation candidate. |
| `_sync_oa_invoice_offset_auto_pair_relations(...)` | `list_active_relations()` | repair/write precondition read | Later repair/precondition port; do not mix with payload enrichment. |
| `_repair_active_relations_with_oa_attachment_context(...)` | `list_active_relations()` | repair/write precondition read | Later repair/precondition port; do not mix with payload enrichment. |
| `_expand_confirm_link_row_ids_for_existing_context(...)` | `active_relations_for_row_ids(...)` | confirm-link precondition/context read | Later confirm precondition port; do not mix with payload enrichment. |
| `_relation_for_group(...)` | `get_active_relation_by_row_id(...)` | Workbench group payload relation enrichment | Next implementation candidate. |
| `_resolve_live_rows_direct(...)` | `get_active_relation_by_row_id(...)` | Workbench live-row payload relation enrichment | Next implementation candidate. |
| `_auto_pair_conflicts_with_manual_relation(...)` | `get_active_relation_by_row_id(...)` | auto-pair precondition read | Later auto-pair precondition port; do not mix with payload enrichment. |

## Findings

- The remaining direct reads are not one homogeneous legacy path.
- Snapshot calls serve source-version, rollback, transaction-persist, and local persistence semantics. Moving them together with page payload reads would widen the slice and risk conflating fact ownership with UI enrichment.
- Repair/precondition reads already mix relation reads with command-service writes. They should be extracted after payload enrichment so write-adjacent behavior has a narrower audit trail.
- The highest user-visible inconsistency risk is Workbench page payload/live-row enrichment:
  - `_apply_pair_relations_to_payload(...)`
  - `_supplement_missing_active_pair_relation_rows(...)`
  - `_relation_for_group(...)`
  - `_resolve_live_rows_direct(...)`
- Those functions read active relation facts only to enrich rows/groups that are displayed or reused as live row detail. They can move behind an explicit `WorkbenchServerRelationReadPort` without changing writes, dirty scopes, read model refresh, matching, API shape or frontend behavior.

## Decision

Next boundary:

`workbench-relations:server-workbench-payload-relation-read-port-extraction`

Scope:

- Add an explicit server-side Workbench payload relation read port for active relation reads used by payload/live-row enrichment.
- Move these calls behind the port:
  - `_apply_pair_relations_to_payload(...)`
  - `_supplement_missing_active_pair_relation_rows(...)`
  - `_relation_for_group(...)`
  - `_resolve_live_rows_direct(...)`
- Keep repair/precondition, source-version, transaction-persist, rollback and local persistence snapshot reads unchanged for later slices.
- Add static guard coverage focused on the extracted payload enrichment methods so they cannot call `_workbench_pair_relation_service` directly.

Not in scope:

- Do not change relation writes, command service behavior, matching rules, source-version calculation, operation barrier behavior, dirty scopes, read model refresh, API response shape or frontend behavior.
- Do not convert canonical relation reads to downstream relation read model payloads unless a later slice proves it is semantically correct.
- Do not declare `workbench_relation` module closed.
- Do not implement Go/Fiber/Go Worker.

## Legacy Path Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| Workbench payload/live-row active relation reads | explicit-port candidate | User-facing payload enrichment; next implementation slice. |
| Source-version snapshot reads | explicit source-version provider candidate | Freshness/version fact reads; later slice. |
| Transaction persist snapshot reads | retained canonical transaction persistence | Already writes through `PostgresWorkbenchRelationRepository`; not a read-helper cleanup. |
| Exception/batch rollback snapshots | compat/rollback snapshot candidate | Restore services exist; snapshot capture still needs later cleanup. |
| Repair/precondition relation reads | explicit repair/precondition port candidate | Write-adjacent and should stay separate. |
| Whole-state persistence snapshot | compat-only local persistence | Legacy snapshot-style persistence surface; later closure accounting. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice closes only the server relation read helper audit. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Decision |
| --- | --- | --- |
| Business core unit tests | Not changed in this audit slice | Next implementation should preserve row/group enrichment behavior. |
| Service-layer tests | Not changed in this audit slice | Next implementation should use Workbench API/route characterization or focused server helper tests where available. |
| API contract tests | Not changed in this audit slice | Next implementation touches Workbench payload shape and should preserve API shape with existing tests. |
| Read model/cache/background job tests | Not changed in this audit slice | No read model, cache, dirty scope or worker behavior changed. |
| Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this analysis-only slice | No runtime behavior changed. |
| Existing feature regression tests | Existing tests identified | `tests/test_workbench_v2_api.py` covers several relevant payload/repair surfaces; static guards should be extended in the next implementation slice. |

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the audit/classification of remaining `server.py` relation read helpers. It does not remove direct reads, close `workbench_relation`, validate production PostgreSQL/worker evidence, or unblock Go/Fiber/Go Worker admission.

## Next Boundary

`workbench-relations:server-workbench-payload-relation-read-port-extraction`
