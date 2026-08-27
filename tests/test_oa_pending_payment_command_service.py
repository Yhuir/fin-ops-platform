from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_pending_payment_command_service import OaPendingPaymentCommandService
from fin_ops_platform.services.oa_pending_payment_query_contract import OaPendingPaymentError


class StaticOAProjection:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records = list(records)

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        wanted = {str(row_id) for row_id in row_ids}
        return [record for record in self.records if record.id in wanted]

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        return list(self.records)


class FakeRelationCommandService:
    def __init__(self, active_relations: list[dict[str, object]] | None = None) -> None:
        self.active_relations = [dict(relation) for relation in list(active_relations or [])]
        self.confirm_calls: list[dict[str, object]] = []

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, object]]:
        wanted = {str(row_id) for row_id in row_ids}
        return [
            relation
            for relation in self.active_relations
            if wanted & {str(row_id) for row_id in list(relation.get("row_ids") or [])}
        ]

    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        self.confirm_calls.append(dict(kwargs))
        relation = {
            "case_id": kwargs["case_id"],
            "row_ids": list(kwargs["row_ids"]),  # type: ignore[arg-type]
            "row_types": list(kwargs["row_types"]),  # type: ignore[arg-type]
            "relation_mode": kwargs["relation_mode"],
            "amount_check": dict(kwargs["amount_check"]),  # type: ignore[arg-type]
            "month_scope": kwargs["month_scope"],
        }
        self.active_relations.append(relation)
        return {
            "status": "confirmed",
            "relation": relation,
            "changed_case_ids": [kwargs["case_id"]],
            "affected_months": [kwargs["month_scope"]],
        }


