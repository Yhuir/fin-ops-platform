# server-py:workbench-oa-invoice-offset-rebuild-helper-audit

Date: 2026-06-25
Status: analysis-closed

## Scope

Audited `Application._cached_payload_needs_oa_invoice_offset_rebuild(...)` and the directly related `_oa_attachment_invoice_rows_for_oa(...)` compatibility helper.

## Findings

- The cache rebuild decision is pure payload inspection plus three injected facts:
  - configured OA invoice offset applicant names;
  - OA attachment invoice row-to-OA matching;
  - the configured OA invoice offset tag.
- The logic does not require HTTP request/response handling, repository access, cache writes, worker enqueueing, or read-model refresh ownership.
- The existing rule contract is narrow:
  - no configured applicant names means no rebuild;
  - matching configured applicant + attachment invoice in `open` means rebuild;
  - matching configured applicant + attachment invoice in `paired` means rebuild when any related OA/invoice row lacks the offset tag or `cost_excluded`;
  - complete paired metadata means the cached payload can stay usable.
- `_oa_attachment_invoice_rows_for_oa(...)` is only used inside `Application` and can remain as a compatibility delegate.

## Decision

Select `server-py:workbench-oa-invoice-offset-rebuild-helper-extraction`.

Create `WorkbenchOaInvoiceOffsetRebuildHelper` under `services/`, inject applicant-name provider, attachment matcher and offset tag explicitly, then make `Application` delegate both cache rebuild detection and attachment invoice row matching.

## Deferred

- `_oa_invoice_offset_desired_relations(...)` and `_sync_oa_invoice_offset_auto_pair_relations(...)` remain in `Application` for a dedicated relation-sync boundary.
- Production browser/admin/write evidence remains deferred.
