# Quick Task 260629-kcu: pending invoices +N drawer and input invoice usage relation status display

**Date:** 2026-06-29

## Scope

- Verify pending invoice `+N` relation controls use the existing relation drawer by relation kind.
- Fix input invoice usage payment status at the shared backend relation/status boundary, not by page-only tag overrides.
- Update module docs only if the boundary/I/O contract changes.

## Plan

1. Add focused regression coverage for pending invoice `+N` drawer click behavior and split/multi relation payment status.
2. Fix `InputInvoiceUsageQueryService` relation completeness to treat linked invoice-OA and invoice-bank evidence as one invoice proof when confirmed relation amounts match.
3. Run affected backend/frontend checks and record summary.

## Acceptance

- Pending invoice `+N` opens relation detail for the clicked kind.
- Input invoice usage rows with confirmed OA total + confirmed bank total matching invoice total show `paid` / `已付款`.
- Candidate relations remain `pending`.