class OaPendingPaymentCommandServiceTests(unittest.TestCase):
    def test_manual_writeback_commands_are_not_exposed(self) -> None:
        self.assertFalse(hasattr(OaPendingPaymentCommandService, "confirm_paid"))
        self.assertFalse(hasattr(OaPendingPaymentCommandService, "writeback_paid"))

    def test_link_bank_transactions_creates_relation_and_queues_automatic_sync(self) -> None:
        relation_command = FakeRelationCommandService()
        service = _service(
            oa_records=[_oa("oa-link", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-link", "100.00")],
            relation_command=relation_command,
        )

        payload = service.link_bank_transactions(
            {"oa_row_ids": ["oa-link"], "bank_transaction_ids": ["bank-link"], "idempotency_key": "link-1"},
            actor_id="tester",
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["action"], "oa_pending_payment_link_bank_transactions")
        self.assertEqual(payload["paymentStatusSync"]["code"], "queued")
        self.assertNotIn("autoWriteback", payload)
        self.assertNotIn("oaPaymentWriteback", payload)
        create_call = relation_command.confirm_calls[0]
        self.assertEqual(create_call["row_ids"], ["oa-link", "bank-link"])
        self.assertEqual(create_call["row_types"], ["oa", "bank"])
        self.assertEqual(create_call["special_metadata"]["origin"], "oa_pending_payment")

    def test_link_bank_transactions_queues_sync_even_when_amount_mismatches(self) -> None:
        relation_command = FakeRelationCommandService()
        service = _service(
            oa_records=[_oa("oa-link-mismatch", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-link-90", "90.00")],
            relation_command=relation_command,
        )

        payload = service.link_bank_transactions(
            {"oa_row_ids": ["oa-link-mismatch"], "bank_transaction_ids": ["bank-link-90"]},
            actor_id="tester",
        )

        self.assertEqual(payload["paymentStatusSync"]["code"], "queued")
        self.assertFalse(relation_command.confirm_calls[0]["amount_check"]["matched"])

    def test_link_bank_transactions_ignores_client_case_id_and_uses_stable_identity(self) -> None:
        relation_command = FakeRelationCommandService()
        service = _service(
            oa_records=[_oa("oa-b", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-b", "100.00")],
            relation_command=relation_command,
        )

        service.link_bank_transactions(
            {"oa_row_ids": ["oa-b"], "bank_transaction_ids": ["bank-b"], "caseId": "client-forged-case"},
            actor_id="tester",
        )

        self.assertRegex(str(relation_command.confirm_calls[0]["case_id"]), r"^OA-PAY-[0-9a-f]{16}$")
        self.assertNotEqual(relation_command.confirm_calls[0]["case_id"], "client-forged-case")

    def test_link_bank_transactions_extends_existing_bank_invoice_case_without_new_case(self) -> None:
        relation_command = FakeRelationCommandService(
            [{
                "case_id": "case-bank-invoice",
                "row_ids": ["bank-linked", "invoice-linked"],
                "row_types": ["bank", "invoice"],
                "relation_mode": "manual_confirmed",
                "month_scope": "2026-06",
                "special_metadata": {"requires_oa": False, "requires_invoice": True},
            }]
        )
        service = _service(
            oa_records=[_oa("oa-in-progress", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-linked", "100.00")],
            relation_command=relation_command,
        )

        service.link_bank_transactions(
            {"oa_row_ids": ["oa-in-progress"], "bank_transaction_ids": ["bank-linked"]},
            actor_id="tester",
        )

        call = relation_command.confirm_calls[0]
        self.assertEqual(call["case_id"], "case-bank-invoice")
        self.assertEqual(call["row_ids"], ["bank-linked", "invoice-linked", "oa-in-progress"])
        self.assertEqual(call["row_types"], ["bank", "invoice", "oa"])
        self.assertTrue(call["replace_existing"])

    def test_link_bank_transactions_rejects_income_bank(self) -> None:
        relation_command = FakeRelationCommandService()
        service = _service(
            oa_records=[_oa("oa-link", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-income", "100.00", direction=TransactionDirection.INFLOW)],
            relation_command=relation_command,
        )

        with self.assertRaises(OaPendingPaymentError) as context:
            service.link_bank_transactions(
                {"oa_row_ids": ["oa-link"], "bank_transaction_ids": ["bank-income"]},
                actor_id="tester",
            )

        self.assertEqual(context.exception.error_code, "bank_transaction_not_outflow")
        self.assertEqual(relation_command.confirm_calls, [])


def _service(
    *,
    oa_records: list[OAApplicationRecord],
    transactions: list[BankTransaction],
    relation_command: FakeRelationCommandService,
) -> OaPendingPaymentCommandService:
    return OaPendingPaymentCommandService(
        import_service=ImportNormalizationService(existing_transactions=transactions),
        oa_projection=StaticOAProjection(oa_records),
        relation_command_service=relation_command,
    )


def _oa(record_id: str, amount: str, *, workflow_status: str, month: str = "2026-06") -> OAApplicationRecord:
    return OAApplicationRecord(
        id=record_id,
        month=month,
        section="unpaired",
        case_id=None,
        applicant="刘际涛",
        project_name="测试项目",
        apply_type="支付申请",
        amount=amount,
        counterparty_name="测试供应商",
        reason="测试付款",
        relation_code="pending_match",
        relation_label="待找流水",
        relation_tone="warn",
        workflow_status=workflow_status,
        detail_fields={
            "流程实例ID": "proc-from-record",
            "Mongo文档ID": record_id.removeprefix("oa-pay-"),
            "申请日期": "2026-06-17",
        },
    )


def _bank(
    bank_id: str,
    amount: str,
    *,
    direction: TransactionDirection = TransactionDirection.OUTFLOW,
) -> BankTransaction:
    signed_amount = -Decimal(amount) if direction == TransactionDirection.OUTFLOW else Decimal(amount)
    return BankTransaction(
        id=bank_id,
        account_no="622200001234",
        txn_direction=direction,
        counterparty_name_raw="测试供应商",
        amount=Decimal(amount),
        signed_amount=signed_amount,
        txn_date="2026-06-17",
        trade_time="2026-06-17 10:00:00",
        imported_bank_name="测试银行",
        imported_bank_last4="1234",
    )


if __name__ == "__main__":
    unittest.main()
