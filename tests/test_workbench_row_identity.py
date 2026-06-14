from __future__ import annotations

from fin_ops_platform.services.workbench_row_identity import (
    looks_like_bank_workbench_row_id,
    looks_like_invoice_workbench_row_id,
    looks_like_oa_workbench_row_id,
    row_type_for_workbench_row_id,
)


def test_row_type_for_workbench_row_id_covers_imported_invoice_ids() -> None:
    assert row_type_for_workbench_row_id("inv_imported_1643") == "invoice"
    assert row_type_for_workbench_row_id("inv-imported-1643") == "invoice"
    assert row_type_for_workbench_row_id("invoice_1643") == "invoice"
    assert row_type_for_workbench_row_id("oa-att-inv-oa-1-0") == "invoice"
    assert looks_like_invoice_workbench_row_id("inv_imported_1643") is True


def test_row_type_for_workbench_row_id_preserves_existing_prefixes() -> None:
    assert row_type_for_workbench_row_id("txn_imported_1284") == "bank"
    assert row_type_for_workbench_row_id("txn-1284") == "bank"
    assert row_type_for_workbench_row_id("bank-1284") == "bank"
    assert row_type_for_workbench_row_id("oa-123") == "oa"
    assert row_type_for_workbench_row_id("unknown-row") == "unknown"
    assert row_type_for_workbench_row_id("unknown-row", unknown="") == ""
    assert looks_like_bank_workbench_row_id("txn_imported_1284") is True
    assert looks_like_oa_workbench_row_id("oa-123") is True
