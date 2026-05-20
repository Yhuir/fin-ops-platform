from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.pending_invoice_service import (
    PendingInvoiceApplicationService,
    PendingInvoiceError,
    PendingInvoiceQueryService,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class PendingInvoiceQueryServiceTests(unittest.TestCase):
    def test_expense_rows_use_input_invoices_and_keep_multiple_invoices_in_one_bank_row(self) -> None:
        vendor = self._counterparty("cp_vendor", "Vendor A")
        txn = self._bank_transaction("txn_expense", TransactionDirection.OUTFLOW, "Vendor A", "100.00")
        inv_1 = self._invoice("inv_input_1", InvoiceType.INPUT, "IN-001", vendor, seller_name="Vendor A")
        inv_2 = self._invoice("inv_input_2", InvoiceType.INPUT, "IN-002", vendor, seller_name="Vendor A")
        unrelated_output = self._invoice("inv_output_1", InvoiceType.OUTPUT, "OUT-001", vendor, buyer_name="Vendor A")
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case_input_1",
            row_ids=[txn.id, inv_1.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
            special_metadata={"applicant": "张三"},
        )
        pair_service.create_active_relation(
            case_id="case_input_2",
            row_ids=[txn.id, inv_2.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        pair_service.create_active_relation(
            case_id="case_output_ignored",
            row_ids=[txn.id, unrelated_output.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        service = self._query_service(
            transactions=[txn],
            invoices=[inv_1, inv_2, unrelated_output],
            pair_service=pair_service,
        )

        payload = service.list_rows(direction="expense", filter="all")

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["rows"][0]["id"], txn.id)
        self.assertEqual([invoice["id"] for invoice in payload["rows"][0]["invoices"]], ["inv_input_1", "inv_input_2"])
        self.assertEqual(payload["rows"][0]["oa_applicant"], "张三")
        self.assertFalse(payload["rows"][0]["can_create_invoice"])
        self.assertEqual(payload["rows"][0]["relation_case_ids"], ["case_input_1", "case_input_2"])

    def test_income_rows_use_output_invoices_and_missing_relation_has_dash_applicant(self) -> None:
        customer = self._counterparty("cp_customer", "Customer A")
        txn = self._bank_transaction("txn_income", TransactionDirection.INFLOW, "Customer A", "220.00")
        output_invoice = self._invoice("inv_output", InvoiceType.OUTPUT, "OUT-220", customer, buyer_name="Customer A")
        input_invoice = self._invoice("inv_input", InvoiceType.INPUT, "IN-220", customer, seller_name="Customer A")
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case_output",
            row_ids=[txn.id, output_invoice.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        pair_service.create_active_relation(
            case_id="case_input_ignored",
            row_ids=[txn.id, input_invoice.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        service = self._query_service(
            transactions=[txn],
            invoices=[output_invoice, input_invoice],
            pair_service=pair_service,
        )

        payload = service.list_rows(direction="income", filter="all")

        self.assertEqual([invoice["id"] for invoice in payload["rows"][0]["invoices"]], ["inv_output"])
        self.assertEqual(payload["rows"][0]["oa_applicant"], "—")

    def test_filter_rules_and_can_create_invoice_follow_pending_invoice_tag_groups(self) -> None:
        requires_txn = self._bank_transaction("txn_requires", TransactionDirection.OUTFLOW, "Vendor R", "10.00")
        statement_txn = self._bank_transaction("txn_statement", TransactionDirection.OUTFLOW, "Vendor S", "20.00")
        no_invoice_txn = self._bank_transaction("txn_no_invoice", TransactionDirection.OUTFLOW, "Vendor N", "30.00")
        unmapped_txn = self._bank_transaction("txn_unmapped", TransactionDirection.OUTFLOW, "Vendor U", "40.00")
        income_txn = self._bank_transaction("txn_income", TransactionDirection.INFLOW, "Customer", "50.00")
        category_service = BankTransactionCategoryService(
            categories={
                "txn_requires": {"category_code": "fee", "version": 1},
                "txn_statement": {"category_code": "salary", "version": 1},
                "txn_no_invoice": {"category_code": "bonus", "version": 1},
            }
        )
        service = self._query_service(
            transactions=[requires_txn, statement_txn, no_invoice_txn, unmapped_txn, income_txn],
            category_service=category_service,
            tag_groups={
                "requires_invoice": ["fee"],
                "bank_statement_as_invoice": ["salary"],
                "no_invoice_required": ["bonus"],
            },
        )

        requires_payload = service.list_rows(direction="expense", filter="requires_invoice")
        statement_payload = service.list_rows(direction="expense", filter="bank_statement_as_invoice")
        no_invoice_payload = service.list_rows(direction="expense", filter="no_invoice_required")
        all_payload = service.list_rows(direction="expense", filter="all")
        income_payload = service.list_rows(direction="income", filter="all")

        self.assertEqual([row["id"] for row in requires_payload["rows"]], ["txn_requires"])
        self.assertTrue(requires_payload["rows"][0]["can_create_invoice"])
        self.assertEqual([row["id"] for row in statement_payload["rows"]], ["txn_statement"])
        self.assertTrue(statement_payload["rows"][0]["can_create_invoice"])
        self.assertEqual([row["id"] for row in no_invoice_payload["rows"]], ["txn_no_invoice"])
        self.assertFalse(no_invoice_payload["rows"][0]["can_create_invoice"])
        self.assertEqual(
            {row["id"]: row["can_create_invoice"] for row in all_payload["rows"]},
            {
                "txn_requires": True,
                "txn_statement": True,
                "txn_no_invoice": False,
                "txn_unmapped": True,
            },
        )
        self.assertEqual(income_payload["rows"][0]["id"], "txn_income")
        self.assertTrue(income_payload["rows"][0]["can_create_invoice"])

    def test_filter_rules_use_effective_auto_categories(self) -> None:
        auto_no_invoice_txn = self._bank_transaction(
            "txn_auto_no_invoice",
            TransactionDirection.OUTFLOW,
            "Tax Bureau",
            "30.00",
        )

        class EffectiveProvider:
            def bulk_get_for_rows(self, rows: list[BankTransaction]) -> dict[str, dict[str, object]]:
                return {
                    row.id: {
                        "category_code": "tax_payment",
                        "category_label": "税款支出",
                        "category_source": "auto",
                    }
                    for row in rows
                }

        service = self._query_service(
            transactions=[auto_no_invoice_txn],
            effective_category_provider=EffectiveProvider(),
            tag_groups={"no_invoice_required": ["tax_payment"]},
        )

        payload = service.list_rows(direction="expense", filter="no_invoice_required")

        self.assertEqual([row["id"] for row in payload["rows"]], ["txn_auto_no_invoice"])
        self.assertFalse(payload["rows"][0]["can_create_invoice"])
        self.assertEqual(payload["rows"][0]["bank_transaction"]["effective_tag_code"], "tax_payment")

    def test_income_rejects_expense_only_filters(self) -> None:
        service = self._query_service(transactions=[])

        with self.assertRaises(PendingInvoiceError) as context:
            service.list_rows(direction="income", filter="requires_invoice")

        self.assertEqual(context.exception.error_code, "invalid_filter_for_income")

    @staticmethod
    def _counterparty(counterparty_id: str, name: str) -> Counterparty:
        return Counterparty(id=counterparty_id, name=name, normalized_name=name.lower(), counterparty_type="unknown")

    @classmethod
    def _bank_transaction(
        cls,
        transaction_id: str,
        direction: TransactionDirection,
        counterparty_name: str,
        amount: str,
    ) -> BankTransaction:
        signed = Decimal(amount) if direction == TransactionDirection.INFLOW else -Decimal(amount)
        return BankTransaction(
            id=transaction_id,
            account_no="622200001234",
            txn_direction=direction,
            counterparty_name_raw=counterparty_name,
            amount=Decimal(amount),
            signed_amount=signed,
            txn_date="2026-05-20",
            trade_time="2026-05-20 10:00:00",
            imported_bank_name="工商银行",
            imported_bank_last4="1234",
        )

    @classmethod
    def _invoice(
        cls,
        invoice_id: str,
        invoice_type: InvoiceType,
        invoice_no: str,
        counterparty: Counterparty,
        *,
        seller_name: str | None = None,
        buyer_name: str | None = None,
    ) -> Invoice:
        return Invoice(
            id=invoice_id,
            invoice_type=invoice_type,
            invoice_no=invoice_no,
            counterparty=counterparty,
            amount=Decimal("100.00"),
            signed_amount=Decimal("100.00"),
            invoice_date="2026-05-20",
            total_with_tax=Decimal("100.00"),
            seller_name=seller_name,
            buyer_name=buyer_name,
        )

    @staticmethod
    def _query_service(
        *,
        transactions: list[BankTransaction],
        invoices: list[Invoice] | None = None,
        pair_service: WorkbenchPairRelationService | None = None,
        category_service: BankTransactionCategoryService | None = None,
        effective_category_provider: object | None = None,
        tag_groups: dict[str, list[str]] | None = None,
    ) -> PendingInvoiceQueryService:
        import_service = ImportNormalizationService(
            existing_transactions=transactions,
            existing_invoices=invoices or [],
        )
        settings_payload = {
            "bank_transaction_tags": category_service.tag_dictionary_payload()
            if category_service is not None
            else BankTransactionCategoryService().tag_dictionary_payload(),
            "pending_invoice_tag_groups": {
                "version": 1,
                "groups": {
                    "requires_invoice": {"tag_codes": list((tag_groups or {}).get("requires_invoice") or [])},
                    "bank_statement_as_invoice": {
                        "tag_codes": list((tag_groups or {}).get("bank_statement_as_invoice") or [])
                    },
                    "no_invoice_required": {"tag_codes": list((tag_groups or {}).get("no_invoice_required") or [])},
                },
            },
        }
        return PendingInvoiceQueryService(
            import_service=import_service,
            pair_relation_service=pair_service or WorkbenchPairRelationService(),
            category_service=category_service or BankTransactionCategoryService(),
            app_settings_provider=lambda: settings_payload,
            effective_category_provider=effective_category_provider,
        )


class PendingInvoiceApplicationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.vendor = Counterparty(id="cp_vendor", name="Vendor A", normalized_name="vendor a", counterparty_type="vendor")
        self.expense_txn = BankTransaction(
            id="txn_expense",
            account_no="622200001234",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="Vendor A",
            amount=Decimal("118.00"),
            signed_amount=Decimal("-118.00"),
            txn_date="2026-05-20",
            trade_time="2026-05-20 10:00:00",
        )
        self.import_service = ImportNormalizationService(existing_transactions=[self.expense_txn])
        self.pair_service = WorkbenchPairRelationService()
        self.audit_events: list[dict[str, object]] = []
        self.finalize_events: list[dict[str, object]] = []
        self.command_store: dict[str, dict[str, object]] = {}
        self.service = PendingInvoiceApplicationService(
            import_service=self.import_service,
            pair_relation_service=self.pair_service,
            command_store=self.command_store,
            audit_recorder=self.audit_events.append,
            finalizer=self.finalize_events.append,
        )

    def test_preview_validates_without_writes_and_returns_identity_relation_impact(self) -> None:
        preview = self.service.preview_manual_invoice(self._payload())

        self.assertTrue(preview["preview_id"].startswith("pending_invoice_preview_"))
        self.assertEqual(preview["target_invoice_type"], "input")
        self.assertEqual(preview["bank_transaction_summary"]["id"], "txn_expense")
        self.assertEqual(preview["duplicate_check"]["status"], "clear")
        self.assertEqual(preview["relation_impact"]["relation_mode"], "pending_invoice_manual_invoice")
        self.assertEqual(preview["relation_impact"]["affected_months"], ["2026-05"])
        self.assertEqual(self.import_service.list_invoices(), [])
        self.assertEqual(self.pair_service.list_active_relations(), [])

    def test_confirm_creates_canonical_invoice_relation_audit_and_finalization(self) -> None:
        preview = self.service.preview_manual_invoice(self._payload())

        result = self.service.confirm_manual_invoice(
            {**self._payload(), "preview_id": preview["preview_id"], "request_id": "request-001"},
            actor_id="finance-user",
        )

        invoice = self.import_service.get_invoice(result["invoice_id"])
        self.assertEqual(invoice.invoice_type, InvoiceType.INPUT)
        self.assertEqual(invoice.source_links[0]["source_type"], "manual_invoice_import")
        self.assertEqual(invoice.source_links[0]["request_key"], preview["request_key"])
        relation = self.pair_service.get_active_relation_by_case_id(result["relation_case_id"])
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "pending_invoice_manual_invoice")
        self.assertEqual(relation["row_types"], ["bank", "invoice"])
        self.assertEqual(self.command_store["request-001"]["status"], "completed")
        self.assertEqual(self.audit_events[0]["actor_id"], "finance-user")
        self.assertEqual(self.audit_events[0]["invoice_id"], result["invoice_id"])
        self.assertEqual(self.finalize_events[0]["affected_months"], ["2026-05"])

    def test_confirm_allows_existing_bank_oa_relation_when_creating_invoice_relation(self) -> None:
        self.pair_service.create_active_relation(
            case_id="case_existing_oa_bank",
            row_ids=["oa_001", self.expense_txn.id],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="tester",
            special_metadata={"applicant": "张三"},
        )
        preview = self.service.preview_manual_invoice(self._payload(invoice_no="MAN-OA"))

        result = self.service.confirm_manual_invoice(
            {**self._payload(invoice_no="MAN-OA"), "preview_id": preview["preview_id"], "request_id": "request-oa-bank"},
            actor_id="finance-user",
        )

        relation_modes = {
            relation["relation_mode"]
            for relation in self.pair_service.active_relations_for_row_ids([self.expense_txn.id])
        }
        self.assertIn("manual_confirmed", relation_modes)
        self.assertIn("pending_invoice_manual_invoice", relation_modes)
        self.assertEqual(self.command_store["request-oa-bank"]["relation_case_id"], result["relation_case_id"])

    def test_same_request_id_is_idempotent(self) -> None:
        preview = self.service.preview_manual_invoice(self._payload())
        request = {**self._payload(), "preview_id": preview["preview_id"], "request_id": "request-dup"}

        first = self.service.confirm_manual_invoice(request, actor_id="finance-user")
        second = self.service.confirm_manual_invoice(request, actor_id="finance-user")

        self.assertEqual(second, first)
        self.assertEqual(len(self.import_service.list_invoices()), 1)
        self.assertEqual(len(self.pair_service.list_active_relations()), 1)

    def test_retry_recovers_invoice_created_before_relation_created(self) -> None:
        preview = self.service.preview_manual_invoice(self._payload())
        failing = PendingInvoiceApplicationService(
            import_service=self.import_service,
            pair_relation_service=self.pair_service,
            command_store=self.command_store,
            fault_injector=lambda phase, _command: (_ for _ in ()).throw(RuntimeError("boom"))
            if phase == "after_invoice_created"
            else None,
        )
        request = {**self._payload(), "preview_id": preview["preview_id"], "request_id": "request-recover-invoice"}

        with self.assertRaises(RuntimeError):
            failing.confirm_manual_invoice(request, actor_id="finance-user")
        self.assertEqual(self.command_store["request-recover-invoice"]["status"], "failed_recoverable")
        self.assertEqual(self.command_store["request-recover-invoice"]["last_successful_status"], "invoice_created")

        recovered = self.service.confirm_manual_invoice(request, actor_id="finance-user")

        self.assertEqual(self.command_store["request-recover-invoice"]["status"], "completed")
        self.assertEqual(recovered["invoice_id"], self.command_store["request-recover-invoice"]["invoice_id"])
        self.assertEqual(len(self.import_service.list_invoices()), 1)
        self.assertEqual(len(self.pair_service.list_active_relations()), 1)

    def test_retry_recovers_relation_created_before_finalization(self) -> None:
        preview = self.service.preview_manual_invoice(self._payload(invoice_no="MAN-REL"))
        failing = PendingInvoiceApplicationService(
            import_service=self.import_service,
            pair_relation_service=self.pair_service,
            command_store=self.command_store,
            fault_injector=lambda phase, _command: (_ for _ in ()).throw(RuntimeError("boom"))
            if phase == "after_relation_created"
            else None,
        )
        request = {**self._payload(invoice_no="MAN-REL"), "preview_id": preview["preview_id"], "request_id": "request-recover-relation"}

        with self.assertRaises(RuntimeError):
            failing.confirm_manual_invoice(request, actor_id="finance-user")
        self.assertEqual(self.command_store["request-recover-relation"]["status"], "failed_recoverable")
        self.assertEqual(self.command_store["request-recover-relation"]["last_successful_status"], "relation_created")

        recovered = self.service.confirm_manual_invoice(request, actor_id="finance-user")

        self.assertEqual(self.command_store["request-recover-relation"]["status"], "completed")
        self.assertEqual(len(self.import_service.list_invoices()), 1)
        self.assertEqual(len(self.pair_service.list_active_relations()), 1)
        self.assertEqual(recovered["relation_case_id"], self.command_store["request-recover-relation"]["relation_case_id"])

    def test_orphan_invoice_with_same_request_key_is_repaired_without_duplicate_invoice(self) -> None:
        payload = self._payload(invoice_no="MAN-ORPHAN")
        preview = self.service.preview_manual_invoice(payload)
        batch_preview = self.import_service.preview_import(
            batch_type=self.service.batch_type_for_direction("expense"),
            source_name="pending_invoice_manual_entry",
            imported_by="finance-user",
            rows=[self.service.invoice_import_row(payload, preview["request_key"])],
        )
        self.import_service.confirm_import(batch_preview.id)
        orphan_invoice_id = batch_preview.row_results[0].linked_object_id

        result = self.service.confirm_manual_invoice(
            {**payload, "preview_id": preview["preview_id"], "request_id": "request-orphan"},
            actor_id="finance-user",
        )

        self.assertEqual(result["invoice_id"], orphan_invoice_id)
        self.assertEqual(len(self.import_service.list_invoices()), 1)
        self.assertEqual(len(self.pair_service.list_active_relations()), 1)

    def test_duplicate_invoice_marks_command_failed_terminal(self) -> None:
        preview = self.service.preview_manual_invoice(self._payload(invoice_no="MAN-DUP"))
        request = {**self._payload(invoice_no="MAN-DUP"), "preview_id": preview["preview_id"], "request_id": "request-original"}
        self.service.confirm_manual_invoice(request, actor_id="finance-user")
        duplicate_preview = self.service.preview_manual_invoice(self._payload(invoice_no="MAN-DUP"))

        with self.assertRaises(PendingInvoiceError) as context:
            self.service.confirm_manual_invoice(
                {**self._payload(invoice_no="MAN-DUP"), "preview_id": duplicate_preview["preview_id"], "request_id": "request-duplicate"},
                actor_id="finance-user",
            )

        self.assertEqual(context.exception.error_code, "duplicate_invoice")
        self.assertEqual(self.command_store["request-duplicate"]["status"], "failed_terminal")
        self.assertEqual(
            sorted({status for command in self.command_store.values() for status in command["status_history"]}),
            ["completed", "failed_terminal", "invoice_created", "relation_created", "started"],
        )

    def _payload(self, *, invoice_no: str = "MAN-001") -> dict[str, object]:
        return {
            "bank_transaction_id": "txn_expense",
            "invoice_no": invoice_no,
            "issue_date": "2026-05-20",
            "total_with_tax": "118.00",
            "tax_amount": "6.68",
            "seller_name": "Vendor A",
            "buyer_name": "云南溯源科技有限公司",
        }


if __name__ == "__main__":
    unittest.main()
