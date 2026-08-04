from io import StringIO
import unittest
from unittest.mock import patch

from fin_ops_platform.services.app_settings_service import OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING
from fin_ops_platform.services.oa_attachment_invoice_promotion_service import OAAttachmentInvoiceCandidate
from fin_ops_platform.tools.oa_attachment_invoice_promotion import (
    _load_candidates,
    audit_oa_attachment_invoice_promotion,
    main,
)


class OAAttachmentInvoicePromotionToolTests(unittest.TestCase):
    def test_dry_run_delegates_to_shared_promotion_service(self) -> None:
        candidate = _candidate()
        expected = {"mode": "dry_run", "summary": {"cache_candidate_count": 1}}

        with (
            patch(
                "fin_ops_platform.tools.oa_attachment_invoice_promotion._load_candidates",
                return_value=[candidate],
            ),
            patch(
                "fin_ops_platform.tools.oa_attachment_invoice_promotion."
                "OAAttachmentInvoicePromotionService.promote_candidates",
                return_value=expected,
            ) as promote,
        ):
            report = audit_oa_attachment_invoice_promotion(connection=object(), example_limit=7)

        self.assertEqual(report, expected)
        promote.assert_called_once_with(
            [candidate],
            promotion_mode=OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING,
            apply=False,
            example_limit=7,
        )

    def test_apply_requires_explicit_confirmation_flag(self) -> None:
        stdout = StringIO()

        exit_code = main(["--apply"], stdout=stdout)

        self.assertEqual(exit_code, 2)
        self.assertIn("--confirm-apply-oa-attachment-invoices", stdout.getvalue())

    def test_load_candidates_keeps_all_source_contexts_instead_of_first_only(self) -> None:
        rows = [
            _source_row("oa-exp-2321", "item-0", "outbound.pdf", "attachment-outbound"),
            _source_row("oa-exp-2321", "item-0", "return.pdf", "attachment-return"),
        ]
        connection = FakeConnection(rows)

        candidates = _load_candidates(connection)

        self.assertEqual(len(candidates), 2)
        self.assertNotIn("limit 1", connection.last_sql.lower())
        self.assertEqual(
            [candidate.attachment_invoice["source_attachment_key"] for candidate in candidates],
            ["attachment-outbound", "attachment-return"],
        )
        self.assertTrue(all(candidate.attachment_invoice["source_expense_item_id"] == "item-0" for candidate in candidates))

    def test_load_candidates_does_not_infer_missing_parent_oa_from_item_id(self) -> None:
        row = _source_row(None, "oa-exp-orphan:item:2:abcdef", "orphan.pdf", "attachment-orphan")

        candidates = _load_candidates(FakeConnection([row]))

        self.assertEqual(len(candidates), 1)
        self.assertIsNone(candidates[0].oa_row_id)
        self.assertIsNone(candidates[0].source_workbench_row_id)

    def test_load_candidates_can_limit_production_backfill_to_exact_oa_row(self) -> None:
        connection = FakeConnection(
            [_source_row("oa-exp-2321", "item-0", "outbound.pdf", "attachment-outbound")]
        )

        candidates = _load_candidates(connection, oa_row_ids=["oa-exp-2321"])

        self.assertEqual(len(candidates), 1)
        self.assertIn("context.oa_row_id = any", connection.last_sql)
        self.assertEqual(connection.last_params, (["oa-exp-2321"],))


class FakeConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def fetch_all(self, sql: str, params: object = None) -> list[dict[str, object]]:
        self.last_sql = sql
        self.last_params = params
        return list(self.rows)


def _source_row(
    oa_row_id: str | None,
    item_id: str,
    filename: str,
    source_attachment_key: str,
) -> dict[str, object]:
    return {
        "cache_source_attachment_key": "cache-key-1",
        "invoices": [
            {
                "evidence_type": "tax_invoice",
                "digital_invoice_no": (
                    "26539150014000401220" if "outbound" in filename else "26539148197001628598"
                ),
                "seller_name": "中国铁路",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-06-29",
                "total_with_tax": "145.00",
            }
        ],
        "oa_application_id": "application-1" if oa_row_id else None,
        "oa_source_id": oa_row_id,
        "oa_row_id": oa_row_id,
        "source_expense_item_id": item_id,
        "source_expense_row_index": "0",
        "source_attachment_key": source_attachment_key,
        "source_attachment_name": filename,
    }


def _candidate() -> OAAttachmentInvoiceCandidate:
    return OAAttachmentInvoiceCandidate(
        cache_source_attachment_key="cache-key-1",
        invoice_index=0,
        attachment_invoice={"digital_invoice_no": "26539150014000401220"},
        oa_form_id="application-1",
        oa_row_id="oa-exp-2321",
        source_workbench_row_id="oa-att-inv-oa-exp-2321-1",
        context={},
    )


if __name__ == "__main__":
    unittest.main()
