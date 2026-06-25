# Next Prompt

Continue after `server-py:etc-legacy-batch-route-callback-collapse-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-legacy-batch-route-callback-collapse-audit`.
- Row321 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-route-callback-collapse-audit-2026-06-25.md`.
- Row321 collapsed legacy batch list/detail/delete/draft/confirm/reopen HTTP callbacks into `EtcLegacyBatchApiRoutes`.
- `server.py` now assembles the legacy batch read facade, delete service, lifecycle service, OA client builder, error/refresh/persist ports and narrow business-batch legacy delete fallback.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-invoice-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-route-callback-collapse-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` residual `/api/etc/invoices` and revoke-submitted handlers
   - existing ETC route owners under `backend/src/fin_ops_platform/app/routes_etc*.py`
   - ETC service methods used by `_handle_api_etc_invoices(...)` and `_handle_api_etc_revoke_submitted(...)`
   - `tests/test_platform_runtime_boundary_guards.py`
   - targeted ETC invoice/revoke tests in `tests/test_etc_backend.py`
3. Use CodeGraph to inspect callers/callees for `_handle_api_etc_invoices`, `_handle_api_etc_revoke_submitted`, `revoke_submitted`, and invoice listing payload ownership.
4. Decide whether the next safe implementation is:
   - extracting a narrow `EtcInvoiceApiRoutes` owner for GET invoice list and revoke-submitted HTTP mapping;
   - extracting revoke-submitted side effects before route ownership;
   - or closing a smaller analysis-only slice if the current ownership is too coupled.
5. Update analysis/state and add or update tests for any accepted implementation.

## Stop Gates

- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not pass `Application` into route owners or services.
- Do not change business-batch v2 behavior.
- Do not move SQL/table knowledge into route owners.
- Keep read model refresh through existing explicit freshness/enqueue boundaries.
