from __future__ import annotations


AMOUNT_EXCEPTION_CODES = (
    "oa_bank_equal_invoice_more",
    "oa_bank_equal_invoice_less",
    "oa_invoice_equal_bank_more",
    "oa_invoice_equal_bank_less",
    "bank_invoice_equal_oa_less",
    "bank_invoice_equal_oa_more",
    "all_amounts_different",
)
EXCEPTION_VIEWS = ("amount", "document_only")
