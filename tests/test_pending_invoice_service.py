from __future__ import annotations

from decimal import Decimal
from typing import Callable
import unittest

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.pending_invoice_service import (
    InMemoryPendingInvoiceCommandRepository,
    PendingInvoiceApplicationService,
    PendingInvoiceError,
    PendingInvoiceQueryService,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class RepositoryOnlyPendingInvoiceFacts:
    def __init__(
        self,
        *,
        transactions: list[BankTransaction] | None = None,
        invoices: list[Invoice] | None = None,
    ) -> None:
        self.transactions = list(transactions or [])
        self.invoices = list(invoices or [])
        self.transaction_page_calls: list[dict[str, object]] = []
        self.invoice_page_calls: list[dict[str, object]] = []

    def list_bank_transactions_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        date_from: str | None = None,
        date_to: str | None = None,
        **_: object,
    ) -> tuple[list[BankTransaction], int]:
        self.transaction_page_calls.append({"page": page, "page_size": page_size, "date_from": date_from, "date_to": date_to})
        rows = [
            transaction
            for transaction in self.transactions
            if (not date_from or str(transaction.txn_date or "") >= date_from)
            and (not date_to or str(transaction.txn_date or "") <= date_to)
        ]
        start = (page - 1) * page_size
        return rows[start : start + page_size], len(rows)

    def list_invoices_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        month: str | None = None,
        invoice_type: str | None = None,
        **_: object,
    ) -> tuple[list[Invoice], int]:
        self.invoice_page_calls.append({"page": page, "page_size": page_size, "month": month, "invoice_type": invoice_type})
        rows = [
            invoice
            for invoice in self.invoices
            if (not month or str(invoice.invoice_date or "").startswith(str(month)[:7]))
            and (not invoice_type or invoice.invoice_type.value == invoice_type)
        ]
        start = (page - 1) * page_size
        return rows[start : start + page_size], len(rows)

    def get_transaction(self, transaction_id: str) -> BankTransaction | None:
        return next((transaction for transaction in self.transactions if transaction.id == transaction_id), None)

    def get_invoice(self, invoice_id: str) -> Invoice | None:
        return next((invoice for invoice in self.invoices if invoice.id == invoice_id), None)


class FakeOAProjection:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records_by_id = {record.id: record for record in records}
        self.requested_row_ids: list[list[str]] = []

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        normalized = [str(row_id).strip() for row_id in row_ids if str(row_id).strip()]
        self.requested_row_ids.append(normalized)
        return [self.records_by_id[row_id] for row_id in normalized if row_id in self.records_by_id]


class FakeWorkbenchRelationFacade:
    def __init__(self, rows: list[dict[str, object]], groups: list[dict[str, object]] | None = None) -> None:
        self.rows_by_id = {str(row.get("row_id")): row for row in rows}
        self.groups_by_id = {str(group.get("group_id")): group for group in list(groups or [])}
        self.calls: list[list[str]] = []

    @classmethod
    def from_pair_service(
        cls,
        *,
        pair_service: WorkbenchPairRelationService,
        transactions: list[BankTransaction],
        invoices: list[Invoice],
        oa_projection: FakeOAProjection | None = None,
    ) -> "FakeWorkbenchRelationFacade":
        transactions_by_id = {transaction.id: transaction for transaction in transactions}
        invoices_by_id = {invoice.id: invoice for invoice in invoices}
        rows_by_id: dict[str, dict[str, object]] = {}
        groups: list[dict[str, object]] = []
        oa_records = getattr(oa_projection, "records_by_id", {}) if oa_projection is not None else {}
        for relation in pair_service.list_active_relations():
            if not isinstance(relation, dict):
                continue
            case_id = str(relation.get("case_id") or "")
            row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
            row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
            linked_bank: list[dict[str, object]] = []
            linked_input: list[dict[str, object]] = []
            linked_output: list[dict[str, object]] = []
            linked_oa: list[dict[str, object]] = []
            metadata = relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {}
            groups.append(
                {
                    "group_id": case_id,
                    "payload": {
                        "group_id": case_id,
                        "row_ids": row_ids,
                        "row_types": row_types,
                        "relation_mode": str(relation.get("relation_mode") or "manual_confirmed"),
                        "special_metadata": dict(metadata),
                        "amount_check": dict(relation.get("amount_check") or {}) if isinstance(relation.get("amount_check"), dict) else {},
                    },
                    "oa_row_ids": [row_id for index, row_id in enumerate(row_ids) if index < len(row_types) and row_types[index] == "oa"],
                    "bank_transaction_ids": [row_id for index, row_id in enumerate(row_ids) if index < len(row_types) and row_types[index] == "bank"],
                    "input_invoice_ids": [
                        row_id
                        for index, row_id in enumerate(row_ids)
                        if index < len(row_types)
                        and row_types[index] == "invoice"
                        and row_id in invoices_by_id
                        and invoices_by_id[row_id].invoice_type == InvoiceType.INPUT
                    ],
                    "output_invoice_ids": [
                        row_id
                        for index, row_id in enumerate(row_ids)
                        if index < len(row_types)
                        and row_types[index] == "invoice"
                        and row_id in invoices_by_id
                        and invoices_by_id[row_id].invoice_type == InvoiceType.OUTPUT
                    ],
                }
            )
            for index, row_id in enumerate(row_ids):
                row_type = row_types[index] if index < len(row_types) else ""
                if row_type == "bank" and row_id in transactions_by_id:
                    transaction = transactions_by_id[row_id]
                    linked_bank.append(
                        {
                            "id": row_id,
                            "amount": f"{transaction.amount:.2f}",
                            "trade_time": transaction.trade_time or transaction.txn_date,
                            "counterparty_name": transaction.counterparty_name_raw,
                            "relation_case_id": case_id,
                        }
                    )
                elif row_type == "invoice" and row_id in invoices_by_id:
                    invoice = invoices_by_id[row_id]
                    invoice_payload = {
                        "id": row_id,
                        "invoice_no": invoice.invoice_no,
                        "digital_invoice_no": invoice.digital_invoice_no,
                        "issue_date": invoice.invoice_date,
                        "total_with_tax": f"{(invoice.total_with_tax if invoice.total_with_tax is not None else invoice.amount):.2f}",
                        "seller_name": invoice.seller_name,
                        "buyer_name": invoice.buyer_name,
                        "relation_case_id": case_id,
                    }
                    if invoice.invoice_type == InvoiceType.OUTPUT:
                        linked_output.append(invoice_payload)
                    else:
                        linked_input.append(invoice_payload)
                elif row_type == "oa":
                    record = oa_records.get(row_id) if isinstance(oa_records, dict) else None
                    linked_oa.append(
                        {
                            "id": row_id,
                            "applicant": getattr(record, "applicant", "") or str(metadata.get("applicant") or metadata.get("oa_applicant") or ""),
                            "application_type": getattr(record, "apply_type", "") or str(metadata.get("application_type") or ""),
                            "project_name": getattr(record, "project_name", "") or str(metadata.get("project_name") or ""),
                            "status": getattr(record, "section", "") or str(metadata.get("status") or ""),
                            "form_no": getattr(record, "case_id", "") or str(metadata.get("form_no") or ""),
                            "detail_available": record is not None,
                            "relation_case_id": case_id,
                        }
                    )
            for row_id in row_ids:
                row = rows_by_id.setdefault(
                    row_id,
                    {
                        "row_id": row_id,
                        "row_type": "bank_transaction",
                        "group_ids": [],
                        "linked_oa": [],
                        "linked_bank_transactions": [],
                        "linked_input_invoices": [],
                        "linked_output_invoices": [],
                    },
                )
                row["group_ids"] = [*list(row.get("group_ids") or []), case_id]
                row["linked_oa"] = [*list(row.get("linked_oa") or []), *linked_oa]
                row["linked_bank_transactions"] = [*list(row.get("linked_bank_transactions") or []), *linked_bank]
                row["linked_input_invoices"] = [*list(row.get("linked_input_invoices") or []), *linked_input]
                row["linked_output_invoices"] = [*list(row.get("linked_output_invoices") or []), *linked_output]
        return cls(list(rows_by_id.values()), groups=groups)

    def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
        normalized = [str(row_id).strip() for row_id in row_ids if str(row_id).strip()]
        self.calls.append(normalized)
        rows = [self.rows_by_id[row_id] for row_id in normalized if row_id in self.rows_by_id]
        group_ids: list[str] = []
        for row in rows:
            for group_id in list(row.get("group_ids") or []):
                group_text = str(group_id).strip()
                if group_text and group_text not in group_ids:
                    group_ids.append(group_text)
        groups = [
            self.groups_by_id[group_id]
            if group_id in self.groups_by_id
            else {
                "group_id": group_id,
                "payload": {
                    "group_id": group_id,
                    "row_ids": [],
                    "row_types": [],
                    "relation_mode": "manual_confirmed",
                },
                "oa_row_ids": [],
                "bank_transaction_ids": [],
                "input_invoice_ids": [],
                "output_invoice_ids": [],
            }
            for group_id in group_ids
        ]
        return {
            "status": "fresh",
            "rows": rows,
            "groups": groups,
            "source_versions": {"schema_version": 52},
            "read_model_scope_keys": ["2026-05"],
            "refresh_enqueued": False,
            "stale_reasons": [],
        }


