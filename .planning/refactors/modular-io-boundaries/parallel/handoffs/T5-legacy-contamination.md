# T5 Legacy Contamination Handoff

**Date:** 2026-06-24
**Workstream:** T5 legacy contamination
**Status:** quarantine-guarded

## Scope

Find old route/service/repository/read model/frontend API paths that can still pollute new module IO boundaries, and remove only when caller evidence is strong. Stop when finance behavior is ambiguous.

## Evidence Reviewed

- `README.md`
- `ARCHITECTURE.md`
- `docs/index.md`
- `docs/app-architecture/README.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/reconciliation-workbench/implementation-notes.md`
- `docs/modules/workbench-relations/README.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-row-detail-route-owner-extraction.md`
- CodeGraph status: 981 indexed files, 35,263 nodes, 89,544 edges.
- CodeGraph caller evidence for `repair_legacy_case_id_collisions`.

## Quarantined Surfaces

### WorkbenchRowDetailApiRoutes.legacy_row_detail

- Location: `backend/src/fin_ops_platform/app/routes_workbench.py`
- Owner wiring: `Application._build_workbench_row_detail_api_routes(...)`
- Old surface: `legacy_row_detail=self._workbench_api_routes.get_row_detail`
- Classification: retained local compatibility fallback, not removable in this slice.
- Reason: the row-detail route-owner extraction intentionally preserved this fallback until a later caller audit. Production SQL runtime already blocks the fallback unless the route query service has an in-memory record. Removing it here would change row-detail compatibility behavior without enough evidence.
- Guard added: `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_legacy_contamination_surfaces_stay_quarantined`
- Guard contract: exactly one route-owner wiring; no relation command service, read model refresh gateway, dirty scope, outbox, readiness, cache or App Status side effects in the row-detail route owner.

### BatchAccountingService.repair_legacy_case_id_collisions

- Location: `backend/src/fin_ops_platform/services/batch_accounting_service.py`
- Classification: test-observed compat repair behavior, not removed.
- CodeGraph caller evidence: callers were only `tests/test_batch_accounting_api.py` repair regression methods.
- Stop condition: despite no active app/service caller found, this is finance relation repair behavior with explicit regression coverage; do not delete until an owner/deletion condition confirms the repair path is obsolete.
- Guard added: static scan proves no app/service active caller invokes `repair_legacy_case_id_collisions(...)` outside the service definition.

## No Removal Decision

No legacy runtime code was removed in this T5 slice. The only code change is a guard test. This follows the instruction to stop when caller evidence is weak and not remove ambiguous finance behavior.

## Tests

Added:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_contamination_surfaces_stay_quarantined -v
```

Covered categories:

- API contract regression guard: protects Workbench row-detail route owner from adding unclassified legacy links or side effects.
- Service-layer regression guard: proves batch accounting legacy repair has no active app/service caller.
- Existing feature regression guard: freezes the current quarantine boundary so future changes cannot silently expand old surfaces.

Not covered:

- Business behavior tests: no behavior changed.
- Read model/cache/background job tests: no queue, worker, cache or freshness behavior changed.
- Frontend tests: no frontend API or UI behavior changed.
- End-to-end business-flow tests: no cross-module runtime behavior changed.

## Docs Impact

Updated `docs/modules/reconciliation-workbench/implementation-notes.md`. No product/API/app-architecture long-term fact changed.

## Stop Condition

Continue with a future narrow slice only after one of these is true:

- `WorkbenchRowDetailApiRoutes.legacy_row_detail` has stronger caller evidence showing the fallback is unreachable in all supported local/legacy modes.
- Batch accounting repair has an explicit owner/deletion condition proving the finance repair path is obsolete.
- A specific old route/service/repository/read model/frontend API path is proven to have no active caller and no finance behavior ambiguity.
