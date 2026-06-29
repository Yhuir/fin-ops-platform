---
status: complete
quick_id: 260629-kcu
date: 2026-06-29
---

# Summary

## Result

- Confirmed pending invoice `+N` already uses the existing relation drawer; added a regression assertion that invoice/bank/OA clicks request `kind=invoice|bank|oa`.
- Fixed input invoice usage payment status at `InputInvoiceUsageQueryService`: confirmed linked multi-OA and multi-bank relation totals now prove `已付款` when their totals match the invoice total.
- Bumped `input_invoice_usage` source version to invalidate old SQL read model rows after the status contract change.
- Updated input invoice usage module boundary/tests docs.

## Root Cause

The old payment status logic required one OA amount and one bank amount inside a confirmed relation to individually equal the full invoice total. In multi-OA `+N` cases, each OA can be partial while the linked OA total matches the invoice, so the page displayed `待处理` even though the confirmed relation proved `已付款`.

## Verification

- `PYTHONPATH=backend/src pytest tests/test_input_invoice_usage_service.py tests/test_invoice_usage_collection_sql_runtime.py tests/test_input_invoice_usage_api.py -q`
- `PYTHONPATH=backend/src pytest tests/test_input_invoice_usage_payment_rules.py tests/test_input_invoice_usage_read_model_fresh_gate_service.py tests/test_invoice_lifecycle_page_integration.py -q`
- `cd web && npm test -- --run src/test/PendingInvoicesPage.test.tsx src/test/InputInvoiceUsagePage.test.tsx`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Remaining Risk

- Production SQL read model needs normal refresh after deploy because `input_invoice_usage_source_version` changed.
