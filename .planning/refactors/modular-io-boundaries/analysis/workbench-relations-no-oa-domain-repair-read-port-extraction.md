# Workbench Relations No-OA Domain Repair Read Port Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:no-oa-domain-repair-read-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move `NoOaBankBatchService` active relation reads for domain repair and relation-backed stale/submitted projection behind an explicit no-OA relation read/repair port, without changing no-OA batch lifecycle, relation write behavior, API payloads, dirty scope semantics or read model refresh behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-no-oa-domain-repair-read-port-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-no-oa-application-pair-snapshot-port-extraction.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `docs/modules/no-oa-bank-batches/README.md`
- `docs/modules/no-oa-bank-batches/state-machine.md`
- `docs/modules/no-oa-bank-batches/tests.md`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- `tests/test_no_oa_bank_batch_service.py`
- `tests/test_no_oa_bank_batch_application_service.py`
- `tests/test_no_oa_bank_batch_api.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph/text search for `NoOaBankBatchService`, `_pair_relation_service`, `_repair_submitted_no_oa_relation_consistency`, `_has_active_no_oa_relation`, `_build_batches_for_month_scope`, `active_relations_for_row_ids`, `get_active_relation_by_case_id`, `_confirm_no_oa_relation`, and `_cancel_no_oa_relation`.

## Implementation

Added `NoOaRelationRepairReadPort` to own no-OA domain relation reads:

- `active_relation_by_case_id(...)`
- `active_relations_for_row_ids(...)`

`NoOaBankBatchService` now stores `_relation_read_port` instead of `_pair_relation_service`.

The service now delegates these domain reads to the port:

- `_repair_submitted_no_oa_relation_consistency(...)` relation-by-case check.
- `_repair_submitted_no_oa_relation_consistency(...)` blocking relation lookup by row ids.
- `_repair_submitted_no_oa_relation_consistency(...)` stale no-OA relation lookup by row ids.
- `_has_active_no_oa_relation(...)` relation-backed stale/submitted projection and withdraw eligibility.

`_build_batches_for_month_scope(...)` forwards `relation_read_port=self._relation_read_port` into scoped child services so month-scoped refresh preserves the same read boundary.

`pair_relation_service` remains as a transitional constructor/factory input only; it is immediately adapted into `NoOaRelationRepairReadPort` and is not stored or called by `NoOaBankBatchService`.

## Legacy Classification

| Surface | Result | Notes |
| --- | --- | --- |
| `NoOaBankBatchService._pair_relation_service` | removed | Service no longer stores direct broad pair service dependency. |
| `_repair_submitted_no_oa_relation_consistency(...)` direct pair reads | removed | Reads go through `_relation_read_port`. |
| `_has_active_no_oa_relation(...)` direct pair read | removed | Stale/submitted projection reads go through `_relation_read_port`. |
| `_build_batches_for_month_scope(...)` pair dependency forwarding | removed | Scoped child service receives the explicit read port. |
| `NoOaRelationRepairReadPort` | explicit legacy read adapter | Only this port adapts `WorkbenchPairRelationService` active relation reads. |
| `_confirm_no_oa_relation(...)` / `_cancel_no_oa_relation(...)` | unchanged canonical write path | Writes remain command-service backed. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/no-oa-bank-batches/state-machine.md`

No global or module state definition changes are required. This slice changes dependency ownership only. It does not alter no-OA lifecycle states, relation status semantics, operation barriers, read model freshness states or worker behavior.

`workbench_relation` remains `implementation-gap-open`. The next boundary is `workbench-relations:post-no-oa-local-implementation-closure-audit`.

## Seven Test Categories

| Category | Applies? | Coverage |
| --- | --- | --- |
| Business core unit tests | Yes. | `tests.test_no_oa_bank_batch_service` covers no-OA status/projection, submitted repair, stale relation repair, internal transfer and withdraw behavior. |
| Service-layer tests | Yes. | `tests.test_no_oa_bank_batch_service` and targeted application service rollback/projection tests cover service orchestration and persistence safety. |
| API contract tests | Targeted. | No API shape changed; rollback API test verifies submit persistence failure still rolls back relation state. |
| Read model/cache/background job tests | Not directly changed. | No refresh/dirty scope/cache logic changed; existing application durable queue boundary test remains in the no-OA suite. |
| Frontend component and interaction tests | Not applicable. | No frontend code or API payload shape changed. |
| End-to-end business-flow integration tests | Covered by service/API regression rather than browser E2E. | The critical relation-backed stale projection and submit rollback paths are tested at service/API level. |
| Existing feature regression tests | Yes. | Static guards prove no-OA domain relation reads use the repair read port and direct pair write fallback remains forbidden. |

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service.NoOaBankBatchApplicationServiceTests.test_sql_read_model_relation_backed_stale_batch_is_presented_as_submitted tests.test_no_oa_bank_batch_api.NoOaBankBatchApiTests.test_submit_returns_error_and_rolls_back_when_no_oa_batch_persistence_fails -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_domain_relation_reads_use_repair_read_port tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_downstream_relation_read_models_use_workbench_relation_distribution tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only no-OA domain repair/read port extraction. It does not close `workbench_relation`, classify ETC or WorkbenchWriteFacade relation dependencies, validate production PostgreSQL/worker evidence, or unblock Go admission.
