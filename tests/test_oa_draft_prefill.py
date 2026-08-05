import unittest
from datetime import date

from fin_ops_platform.services.oa_draft_prefill import (
    ETC_OA_DRAFT_PREFILL_FAMILY,
    INPUT_INVOICE_USAGE_OA_DRAFT_PREFILL_FAMILY,
    OADraftPrefillValidationError,
    default_oa_draft_prefill,
    normalize_oa_draft_prefill,
    render_oa_draft_reason,
)
from fin_ops_platform.services.oa_adapter import detect_etc_batch_metadata


class OADraftPrefillTests(unittest.TestCase):
    def test_defaults_match_live_oa_payment_request_contract(self) -> None:
        etc = default_oa_draft_prefill(ETC_OA_DRAFT_PREFILL_FAMILY)
        reverse = default_oa_draft_prefill(INPUT_INVOICE_USAGE_OA_DRAFT_PREFILL_FAMILY)

        self.assertEqual(etc["application_type"], "s5")
        self.assertEqual(etc["payment_method"], "Bank_transfer")
        self.assertEqual(etc["invoice_kind"], "Special_invoice")
        self.assertEqual(etc["project_id"], "6486ca70cd6cae5d4e2b0b48")
        self.assertEqual(etc["payee"], "刘树刚")
        self.assertEqual(etc["bank"], "建设银行")
        self.assertEqual(etc["bank_account"], "6217003860012460901")
        self.assertEqual(reverse["payee"], "")
        self.assertEqual(reverse["bank"], "")
        self.assertEqual(reverse["bank_account"], "")

    def test_reason_templates_render_business_text_without_internal_ids(self) -> None:
        etc = default_oa_draft_prefill(ETC_OA_DRAFT_PREFILL_FAMILY)
        reverse = default_oa_draft_prefill(INPUT_INVOICE_USAGE_OA_DRAFT_PREFILL_FAMILY)

        etc_reason = render_oa_draft_reason(
            ETC_OA_DRAFT_PREFILL_FAMILY,
            etc["reason_template"],
            submission_date=date(2026, 8, 5),
            bill_date=date(2026, 6, 1),
        )
        reverse_reason = render_oa_draft_reason(
            INPUT_INVOICE_USAGE_OA_DRAFT_PREFILL_FAMILY,
            reverse["reason_template"],
            invoice_numbers=["INV-1", "INV-2"],
        )

        self.assertEqual(etc_reason, "6月账单8月5日 支付 ETC批里提交")
        self.assertEqual(reverse_reason, "进项发票反提 OA，发票数=2；发票号码=INV-1;INV-2")
        self.assertNotIn("batch_id", etc_reason.lower())
        self.assertNotIn("batch_id", reverse_reason.lower())

    def test_normalization_rejects_unknown_oa_option_and_unknown_template_token(self) -> None:
        with self.assertRaises(OADraftPrefillValidationError):
            normalize_oa_draft_prefill(
                ETC_OA_DRAFT_PREFILL_FAMILY,
                {"application_type": "unknown"},
                validate=True,
            )
        with self.assertRaises(OADraftPrefillValidationError):
            normalize_oa_draft_prefill(
                ETC_OA_DRAFT_PREFILL_FAMILY,
                {"reason_template": "{internal_batch_id}"},
                validate=True,
            )

    def test_etc_detection_prefers_structured_batch_id_and_keeps_historical_text_fallback(self) -> None:
        structured = detect_etc_batch_metadata({"data": {"etcBatchId": "etc_20260805_001", "cause": "8月账单"}})
        historical = detect_etc_batch_metadata("ETC批量提交\netc_batch_id=etc_20260503_001")

        self.assertEqual(structured["etc_batch_id"], "etc_20260805_001")
        self.assertEqual(historical["etc_batch_id"], "etc_20260503_001")


if __name__ == "__main__":
    unittest.main()
