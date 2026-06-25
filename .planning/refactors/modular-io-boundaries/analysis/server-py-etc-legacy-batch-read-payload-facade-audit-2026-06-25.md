# server-py:etc-legacy-batch-read-payload-facade-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:etc-legacy-batch-draft-confirm-callback-audit`
**Next boundary:** `server-py:etc-legacy-batch-read-facade-extraction`

## Goal

Audit remaining legacy `/api/etc/batches` list/detail read payload ownership in `Application` and select the next safe local implementation boundary.

No production browser, admin or controlled-write validation was run.

## Evidence Read

- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-draft-confirm-callback-audit-2026-06-25.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py`
- `tests/test_etc_backend.py`
- `tests/test_platform_runtime_boundary_guards.py`

CodeGraph was used to inspect `EtcLegacyBatchApiRoutes`, `_handle_api_etc_batches`, `_handle_api_etc_batch_detail`, `_etc_batch_list_items`, `_etc_batch_detail_payload`, `_etc_batch_counts` and related helpers.

## Findings

`EtcLegacyBatchApiRoutes` owns URL parsing, but legacy read payload ownership remains in `Application` through:

- `_handle_api_etc_batches(...)`
- `_handle_api_etc_batch_detail(...)`
- `_etc_batch_counts()`
- `_etc_batch_list_items(...)`
- `_etc_batch_detail_payload(...)`
- `_etc_business_batch_*_payload(...)`
- `_etc_submission_batch_*_payload(...)`
- `_etc_import_batch_*_payload(...)`
- `_etc_batch_summary_matches_filters(...)`
- `_etc_batch_payload_matches_filters(...)`
- `_etc_batch_detail_filtered_for_query(...)`

This is not a simple route-owner callback cleanup. The read path encodes several business/read-model contracts:

- unified legacy view across business batches, submission batches and import batches;
- hiding task-scoped active business batches from legacy list buckets;
- excluding reconciliation import batches from normal legacy unsubmitted list;
- excluding import/submission batches already represented by business batches;
- preserving submitted/unsubmitted counts;
- preserving month, plate and keyword filtering against invoice dates and invoice fields;
- preserving supplement/reconciliation metadata in submitted detail/list payloads;
- preserving detail invoice serialization and attachment existence checks.

## Decision

Do not move the read logic directly into `EtcLegacyBatchApiRoutes`. The next safe implementation boundary is an explicit read facade/service:

`server-py:etc-legacy-batch-read-facade-extraction`

The facade should:

- receive explicit dependencies only;
- not receive `Application`;
- not import app/auth/server modules;
- expose list/detail payload methods;
- own counts/list/detail/filtering read composition;
- receive serialization ports for values and ETC invoices where needed;
- preserve public response shape and targeted list/detail/query tests.

`Application` should keep HTTP pagination parsing, HTTP status mapping and response construction until route ownership can be migrated safely.

## Next Boundary Scope

Allowed files for the next implementation slice:

- `backend/src/fin_ops_platform/services/etc_legacy_batch_read_facade.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_etc_legacy_batch_read_facade.py`
- `tests/test_platform_runtime_boundary_guards.py`
- targeted ETC backend list/detail/query tests
- ETC module implementation notes and modular IO state files

Out of scope:

- business-batch v2 route behavior;
- production validation;
- broad `server.py` splitting;
- frontend changes;
- read model repository changes.

## Verification

This audit slice is analysis-only. Code and behavior were not changed in this boundary.

## Seven Test Categories

- Business core unit tests: not added in this analysis-only slice; next extraction should add facade/service tests.
- Service-layer tests: not added in this analysis-only slice; next extraction should cover list/detail/count/filter contracts.
- API contract tests: not added in this analysis-only slice; next extraction must rerun targeted list/detail/query regressions.
- Read model/cache/background job tests: not applicable; this path reads in-memory/local ETC payloads and does not change refresh/job behavior.
- Frontend component/interaction tests: not applicable; no UI behavior changed.
- End-to-end business-flow integration tests: not added in this analysis-only slice; existing tests were identified for next boundary.
- Existing feature regression tests: not run for this analysis-only slice; next extraction must run legacy list/detail/query regressions.

## Remaining Risk

Local modular implementation closure is still not proven. Legacy batch read payload ownership remains in `Application` until Row320 extracts the facade and static/API tests prove the boundary.
