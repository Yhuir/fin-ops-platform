# server-py:tax-route-owner-audit

Status: `analysis-closed`

Date: 2026-06-25

## Boundary

Audit tax-offset route ownership in `server.py` and `TaxApiRoutes`.

## Evidence Reviewed

- `docs/modules/tax-offset/README.md`
- `docs/modules/tax-offset/tests.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_tax.py`
- `tests/test_tax_offset_api.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_read_model_architecture_guards.py`

## Current Shape

`TaxApiRoutes` already owns service-level HTTP response mapping for:

- month payload: `handle_month(...)`
- summary payload: `handle_summary(...)`
- calculate: `handle_calculate(...)`
- plan save: `handle_save_plan(...)`
- certified import job payload: `handle_import_job(...)`

`server.py` still owns direct dispatch and wrappers for:

- `GET /api/tax-offset`
- `GET /api/tax-offset/summary`
- `GET /api/tax-offset/certified-import/jobs/{import_job_id}`
- `GET /api/tax-offset/certified-imports`
- `POST /api/tax-offset/calculate`
- `POST /api/tax-offset/plans`
- `POST /api/tax-offset/certified-import/preview`
- `POST /api/tax-offset/certified-import/confirm`

## Classification

Safe first collapse group:

- month/summary reads use read session then delegate to `TaxApiRoutes`.
- calculate is read-like POST: read session, JSON body, route-owned calculation/error response.
- plan save is mutation: mutation session, JSON body, actor id, route-owned plan service/conflict response.
- certified import job read is read session then route-owned job response.
- certified imports list is read session, month validation and application-service records payload.

Deferred group:

- certified import preview owns multipart parsing, file upload normalization and preview application-service call.
- certified import confirm owns queue-vs-inline branching, import job enqueue metadata/idempotency, and direct execution fallback.

## Decision

Select `server-py:tax-offset-read-plan-route-callback-collapse` next:

- add `TaxApiRoutes.route(...)`;
- inject explicit read-session, mutation-session, JSON body loader and actor-id ports;
- move month/summary/calculate/plan-save/import-job/certified-imports list HTTP mapping into route owner;
- remove migrated app callbacks;
- leave certified import preview/confirm for a later audit.

## Stop Gates

- Do not change tax calculation, read-model freshness, plan conflict/idempotency, import job shape or certified import preview/confirm semantics.
- Do not run production validation or mutation.
- Do not claim tax module/global closure.
