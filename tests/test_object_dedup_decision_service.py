from __future__ import annotations

import unittest
from decimal import Decimal

from fin_ops_platform.domain.enums import ImportDecision, InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.object_dedup_decision_service import ObjectDedupDecisionService
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy


class FakeObjectIdentityRepository:
    def __init__(self, *, invoices: list[Invoice] | None = None, transactions: list[BankTransaction] | None = None) -> None:
        self.invoices = list(invoices or [])
        self.transactions = list(transactions or [])
        self.invoice_queries: list[tuple[str | None, str | None]] = []
        self.bank_queries: list[tuple[str | None, str | None]] = []

    def find_invoice_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> Invoice | None:
        self.invoice_queries.append((canonical_key, suspected_key))
        for invoice in self.invoices:
            if canonical_key and invoice.source_unique_key == canonical_key:
                return invoice
            if suspected_key and invoice.data_fingerprint == suspected_key:
                return invoice
        return None

    def find_bank_transaction_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> BankTransaction | None:
        self.bank_queries.append((canonical_key, suspected_key))
        for transaction in self.transactions:
            if canonical_key and transaction.source_unique_key == canonical_key:
                return transaction
            if suspected_key and transaction.data_fingerprint == suspected_key:
                return transaction
        return None

    def find_bank_transactions_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> list[BankTransaction]:
        self.bank_queries.append((canonical_key, suspected_key))
        return [
            transaction
            for transaction in self.transactions
            if (canonical_key and transaction.source_unique_key == canonical_key)
            or (suspected_key and transaction.data_fingerprint == suspected_key)
        ]

    def canonical_invoice_key_exists(self, canonical_key: str) -> bool:
        return self.find_invoice_by_identity(canonical_key=canonical_key) is not None


class ObjectDedupDecisionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.counterparty = Counterparty(id="cp-1", name="Acme", normalized_name="acme", counterparty_type="vendor")
        self.invoice = Invoice(
            id="inv-1",
            invoice_type=InvoiceType.INPUT,
            invoice_no="9001",
            invoice_code="033001",
            counterparty=self.counterparty,
            amount=Decimal("100"),
            signed_amount=Decimal("100"),
            invoice_date="2026-03-21",
            source_unique_key="033001:9001",
            data_fingerprint="invoice:acme:2026-03-21:100.00",
            invoice_status_from_source="valid",
        )
        self.transaction = BankTransaction(
            id="txn-1",
            account_no="62220001",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="Acme",
            amount=Decimal("88.00"),
            signed_amount=Decimal("-88.00"),
            trade_time="2026-03-23 09:15:01",
            bank_serial_no="SERIAL-001",
            source_unique_key="bank-v2:62220001:bank_serial_no:SERIAL-001",
            data_fingerprint="bank:62220001:2026-03-23 09:15:01:outflow:88.00:acme",
        )

    def test_invoice_decision_returns_status_update_duplicate_and_suspected(self) -> None:
        repo = FakeObjectIdentityRepository(invoices=[self.invoice])
        service = ObjectDedupDecisionService(identity_policy=FinancialObjectIdentityPolicy(), object_identity_repository=repo)

        status_update = service.decide_invoice_import(
            {
                "invoice_code": "033001",
                "invoice_no": "9001",
                "invoice_status_from_source": "cancelled",
            }
        )
        duplicate = service.decide_invoice_import(
            {
                "invoice_code": "033001",
                "invoice_no": "9001",
                "invoice_status_from_source": "valid",
            }
        )
        suspected = service.decide_invoice_import(
            {
                "seller_name": "Acme",
                "buyer_name": "Buyer",
                "invoice_date": "2026-03-22",
                "total_with_tax": "66.00",
            }
        )

        self.assertEqual(status_update.decision, ImportDecision.STATUS_UPDATED)
        self.assertEqual(status_update.linked_object_id, "inv-1")
        self.assertEqual(duplicate.decision, ImportDecision.DUPLICATE_SKIPPED)
        self.assertEqual(suspected.decision, ImportDecision.CREATED)
        self.assertEqual(repo.invoice_queries[0], ("033001:9001", None))

    def test_suspected_invoice_uses_suspected_key_only_without_canonical_key(self) -> None:
        suspected_invoice = Invoice(
            id="inv-2",
            invoice_type=InvoiceType.INPUT,
            invoice_no="",
            counterparty=self.counterparty,
            amount=Decimal("66.00"),
            signed_amount=Decimal("66.00"),
            data_fingerprint="suspected:Acme:Buyer:2026-03-22:66.00",
        )
        service = ObjectDedupDecisionService(
            object_identity_repository=FakeObjectIdentityRepository(invoices=[suspected_invoice])
        )

        decision = service.decide_invoice_import(
            {
                "seller_name": "Acme",
                "buyer_name": "Buyer",
                "invoice_date": "2026-03-22",
                "total_with_tax": "66.00",
            }
        )

        self.assertEqual(decision.decision, ImportDecision.SUSPECTED_DUPLICATE)
        self.assertEqual(decision.linked_object_id, "inv-2")

    def test_invoice_with_new_canonical_key_falls_back_to_fingerprint_before_create(self) -> None:
        repo = FakeObjectIdentityRepository(invoices=[self.invoice])
        service = ObjectDedupDecisionService(object_identity_repository=repo)

        decision = service.decide_invoice_import(
            {
                "digital_invoice_no": "DIFFERENT-INVOICE-NO",
                "normalized_counterparty_name": "acme",
                "invoice_date": "2026-03-21",
                "total_with_tax": "100.00",
                "invoice_status_from_source": "valid",
            }
        )

        self.assertEqual(decision.decision, ImportDecision.DUPLICATE_SKIPPED)
        self.assertEqual(decision.linked_object_id, "inv-1")
        self.assertEqual(
            repo.invoice_queries,
            [
                ("DIFFERENT-INVOICE-NO", None),
                (None, "invoice:acme:2026-03-21:100.00"),
            ],
        )

    def test_bank_transaction_decision_uses_canonical_key_repository_lookup(self) -> None:
        repo = FakeObjectIdentityRepository(transactions=[self.transaction])
        service = ObjectDedupDecisionService(object_identity_repository=repo)

        decision = service.decide_bank_transaction_import(
            {
                "account_no": "62220001",
                "trade_time": "2026-03-23 09:15:01",
                "txn_direction": "outflow",
                "amount": "88.00",
                "counterparty_name": "Acme",
                "bank_serial_no": "SERIAL-001",
            }
        )

        self.assertEqual(decision.decision, ImportDecision.DUPLICATE_SKIPPED)
        self.assertEqual(decision.linked_object_id, "txn-1")
        self.assertEqual(len(repo.bank_queries), 2)
        self.assertTrue(repo.bank_queries[0][0].startswith("bank-v3:62220001:bank_serial_no:SERIAL-001:"))
        self.assertEqual(repo.bank_queries[0][1], None)
        self.assertEqual(repo.bank_queries[1], (None, self.transaction.data_fingerprint))

    def test_bank_reference_reuse_does_not_hide_a_distinct_fee_row(self) -> None:
        repo = FakeObjectIdentityRepository(transactions=[self.transaction])
        service = ObjectDedupDecisionService(object_identity_repository=repo)

        decision = service.decide_bank_transaction_import(
            {
                "account_no": "62220001",
                "trade_time": "2026-03-23 09:15:02",
                "txn_direction": "outflow",
                "amount": "0.90",
                "counterparty_name": "Bank fee",
                "bank_serial_no": "SERIAL-001",
            }
        )

        self.assertEqual(decision.decision, ImportDecision.CREATED)
        self.assertEqual(len(repo.bank_queries), 2)
        self.assertNotEqual(repo.bank_queries[1][1], self.transaction.data_fingerprint)

    def test_same_fingerprint_with_different_official_reference_is_not_auto_deduplicated(self) -> None:
        repo = FakeObjectIdentityRepository(transactions=[self.transaction])
        service = ObjectDedupDecisionService(object_identity_repository=repo)

        decision = service.decide_bank_transaction_import(
            {
                "account_no": "62220001",
                "trade_time": "2026-03-23 09:15:01",
                "txn_direction": "outflow",
                "amount": "88.00",
                "counterparty_name": "Acme",
                "bank_serial_no": "SERIAL-002",
            }
        )

        self.assertEqual(decision.decision, ImportDecision.CREATED)
        self.assertEqual(len(repo.bank_queries), 2)

    def test_same_canonical_identity_with_different_balance_is_not_deduplicated(self) -> None:
        incoming = {
            "account_no": "62220001",
            "trade_time": "2026-03-23 09:15:01",
            "txn_direction": "outflow",
            "amount": "88.00",
            "balance": "912.00",
            "currency": "人民币元",
            "counterparty_name": "Acme",
            "bank_serial_no": "SERIAL-001",
        }
        identity = FinancialObjectIdentityPolicy().identify_bank_transaction_mapping(incoming)
        self.transaction.source_unique_key = identity.canonical_key
        self.transaction.balance = Decimal("1000.00")
        self.transaction.currency = "CNY"
        repo = FakeObjectIdentityRepository(transactions=[self.transaction])
        service = ObjectDedupDecisionService(object_identity_repository=repo)

        decision = service.decide_bank_transaction_import(incoming)

        self.assertEqual(decision.decision, ImportDecision.CREATED)
        self.assertIsNone(decision.linked_object_id)
        self.assertTrue(str(decision.identity.canonical_key).startswith("bank-v4:"))
        self.assertEqual(decision.identity.audit_fields["base_canonical_key"], identity.canonical_key)

    def test_same_canonical_identity_with_equal_position_is_deduplicated(self) -> None:
        incoming = {
            "account_no": "62220001",
            "trade_time": "2026-03-23 09:15:01",
            "txn_direction": "outflow",
            "amount": "88.00",
            "balance": "1000.000",
            "currency": "RMB",
            "counterparty_name": "Acme",
            "bank_serial_no": "SERIAL-001",
        }
        identity = FinancialObjectIdentityPolicy().identify_bank_transaction_mapping(incoming)
        self.transaction.source_unique_key = identity.canonical_key
        self.transaction.balance = Decimal("1000.00")
        self.transaction.currency = "人民币元"
        repo = FakeObjectIdentityRepository(transactions=[self.transaction])
        service = ObjectDedupDecisionService(object_identity_repository=repo)

        decision = service.decide_bank_transaction_import(incoming)

        self.assertEqual(decision.decision, ImportDecision.DUPLICATE_SKIPPED)
        self.assertEqual(decision.linked_object_id, "txn-1")

    def test_reused_canonical_reference_reimport_matches_existing_position_identity(self) -> None:
        incoming = {
            "account_no": "62220001",
            "trade_time": "2026-03-23 09:15:01",
            "txn_direction": "outflow",
            "amount": "88.00",
            "balance": "912.00",
            "currency": "人民币元",
            "counterparty_name": "Acme",
            "bank_serial_no": "SERIAL-001",
        }
        policy = FinancialObjectIdentityPolicy()
        base_identity = policy.identify_bank_transaction_mapping(incoming)
        position_identity = policy.identify_bank_transaction_position_mapping(incoming)
        self.transaction.source_unique_key = base_identity.canonical_key
        self.transaction.balance = Decimal("1000.00")
        self.transaction.currency = "CNY"
        position_transaction = BankTransaction(
            id="txn-position-1",
            account_no="62220001",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="Acme",
            amount=Decimal("88.00"),
            signed_amount=Decimal("-88.00"),
            trade_time="2026-03-23 09:15:01",
            bank_serial_no="SERIAL-001",
            balance=Decimal("912.00"),
            currency="CNY",
            source_unique_key=position_identity.canonical_key,
            data_fingerprint="legacy-drifted-fingerprint",
        )
        repo = FakeObjectIdentityRepository(
            transactions=[self.transaction, position_transaction]
        )
        service = ObjectDedupDecisionService(
            identity_policy=policy,
            object_identity_repository=repo,
        )

        decision = service.decide_bank_transaction_import(incoming)

        self.assertEqual(decision.decision, ImportDecision.DUPLICATE_SKIPPED)
        self.assertEqual(decision.linked_object_id, "txn-position-1")
        self.assertEqual(decision.identity.canonical_key, position_identity.canonical_key)
        self.assertEqual(
            repo.bank_queries[-1],
            (position_identity.canonical_key, None),
        )

    def test_fingerprint_match_without_existing_official_reference_is_suspected(self) -> None:
        self.transaction.bank_serial_no = None
        repo = FakeObjectIdentityRepository(transactions=[self.transaction])
        service = ObjectDedupDecisionService(object_identity_repository=repo)

        decision = service.decide_bank_transaction_import(
            {
                "account_no": "62220001",
                "trade_time": "2026-03-23 09:15:01",
                "txn_direction": "outflow",
                "amount": "88.00",
                "counterparty_name": "Acme",
                "bank_serial_no": "SERIAL-001",
            }
        )

        self.assertEqual(decision.decision, ImportDecision.SUSPECTED_DUPLICATE)
        self.assertEqual(decision.linked_object_id, "txn-1")

    def test_bank_transaction_weak_match_is_only_suspected(self) -> None:
        repo = FakeObjectIdentityRepository(transactions=[self.transaction])
        service = ObjectDedupDecisionService(object_identity_repository=repo)

        decision = service.decide_bank_transaction_import(
            {
                "account_no": "62220001",
                "trade_time": "2026-03-23 09:15:01",
                "txn_direction": "outflow",
                "amount": "88.00",
                "counterparty_name": "Acme",
            }
        )

        self.assertEqual(decision.decision, ImportDecision.SUSPECTED_DUPLICATE)
        self.assertEqual(repo.bank_queries, [(None, self.transaction.data_fingerprint)])


if __name__ == "__main__":
    unittest.main()
