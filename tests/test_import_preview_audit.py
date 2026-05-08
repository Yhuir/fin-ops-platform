from __future__ import annotations

import unittest

from fin_ops_platform.services.import_preview_audit import (
    BankTransactionIdentityStrategy,
    ImportPreviewAuditRow,
    InvoiceIdentityStrategy,
    build_import_preview_session_audit,
)


class ImportPreviewAuditTests(unittest.TestCase):
    def test_invoice_placeholder_digital_number_falls_back_to_code_and_number(self) -> None:
        identity = InvoiceIdentityStrategy().identify(
            {
                "digital_invoice_no": "--",
                "invoice_code": "033001",
                "invoice_no": "9001",
                "seller_tax_no": "seller-tax",
                "buyer_tax_no": "buyer-tax",
                "invoice_date": "2026-03-21",
                "total_with_tax": "100.00",
            }
        )

        self.assertEqual(identity.identity_kind, "stable")
        self.assertEqual(identity.identity_key, "033001:9001")

    def test_same_digital_invoice_number_is_grouped_as_duplicate(self) -> None:
        rows = [
            ImportPreviewAuditRow(
                file_id="file_001",
                file_name="jan.xlsx",
                row_no=1,
                record_type="invoice",
                identity_key="digital-001",
                identity_kind="stable",
            ),
            ImportPreviewAuditRow(
                file_id="file_001",
                file_name="jan.xlsx",
                row_no=2,
                record_type="invoice",
                identity_key="digital-001",
                identity_kind="stable",
            ),
        ]

        session_audit = build_import_preview_session_audit(rows)

        self.assertEqual(session_audit.audit.original_count, 2)
        self.assertEqual(session_audit.audit.unique_count, 1)
        self.assertEqual(session_audit.audit.duplicate_in_file_count, 1)
        self.assertEqual(session_audit.audit.duplicate_count, 1)
        self.assertEqual(len(session_audit.duplicate_groups), 1)
        self.assertEqual(session_audit.duplicate_groups[0].duplicate_type, "duplicate_in_file")

    def test_bank_transaction_without_official_serial_uses_stable_business_identity(self) -> None:
        identity = BankTransactionIdentityStrategy().identify(
            {
                "account_no": "acct-a",
                "trade_time": "2026-03-23 09:15:01",
                "txn_direction": "outflow",
                "amount": "88.00",
                "normalized_counterparty_name": "acme supplies",
            }
        )

        self.assertEqual(identity.identity_kind, "stable")
        self.assertEqual(identity.identity_key, "bank:acct-a:2026-03-23 09:15:01:outflow:88.00:acme supplies")

    def test_bank_transaction_same_serial_on_different_accounts_is_not_duplicate(self) -> None:
        strategy = BankTransactionIdentityStrategy()

        first = strategy.identify(
            {
                "account_no": "acct-a",
                "trade_time": "2026-03-23 09:15:01",
                "txn_direction": "outflow",
                "amount": "88.00",
                "counterparty_name": "Acme Supplies",
                "bank_serial_no": "SERIAL-001",
            }
        )
        second = strategy.identify(
            {
                "account_no": "acct-b",
                "trade_time": "2026-03-23 09:15:01",
                "txn_direction": "outflow",
                "amount": "88.00",
                "counterparty_name": "Acme Supplies",
                "bank_serial_no": "SERIAL-001",
            }
        )

        self.assertEqual(first.identity_kind, "stable")
        self.assertEqual(second.identity_kind, "stable")
        self.assertNotEqual(first.identity_key, second.identity_key)

    def test_bank_transaction_date_only_time_has_no_identity(self) -> None:
        identity = BankTransactionIdentityStrategy().identify(
            {
                "account_no": "acct-a",
                "txn_date": "2026-03-23",
                "txn_direction": "outflow",
                "amount": "88.00",
                "normalized_counterparty_name": "acme supplies",
            }
        )

        self.assertIsNone(identity.identity_kind)
        self.assertIsNone(identity.identity_key)

    def test_bank_transaction_duplicate_group_rows_include_decision_and_display_fields(self) -> None:
        rows = [
            ImportPreviewAuditRow(
                file_id="file_001",
                file_name="bank.xlsx",
                row_no=1,
                record_type="bank_transaction",
                identity_key="bank:acct-a:2026-03-23 09:15:01:outflow:88.00:acme",
                identity_kind="stable",
                decision="created",
                decision_reason="Ready to create new bank transaction.",
                account_no="acct-a",
                trade_time="2026-03-23 09:15:01",
                direction="outflow",
                amount="88.00",
                counterparty_name="acme",
            ),
            ImportPreviewAuditRow(
                file_id="file_001",
                file_name="bank.xlsx",
                row_no=2,
                record_type="bank_transaction",
                identity_key="bank:acct-a:2026-03-23 09:15:01:outflow:88.00:acme",
                identity_kind="stable",
                decision="duplicate_skipped",
                decision_reason="Duplicate within this preview.",
                account_no="acct-a",
                trade_time="2026-03-23 09:15:01",
                direction="outflow",
                amount="88.00",
                counterparty_name="acme",
            ),
        ]

        session_audit = build_import_preview_session_audit(rows)

        self.assertEqual(session_audit.audit.importable_count, 1)
        self.assertEqual(session_audit.audit.duplicate_in_file_count, 1)
        duplicate_row = session_audit.duplicate_groups[0].rows[1]
        self.assertEqual(duplicate_row["decision"], "duplicate_skipped")
        self.assertEqual(duplicate_row["decision_reason"], "Duplicate within this preview.")
        self.assertEqual(duplicate_row["identity_kind"], "stable")
        self.assertEqual(duplicate_row["account_no"], "acct-a")
        self.assertEqual(duplicate_row["trade_time"], "2026-03-23 09:15:01")
        self.assertEqual(duplicate_row["direction"], "outflow")
        self.assertEqual(duplicate_row["amount"], "88.00")
        self.assertEqual(duplicate_row["counterparty_name"], "acme")


if __name__ == "__main__":
    unittest.main()
