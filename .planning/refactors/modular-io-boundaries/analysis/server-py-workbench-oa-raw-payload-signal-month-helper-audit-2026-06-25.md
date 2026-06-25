# server-py:workbench-oa-raw-payload-signal-month-helper-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-raw-payload-mutation-helper-extraction`
**Next boundary:** `server-py:workbench-oa-raw-payload-signal-month-helper-extraction`

## Purpose

Audit OA raw payload signal/month extraction helpers that remain in `Application`.

## Findings

- `_first_month_from_oa_row(...)` owns OA row month candidate extraction from top-level fields and detail/summary fields.
- `_oa_months_from_raw_workbench_payload(...)` owns raw payload OA section scanning and month collection.
- `_raw_payload_has_oa_attachment_invoice_signal(...)` owns OA attachment signal detection from tags and detail/summary fields.
- The helpers are pure and do not need HTTP, auth, repositories, queues, caches, read-model readiness or persistence.
- The only external policy is month-prefix validation, which can be injected from `Application` using `SEARCH_MONTH_RE`.

## Selected Boundary

Extract signal/month extraction into `WorkbenchOaRawPayloadSignalMonthHelper`.

## Deferrals

- Live/OA merge and row-id dedupe helper extraction remains deferred.
- Production browser/admin/write evidence remains deferred.

## Completion Semantics

This audit may be marked `analysis-closed` after the implementation boundary is selected and recorded. It does not claim Workbench module/global closure.
