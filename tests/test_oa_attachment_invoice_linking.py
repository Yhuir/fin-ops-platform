from fin_ops_platform.services.oa_attachment_invoice_linking import (
    normalize_oa_attachment_expense_item_ids,
)


def test_normalizes_historical_attachment_item_ids_to_current_canonical_item() -> None:
    oa_row = {
        "id": "oa-exp-350",
        "type": "oa",
        "expense_items": [
            {
                "id": "oa-exp-350:item:0:currenthash",
                "expense_item_id": "oa-exp-350:item:0:currenthash",
                "row_index": "0",
                "amount": "350.00",
                "attachment_file_count": 6,
            }
        ],
    }
    invoices = [
        {
            "id": f"invoice-{amount}-{index}",
            "type": "invoice",
            "source_kind": "oa_attachment_invoice",
            "source_links": [
                {
                    "source_type": "oa_attachment_invoice",
                    "source_expense_item_id": "oa-exp-350:item:0:historicalhash",
                    "source_expense_row_index": "0",
                }
            ],
            "source_expense_item_ids": ["oa-exp-350:item:0:historicalhash"],
            "total_with_tax": amount,
        }
        for index, amount in enumerate(("150.00", "100.00", "100.00"))
    ]

    normalize_oa_attachment_expense_item_ids([oa_row, *invoices])

    assert {
        tuple(invoice["source_expense_item_ids"])
        for invoice in invoices
    } == {("oa-exp-350:item:0:currenthash",)}
    assert {invoice["source_oa_id"] for invoice in invoices} == {"oa-exp-350"}
    assert {invoice["source_oa_row_id"] for invoice in invoices} == {"oa-exp-350"}


def test_leaves_ambiguous_or_foreign_attachment_sources_unassigned() -> None:
    rows = [
        {
            "id": "oa-exp-350",
            "type": "oa",
            "expense_items": [
                {"id": "item-a", "row_index": "0"},
                {"id": "item-b", "row_index": "0"},
            ],
        },
        {
            "id": "invoice-foreign",
            "type": "invoice",
            "source_kind": "oa_attachment_invoice",
            "source_links": [
                {
                    "source_type": "oa_attachment_invoice",
                    "source_expense_item_id": "oa-exp-other:item:0:old",
                    "source_expense_row_index": "0",
                }
            ],
            "source_expense_item_ids": ["oa-exp-other:item:0:old"],
        },
    ]

    normalize_oa_attachment_expense_item_ids(rows)

    assert rows[1]["source_expense_item_ids"] == ["oa-exp-other:item:0:old"]
    assert "source_oa_id" not in rows[1]
