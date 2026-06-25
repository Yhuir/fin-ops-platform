# server-py:pending-invoice-route-owner-audit

Status: `analysis-closed`

Date: 2026-06-25

## Boundary

Audit remaining `/api/pending-invoices*` route ownership in `Application` and select the next bounded local implementation slice.

This is an analysis boundary only. It does not change runtime code and does not claim pending invoice module/global closure or production PostgreSQL/worker/App Status/browser closure.

## Evidence Reviewed

- `docs/modules/pending-invoices/README.md`
- `docs/modules/pending-invoices/state-machine.md`
- `docs/modules/pending-invoices/tests.md`
- CodeGraph context for pending invoice read model and route ownership.
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
- `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
- `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- `tests/test_pending_invoice_api.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Current Shape

`PendingInvoiceApiRoutes` already owns module-level methods for:

- rows;
- filter options;
- invoice candidates single/batch;
- relation detail;
- bank/invoice/OA detail;
- attach existing preview/confirm single and batch;
- rules get/update;
- income status single/batch update;
- export preview/download.

`PendingInvoiceReadModelService` owns rows/filter/export fresh gate and all-rows behavior. `PendingInvoiceApplicationService` owns attach existing and income status state changes. `PendingInvoiceRulesApplicationService` owns rules validation/persistence/fan-out.

`server.py` still owns direct dispatch plus many callbacks under `/api/pending-invoices*`.

## Callback Groups

- Read/detail group:
  - rows;
  - filter options;
  - invoice candidates;
  - relation detail;
  - bank transaction detail;
  - invoice detail;
  - OA detail.
- Candidate body-read group:
  - batch invoice candidates.
- Export group:
  - export preview;
  - export download and audit/XLSX response.
- Rules group:
  - rules GET;
  - rules PUT with body/session/error mapping.
- Attach existing group:
  - single preview;
  - single confirm with persist-state semantics;
  - batch preview;
  - batch confirm with persist-state semantics.
- Income status group:
  - single income status update with persist-state semantics;
  - batch income status update with persist-state semantics.

## Classification

- Rows/filter/export fresh-gate behavior is already service-owned by `PendingInvoiceReadModelService`.
- Detail/candidate business payload construction is service-owned by `PendingInvoiceQueryService`.
- Attach/rules/income writes are service-owned, but the app callbacks still own important HTTP/session/body/persist-state/audit adapter behavior.
- Export download still has explicit app-owned audit and XLSX response mapping that should be injected as route-owner ports, not mixed with business behavior.

## Decision

The next safe implementation slice is:

`server-py:pending-invoice-read-export-route-callback-collapse`

Scope:

- Add `route(method, route_path, query, body, headers)` to `PendingInvoiceApiRoutes`.
- Inject explicit ports for read-session resolution, JSON response, JSON body loading, error response, export audit and XLSX response.
- Move read/detail/candidates/export mapping into the route owner:
  - rows;
  - filter options;
  - invoice candidates;
  - batch invoice candidates;
  - relation detail;
  - bank transaction detail;
  - invoice detail;
  - OA detail;
  - export preview;
  - export download.
- Leave rules, attach existing confirm/preview and income status writes in `Application` for separate audits because they carry write-session/persist-state semantics.

## Verification Plan For Next Slice

- Update `tests/test_pending_invoice_api.py` for route-owner dispatch and export behavior.
- Add/update `tests/test_platform_runtime_boundary_guards.py` so read/detail/candidate/export callbacks cannot return to `server.py`.
- Run:
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api -v`
  - targeted platform runtime boundary Guard
  - `bash scripts/verify.sh docs`
  - `git diff --check`

## Next Boundary

`server-py:pending-invoice-read-export-route-callback-collapse`