class LiveWorkbenchRelationFacade:
    def __init__(
        self,
        *,
        pair_service: WorkbenchPairRelationService,
        import_service_provider: Callable[[], ImportNormalizationService],
    ) -> None:
        self._pair_service = pair_service
        self._import_service_provider = import_service_provider

    def get_by_row_ids(self, row_ids: list[str], **kwargs: object) -> dict[str, object]:
        import_service = self._import_service_provider()
        facade = FakeWorkbenchRelationFacade.from_pair_service(
            pair_service=self._pair_service,
            transactions=import_service.list_transactions(month="all"),
            invoices=import_service.list_invoices(),
        )
        return facade.get_by_row_ids(row_ids, **kwargs)


class PendingInvoiceQueryServiceTests(unittest.TestCase):
    def test_expense_rows_use_input_invoices_and_keep_multiple_invoices_in_one_bank_row(self) -> None:
        vendor = self._counterparty("cp_vendor", "Vendor A")
        txn = self._bank_transaction("txn_expense", TransactionDirection.OUTFLOW, "Vendor A", "100.00")
        inv_1 = self._invoice("inv_input_1", InvoiceType.INPUT, "IN-001", vendor, seller_name="Vendor A", total_with_tax="60.00")
        inv_2 = self._invoice("inv_input_2", InvoiceType.INPUT, "IN-002", vendor, seller_name="Vendor A", total_with_tax="40.00")
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
        self.assertEqual(payload["rows"][0]["invoice_acquisition_status"]["code"], "paid_invoiced")
        self.assertEqual(payload["rows"][0]["input_invoices"]["relation_count"], 2)
        self.assertEqual(payload["rows"][0]["input_invoices"]["primary"]["invoice_no"], "IN-001")
        self.assertTrue(payload["rows"][0]["input_invoices"]["has_multiple"])
        self.assertEqual(payload["rows"][0]["input_invoices"]["payment_summary"]["invoice_total"], "100.00")
        self.assertEqual(payload["rows"][0]["input_invoices"]["payment_summary"]["paid_total"], "100.00")
        self.assertEqual(payload["rows"][0]["oa"]["primary"]["applicant"], "张三")

    def test_oa_detail_uses_oa_projection_payment_application_layout(self) -> None:
        txn = self._bank_transaction("txn_expense", TransactionDirection.OUTFLOW, "重庆维诺安工程技术有限公司", "7680.00")
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case_oa_payment",
            row_ids=[txn.id, "oa-pay-2048"],
            row_types=["bank", "oa"],
            relation_mode="manual_confirmed",
            created_by="tester",
            special_metadata={"applicant": "旧元数据申请人", "project_name": "旧元数据项目"},
        )
        oa_projection = FakeOAProjection([
            OAApplicationRecord(
                id="oa-pay-2048",
                month="2026-05",
                section="已完成",
                case_id="2048",
                applicant="杨丽萍",
                project_name="大理卷烟厂余热综合利用项目",
                apply_type="支付申请",
                amount="7680.00",
                counterparty_name="重庆维诺安工程技术有限公司",
                reason="压力变送器尾款+底座、堵头4件",
                relation_code="pending_match",
                relation_label="待找流水与发票",
                relation_tone="warn",
                expense_type="设备贷款及材料费",
                detail_fields={
                    "申请日期": "2026-05-25",
                    "付款方式": "银行转账",
                    "票据类型": "增值税专用发票",
                    "开户行": "交通银行股份有限公司重庆人民路支行",
                    "收款账号": "500500037015003460594",
                    "审批记录": [
                        {
                            "title": "项目负责人审核",
                            "opinion": "同意",
                            "acted_at": "2026-05-25 14:51:04",
                            "actor": "刘涵静",
                            "signature": "刘涵静",
                        }
                    ],
                },
            )
        ])
        service = self._query_service(
            transactions=[txn],
            pair_service=pair_service,
            oa_projection=oa_projection,
        )

        rows_payload = service.list_rows(direction="expense", filter="all")
        detail_payload = service.oa_detail("oa-pay-2048")

        self.assertEqual(rows_payload["rows"][0]["oa"]["primary"]["applicant"], "杨丽萍")
        self.assertTrue(rows_payload["rows"][0]["oa"]["detail_available"])
        self.assertEqual(detail_payload["title"], "打印选择")
        self.assertTrue(detail_payload["detail_available"])
        self.assertEqual(detail_payload["oa_print_layout"]["form_title"], "支付申请")
        self.assertIn({"label": "申请人", "value": "杨丽萍"}, detail_payload["oa_print_layout"]["fields"])
        self.assertIn({"label": "项目名称", "value": "大理卷烟厂余热综合利用项目"}, detail_payload["oa_print_layout"]["fields"])
        self.assertEqual(detail_payload["oa_print_layout"]["approvals"][1]["title"], "项目负责人审核")
        self.assertEqual(detail_payload["oa_print_layout"]["approvals"][1]["signature"], "刘涵静")
        self.assertIn(["oa-pay-2048"], oa_projection.requested_row_ids)

    def test_oa_detail_rejects_candidate_relation_case_id(self) -> None:
        service = self._query_service(transactions=[])

        with self.assertRaises(PendingInvoiceError) as context:
            service.oa_detail("candidate:030404426078")

        self.assertEqual(context.exception.error_code, "invalid_oa_detail_id")

    def test_relation_detail_uses_workbench_relation_distribution_for_oa_attachment_invoices(self) -> None:
        vendor = self._counterparty("cp_vendor", "Vendor A")
        txn = self._bank_transaction("txn_expense", TransactionDirection.OUTFLOW, "Vendor A", "196.00")
        inv_1 = self._invoice("oa-att-inv-001", InvoiceType.INPUT, "ATT-001", vendor, seller_name="Vendor A", total_with_tax="70.00")
        inv_2 = self._invoice("oa-att-inv-002", InvoiceType.INPUT, "ATT-002", vendor, seller_name="Vendor A", total_with_tax="126.00")
        pair_service = WorkbenchPairRelationService()
        relation_facade = FakeWorkbenchRelationFacade([
            {
                "row_id": txn.id,
                "row_type": "bank_transaction",
                "group_ids": ["case_tmw_196"],
                "linked_oa": [
                    {
                        "id": "oa-tmw-196",
                        "applicant": "田孟维",
                        "project_name": "云南溯源科技",
                        "application_type": "日常报销",
                        "relation_case_id": "case_tmw_196",
                        "detail_available": True,
                    }
                ],
                "linked_bank_transactions": [
                    {"id": txn.id, "amount": "196.00", "direction": "outflow", "relation_case_id": "case_tmw_196"}
                ],
                "linked_input_invoices": [
                    {"id": inv_1.id, "invoice_no": "ATT-001", "seller_name": "Vendor A", "total_with_tax": "70.00", "relation_case_id": "case_tmw_196"},
                    {"id": inv_2.id, "invoice_no": "ATT-002", "seller_name": "Vendor A", "total_with_tax": "126.00", "relation_case_id": "case_tmw_196"},
                ],
                "linked_output_invoices": [],
            }
        ])
        service = self._query_service(
            transactions=[txn],
            invoices=[inv_1, inv_2],
            pair_service=pair_service,
            relation_facade=relation_facade,
        )

        detail = service.relation_detail(transaction_id=txn.id, direction="expense")

        self.assertEqual([invoice["id"] for invoice in detail["related_invoices"]], ["oa-att-inv-001", "oa-att-inv-002"])
        self.assertEqual([oa["id"] for oa in detail["related_oa"]], ["oa-tmw-196"])
        self.assertEqual(detail["relation_case_ids"], ["case_tmw_196"])
        self.assertIn([txn.id], relation_facade.calls)

    def test_oa_detail_uses_workbench_relation_distribution_case_id(self) -> None:
        relation_facade = FakeWorkbenchRelationFacade([
            {
                "row_id": "oa-pay-2048",
                "row_type": "oa",
                "group_ids": ["case_distributed_oa"],
                "linked_oa": [{"id": "oa-pay-2048", "relation_case_id": "case_distributed_oa"}],
                "linked_bank_transactions": [],
                "linked_input_invoices": [],
                "linked_output_invoices": [],
            }
        ])
        oa_projection = FakeOAProjection([
            OAApplicationRecord(
                id="oa-pay-2048",
                month="2026-05",
                section="已完成",
                case_id="2048",
                applicant="杨丽萍",
                project_name="大理项目",
                apply_type="支付申请",
                amount="7680.00",
                counterparty_name="Vendor A",
                reason="服务费",
                relation_code="pending_match",
                relation_label="待找流水与发票",
                relation_tone="warn",
            )
        ])
        service = self._query_service(
            transactions=[],
            pair_service=WorkbenchPairRelationService(),
            relation_facade=relation_facade,
            oa_projection=oa_projection,
        )

        detail_payload = service.oa_detail("oa-pay-2048")

        self.assertEqual(detail_payload["oa"]["relation_case_id"], "case_distributed_oa")
        self.assertIn(["oa-pay-2048"], relation_facade.calls)

    def test_rows_keep_candidate_case_id_separate_from_real_oa_id(self) -> None:
        vendor = self._counterparty("cp_vendor", "Vendor A")
        txn = self._bank_transaction("txn_expense", TransactionDirection.OUTFLOW, "Vendor A", "118.00")
        invoice = self._invoice("inv_input_1", InvoiceType.INPUT, "IN-001", vendor, seller_name="Vendor A", total_with_tax="118.00")
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="candidate:oa-bank-invoice",
            row_ids=["oa-pay-2048", txn.id, invoice.id],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        oa_projection = FakeOAProjection([
            OAApplicationRecord(
                id="oa-pay-2048",
                month="2026-05",
                section="已完成",
                case_id="2048",
                applicant="杨丽萍",
                project_name="大理项目",
                apply_type="支付申请",
                amount="118.00",
                counterparty_name="Vendor A",
                reason="服务费",
                relation_code="pending_match",
                relation_label="待找流水与发票",
                relation_tone="warn",
            )
        ])
        service = self._query_service(
            transactions=[txn],
            invoices=[invoice],
            pair_service=pair_service,
            oa_projection=oa_projection,
        )

        payload = service.list_rows(direction="expense", filter="all")
        row = payload["rows"][0]

        self.assertEqual(row["oa"]["primary"]["id"], "oa-pay-2048")
        self.assertEqual(row["oa"]["primary"]["relation_case_id"], "candidate:oa-bank-invoice")
        self.assertEqual(row["relation_case_ids"], ["candidate:oa-bank-invoice"])
        self.assertNotEqual(row["oa"]["primary"]["id"], row["relation_case_ids"][0])

    def test_income_relation_detail_uses_income_direction_and_output_invoices(self) -> None:
        customer = self._counterparty("cp_customer", "Customer A")
        txn = self._bank_transaction("txn_income", TransactionDirection.INFLOW, "Customer A", "118.00")
        output_invoice = self._invoice(
            "out_income_1",
            InvoiceType.OUTPUT,
            "OUT-001",
            customer,
            buyer_name="Customer A",
            total_with_tax="118.00",
        )
        ignored_input_invoice = self._invoice(
            "in_ignored",
            InvoiceType.INPUT,
            "IN-IGNORED",
            customer,
            seller_name="Vendor Ignored",
            total_with_tax="118.00",
        )
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case_income_output",
            row_ids=[txn.id, output_invoice.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        pair_service.create_active_relation(
            case_id="case_income_input_ignored",
            row_ids=[txn.id, ignored_input_invoice.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        service = self._query_service(
            transactions=[txn],
            invoices=[output_invoice, ignored_input_invoice],
            pair_service=pair_service,
        )

        detail = service.relation_detail(transaction_id=txn.id, direction="income")

        self.assertEqual(detail["transaction_summary"]["id"], txn.id)
        self.assertEqual([invoice["id"] for invoice in detail["related_invoices"]], ["out_income_1"])
        self.assertEqual(detail["relation_case_ids"], ["case_income_output"])
        self.assertEqual(detail["available_actions"], [])

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
        self.assertFalse(income_payload["rows"][0]["can_create_invoice"])

    def test_all_direction_combines_expense_and_income_rows(self) -> None:
        expense_txn = self._bank_transaction("txn_expense_all", TransactionDirection.OUTFLOW, "Vendor", "10.00")
        income_txn = self._bank_transaction("txn_income_all", TransactionDirection.INFLOW, "Customer", "20.00")
        service = self._query_service(transactions=[expense_txn, income_txn])

        payload = service.list_rows(direction="all", filter="all")

        self.assertEqual([row["id"] for row in payload["rows"]], ["txn_expense_all", "txn_income_all"])
        self.assertEqual(payload["summary"]["source_summary"]["current_direction_rows"], 2)
        self.assertEqual(payload["summary"]["source_summary"]["excluded_direction_rows"], 0)

    def test_income_statuses_use_output_invoices_rules_and_manual_override(self) -> None:
        customer = self._counterparty("cp_income_status", "Customer Status")
        invoiced_txn = self._bank_transaction("txn_income_invoiced", TransactionDirection.INFLOW, "Customer Status", "100.00")
        no_invoice_txn = self._bank_transaction("txn_income_no_invoice", TransactionDirection.INFLOW, "Customer No", "20.00")
        cash_txn = self._bank_transaction("txn_income_cash", TransactionDirection.INFLOW, "Customer Cash", "30.00")
        override_txn = self._bank_transaction("txn_income_override", TransactionDirection.INFLOW, "Customer Override", "40.00")
        pending_txn = self._bank_transaction("txn_income_pending", TransactionDirection.INFLOW, "Customer Pending", "50.00")
        output_invoice = self._invoice("inv_income_status", InvoiceType.OUTPUT, "OUT-STATUS", customer, buyer_name="Customer Status")
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case_income_status",
            row_ids=[invoiced_txn.id, output_invoice.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        category_service = BankTransactionCategoryService(
            categories={
                no_invoice_txn.id: {"category_code": "salary", "version": 1},
                cash_txn.id: {"category_code": "fee", "version": 1},
            }
        )
        service = self._query_service(
            transactions=[invoiced_txn, no_invoice_txn, cash_txn, override_txn, pending_txn],
            invoices=[output_invoice],
            pair_service=pair_service,
            category_service=category_service,
            income_tag_groups={"no_invoice_required": ["salary"], "cash_income": ["fee"]},
            income_status_override_provider=lambda transaction_id: (
                {"status_code": "income_no_invoice_required"} if transaction_id == override_txn.id else None
            ),
        )

        payload = service.list_rows(direction="income", filter="all", page_size=10)

        statuses = {row["id"]: row["invoice_acquisition_status"]["code"] for row in payload["rows"]}
        self.assertEqual(statuses[invoiced_txn.id], "income_invoiced")
        self.assertEqual(statuses[no_invoice_txn.id], "income_no_invoice_required")
        self.assertEqual(statuses[cash_txn.id], "cash_income")
        self.assertEqual(statuses[override_txn.id], "income_no_invoice_required")
        self.assertEqual(statuses[pending_txn.id], "income_pending_invoice")

    def test_income_filters_use_pending_output_invoice_rule_groups(self) -> None:
        customer = self._counterparty("cp_income_filter", "Customer Filter")
        invoiced_txn = self._bank_transaction("txn_income_requires_invoiced", TransactionDirection.INFLOW, "Customer Invoiced", "100.00")
        pending_txn = self._bank_transaction("txn_income_requires_pending", TransactionDirection.INFLOW, "Customer Pending", "110.00")
        no_invoice_txn = self._bank_transaction("txn_income_no_invoice_filter", TransactionDirection.INFLOW, "Customer No", "120.00")
        cash_txn = self._bank_transaction("txn_income_cash_filter", TransactionDirection.INFLOW, "Customer Cash", "130.00")
        output_invoice = self._invoice("inv_income_filter", InvoiceType.OUTPUT, "OUT-FILTER", customer, buyer_name="Customer Invoiced")
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case_income_filter",
            row_ids=[invoiced_txn.id, output_invoice.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        category_service = BankTransactionCategoryService(
            categories={
                invoiced_txn.id: {"category_code": "bonus", "version": 1},
                pending_txn.id: {"category_code": "bonus", "version": 1},
                no_invoice_txn.id: {"category_code": "internal_transfer", "version": 1},
                cash_txn.id: {"category_code": "fee", "version": 1},
            }
        )
        service = self._query_service(
            transactions=[invoiced_txn, pending_txn, no_invoice_txn, cash_txn],
            invoices=[output_invoice],
            pair_service=pair_service,
            category_service=category_service,
            income_tag_groups={
                "requires_invoice": ["bonus"],
                "no_invoice_required": ["internal_transfer"],
                "cash_income": ["fee"],
            },
        )

        requires_payload = service.list_rows(direction="income", filter="requires_invoice", page_size=10)
        no_invoice_payload = service.list_rows(direction="income", filter="no_invoice_required", page_size=10)
        cash_payload = service.list_rows(direction="income", filter="cash_income", page_size=10)

        self.assertEqual([row["id"] for row in requires_payload["rows"]], [invoiced_txn.id, pending_txn.id])
        self.assertEqual(requires_payload["rows"][0]["invoice_acquisition_status"]["code"], "income_invoiced")
        self.assertEqual([row["id"] for row in no_invoice_payload["rows"]], [no_invoice_txn.id])
        self.assertEqual([row["id"] for row in cash_payload["rows"]], [cash_txn.id])

    def test_requires_invoice_filter_uses_active_tag_complement(self) -> None:
        fee_txn = self._bank_transaction("txn_fee", TransactionDirection.OUTFLOW, "Fee Vendor", "10.00")
        salary_txn = self._bank_transaction("txn_salary", TransactionDirection.OUTFLOW, "Salary Vendor", "20.00")
        custom_txn = self._bank_transaction("txn_custom_meal", TransactionDirection.OUTFLOW, "Meal Vendor", "30.00")
        no_category_txn = self._bank_transaction("txn_no_category", TransactionDirection.OUTFLOW, "No Category", "40.00")
        archived_txn = self._bank_transaction("txn_archived", TransactionDirection.OUTFLOW, "Archived Vendor", "50.00")
        unknown_txn = self._bank_transaction("txn_unknown", TransactionDirection.OUTFLOW, "Unknown Vendor", "60.00")

        class EffectiveProvider:
            def bulk_get_for_rows(self, rows: list[BankTransaction]) -> dict[str, dict[str, object]]:
                categories = {
                    "txn_fee": {"category_code": "fee", "category_label": "手续费"},
                    "txn_salary": {"category_code": "salary", "category_label": "工资"},
                    "txn_custom_meal": {"category_code": "custom_meal", "category_label": "餐饮"},
                    "txn_archived": {"category_code": "custom_archived", "category_label": "归档"},
                    "txn_unknown": {"category_code": "unknown_external_code", "category_label": "未知"},
                }
                return {row.id: categories.get(row.id, {}) for row in rows}

        category_service = BankTransactionCategoryService(
            tag_dictionary={
                "version": 7,
                "definitions": [
                    {
                        "code": "custom_meal",
                        "label": "餐饮",
                        "path": ["餐饮"],
                        "source": "custom",
                        "status": "active",
                        "rules": {"match_fields": ["all_text"], "contains": ["餐饮"]},
                    },
                    {
                        "code": "custom_archived",
                        "label": "归档",
                        "path": ["历史"],
                        "source": "custom",
                        "status": "archived",
                    },
                ],
            }
        )
        service = self._query_service(
            transactions=[fee_txn, salary_txn, custom_txn, no_category_txn, archived_txn, unknown_txn],
            category_service=category_service,
            effective_category_provider=EffectiveProvider(),
            tag_groups={
                "requires_invoice": ["legacy_requires_should_be_ignored"],
                "bank_statement_as_invoice": ["fee"],
                "no_invoice_required": ["salary"],
            },
        )

        payload = service.list_rows(direction="expense", filter="requires_invoice")

        self.assertEqual([row["id"] for row in payload["rows"]], ["txn_custom_meal"])
        self.assertEqual(payload["rows"][0]["invoice_acquisition_status"]["matched_rule"]["group"], "requires_invoice")

    def test_expense_status_priority_uses_rules_and_invoice_payment_facts(self) -> None:
        vendor = self._counterparty("cp_vendor", "Vendor A")
        partial_txn = self._bank_transaction("txn_partial", TransactionDirection.OUTFLOW, "Vendor A", "100.00")
        paid_txn = self._bank_transaction("txn_paid", TransactionDirection.OUTFLOW, "Vendor B", "100.00")
        no_rule_txn = self._bank_transaction("txn_no_rule", TransactionDirection.OUTFLOW, "Vendor N", "30.00")
        statement_txn = self._bank_transaction("txn_statement", TransactionDirection.OUTFLOW, "Vendor S", "40.00")
        missing_txn = self._bank_transaction("txn_missing", TransactionDirection.OUTFLOW, "Vendor M", "50.00")
        partial_invoice = self._invoice("inv_partial", InvoiceType.INPUT, "IN-PARTIAL", vendor, seller_name="Vendor A", total_with_tax="150.00")
        paid_invoice = self._invoice("inv_paid", InvoiceType.INPUT, "IN-PAID", vendor, seller_name="Vendor B", total_with_tax="100.00")
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case_partial",
            row_ids=[partial_txn.id, partial_invoice.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        pair_service.create_active_relation(
            case_id="case_paid",
            row_ids=[paid_txn.id, paid_invoice.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        category_service = BankTransactionCategoryService(
            categories={
                no_rule_txn.id: {"category_code": "bonus", "version": 1},
                statement_txn.id: {"category_code": "salary", "version": 1},
                missing_txn.id: {"category_code": "fee", "version": 1},
            }
        )
        service = self._query_service(
            transactions=[partial_txn, paid_txn, no_rule_txn, statement_txn, missing_txn],
            invoices=[partial_invoice, paid_invoice],
            pair_service=pair_service,
            category_service=category_service,
            tag_groups={
                "requires_invoice": ["fee"],
                "bank_statement_as_invoice": ["salary"],
                "no_invoice_required": ["bonus"],
            },
        )

        payload = service.list_rows(direction="expense", filter="all", page_size=10)

        statuses = {row["id"]: row["invoice_acquisition_status"]["code"] for row in payload["rows"]}
        self.assertEqual(statuses[partial_txn.id], "invoice_not_fully_paid")
        self.assertEqual(statuses[paid_txn.id], "paid_invoiced")
        self.assertEqual(statuses[no_rule_txn.id], "no_invoice_required")
        self.assertEqual(statuses[statement_txn.id], "bank_statement_as_invoice")
        self.assertEqual(statuses[missing_txn.id], "paid_pending_invoice")

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
                        "category_primary_label": "税费",
                        "category_sub_label": "税款支出",
                        "category_label_path": ["税费", "税款支出"],
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
        self.assertEqual(payload["rows"][0]["bank_transaction"]["effective_tag_primary_label"], "税费")
        self.assertEqual(payload["rows"][0]["bank_transaction"]["effective_tag_sub_label"], "税款支出")
        self.assertEqual(payload["rows"][0]["bank_transaction"]["effective_tag_label_path"], ["税费", "税款支出"])
        matched_rule = payload["rows"][0]["invoice_acquisition_status"]["matched_rule"]
        self.assertEqual(matched_rule["tag_primary_label"], "税费")
        self.assertEqual(matched_rule["tag_sub_label"], "税款支出")
        self.assertEqual(matched_rule["tag_label_path"], ["税费", "税款支出"])

    def test_expense_rule_filters_use_effective_category_path_for_bank_statement_group(self) -> None:
        equipment_txn = self._bank_transaction(
            "txn_equipment_purchase",
            TransactionDirection.OUTFLOW,
            "云南辰飞机电工程有限公司",
            "23053.31",
        )

        class EffectiveProvider:
            def bulk_get_for_rows(self, rows: list[BankTransaction]) -> dict[str, dict[str, object]]:
                return {
                    row.id: {
                        "effective_category_code": "equipment_purchase",
                        "effective_category_label": "设备采购",
                        "effective_category_primary_label": "货款",
                        "effective_category_sub_label": "设备采购",
                        "effective_category_label_path": ["货款", "设备采购"],
                        "effective_category_source": "auto",
                    }
                    for row in rows
                }

        category_service = BankTransactionCategoryService(
            tag_dictionary={
                "version": 12,
                "definitions": [
                    {
                        "code": "equipment_purchase",
                        "label": "设备采购",
                        "status": "active",
                        "direction": "expense",
                        "rules": {"match_fields": ["all_text"], "contains": ["设备采购"]},
                    },
                ],
            }
        )
        service = self._query_service(
            transactions=[equipment_txn],
            category_service=category_service,
            effective_category_provider=EffectiveProvider(),
            tag_groups={"bank_statement_as_invoice": ["equipment_purchase"]},
        )

        payload = service.list_rows(direction="expense", filter="bank_statement_as_invoice")

        self.assertEqual([row["id"] for row in payload["rows"]], ["txn_equipment_purchase"])
        row = payload["rows"][0]
        self.assertEqual(row["invoice_acquisition_status"]["code"], "bank_statement_as_invoice")
        self.assertEqual(row["invoice_acquisition_status"]["matched_rule"]["tag_code"], "equipment_purchase")
        self.assertEqual(row["invoice_acquisition_status"]["matched_rule"]["tag_label_path"], ["货款", "设备采购"])
        self.assertEqual(row["bank_transaction"]["effective_tag_label_path"], ["货款", "设备采购"])

    def test_income_rule_filters_use_effective_categories_and_active_requires_complement(self) -> None:
        no_invoice_txn = self._bank_transaction("txn_income_no_invoice_effective", TransactionDirection.INFLOW, "客户免票", "120.00")
        cash_txn = self._bank_transaction("txn_income_cash_effective", TransactionDirection.INFLOW, "现金客户", "80.00")
        requires_txn = self._bank_transaction("txn_income_requires_effective", TransactionDirection.INFLOW, "服务客户", "300.00")
        unknown_txn = self._bank_transaction("txn_income_unknown_effective", TransactionDirection.INFLOW, "未知客户", "90.00")
        archived_txn = self._bank_transaction("txn_income_archived_effective", TransactionDirection.INFLOW, "归档客户", "70.00")

        class EffectiveProvider:
            def bulk_get_for_rows(self, rows: list[BankTransaction]) -> dict[str, dict[str, object]]:
                categories = {
                    no_invoice_txn.id: {
                        "effective_category_code": "income_internal_transfer",
                        "effective_category_label": "内部往来",
                        "effective_category_label_path": ["收入", "内部往来"],
                    },
                    cash_txn.id: {
                        "effective_category_code": "cash_sale",
                        "effective_category_label": "现金销售",
                        "effective_category_label_path": ["收入", "现金销售"],
                    },
                    requires_txn.id: {
                        "effective_category_code": "service_income",
                        "effective_category_label": "服务收入",
                        "effective_category_label_path": ["收入", "服务收入"],
                    },
                    unknown_txn.id: {
                        "effective_category_code": "unknown_income",
                        "effective_category_label": "未知收入",
                        "effective_category_label_path": ["收入", "未知收入"],
                    },
                    archived_txn.id: {
                        "effective_category_code": "archived_income",
                        "effective_category_label": "归档收入",
                        "effective_category_label_path": ["收入", "归档收入"],
                    },
                }
                return {row.id: categories.get(row.id, {}) for row in rows}

        category_service = BankTransactionCategoryService(
            tag_dictionary={
                "version": 12,
                "definitions": [
                    {"code": "service_income", "label": "服务收入", "status": "active", "direction": "income", "rules": {"match_fields": ["all_text"], "contains": ["服务收入"]}},
                    {"code": "income_internal_transfer", "label": "内部往来", "status": "active", "direction": "income", "rules": {"match_fields": ["all_text"], "contains": ["内部往来"]}},
                    {"code": "cash_sale", "label": "现金销售", "status": "active", "direction": "income", "rules": {"match_fields": ["all_text"], "contains": ["现金销售"]}},
                    {"code": "archived_income", "label": "归档收入", "status": "archived", "direction": "income", "rules": {"match_fields": ["all_text"], "contains": ["归档收入"]}},
                ],
            }
        )
        service = self._query_service(
            transactions=[no_invoice_txn, cash_txn, requires_txn, unknown_txn, archived_txn],
            category_service=category_service,
            effective_category_provider=EffectiveProvider(),
            income_tag_groups={"no_invoice_required": ["income_internal_transfer"], "cash_income": ["cash_sale"]},
        )

        no_invoice_payload = service.list_rows(direction="income", filter="no_invoice_required", page_size=10)
        cash_payload = service.list_rows(direction="income", filter="cash_income", page_size=10)
        requires_payload = service.list_rows(direction="income", filter="requires_invoice", page_size=10)

        self.assertEqual([row["id"] for row in no_invoice_payload["rows"]], [no_invoice_txn.id])
        self.assertEqual([row["id"] for row in cash_payload["rows"]], [cash_txn.id])
        self.assertEqual([row["id"] for row in requires_payload["rows"]], [requires_txn.id])
        self.assertEqual(requires_payload["rows"][0]["invoice_acquisition_status"]["matched_rule"]["tag_label_path"], ["收入", "服务收入"])

    def test_bank_account_label_uses_bank_mapping_not_company_account_name(self) -> None:
        txn = BankTransaction(
            id="txn_bank_mapping",
            account_no="6222000011118106",
            account_name="云南溯源科技有限公司",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="Vendor Mapping",
            amount=Decimal("1.00"),
            signed_amount=Decimal("-1.00"),
            txn_date="2026-04-19",
            trade_time="2026-04-19T10:52:02+08:00",
        )
        service = self._query_service(
            transactions=[txn],
            bank_account_mappings=[{"id": "mapping-8106", "bank_name": "建设银行", "short_name": "建行", "last4": "8106"}],
        )

        row = service.list_rows(direction="expense", filter="all")["rows"][0]["bank_transaction"]

        self.assertEqual(row["bank_name"], "建设银行")
        self.assertEqual(row["bank_short_name"], "建行")
        self.assertEqual(row["account_name"], "云南溯源科技有限公司")
        self.assertEqual(row["account_last4"], "8106")

    def test_list_rows_reads_repository_transactions_without_snapshot_imports(self) -> None:
        txn = self._bank_transaction("txn_repository", TransactionDirection.OUTFLOW, "Repository Vendor", "10.00")
        repository = RepositoryOnlyPendingInvoiceFacts(transactions=[txn])
        service = self._query_service(
            transactions=[],
            import_service=ImportNormalizationService(fact_repository=repository),
        )

        payload = service.list_rows(direction="expense", filter="all")

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["rows"][0]["id"], "txn_repository")
        self.assertEqual(repository.transaction_page_calls[0]["page"], 1)

    def test_relation_detail_looks_up_transaction_directly_beyond_first_page(self) -> None:
        transactions = [
            self._bank_transaction(f"txn_page_{index:03d}", TransactionDirection.OUTFLOW, f"Vendor {index:03d}", "1.00")
            for index in range(1, 202)
        ]
        service = self._query_service(transactions=transactions)

        detail = service.relation_detail(transaction_id="txn_page_201")

        self.assertEqual(detail["transaction_summary"]["id"], "txn_page_201")
        self.assertEqual(detail["transaction_summary"]["counterparty_name"], "Vendor 201")

    def test_invoice_candidates_load_repository_transaction_without_snapshot_imports(self) -> None:
        vendor = self._counterparty("cp_repo", "Repository Vendor")
        txn = self._bank_transaction("txn_repository_candidate", TransactionDirection.OUTFLOW, "Repository Vendor", "100.00")
        invoice = self._invoice(
            "inv_repository_candidate",
            InvoiceType.INPUT,
            "REPO-INV",
            vendor,
            seller_name="Repository Vendor",
            total_with_tax="100.00",
        )
        repository = RepositoryOnlyPendingInvoiceFacts(transactions=[txn], invoices=[invoice])
        service = self._query_service(
            transactions=[],
            import_service=ImportNormalizationService(fact_repository=repository),
        )

        payload = service.invoice_candidates(transaction_id=txn.id)

        self.assertEqual(payload["rows"][0]["invoice_id"], invoice.id)
        self.assertEqual(payload["rows"][0]["amount_difference_abs"], "0.00")

    def test_filter_json_and_sort_use_four_zone_fields(self) -> None:
        vendor = self._counterparty("cp_vendor", "Vendor A")
        txn_a = self._bank_transaction("txn_a", TransactionDirection.OUTFLOW, "Vendor A", "300.00")
        txn_b = self._bank_transaction("txn_b", TransactionDirection.OUTFLOW, "Vendor B", "100.00")
        inv_a = self._invoice("inv_a", InvoiceType.INPUT, "IN-A", vendor, seller_name="Alpha Seller", total_with_tax="300.00")
        inv_b = self._invoice("inv_b", InvoiceType.INPUT, "IN-B", vendor, seller_name="Beta Seller", total_with_tax="100.00")
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case_a",
            row_ids=[txn_a.id, inv_a.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
            special_metadata={"applicant": "李四", "project_name": "项目A"},
        )
        pair_service.create_active_relation(
            case_id="case_b",
            row_ids=[txn_b.id, inv_b.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
            special_metadata={"applicant": "张三", "project_name": "项目B"},
        )
        service = self._query_service(
            transactions=[txn_b, txn_a],
            invoices=[inv_b, inv_a],
            pair_service=pair_service,
        )

        payload = service.list_rows(
            direction="expense",
            filter="all",
            filters='[{"field":"seller_name","operator":"contains","value":"Seller"},{"field":"invoice_total","operator":"between","value":{"min":"200","max":"400"}}]',
            sort_field="invoice_total",
            sort_direction="desc",
        )

        self.assertEqual([row["id"] for row in payload["rows"]], ["txn_a"])
        self.assertEqual(payload["rows"][0]["input_invoices"]["primary"]["seller_name"], "Alpha Seller")

    def test_invoice_candidates_sort_status_and_amount_difference(self) -> None:
        vendor = self._counterparty("cp_vendor", "Vendor A")
        txn = self._bank_transaction("txn_candidate", TransactionDirection.OUTFLOW, "Vendor A", "100.00")
        available = self._invoice("inv_available", InvoiceType.INPUT, "IN-100", vendor, seller_name="Vendor A", total_with_tax="100.00")
        near = self._invoice("inv_near", InvoiceType.INPUT, "IN-101", vendor, seller_name="Vendor A", total_with_tax="101.00")
        output = self._invoice("inv_output", InvoiceType.OUTPUT, "OUT-100", vendor, buyer_name="Vendor A", total_with_tax="100.00")
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case_already",
            row_ids=[txn.id, near.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        service = self._query_service(
            transactions=[txn],
            invoices=[near, available, output],
            pair_service=pair_service,
        )

        payload = service.invoice_candidates(transaction_id=txn.id)

        self.assertEqual([row["invoice_id"] for row in payload["rows"]], ["inv_available", "inv_near"])
        self.assertEqual(payload["rows"][0]["candidate_status"], "available")
        self.assertEqual(payload["rows"][0]["amount_difference_abs"], "0.00")
        self.assertEqual(payload["rows"][1]["candidate_status"], "already_related")

    def test_invoice_candidate_with_other_bank_payment_remains_available(self) -> None:
        vendor = self._counterparty("cp_vendor", "Vendor A")
        existing_payment = self._bank_transaction("txn_paid_part", TransactionDirection.OUTFLOW, "Vendor A", "60.00")
        current_payment = self._bank_transaction("txn_candidate_part", TransactionDirection.OUTFLOW, "Vendor A", "40.00")
        invoice = self._invoice("inv_multi_pay", InvoiceType.INPUT, "IN-MULTI", vendor, seller_name="Vendor A", total_with_tax="100.00")
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case_paid_part",
            row_ids=[existing_payment.id, invoice.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        service = self._query_service(
            transactions=[existing_payment, current_payment],
            invoices=[invoice],
            pair_service=pair_service,
        )

        payload = service.invoice_candidates(transaction_id=current_payment.id)

        self.assertEqual(payload["rows"][0]["invoice_id"], invoice.id)
        self.assertEqual(payload["rows"][0]["candidate_status"], "available")
        self.assertEqual(payload["rows"][0]["related_paid_total"], "60.00")

    def test_income_rejects_expense_only_filters(self) -> None:
        service = self._query_service(transactions=[])

        with self.assertRaises(PendingInvoiceError) as context:
            service.list_rows(direction="income", filter="bank_statement_as_invoice")

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
        total_with_tax: str | None = None,
    ) -> Invoice:
        resolved_total = Decimal(total_with_tax) if total_with_tax is not None else Decimal("100.00")
        return Invoice(
            id=invoice_id,
            invoice_type=invoice_type,
            invoice_no=invoice_no,
            counterparty=counterparty,
            amount=resolved_total,
            signed_amount=resolved_total,
            invoice_date="2026-05-20",
            total_with_tax=resolved_total,
            seller_name=seller_name,
            buyer_name=buyer_name,
        )

    @staticmethod
    def _query_service(
        *,
        transactions: list[BankTransaction],
        import_service: ImportNormalizationService | None = None,
        invoices: list[Invoice] | None = None,
        pair_service: WorkbenchPairRelationService | None = None,
        category_service: BankTransactionCategoryService | None = None,
        effective_category_provider: object | None = None,
        tag_groups: dict[str, list[str]] | None = None,
        income_tag_groups: dict[str, list[str]] | None = None,
        bank_account_mappings: list[dict[str, str]] | None = None,
        oa_projection: object | None = None,
        income_status_override_provider: object | None = None,
        relation_facade: object | None = None,
    ) -> PendingInvoiceQueryService:
        resolved_import_service = import_service or ImportNormalizationService(
            existing_transactions=transactions,
            existing_invoices=invoices or [],
        )
        settings_payload = {
            "bank_account_mappings": list(bank_account_mappings or []),
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
            "pending_output_invoice_tag_groups": {
                "version": 1,
                "groups": {
                    "requires_invoice": {"tag_codes": list((income_tag_groups or {}).get("requires_invoice") or [])},
                    "no_invoice_required": {"tag_codes": list((income_tag_groups or {}).get("no_invoice_required") or [])},
                    "cash_income": {"tag_codes": list((income_tag_groups or {}).get("cash_income") or [])},
                },
            },
        }
        resolved_pair_service = pair_service or WorkbenchPairRelationService()
        resolved_relation_facade = relation_facade
        if resolved_relation_facade is None:
            resolved_relation_facade = FakeWorkbenchRelationFacade.from_pair_service(
                pair_service=resolved_pair_service,
                transactions=list(transactions or []),
                invoices=list(invoices or []),
                oa_projection=oa_projection,
            )
        return PendingInvoiceQueryService(
            import_service=resolved_import_service,
            pair_relation_service=resolved_pair_service,
            category_service=category_service or BankTransactionCategoryService(),
            app_settings_provider=lambda: settings_payload,
            effective_category_provider=effective_category_provider,
            oa_projection=oa_projection,
            income_status_override_provider=income_status_override_provider,
            relation_facade=resolved_relation_facade,
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
            command_repository=InMemoryPendingInvoiceCommandRepository(self.command_store),
            audit_recorder=self.audit_events.append,
            finalizer=self.finalize_events.append,
            relation_facade=LiveWorkbenchRelationFacade(
                pair_service=self.pair_service,
                import_service_provider=lambda: self.import_service,
            ),
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

    def test_preview_and_confirm_attach_existing_invoice_are_idempotent(self) -> None:
        invoice = Invoice(
            id="inv_existing",
            invoice_type=InvoiceType.INPUT,
            invoice_no="EXISTING-001",
            counterparty=self.vendor,
            amount=Decimal("118.00"),
            signed_amount=Decimal("118.00"),
            invoice_date="2026-05-20",
            total_with_tax=Decimal("118.00"),
            seller_name="Vendor A",
            buyer_name="云南溯源科技有限公司",
        )
        self.import_service = ImportNormalizationService(existing_transactions=[self.expense_txn], existing_invoices=[invoice])
        self.service = PendingInvoiceApplicationService(
            import_service=self.import_service,
            pair_relation_service=self.pair_service,
            command_store=self.command_store,
            audit_recorder=self.audit_events.append,
            finalizer=self.finalize_events.append,
            relation_facade=LiveWorkbenchRelationFacade(
                pair_service=self.pair_service,
                import_service_provider=lambda: self.import_service,
            ),
        )

        preview = self.service.preview_attach_existing_invoice(
            transaction_id=self.expense_txn.id,
            payload={"invoice_id": invoice.id, "request_id": "preview-attach"},
        )
        result = self.service.confirm_attach_existing_invoice(
            transaction_id=self.expense_txn.id,
            payload={"preview_id": preview["preview_id"], "invoice_id": invoice.id, "request_id": "attach-001"},
            actor_id="finance-user",
        )
        retry = self.service.confirm_attach_existing_invoice(
            transaction_id=self.expense_txn.id,
            payload={"preview_id": preview["preview_id"], "invoice_id": invoice.id, "request_id": "attach-001"},
            actor_id="finance-user",
        )

        self.assertEqual(preview["request_key"], "pending_invoice_attach_existing:txn_expense:inv_existing")
        self.assertTrue(preview["can_confirm"])
        self.assertEqual(result, retry)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["relation_mode"], "pending_invoice_attach_existing_invoice")
        self.assertEqual(len(self.pair_service.list_active_relations()), 1)
        self.assertEqual(self.audit_events[0]["action"], "pending_invoice_attach_existing_invoice_confirmed")

    def test_attach_existing_allows_invoice_already_linked_to_another_bank_payment(self) -> None:
        previous_txn = BankTransaction(
            id="txn_previous_payment",
            account_no="622200001234",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="Vendor A",
            amount=Decimal("60.00"),
            signed_amount=Decimal("-60.00"),
            txn_date="2026-05-19",
            trade_time="2026-05-19 10:00:00",
        )
        current_txn = BankTransaction(
            id="txn_current_payment",
            account_no="622200001234",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="Vendor A",
            amount=Decimal("40.00"),
            signed_amount=Decimal("-40.00"),
            txn_date="2026-05-20",
            trade_time="2026-05-20 10:00:00",
        )
        invoice = Invoice(
            id="inv_multi_payment",
            invoice_type=InvoiceType.INPUT,
            invoice_no="EXISTING-MULTI",
            counterparty=self.vendor,
            amount=Decimal("100.00"),
            signed_amount=Decimal("100.00"),
            invoice_date="2026-05-20",
            total_with_tax=Decimal("100.00"),
            seller_name="Vendor A",
            buyer_name="云南溯源科技有限公司",
        )
        self.pair_service.create_active_relation(
            case_id="case_previous_payment",
            row_ids=[previous_txn.id, invoice.id],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        self.import_service = ImportNormalizationService(existing_transactions=[previous_txn, current_txn], existing_invoices=[invoice])
        self.service = PendingInvoiceApplicationService(
            import_service=self.import_service,
            pair_relation_service=self.pair_service,
            command_store=self.command_store,
            audit_recorder=self.audit_events.append,
            finalizer=self.finalize_events.append,
            relation_facade=LiveWorkbenchRelationFacade(
                pair_service=self.pair_service,
                import_service_provider=lambda: self.import_service,
            ),
        )

        preview = self.service.preview_attach_existing_invoice(
            transaction_id=current_txn.id,
            payload={"invoice_id": invoice.id},
        )
        result = self.service.confirm_attach_existing_invoice(
            transaction_id=current_txn.id,
            payload={"preview_id": preview["preview_id"], "invoice_id": invoice.id, "request_id": "attach-multi"},
            actor_id="finance-user",
        )

        self.assertTrue(preview["can_confirm"])
        self.assertEqual(preview["payment_impact"]["paid_total_before"], "60.00")
        self.assertEqual(preview["payment_impact"]["paid_total_after"], "100.00")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(self.pair_service.list_active_relations()), 2)
        self.assertEqual(self.audit_events[0]["entity_type"], "pending_invoice_attach_existing_invoice")
        self.assertEqual(self.finalize_events[0]["action"], "pending_invoice_attach_existing_invoice_confirmed")

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
