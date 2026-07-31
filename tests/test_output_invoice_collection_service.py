from __future__ import annotations

from decimal import Decimal
import unittest
from typing import Any

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.output_invoice_collection_canonical_query_service import (
    OutputInvoiceCollectionCanonicalQueryService,
)
from fin_ops_platform.services.output_invoice_collection_service import (
    OutputInvoiceCollectionError,
    OutputInvoiceCollectionQueryService,
)
from fin_ops_platform.services.workbench_relation_modes import (
    OUTPUT_INVOICE_REVERSAL_RELATION_MODE,
)


class FakeOutputRelationFacade:
    def __init__(self, relations: list[dict[str, Any]]) -> None:
        self._relations = relations

    def get_by_row_ids(
        self,
        row_ids: list[str],
        **_kwargs: Any,
    ) -> dict[str, Any]:
        wanted = set(row_ids)
        return self._payload(
            [
                relation
                for relation in self._relations
                if wanted.intersection(relation["row_ids"])
            ]
        )

    def list_by_month(self, _month: str, **_kwargs: Any) -> dict[str, Any]:
        return self._payload(self._relations)

    @staticmethod
    def _payload(relations: list[dict[str, Any]]) -> dict[str, Any]:
        groups: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        for relation in relations:
            case_id = relation["case_id"]
            row_ids = list(relation["row_ids"])
            row_types = list(relation["row_types"])
            payload = {
                "case_id": case_id,
                "row_ids": row_ids,
                "row_types": row_types,
                "relation_status": "linked",
                "relation_mode": relation.get("relation_mode", "manual_confirmed"),
                "amount_check": dict(relation.get("amount_check") or {}),
                "special_metadata": dict(relation.get("special_metadata") or {}),
            }
            groups.append(
                {
                    "group_id": case_id,
                    "scope_month": "2026-05",
                    "oa_row_ids": [],
                    "bank_transaction_ids": [
                        row_id
                        for row_id, row_type in zip(row_ids, row_types)
                        if row_type == "bank"
                    ],
                    "input_invoice_ids": [],
                    "output_invoice_ids": [
                        row_id
                        for row_id, row_type in zip(row_ids, row_types)
                        if row_type == "invoice"
                    ],
                    "payload": payload,
                }
            )
            rows.extend(
                {
                    "row_id": row_id,
                    "row_type": row_type,
                    "relation_status": "linked",
                    "group_ids": [case_id],
                }
                for row_id, row_type in zip(row_ids, row_types)
            )
        return {
            "status": "fresh",
            "rows": rows,
            "groups": groups,
            "source_versions": {},
            "read_model_scope_keys": [],
        }


