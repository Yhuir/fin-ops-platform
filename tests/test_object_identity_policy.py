from __future__ import annotations

import unittest
from decimal import Decimal

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy


class FinancialObjectIdentityPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = FinancialObjectIdentityPolicy()

    def test_invoice_canonical_priority_and_suspected_key(self) -> None:
        digital = self.policy.identify_invoice_mapping(
            {
                "digital_invoice_no": "26372000000990000001",
                "invoice_code": "033001",
                "invoice_no": "9001",
            }
        )
        code_no = self.policy.identify_invoice_mapping({"invoice_code": "033001", "invoice_no": "9001"})
        tax_amount = self.policy.identify_invoice_mapping(
            {
                "seller_tax_no": "SELLER-TAX",
                "buyer_tax_no": "BUYER-TAX",
                "invoice_date": "2026-03-21",
                "total_with_tax": "100.00",
            }
        )
        suspected = self.policy.identify_invoice_mapping(
            {
                "seller_name": "云南省交通投资建设集团有限公司",
                "buyer_name": "云南溯源科技有限公司",
                "invoice_date": "2026-03-21",
                "total_with_tax": "100.00",
            }
        )

        self.assertEqual(digital.canonical_key, "26372000000990000001")
        self.assertEqual(digital.canonical_key_kind, "digital_invoice_no")
        self.assertEqual(code_no.canonical_key, "033001:9001")
        self.assertEqual(code_no.canonical_key_kind, "invoice_code_no")
        self.assertEqual(tax_amount.canonical_key, "tax:SELLER-TAX:BUYER-TAX:2026-03-21:100.00")
        self.assertEqual(tax_amount.canonical_key_kind, "tax_amount_fingerprint")
        self.assertIsNone(suspected.canonical_key)
        self.assertEqual(suspected.suspected_key, "suspected:云南省交通投资建设集团有限公司:云南溯源科技有限公司:2026-03-21:100.00")

    def test_invoice_placeholder_numbers_are_not_canonical_identity(self) -> None:
        identity = self.policy.identify_invoice_mapping(
            {
                "digital_invoice_no": "—",
                "invoice_code": "--",
                "invoice_no": "-",
            }
        )

        self.assertIsNone(identity.canonical_key)
        self.assertIsNone(identity.canonical_key_kind)
        self.assertEqual(identity.confidence, "missing")

    def test_invoice_import_counterparty_amount_fingerprint_is_centralized_weak_key(self) -> None:
        identity = self.policy.identify_invoice_mapping(
            {
                "counterparty_name": " Acme Supplies ",
                "invoice_date": "2026-03-22",
                "amount": "66.00",
            }
        )

        self.assertIsNone(identity.canonical_key)
        self.assertEqual(identity.suspected_key, "invoice:acme supplies:2026-03-22:66.00")
        self.assertEqual(identity.audit_fields["suspected_key_kind"], "legacy_counterparty_amount")

    def test_bank_transaction_identity_uses_account_scoped_official_serial(self) -> None:
        first = self.policy.identify_bank_transaction_mapping(
            {
                "account_no": "62220001",
                "trade_time": "2026-03-23 09:15:01",
                "txn_direction": "outflow",
                "amount": "88.00",
                "counterparty_name": "Acme Supplies",
                "bank_serial_no": "SERIAL-SAME",
            }
        )
        second = self.policy.identify_bank_transaction_mapping(
            {
                "account_no": "62220002",
                "trade_time": "2026-03-23 09:15:01",
                "txn_direction": "outflow",
                "amount": "88.00",
                "counterparty_name": "Acme Supplies",
                "bank_serial_no": "SERIAL-SAME",
            }
        )

        self.assertEqual(first.canonical_key_kind, "bank_serial_no")
        self.assertTrue(first.canonical_key.startswith("bank-v3:62220001:bank_serial_no:SERIAL-SAME:"))
        self.assertNotEqual(first.canonical_key, second.canonical_key)

    def test_oa_attachment_invoice_identity_preserves_existing_stable_hash(self) -> None:
        attachment = {
            "source_attachment_key": "att-001",
            "source_expense_item_id": "item-001",
            "digital_invoice_no": "26372000000990000001",
            "seller_tax_no": "SELLER-TAX",
            "buyer_tax_no": "BUYER-TAX",
            "total_with_tax": "126.00",
        }

        identity = self.policy.identify_oa_attachment_invoice(attachment)

        self.assertEqual(identity.canonical_key, "26372000000990000001")
        self.assertEqual(identity.canonical_key_kind, "digital_invoice_no")
        self.assertEqual(len(self.policy.oa_attachment_invoice_stable_identity(attachment)), 16)
        self.assertEqual(len(self.policy.oa_attachment_invoice_candidate_identity(attachment)), 16)
        self.assertEqual(
            self.policy.oa_attachment_invoice_row_id("oa-exp-001", 0, attachment),
            f"oa-att-inv-oa-exp-001-{self.policy.oa_attachment_invoice_stable_identity(attachment)}",
        )
        self.assertEqual(
            self.policy.oa_attachment_invoice_row_id("oa-exp-001", 2, None),
            "oa-att-inv-oa-exp-001-03",
        )

    def test_oa_attachment_invoice_weak_tax_amount_key_is_only_suspected(self) -> None:
        attachment = {
            "source_attachment_key": "att-001",
            "seller_tax_no": "91530111MA6KHWY107",
            "buyer_tax_no": "915300007194052520",
            "seller_name": "云南滇约出行科技有限公司",
            "buyer_name": "云南溯源科技有限公司",
            "issue_date": "2026-01-12",
            "total_with_tax": "45.00",
            "passenger_name": "吴云江",
            "travel_date": "2026-01-09",
        }

        identity = self.policy.identify_oa_attachment_invoice(attachment)

        self.assertNotEqual(identity.canonical_key, "tax:91530111MA6KHWY107:915300007194052520:2026-01-12:45.00")
        self.assertEqual(identity.canonical_key_kind, "oa_attachment_stable_hash")
        self.assertEqual(identity.suspected_key, "tax:91530111MA6KHWY107:915300007194052520:2026-01-12:45.00")
        self.assertEqual(
            identity.audit_fields["weak_invoice_identity"],
            "tax:91530111MA6KHWY107:915300007194052520:2026-01-12:45.00",
        )

    def test_oa_attachment_invoice_dedupe_keys_keep_legacy_priority_inside_policy(self) -> None:
        digital = {
            "source_attachment_key": "att-001",
            "digital_invoice_no": "26372000000990000001",
            "invoice_code": "053002200111",
            "invoice_no": "40512344",
            "seller_name": "云南顺丰速运有限公司",
            "issue_date": "2026-03-22",
            "total_with_tax": "12.00",
        }
        fallback_only = {
            "source_attachment_key": "att-002",
            "source_region_key": "region-1",
            "document_kind": "云南增值税电子普通发票",
            "seller_name": "云南顺丰速运有限公司",
            "issue_date": "2026-03-22",
            "amount": "12.00",
        }

        digital_keys = self.policy.oa_attachment_invoice_dedupe_keys(digital)
        fallback_keys = self.policy.oa_attachment_invoice_dedupe_keys(fallback_only)

        self.assertEqual(digital_keys[0], ("invoice:digital_invoice_no", "26372000000990000001"))
        self.assertEqual(digital_keys[1], ("invoice:code_no", "053002200111:40512344"))
        self.assertIn("invoice:stable", {key_kind for key_kind, _value in digital_keys})
        self.assertEqual(fallback_keys[0][0], "invoice:fallback")
        self.assertIn("source_region_key", fallback_keys[0][1])
        self.assertIn("invoice:stable", {key_kind for key_kind, _value in fallback_keys})

    def test_oa_attachment_invoice_evidence_classification_is_centralized(self) -> None:
        self.assertTrue(self.policy.is_oa_attachment_invoice_evidence({"evidence_type": "tax_invoice"}))
        self.assertTrue(self.policy.is_oa_attachment_invoice_evidence({"evidence_type": "machine_invoice"}))
        self.assertFalse(self.policy.is_oa_attachment_invoice_evidence({"evidence_type": "non_tax_receipt"}))
        self.assertTrue(
            self.policy.is_oa_attachment_invoice_evidence(
                {
                    "document_kind": "digital_invoice",
                    "digital_invoice_no": "26372000000990000001",
                }
            )
        )
        self.assertTrue(
            self.policy.is_oa_attachment_invoice_evidence(
                {
                    "document_kind": "云南增值税电子普通发票",
                    "invoice_code": "053002200111",
                    "invoice_no": "40512344",
                }
            )
        )
        self.assertTrue(
            self.policy.is_oa_attachment_invoice_evidence(
                {
                    "invoice_type": "进项发票",
                    "invoice_no": "40512344",
                }
            )
        )
        self.assertFalse(self.policy.is_oa_attachment_invoice_evidence({"digital_invoice_no": "26372000000990000001"}))
        self.assertFalse(self.policy.is_oa_attachment_invoice_evidence({"invoice_code": "053002200111"}))
        self.assertFalse(
            self.policy.is_oa_attachment_invoice_evidence(
                {
                    "evidence_type": "payment_receipt",
                    "transaction_no": "4200003046202603030281812965",
                }
            )
        )
        self.assertFalse(self.policy.is_oa_attachment_invoice_evidence({"evidence_type": "unknown", "amount": "23.00"}))
        self.assertFalse(
            self.policy.is_oa_attachment_invoice_evidence({"evidence_type": "unknown", "invoice_no": "40512344"})
        )

    def test_tax_certified_unique_key_keeps_existing_shape_inside_policy(self) -> None:
        self.assertEqual(
            self.policy.tax_certified_unique_key(
                {
                    "digital_invoice_no": "25502000000145098656",
                    "invoice_code": "053002200111",
                    "invoice_no": "45098656",
                    "seller_tax_no": "91500226MA60KH3C0Q",
                    "issue_date": "2026-01-10",
                    "tax_amount": "10.00",
                }
            ),
            "digital:25502000000145098656",
        )
        self.assertEqual(
            self.policy.tax_certified_unique_key(
                {
                    "invoice_code": "053002200111",
                    "invoice_no": "45098656",
                    "seller_tax_no": "91500226MA60KH3C0Q",
                    "issue_date": "2026-01-10",
                    "tax_amount": "10.00",
                }
            ),
            "invoice:053002200111:45098656",
        )
        self.assertEqual(
            self.policy.tax_certified_unique_key(
                {
                    "seller_tax_no": "91500226MA60KH3C0Q",
                    "issue_date": "2026-01-10",
                    "tax_amount": "10",
                }
            ),
            "fallback:91500226MA60KH3C0Q:2026-01-10:10.00",
        )

    def test_legacy_invoice_identity_key_keeps_existing_response_shape(self) -> None:
        invoice = Invoice(
            id="inv-1",
            invoice_type=InvoiceType.OUTPUT,
            invoice_no="9001",
            invoice_code="033001",
            counterparty=Counterparty(id="cp-1", name="客户", normalized_name="客户", counterparty_type="customer"),
            amount=Decimal("100"),
            signed_amount=Decimal("100"),
        )
        digital_invoice = Invoice(
            id="inv-2",
            invoice_type=InvoiceType.INPUT,
            invoice_no="9002",
            digital_invoice_no="26372000000990000001",
            counterparty=Counterparty(id="cp-2", name="供应商", normalized_name="供应商", counterparty_type="vendor"),
            amount=Decimal("100"),
            signed_amount=Decimal("100"),
        )
        fallback = Invoice(
            id="inv-3",
            invoice_type=InvoiceType.INPUT,
            invoice_no="",
            counterparty=Counterparty(id="cp-3", name="供应商", normalized_name="供应商", counterparty_type="vendor"),
            amount=Decimal("100"),
            signed_amount=Decimal("100"),
            invoice_date="2026-03-22",
        )

        self.assertEqual(self.policy.legacy_invoice_identity_key(invoice), "code_no:033001:9001")
        self.assertEqual(self.policy.legacy_invoice_identity_key(digital_invoice), "digital:26372000000990000001")
        self.assertEqual(self.policy.legacy_invoice_identity_key(fallback), "id:inv-3")
        self.assertEqual(
            self.policy.identify_invoice(fallback).suspected_key,
            "invoice:供应商:2026-03-22:100.00",
        )

    def test_identify_existing_domain_objects(self) -> None:
        transaction = BankTransaction(
            id="txn-1",
            account_no="62220001",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="Acme Supplies",
            amount=Decimal("88.00"),
            signed_amount=Decimal("-88.00"),
            trade_time="2026-03-23 09:15:01",
        )

        identity = self.policy.identify_bank_transaction(transaction)

        self.assertIsNone(identity.canonical_key)
        self.assertEqual(identity.suspected_key, "bank:62220001:2026-03-23 09:15:01:outflow:88.00:acme supplies")
        self.assertEqual(identity.source_row_id, "txn-1")


if __name__ == "__main__":
    unittest.main()
