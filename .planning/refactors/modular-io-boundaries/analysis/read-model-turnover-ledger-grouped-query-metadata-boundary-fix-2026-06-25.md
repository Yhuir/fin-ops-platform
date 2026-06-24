# Read Model Turnover Ledger Grouped Query Metadata Boundary Fix - 2026-06-25

**Boundary:** `read-models:turnover-ledger-grouped-query-metadata-boundary-fix`
**Status:** `implementation-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Previous boundary:** `production:turnover-ledger-user-scope-hidden-refresh-enqueue-diagnosis`

## Goal

Fix the local turnover ledger grouped GET boundary so `view=grouped` preserves read-model freshness/enqueue metadata when converting SQL/read-model flat payloads to grouped payloads.

## Production Diagnosis Input

Row286 proved live production `GET /api/turnover-ledger?view=grouped&page=1&page_size=50` returned HTTP 200 grouped data with no top-level `read_model_status`, `refresh_enqueued`, `refresh_reason` or stale-reason metadata, while the same GET created `turnover_ledger.read_model.refresh` for `turnover_ledger:all`.

## Root Cause

`TurnoverLedgerQueryService` / `ReadModelQueryGateway` can attach read-model metadata to SQL/read-model payloads. But `TurnoverLedgerApiRoutes._flat_payload_to_grouped(...)` rebuilt the response as a new dict containing only:

- `summary`;
- `family_summaries`;
- `groups`;
- `pagination`;
- `filters`.

That discarded top-level `read_model_status`, `read_model_scope_key`, `read_model_stale_reasons`, `refresh_enqueued`, `refresh_reason`, `source_versions`, schema/cache metadata and any future gateway metadata fields.

## Implementation

Changed `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` so `_flat_payload_to_grouped(...)` starts from the original payload without legacy `rows`, then overwrites grouped response fields. This preserves the grouped business response shape while keeping gateway metadata observable.

## Tests Added

`tests/test_turnover_ledger_api.py`:

- `test_get_turnover_ledger_grouped_preserves_fresh_sql_read_model_metadata`
  - Proves fresh SQL/read-model grouped GET returns `read_model_status=fresh`, `refresh_enqueued=false`, normalized `source_versions`, grouped rows, and no queue enqueue.
- `test_get_turnover_ledger_grouped_preserves_stale_sql_refresh_metadata`
  - Proves stale SQL/read-model grouped GET preserves `read_model_status=refreshing`, `refresh_enqueued=true`, `refresh_reason=source_version_mismatch`, grouped rows and `turnover_ledger:all` enqueue evidence.

## Verification

- `PYTHONPATH=backend/src pytest -q tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_get_turnover_ledger_grouped_preserves_fresh_sql_read_model_metadata tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_get_turnover_ledger_grouped_preserves_stale_sql_refresh_metadata tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_get_turnover_ledger_grouped_view_returns_groups tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_get_turnover_ledger_enqueues_refresh_for_stale_sql_read_model_source_versions tests/test_turnover_ledger_query_service.py`
  - Result: `10 passed`.
- `PYTHONPATH=backend/src pytest -q tests/test_turnover_ledger_api.py tests/test_turnover_ledger_query_service.py tests/test_turnover_ledger_read_facade.py`
  - Result: `148 passed`, `31 subtests passed`.
- `python3 -m compileall -q backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`
  - Result: passed.

## Docs Impact

Updated:

- `docs/modules/turnover-ledger/tests.md`
- `docs/modules/turnover-ledger/implementation-notes.md`

No long-term product semantics changed. API freshness metadata observability changed for grouped SQL/read-model responses.

## Seven Test Categories

- Business core unit tests: not applicable; no amount/tag/closure/withdraw/extra business rules changed.
- Service-layer tests: covered through `tests/test_turnover_ledger_query_service.py` and read facade/API wiring.
- API contract tests: covered by new grouped fresh/stale metadata tests and existing grouped shape regression.
- Read model/cache/background job tests: covered by stale grouped source-version mismatch enqueue assertion.
- Frontend component and interaction tests: not changed in this slice; existing frontend stale/grouped tests remain consumer-side coverage.
- End-to-end business-flow integration tests: not applicable; no write flow changed.
- Existing feature regression tests: covered by full `tests/test_turnover_ledger_api.py` plus read facade/query service tests.

## Remaining Risk

This is a local implementation fix only. Production deploy and focused turnover grouped re-smoke are required in a separate controlled boundary before Row285 full user-scope API smoke can be retried as no-hidden-enqueue evidence.
