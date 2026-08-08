from __future__ import annotations

import unittest
from decimal import Decimal

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.bank_transaction_identity_service import BankTransactionIdentityService


class BankTransactionIdentityServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = BankTransactionIdentityService()

    def test_official_serial_is_strong_and_business_fields_are_only_suspected(self) -> None:
        first = self.service.identity_for_mapping(
            {
                "account_no": "62220001",
                "trade_time": "2026-03-23 09:15:01",
                "txn_direction": "outflow",
                "amount": "88.001",
                "counterparty_name": " Acme   Supplies ",
                "bank_serial_no": "SERIAL-001",
            }
        )
        second = self.service.identity_for_mapping(
            {
                "account_no": "62220001",
                "pay_receive_time": "2026/03/23 09:15:01",
                "txn_direction": "支出",
                "amount": Decimal("88.00"),
                "counterparty_name": "acme supplies",
                "bank_serial_no": "SERIAL-002",
            }
        )

        self.assertNotEqual(first.identity_key, second.identity_key)
        self.assertEqual(first.identity_key, "bank-v2:62220001:bank_serial_no:SERIAL-001")
        self.assertEqual(first.suspected_key, second.suspected_key)
        self.assertEqual(first.suspected_key, "bank:62220001:2026-03-23 09:15:01:outflow:88.00:acme supplies")
        self.assertEqual(first.audit_fields["bank_serial_no"], "SERIAL-001")

    def test_different_second_produces_different_key(self) -> None:
        first = self.service.identity_for_mapping(
            {
                "account_no": "62220001",
                "trade_time": "2026-03-23 09:15:01",
                "txn_direction": "inflow",
                "amount": "88.00",
                "counterparty_name": "Acme Supplies",
            }
        )
        second = self.service.identity_for_mapping(
            {
                "account_no": "62220001",
                "trade_time": "2026-03-23 09:15:02",
                "txn_direction": "inflow",
                "amount": "88.00",
                "counterparty_name": "Acme Supplies",
            }
        )

        self.assertIsNone(first.identity_key)
        self.assertNotEqual(first.suspected_key, second.suspected_key)

    def test_different_direction_amount_or_counterparty_produces_different_key(self) -> None:
        base = {
            "account_no": "62220001",
            "trade_time": "2026-03-23 09:15:01",
            "txn_direction": "inflow",
            "amount": "88.00",
            "counterparty_name": "Acme Supplies",
        }

        identity = self.service.identity_for_mapping(base)
        direction = self.service.identity_for_mapping({**base, "txn_direction": "outflow"})
        amount = self.service.identity_for_mapping({**base, "amount": "88.01"})
        counterparty = self.service.identity_for_mapping({**base, "counterparty_name": "Other Corp"})

        self.assertNotEqual(identity.suspected_key, direction.suspected_key)
        self.assertNotEqual(identity.suspected_key, amount.suspected_key)
        self.assertNotEqual(identity.suspected_key, counterparty.suspected_key)

    def test_same_official_serial_is_same_identity_even_when_business_fields_differ(self) -> None:
        first = self.service.identity_for_mapping(
            {
                "account_no": "62220001",
                "trade_time": "2026-03-23 09:15:01",
                "txn_direction": "outflow",
                "amount": "88.00",
                "counterparty_name": "Acme Supplies",
                "bank_serial_no": "SERIAL-001",
            }
        )
        second = self.service.identity_for_mapping(
            {
                "account_no": "62220001",
                "trade_time": "2026-03-23 09:15:01",
                "txn_direction": "outflow",
                "amount": "99.00",
                "counterparty_name": "Acme Supplies",
                "bank_serial_no": "SERIAL-001",
            }
        )

        self.assertEqual(first.identity_key, second.identity_key)
        self.assertNotEqual(first.suspected_key, second.suspected_key)

    def test_bank_transaction_model_is_supported(self) -> None:
        transaction = BankTransaction(
            id="txn_001",
            account_no="62220001",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="Acme Supplies",
            amount=Decimal("88.00"),
            signed_amount=Decimal("-88.00"),
            trade_time="2026-03-23 09:15:01",
            bank_serial_no="SERIAL-001",
        )

        identity = self.service.identity_for_transaction(transaction)

        self.assertEqual(identity.identity_key, "bank-v2:62220001:bank_serial_no:SERIAL-001")
        self.assertEqual(identity.suspected_key, "bank:62220001:2026-03-23 09:15:01:outflow:88.00:acme supplies")

    def test_date_only_time_does_not_generate_identity(self) -> None:
        identity = self.service.identity_for_mapping(
            {
                "account_no": "62220001",
                "txn_date": "2026-03-23",
                "txn_direction": "outflow",
                "amount": "88.00",
                "counterparty_name": "Acme Supplies",
            }
        )

        self.assertIsNone(identity.identity_key)
        self.assertIn("trade_time", identity.missing_fields)

    def test_account_detail_number_has_priority_and_is_normalized(self) -> None:
        identity = self.service.identity_for_mapping(
            {
                "account_no": "62220001",
                "account_detail_no": "  abc 001 ",
                "bank_serial_no": "SERIAL-001",
            }
        )

        self.assertEqual(identity.identity_key, "bank-v2:62220001:account_detail_no:ABC001")
        self.assertEqual(identity.canonical_key_kind, "account_detail_no")
        self.assertIsNone(identity.suspected_key)


if __name__ == "__main__":
    unittest.main()
