# server-py:workbench-pair-relation-display-policy-extraction

Date: 2026-06-25
Status: local-implementation-closed

## Completed

- Added `WorkbenchPairRelationDisplayPolicy`.
- Moved relation display payload mapping out of `Application._pair_relation_display_payload(...)`.
- Preserved `Application._pair_relation_display_payload(...)` as a compatibility delegate.
- Injected explicit ports for:
  - no-OA display policy;
  - bank transaction tag label lookup;
  - no-OA relation mode;
  - personal advance repayment mode;
  - OA invoice offset relation mode.

## Local Proof

- Added `tests/test_workbench_pair_relation_display_policy.py`.
- Added static Guard `test_workbench_pair_relation_display_policy_extraction_stays_local`.

## Remaining Work

mode-specific metadata mutation remains deferred. The next local boundary is `server-py:workbench-pair-relation-row-mutation-audit`, focused on `_apply_pair_relation_to_row(...)`, relation metadata propagation, amount check propagation, available actions and mode-specific decorators. Production browser/admin/write evidence remains deferred.
