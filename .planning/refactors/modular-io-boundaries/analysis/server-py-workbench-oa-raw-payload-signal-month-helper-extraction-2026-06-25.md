# server-py:workbench-oa-raw-payload-signal-month-helper-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-oa-raw-payload-signal-month-helper-audit`
**Next boundary:** `server-py:workbench-live-oa-merge-helper-audit`

## Purpose

Move OA raw payload signal/month extraction out of `Application`.

## Implementation

- Added `WorkbenchOaRawPayloadSignalMonthHelper` in `backend/src/fin_ops_platform/services/workbench_oa_raw_payload_signal_month_helper.py`.
- The helper owns:
  - OA row month candidate extraction;
  - raw payload OA month collection;
  - OA attachment invoice signal detection from tags and detail/summary fields.
- `Application._first_month_from_oa_row(...)`, `_oa_months_from_raw_workbench_payload(...)` and `_raw_payload_has_oa_attachment_invoice_signal(...)` now delegate to the helper.
- `Application` injects month-prefix validation through `SEARCH_MONTH_RE`.

## Inputs

- OA row dictionaries.
- Raw Workbench payload dictionaries.
- Month-prefix validation callable.

## Outputs

- First OA row month or `None`.
- Raw payload OA month set.
- OA attachment signal boolean.

## State And Events

The helper is pure and read-only. It does not know HTTP, repositories, auth, queues, caches, persistence, read-model freshness or worker state.

## Read Model/Freshness Contract

No read-model freshness semantics changed. Existing retained all-OA and canonical OA attachment row flows still call the same `Application` helper names, which now delegate to the helper.

## Tests And Guards

- Added `tests/test_workbench_oa_raw_payload_signal_month_helper.py`.
- Updated static Guard coverage proving `Application` no longer owns signal/month extraction details.

## Out Of Scope

- live/OA merge helper extraction remains deferred.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
