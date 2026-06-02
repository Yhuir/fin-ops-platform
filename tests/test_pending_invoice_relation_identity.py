from __future__ import annotations

import unittest

from fin_ops_platform.services.pending_invoice_relation_identity import pending_invoice_relation_identity


class PendingInvoiceRelationIdentityTests(unittest.TestCase):
    def test_extracts_typed_real_oa_bank_invoice_ids_and_case_ids(self) -> None:
        identity = pending_invoice_relation_identity(
            [
                {
                    "case_id": "candidate:oa-bank-invoice",
                    "row_ids": ["oa-pay-2048", "txn-expense", "inv-input-1"],
                    "row_types": ["oa", "bank", "invoice"],
                }
            ]
        )

        self.assertEqual(identity.oa_row_ids, ["oa-pay-2048"])
        self.assertEqual(identity.bank_transaction_ids, ["txn-expense"])
        self.assertEqual(identity.invoice_ids, ["inv-input-1"])
        self.assertEqual(identity.relation_case_ids, ["candidate:oa-bank-invoice"])

    def test_rejects_candidate_ids_as_oa_row_identity(self) -> None:
        identity = pending_invoice_relation_identity(
            [
                {
                    "case_id": "case-real",
                    "row_ids": ["candidate:wrong-oa-id", "txn-expense"],
                    "row_types": ["oa", "bank"],
                }
            ]
        )

        self.assertEqual(identity.oa_row_ids, [])
        self.assertEqual(identity.bank_transaction_ids, ["txn-expense"])
        self.assertEqual(identity.invalid_oa_row_ids, ["candidate:wrong-oa-id"])

    def test_falls_back_to_prefixes_without_guessing_candidate_type(self) -> None:
        identity = pending_invoice_relation_identity(
            [
                {
                    "case_id": "candidate:prefix-fallback",
                    "row_ids": ["oa-pay-1", "txn-expense", "invoice-input-1", "candidate:not-a-row"],
                    "row_types": [],
                }
            ]
        )

        self.assertEqual(identity.oa_row_ids, ["oa-pay-1"])
        self.assertEqual(identity.bank_transaction_ids, ["txn-expense"])
        self.assertEqual(identity.invoice_ids, ["invoice-input-1"])
        self.assertNotIn("candidate:not-a-row", identity.oa_row_ids)


if __name__ == "__main__":
    unittest.main()
