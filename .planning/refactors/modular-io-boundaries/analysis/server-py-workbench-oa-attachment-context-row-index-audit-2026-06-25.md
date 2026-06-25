# server-py:workbench-oa-attachment-context-row-index-audit

Date: 2026-06-25
Status: analysis-closed

## Scope

Audited `_raw_workbench_payload_rows_by_id(...)`, `_oa_attachment_context_row_ids_by_oa_id(...)`, `_invoice_row_is_oa_attachment_context(...)` and `_oa_id_from_attachment_invoice_id(...)`.

## Findings

- These helpers are pure row-index/source matching logic:
  - raw payload row indexing across paired/open OA/bank/invoice panes;
  - OA attachment invoice row detection by row type and source kind;
  - direct `derived_from_oa_id` matching;
  - parent OA id matching;
  - source-link based OA matching;
  - attachment invoice id fallback matching.
- The logic does not require `Application`, HTTP, repositories, read-model gateways, caches, workers, auth or persistence.
- The only required dependencies are the existing OA attachment matching helpers.

## Decision

Select `server-py:workbench-oa-attachment-context-row-index-extraction`.

## Deferred

- Generic raw payload row id set extraction remains separate.
- Production browser/admin/write evidence remains deferred.