class OutputInvoiceCollectionQueryServiceTests(unittest.TestCase):
    def test_rows_expose_only_canonical_invoice_status_bank_and_invoice_relations(self) -> None:
        row = self._service(
            invoices=[self._invoice("blue", "1001", total_with_tax="100.00")]
        ).list_rows()["rows"][0]

        self.assertEqual(
            set(row),
            {
                "id",
                "invoiceId",
                "invoiceIdentityKey",
                "invoice",
                "collectionStatus",
                "bankTransactions",
                "invoiceRelations",
            },
        )
        self.assertEqual(row["collectionStatus"]["code"], "pending_collection")
        self.assertNotIn("oa", row)
        self.assertNotIn("receipt", row)
        self.assertNotIn("redInvoiceRelation", row)

    def test_collection_status_counts_only_linked_income_transactions(self) -> None:
        invoices = [
            self._invoice("paid", "1001", total_with_tax="100.00"),
            self._invoice("partial", "1002", total_with_tax="100.00"),
            self._invoice("pending", "1003", total_with_tax="100.00"),
        ]
        banks = [
            self._bank("income-paid", "100.00", TransactionDirection.INFLOW),
            self._bank("income-partial", "40.00", TransactionDirection.INFLOW),
            self._bank("outflow", "100.00", TransactionDirection.OUTFLOW),
        ]
        service = self._service(
            invoices=invoices,
            transactions=banks,
            relations=[
                self._relation("case-paid", ["paid", "income-paid"], ["invoice", "bank"]),
                self._relation(
                    "case-partial",
                    ["partial", "income-partial"],
                    ["invoice", "bank"],
                    matched=False,
                ),
                self._relation("case-outflow", ["pending", "outflow"], ["invoice", "bank"]),
            ],
        )

        rows = {row["invoiceId"]: row for row in service.list_rows()["rows"]}

        self.assertEqual(rows["paid"]["collectionStatus"]["code"], "collected")
        self.assertEqual(rows["partial"]["collectionStatus"]["code"], "partial_collected")
        self.assertEqual(rows["partial"]["collectionStatus"]["collectedAmount"], "40.00")
        self.assertEqual(rows["partial"]["collectionStatus"]["pendingAmount"], "60.00")
        self.assertEqual(rows["pending"]["collectionStatus"]["code"], "pending_collection")
        self.assertEqual(rows["pending"]["bankTransactions"]["receivedTotal"], "0.00")

    def test_exact_reversal_relation_drives_blue_red_and_unmatched_red_statuses(self) -> None:
        blue = self._invoice("blue", "2001", total_with_tax="100.00")
        red = self._invoice(
            "red",
            "2002",
            amount="-94.34",
            tax_amount="-5.66",
            total_with_tax="-100.00",
            is_positive_invoice="否",
            invoice_date="2026-05-21",
        )
        unmatched_red = self._invoice(
            "red-unmatched",
            "2003",
            amount="-47.17",
            tax_amount="-2.83",
            total_with_tax="-50.00",
            is_positive_invoice="否",
            invoice_date="2026-05-22",
        )
        service = self._service(
            invoices=[blue, red, unmatched_red],
            relations=[
                self._relation(
                    "reversal-blue-red",
                    ["blue", "red"],
                    ["invoice", "invoice"],
                    relation_mode=OUTPUT_INVOICE_REVERSAL_RELATION_MODE,
                )
            ],
        )

        rows = {row["invoiceId"]: row for row in service.list_rows()["rows"]}

        self.assertEqual(rows["blue"]["collectionStatus"]["code"], "reversed_by_red")
        self.assertEqual(rows["red"]["collectionStatus"]["code"], "reverses_blue")
        self.assertEqual(
            rows["red-unmatched"]["collectionStatus"]["code"],
            "unmatched_red",
        )
        self.assertEqual(
            {item["invoiceId"] for item in rows["blue"]["invoiceRelations"]["summaries"]},
            {"blue", "red"},
        )
        self.assertTrue(
            all(
                item["relationMode"] == OUTPUT_INVOICE_REVERSAL_RELATION_MODE
                for item in rows["blue"]["invoiceRelations"]["summaries"]
            )
        )

    def test_filter_sort_paging_and_export_use_current_contract(self) -> None:
        service = self._service(
            invoices=[
                self._invoice("a", "3001", buyer_name="甲客户", total_with_tax="30.00"),
                self._invoice("b", "3002", buyer_name="乙客户", total_with_tax="10.00"),
                self._invoice("c", "3003", buyer_name="甲客户", total_with_tax="20.00"),
            ]
        )

        payload = service.list_rows(
            page=1,
            page_size=1,
            filters='[{"field":"buyer_name","operator":"in","values":["甲客户"]}]',
            sort_field="total_with_tax",
            sort_direction="desc",
        )
        options = service.filter_options()
        preview = service.export_preview()

        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 1, "total": 2})
        self.assertEqual(payload["rows"][0]["invoiceId"], "a")
        fields = {field["field"] for field in options["fields"]}
        self.assertIn("collection_status", fields)
        self.assertNotIn("receipt_status", fields)
        self.assertNotIn("oa_status", fields)
        self.assertIn("红蓝票关系", preview["columns"])
        self.assertFalse(any("收据" in column or "OA" in column for column in preview["columns"]))

    def test_relation_details_allow_only_bank_and_invoice(self) -> None:
        invoice = self._invoice("invoice", "4001", total_with_tax="100.00")
        bank = self._bank("bank", "100.00", TransactionDirection.INFLOW)
        assembler = self._service(
            invoices=[invoice],
            transactions=[bank],
            relations=[self._relation("case", ["invoice", "bank"], ["invoice", "bank"])],
        )
        canonical = OutputInvoiceCollectionCanonicalQueryService(
            repository=None,
            row_assembler=assembler,
        )
        row_id = assembler.list_rows()["rows"][0]["id"]

        bank_details = canonical.relation_details(row_id, {"kind": ["bank"]})
        invoice_details = canonical.relation_details(row_id, {"kind": ["invoice"]})

        self.assertEqual(bank_details["relationCount"], 1)
        self.assertEqual(invoice_details["relationCount"], 1)
        with self.assertRaises(OutputInvoiceCollectionError) as context:
            canonical.relation_details(row_id, {"kind": ["oa"]})
        self.assertEqual(context.exception.error_code, "invalid_relation_kind")

    def test_page_size_is_bounded(self) -> None:
        service = self._service(invoices=[])

        with self.assertRaises(OutputInvoiceCollectionError) as context:
            service.list_rows(page_size=201)

        self.assertEqual(context.exception.error_code, "invalid_paging")

    @classmethod
    def _service(
        cls,
        *,
        invoices: list[Invoice],
        transactions: list[BankTransaction] | None = None,
        relations: list[dict[str, Any]] | None = None,
    ) -> OutputInvoiceCollectionQueryService:
        return OutputInvoiceCollectionQueryService(
            import_service=ImportNormalizationService(
                existing_invoices=invoices,
                existing_transactions=transactions or [],
            ),
            relation_facade=FakeOutputRelationFacade(relations or []),
        )

    @staticmethod
    def _relation(
        case_id: str,
        row_ids: list[str],
        row_types: list[str],
        *,
        matched: bool = True,
        relation_mode: str = "manual_confirmed",
    ) -> dict[str, Any]:
        return {
            "case_id": case_id,
            "row_ids": row_ids,
            "row_types": row_types,
            "relation_mode": relation_mode,
            "amount_check": {"matched": matched},
        }

    @staticmethod
    def _invoice(
        invoice_id: str,
        invoice_no: str,
        *,
        buyer_name: str = "测试客户",
        amount: str = "94.34",
        tax_amount: str = "5.66",
        total_with_tax: str = "100.00",
        invoice_date: str = "2026-05-20",
        is_positive_invoice: str = "是",
    ) -> Invoice:
        buyer = Counterparty(
            id=f"buyer-{invoice_id}",
            name=buyer_name,
            normalized_name=buyer_name,
            counterparty_type="customer",
            tax_no="91530000BUYER",
        )
        return Invoice(
            id=invoice_id,
            invoice_type=InvoiceType.OUTPUT,
            invoice_no=invoice_no,
            counterparty=buyer,
            amount=Decimal(amount),
            signed_amount=Decimal(total_with_tax),
            invoice_date=invoice_date,
            seller_name="云南溯源科技有限公司",
            buyer_name=buyer_name,
            seller_tax_no="91530000SELLER",
            buyer_tax_no=buyer.tax_no,
            tax_rate="6%",
            tax_amount=Decimal(tax_amount),
            total_with_tax=Decimal(total_with_tax),
            taxable_item_name="服务费",
            is_positive_invoice=is_positive_invoice,
        )

    @staticmethod
    def _bank(
        transaction_id: str,
        amount: str,
        direction: TransactionDirection,
    ) -> BankTransaction:
        return BankTransaction(
            id=transaction_id,
            account_no="622200001234",
            txn_direction=direction,
            counterparty_name_raw="测试客户",
            amount=Decimal(amount),
            signed_amount=(
                Decimal(amount)
                if direction == TransactionDirection.INFLOW
                else -Decimal(amount)
            ),
            txn_date="2026-05-21",
            trade_time="2026-05-21 10:00:00",
            imported_bank_name="建设银行",
            imported_bank_last4="1234",
            summary="服务费",
        )
