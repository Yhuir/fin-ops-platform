# server-py:oa-pending-payment-route-owner-local-closure-audit

Status: `analysis-closed`

Date: 2026-06-25

## Boundary

Audit remaining OA pending payment `Application` surfaces after route callback collapse.

This is an analysis boundary only. It does not claim OA pending payment module/global closure or production PostgreSQL/OA/worker/App Status/browser closure.

## Evidence Reviewed

- `analysis/server-py-oa-pending-payment-route-owner-audit-2026-06-25.md`
- `analysis/server-py-oa-pending-payment-route-callback-collapse-2026-06-25.md`
- `docs/modules/oa-pending-payments/README.md`
- `docs/modules/oa-pending-payments/state-machine.md`
- `docs/modules/oa-pending-payments/tests.md`
- CodeGraph context for remaining OA pending payment `Application` surfaces.
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_command_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_oa_pending_payment_api.py`

## Remaining Application Surfaces

The remaining OA pending payment references in `server.py` are accounted for as explicit composition-root or provider ports:

- `_oa_pending_payment_service(...)`: query-service composition with import service, relation facade, pending relation repository, completed/in-progress OA projections, payment status repository and lifecycle policy.
- `_oa_pending_payment_routes(...)`: route-owner composition and HTTP platform port injection.
- `_configure_oa_pending_payment_route_ports(...)`: composition-root support for configuring prebuilt route-owner instances with HTTP ports.
- `_oa_pending_payment_command_service(...)`: command-service composition with import service, projections, relation command service, pending relation repository, payment status repository, lifecycle policy and refresh producers.
- `_oa_pending_payment_relation_repository(...)`: provider for PostgreSQL or snapshot relation repository.
- `_oa_pending_payment_projection(...)` and `_oa_pending_payment_source_adapter(...)`: provider for payment-admitted OA projection and Mongo OA source adapter.
- `_oa_pending_payment_read_model_service(...)`: read-model fresh/source-version service composition.
- `_oa_pending_payment_error_response(...)`: HTTP error adapter.
- `_oa_pending_payment_expected_source_versions(...)`: source-version provider combining canonical OA pending payment versions and Workbench relation versions.
- `_enqueue_oa_pending_payment_read_model_refresh(...)`: refresh gateway port.
- `_resolve_oa_pending_payment_read_session(...)`: read auth/session adapter.
- Shared invalidation/fan-out helpers can include `oa_pending_payment` as a target scope type when upstream invoice-usage family facts change.

## Classification

- Route ownership: accounted. `/api/oa-pending-payments*` mapping now lives in `OaPendingPaymentApiRoutes.route(...)`.
- Read-model freshness: accounted for this local surface. `OaPendingPaymentReadModelService` owns rows/filter/detail freshness and source-version behavior.
- Command behavior: accounted for this local surface. `OaPendingPaymentCommandService` owns auto reconcile, writeback and link-bank semantics.
- Persistence details: accounted for this local surface. PostgreSQL read-model and pending relation storage remain outside `server.py`.
- Remaining production evidence: deferred. Real PostgreSQL/OA/worker/App Status/high-row/browser evidence still needs later controlled production validation and is not claimed here.

## Decision

OA pending payment local `server.py` route-owner support is accounted for after route callback collapse.

No additional OA pending payment `server.py` implementation slice is selected at this point.

## Next Boundary

`server-py:pending-invoice-route-owner-audit`

Reason: `server.py` still directly dispatches many `/api/pending-invoices*` callbacks even though `PendingInvoiceApiRoutes` exists. The next audit should split thin HTTP/session/body/export/error mapping from residual business/read-model implementation and select the next bounded implementation slice.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_pending_payment_routes_use_route_owner -v`
- `bash scripts/verify.sh docs`
- `git diff --check`
