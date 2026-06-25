# server-py:workbench-raw-payload-mutation-helper-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-canonical-oa-attachment-invoice-row-builder-extraction`
**Next boundary:** `server-py:workbench-raw-payload-mutation-helper-extraction`

## Purpose

Audit raw Workbench payload mutation and summary helpers that remain in `Application`.

## Findings

- `_replace_raw_workbench_row(...)` owns local replacement of rows in paired/open sections and serialization of replacements.
- `_dedupe_raw_workbench_rows_by_id(...)` owns payload-local dedupe by row id across paired/open sections.
- `_refresh_raw_workbench_payload_summary(...)` owns summary recomputation after payload mutation.
- These operations mutate only the raw payload object passed to them and do not need HTTP, auth, repositories, queues, caches, read-model readiness or persistence.
- `_first_month_from_oa_row(...)`, `_oa_months_from_raw_workbench_payload(...)` and `_raw_payload_has_oa_attachment_invoice_signal(...)` are related OA raw payload signal/month helpers but are better kept as a separate small slice.

## Selected Boundary

Extract replace/dedupe/summary mutation behavior into `WorkbenchRawPayloadMutationHelper`.

## Deferrals

- OA raw payload signal/month helpers remain in `Application` for the next slice.
- Production browser/admin/write evidence remains deferred.

## Completion Semantics

This audit may be marked `analysis-closed` after the implementation boundary is selected and recorded. It does not claim Workbench module/global closure.
