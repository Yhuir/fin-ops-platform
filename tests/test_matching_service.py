from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import BatchType, MatchingConfidence, MatchingResultType
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.matching import MatchingEngineService


class MatchingEngineServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.import_service = ImportNormalizationService()
        self.matching_service = MatchingEngineService(self.import_service)

    def test_run_creates_automatic_match_for_exact_one_to_one(self) -> None:
        self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "033001",
                    "invoice_no": "A1001",
                    "counterparty_name": "Alpha Tech",
                    "amount": "100.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        self._confirm(
            BatchType.BANK_TRANSACTION,
            [
                {
                    "account_no": "62221111",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Alpha Tech",
                    "debit_amount": "",
                    "credit_amount": "100.00",
                    "bank_serial_no": "AUTO-001",
                    "summary": "customer payment",
                }
            ],
        )

        run = self.matching_service.run(triggered_by="user_finance_01")

        self.assertEqual(run.automatic_count, 1)
        result = run.results[0]
        self.assertEqual(result.result_type, MatchingResultType.AUTOMATIC_MATCH)
        self.assertEqual(result.confidence, MatchingConfidence.HIGH)
        self.assertEqual(result.rule_code, "exact_counterparty_amount_one_to_one")

    def test_run_creates_suggested_match_for_many_invoices_one_transaction(self) -> None:
        self._confirm(
            BatchType.INPUT_INVOICE,
            [
                {
                    "invoice_code": "044001",
                    "invoice_no": "B2001",
                    "counterparty_name": "Beta Supplies",
                    "amount": "40.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                },
                {
                    "invoice_code": "044001",
                    "invoice_no": "B2002",
                    "counterparty_name": "Beta Supplies",
                    "amount": "60.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                },
            ],
        )
        self._confirm(
            BatchType.BANK_TRANSACTION,
            [
                {
                    "account_no": "62222222",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Beta Supplies",
                    "debit_amount": "100.00",
                    "credit_amount": "",
                    "bank_serial_no": "SUG-001",
                    "summary": "supplier payment",
                }
            ],
        )

        run = self.matching_service.run(triggered_by="user_finance_01")
        result = next(item for item in run.results if item.rule_code == "same_counterparty_many_invoices_one_transaction")

        self.assertEqual(result.result_type, MatchingResultType.SUGGESTED_MATCH)
        self.assertEqual(result.confidence, MatchingConfidence.MEDIUM)
        self.assertEqual(len(result.invoice_ids), 2)
        self.assertEqual(len(result.transaction_ids), 1)

    def test_run_creates_low_confidence_suggestion_for_partial_match(self) -> None:
        self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "055001",
                    "invoice_no": "C3001",
                    "counterparty_name": "Gamma Client",
                    "amount": "100.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        self._confirm(
            BatchType.BANK_TRANSACTION,
            [
                {
                    "account_no": "62223333",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Gamma Client",
                    "debit_amount": "",
                    "credit_amount": "80.00",
                    "bank_serial_no": "PARTIAL-001",
                    "summary": "partial receipt",
                }
            ],
        )

        run = self.matching_service.run(triggered_by="user_finance_01")
        result = next(item for item in run.results if item.rule_code == "same_counterparty_partial_amount_match")

        self.assertEqual(result.result_type, MatchingResultType.SUGGESTED_MATCH)
        self.assertEqual(result.confidence, MatchingConfidence.LOW)
        self.assertEqual(result.difference_amount, Decimal("20.00"))

    def test_run_creates_manual_review_when_no_confident_match_exists(self) -> None:
        self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "066001",
                    "invoice_no": "D4001",
                    "counterparty_name": "Delta Client",
                    "amount": "120.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )

        run = self.matching_service.run(triggered_by="user_finance_01")
        result = next(item for item in run.results if item.rule_code == "no_confident_match")

        self.assertEqual(result.result_type, MatchingResultType.MANUAL_REVIEW)
        self.assertEqual(result.invoice_ids, ["inv_imported_0001"])
        self.assertEqual(result.transaction_ids, [])

    def _confirm(self, batch_type: BatchType, rows: list[dict[str, str]]) -> None:
        preview = self.import_service.preview_import(
            batch_type=batch_type,
            source_name=f"{batch_type.value}.json",
            imported_by="user_finance_01",
            rows=rows,
        )
        self.import_service.confirm_import(preview.id)


if __name__ == "__main__":
    unittest.main()
