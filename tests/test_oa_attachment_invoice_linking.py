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


def test_normalizes_compact_hydration_external_identity_alias() -> None:
    oa_row = {
        "id": "oa-exp-2204",
        "type": "oa",
        "source_identity_aliases": ["6a0ea9ef3bb8164165d8c619"],
        "expense_items": [
            {
                "id": "oa-exp-2204:item:0:currenthash",
                "expense_item_id": "oa-exp-2204:item:0:currenthash",
                "row_index": "0",
            }
        ],
    }
    invoice = {
        "id": "invoice-150",
        "type": "invoice",
        "source_kind": "oa_attachment_invoice",
        "source_links": [
            {
                "source_type": "oa_attachment_invoice",
                "source_expense_item_id": (
                    "oa-exp-6a0ea9ef3bb8164165d8c619:item:0:historicalhash"
                ),
                "source_expense_row_index": "0",
            }
        ],
        "source_expense_item_ids": [
            "oa-exp-6a0ea9ef3bb8164165d8c619:item:0:historicalhash"
        ],
    }

    normalize_oa_attachment_expense_item_ids([oa_row, invoice])

    assert invoice["source_expense_item_ids"] == [
        "oa-exp-2204:item:0:currenthash"
    ]
    assert invoice["source_oa_row_id"] == "oa-exp-2204"


def test_normalizes_historical_parent_aliases_for_multiple_current_expense_items() -> None:
    oa_row = {
        "id": "oa-exp-current",
        "type": "oa",
        "source_aliases": ["oa-exp-historical"],
        "expense_items": [
            {
                "id": "oa-exp-current:item:0:current-a",
                "expense_item_id": "oa-exp-current:item:0:current-a",
                "row_index": "0",
            },
            {
                "id": "oa-exp-current:item:1:current-b",
                "expense_item_id": "oa-exp-current:item:1:current-b",
                "row_index": "1",
            },
        ],
    }
    invoices = [
        {
            "id": "invoice-a",
            "type": "invoice",
            "source_kind": "oa_attachment_invoice",
            "source_links": [
                {
                    "source_type": "manual_invoice_import",
                    "source_id": "batch-import-a",
                },
                {
                    "source_type": "oa_attachment_invoice",
                    "source_expense_item_id": "oa-exp-historical:item:0:old-a",
                    "source_expense_row_index": "0",
                },
            ],
        },
        {
            "id": "invoice-b",
            "type": "invoice",
            "source_kind": "oa_attachment_invoice",
            "source_links": [
                {
                    "source_type": "manual_invoice_import",
                    "source_id": "batch-import-b",
                },
                {
                    "source_type": "oa_attachment_invoice",
                    "source_expense_item_id": "oa-exp-historical:item:1:old-b",
                    "source_expense_row_index": "1",
                },
            ],
        },
    ]

    normalize_oa_attachment_expense_item_ids([oa_row, *invoices])

    assert invoices[0]["source_expense_item_ids"] == [
        "oa-exp-current:item:0:current-a"
    ]
    assert invoices[1]["source_expense_item_ids"] == [
        "oa-exp-current:item:1:current-b"
    ]
    assert {invoice["source_oa_row_id"] for invoice in invoices} == {
        "oa-exp-current"
    }


def test_explicit_expense_item_binding_overrides_historical_attachment_source() -> None:
    oa_row = {
        "id": "oa-exp-2201",
        "type": "oa",
        "expense_items": [
            {"id": "oa-exp-2201:item:3:current", "row_index": "3"},
            {"id": "oa-exp-2201:item:4:current", "row_index": "4"},
        ],
    }
    invoice = {
        "id": "invoice-27-05",
        "type": "invoice",
        "source_kind": "invoice",
        "source_links": [
            {
                "source_type": "oa_attachment_invoice",
                "source_expense_item_id": "oa-exp-2201:item:3:old",
                "source_expense_row_index": "3",
            },
            {
                "source_type": "oa_expense_item_invoice",
                "source_expense_item_id": "oa-exp-2201:item:4:written",
            },
        ],
        "source_expense_item_ids": ["oa-exp-2201:item:3:old"],
    }

    normalize_oa_attachment_expense_item_ids([oa_row, invoice])

    assert invoice["source_expense_item_ids"] == ["oa-exp-2201:item:4:current"]
    assert len(invoice["source_links"]) == 2
    assert invoice["source_links"][0]["source_expense_item_id"] == "oa-exp-2201:item:3:old"


def test_explicit_current_item_id_does_not_require_a_row_index() -> None:
    oa_row = {
        "id": "oa-1",
        "type": "oa",
        "expense_items": [{"id": "oa-1:item:0", "amount": "27.05"}],
    }
    invoice = {
        "id": "invoice-27-05",
        "type": "invoice",
        "source_links": [{
            "source_type": "oa_expense_item_invoice",
            "derived_from_oa_id": "oa-1",
            "source_expense_item_id": "oa-1:item:0",
        }],
    }

    normalize_oa_attachment_expense_item_ids([oa_row, invoice])

    assert invoice["source_expense_item_ids"] == ["oa-1:item:0"]
    assert invoice["source_oa_row_id"] == "oa-1"


def test_malformed_explicit_binding_does_not_fall_back_to_attachment_source() -> None:
    oa_row = {
        "id": "oa-exp-2201",
        "type": "oa",
        "expense_items": [
            {"id": "oa-exp-2201:item:3:current", "row_index": "3"},
        ],
    }
    invoice = {
        "id": "invoice-malformed-explicit",
        "type": "invoice",
        "source_kind": "oa_attachment_invoice",
        "source_links": [
            {
                "source_type": "oa_attachment_invoice",
                "source_expense_item_id": "oa-exp-2201:item:3:old",
                "source_expense_row_index": "3",
            },
            {
                "source_type": "oa_expense_item_invoice",
                "source_expense_item_id": "",
            },
        ],
        "source_expense_item_ids": ["oa-exp-2201:item:3:old"],
    }

    normalize_oa_attachment_expense_item_ids([oa_row, invoice])

    assert invoice["source_expense_item_ids"] == []


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


def test_shared_parent_alias_remains_ambiguous() -> None:
    rows = [
        {
            "id": "oa-a",
            "type": "oa",
            "source_aliases": ["oa-historical"],
            "expense_items": [{"id": "oa-a:item:0", "row_index": "0"}],
        },
        {
            "id": "oa-b",
            "type": "oa",
            "source_aliases": ["oa-historical"],
            "expense_items": [{"id": "oa-b:item:0", "row_index": "0"}],
        },
        {
            "id": "invoice-ambiguous-parent",
            "type": "invoice",
            "source_kind": "oa_attachment_invoice",
            "source_links": [
                {
                    "source_type": "oa_attachment_invoice",
                    "source_expense_item_id": "oa-historical:item:0:old",
                    "source_expense_row_index": "0",
                }
            ],
        },
    ]

    normalize_oa_attachment_expense_item_ids(rows)

    assert "source_oa_id" not in rows[2]
    assert "source_expense_item_ids" not in rows[2]
