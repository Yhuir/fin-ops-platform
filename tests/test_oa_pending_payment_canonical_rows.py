from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord, PAY_STATUS_PAID
from fin_ops_platform.services.oa_pending_payment_canonical_rows import build_oa_pending_payment_rows


class OaPendingPaymentProjectionRowsTests(unittest.TestCase):
    def test_linked_canonical_relation_builds_one_paid_group_without_standalone_duplicates(self) -> None:
        records = [self._oa("oa-1", "40.00"), self._oa("oa-2", "60.00")]
        bank = self._bank("bank-1", "100.00")
        invoice = self._invoice("invoice-1", "100.00")

        rows = self._build(
            records=records,
            relations=[self._relation("case-1", ["oa-1", "oa-2", bank.id, invoice.id])],
            banks=[bank],
            invoices=[invoice],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["oa"]["amount"], "100.00")
        self.assertEqual(rows[0]["oa"]["relationCount"], 2)
        self.assertEqual(rows[0]["paymentStatus"]["code"], "paid")
        self.assertEqual(rows[0]["bankTransaction"]["paidTotal"], "100.00")
        self.assertEqual(rows[0]["invoice"]["totalWithTax"], "100.00")

    def test_candidate_and_unlinked_relations_do_not_pollute_rows(self) -> None:
        record = self._oa("oa-1", "100.00")
        bank = self._bank("bank-1", "100.00")

        rows = self._build(
            records=[record],
            relations=[
                {
                    **self._relation("candidate", [record.id, bank.id]),
                    "status": "candidate",
                    "relation_status": "candidate",
                },
                {
                    **self._relation("unlinked", [record.id, bank.id]),
                    "status": "unlinked",
                    "relation_status": "unlinked",
                },
            ],
            banks=[bank],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["oa"]["relationCount"], 1)
        self.assertEqual(rows[0]["bankTransaction"]["relationCount"], 0)
        self.assertEqual(rows[0]["paymentStatus"]["code"], "unpaid")

    def test_month_shard_excludes_cross_month_oa_member(self) -> None:
        may = self._oa("oa-may", "100.00", month="2026-05")
        june = self._oa("oa-june", "200.00", month="2026-06")
        bank = self._bank("bank-1", "100.00")
        relation = self._relation("case-cross-month", [may.id, june.id, bank.id])

        rows = self._build(records=[may, june], relations=[relation], banks=[bank], scope_key="2026-05")

        self.assertEqual(len(rows), 1)
        self.assertEqual([item["oaId"] for item in rows[0]["oa"]["summaries"]], [may.id])
        self.assertEqual(rows[0]["oa"]["amount"], "100.00")

    def test_missing_or_non_outflow_bank_fact_fails_closed_for_writeback(self) -> None:
        record = self._oa("oa-1", "100.00")
        inflow = self._bank("bank-inflow", "100.00", direction=TransactionDirection.INFLOW)

        missing_rows = self._build(
            records=[record],
            relations=[self._relation("missing", [record.id, "bank-missing"])],
        )
        inflow_rows = self._build(
            records=[record],
            relations=[self._relation("inflow", [record.id, inflow.id])],
            banks=[inflow],
        )

        self.assertEqual(missing_rows[0]["bankTransaction"]["missingBankRelationCount"], 1)
        self.assertEqual(inflow_rows[0]["bankTransaction"]["nonOutflowBankRelationCount"], 1)
        self.assertEqual(missing_rows[0]["oaPaymentWriteback"]["code"], "not_written")
        self.assertEqual(inflow_rows[0]["oaPaymentWriteback"]["code"], "not_written")

    def test_paid_writeback_requires_every_resolved_flow_to_be_paid(self) -> None:
        records = [self._oa("oa-1", "40.00"), self._oa("oa-2", "60.00")]
        relation = self._relation("case-1", ["oa-1", "oa-2", "bank-1"])
        bank = self._bank("bank-1", "100.00")
        statuses = {
            "flow-1": OAPaymentStatusRecord(flow_id="flow-1", pay_status=PAY_STATUS_PAID),
            "flow-2": OAPaymentStatusRecord(flow_id="flow-2", pay_status=PAY_STATUS_PAID),
        }

        rows = build_oa_pending_payment_rows(
            records=records,
            relations=[relation],
            bank_transactions=[bank],
            invoices=[],
            payment_statuses_by_flow_id=statuses,
            flow_id_resolver=lambda record: f"flow-{record.id[-1]}",
            scope_key="2026-05",
        )

        self.assertEqual(rows[0]["oaPaymentWriteback"]["code"], "written")
        self.assertEqual(rows[0]["oaPaymentWriteback"]["flowIds"], ["flow-1", "flow-2"])

    def _build(
        self,
        *,
        records: list[OAApplicationRecord],
        relations: list[dict[str, object]],
        banks: list[BankTransaction] | None = None,
        invoices: list[Invoice] | None = None,
        scope_key: str = "2026-05",
    ) -> list[dict[str, object]]:
        return build_oa_pending_payment_rows(
            records=records,
            relations=relations,
            bank_transactions=list(banks or []),
            invoices=list(invoices or []),
            payment_statuses_by_flow_id=None,
            flow_id_resolver=lambda _record: None,
            scope_key=scope_key,
        )

    @staticmethod
    def _oa(oa_id: str, amount: str, *, month: str = "2026-05") -> OAApplicationRecord:
        return OAApplicationRecord(
            id=oa_id,
            month=month,
            section="审批通过",
            case_id=None,
            applicant="测试申请人",
            project_name="测试项目",
            apply_type="付款",
            amount=amount,
            counterparty_name="测试供应商",
            reason="测试付款",
            relation_code="",
            relation_label="",
            relation_tone="",
            workflow_status="completed",
            detail_fields={},
            project_name_display="测试项目",
        )

    @staticmethod
    def _bank(
        bank_id: str,
        amount: str,
        *,
        direction: TransactionDirection = TransactionDirection.OUTFLOW,
    ) -> BankTransaction:
        return BankTransaction(
            id=bank_id,
            account_no="622200001234",
            txn_direction=direction,
            counterparty_name_raw="测试供应商",
            amount=Decimal(amount),
            signed_amount=-Decimal(amount) if direction == TransactionDirection.OUTFLOW else Decimal(amount),
            txn_date="2026-05-21",
            trade_time="2026-05-21 10:00:00",
            account_name="云南溯源科技有限公司",
            balance=Decimal("900.00"),
            currency="人民币元",
            counterparty_account_no="621700001",
            counterparty_bank_name="建行昆明支行",
            booked_date="20260521",
            summary="电子转账",
            remark="测试付款备注",
            imported_bank_name="建设银行",
            imported_bank_last4="1234",
        )

    @staticmethod
    def _invoice(invoice_id: str, total: str) -> Invoice:
        counterparty = Counterparty(
            id=f"cp-{invoice_id}",
            name="测试供应商",
            normalized_name="测试供应商",
            counterparty_type="supplier",
        )
        return Invoice(
            id=invoice_id,
            invoice_type=InvoiceType.INPUT,
            invoice_no="INV-001",
            digital_invoice_no="INV-001",
            counterparty=counterparty,
            amount=Decimal(total),
            signed_amount=Decimal(total),
            invoice_date="2026-05-20",
            seller_name="测试供应商",
            buyer_name="云南溯源科技有限公司",
            total_with_tax=Decimal(total),
        )

    @staticmethod
    def _relation(case_id: str, row_ids: list[str]) -> dict[str, object]:
        return {
            "case_id": case_id,
            "row_ids": row_ids,
            "row_types": [
                "oa" if row_id.startswith("oa-") else "bank" if row_id.startswith("bank-") else "invoice"
                for row_id in row_ids
            ],
            "status": "active",
            "relation_status": "linked",
            "relation_mode": "manual_confirmed",
        }


if __name__ == "__main__":
    unittest.main()
