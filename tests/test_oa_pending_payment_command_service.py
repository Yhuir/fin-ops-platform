from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord, PAY_STATUS_PAID
from fin_ops_platform.services.oa_pending_payment_command_service import OaPendingPaymentCommandService
from fin_ops_platform.services.oa_pending_payment_service import OaPendingPaymentError


class StaticOAProjection:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records = list(records)

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        wanted = {str(row_id) for row_id in row_ids}
        return [record for record in self.records if record.id in wanted]

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        return list(self.records)


class FakePaymentStatusRepository:
    def __init__(self, *, flow_id: str | None = "507f1f77bcf86cd799439001") -> None:
        self.flow_id = flow_id
        self.resolved_records: list[str] = []
        self.marked_flow_ids: list[str] = []

    def resolve_flow_id(self, record: OAApplicationRecord) -> str | None:
        self.resolved_records.append(record.id)
        return self.flow_id

    def get_payment_status(self, flow_id: str) -> OAPaymentStatusRecord | None:
        return OAPaymentStatusRecord(flow_id=flow_id, pay_status=PAY_STATUS_PAID)

    def mark_paid(self, flow_id: str) -> OAPaymentStatusRecord:
        self.marked_flow_ids.append(flow_id)
        return OAPaymentStatusRecord(flow_id=flow_id, pay_status=PAY_STATUS_PAID)


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
    def test_confirm_paid_creates_relation_then_writes_mysql_payment_status(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439011")
        relation_command = FakeRelationCommandService()
        refresh_calls: list[tuple[str, str, str]] = []
        service = _service(
            oa_records=[_oa("oa-pay-2047", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-100", "100.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
            refresh_calls=refresh_calls,
        )

        payload = service.confirm_paid(
            {"oaRowId": "oa-pay-2047", "bankTransactionId": "bank-100", "idempotencyKey": "idem-1"},
            actor_id="tester",
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["paymentStatus"]["code"], "paid")
        self.assertEqual(payload["oaPaymentWriteback"]["code"], "written")
        self.assertEqual(payload["oaPaymentWriteback"]["flowId"], "507f1f77bcf86cd799439011")
        self.assertEqual(payment_repository.resolved_records, ["oa-pay-2047"])
        self.assertEqual(payment_repository.marked_flow_ids, ["507f1f77bcf86cd799439011"])
        self.assertEqual(len(relation_command.confirm_calls), 1)
        confirm_call = relation_command.confirm_calls[0]
        self.assertEqual(confirm_call["row_ids"], ["oa-pay-2047", "bank-100"])
        self.assertEqual(confirm_call["row_types"], ["oa", "bank"])
        self.assertEqual(confirm_call["relation_mode"], "manual_confirmed")
        self.assertEqual(confirm_call["history_operation_type"], "oa_pending_payment_confirm_paid")
        self.assertEqual(confirm_call["special_metadata"]["origin"], "oa_pending_payment_in_progress")
        self.assertEqual(confirm_call["idempotency_key"], "idem-1")
        self.assertEqual(confirm_call["amount_check"]["matched"], True)
        self.assertEqual(
            refresh_calls,
            [
                ("workbench", "2026-06", "oa_pending_payment_confirm_paid"),
                ("oa_pending_payment", "2026-06", "oa_pending_payment_confirm_paid"),
                ("workbench", "all", "oa_pending_payment_confirm_paid"),
                ("oa_pending_payment", "all", "oa_pending_payment_confirm_paid"),
            ],
        )

    def test_confirm_paid_without_bank_uses_existing_active_relation(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439012")
        relation_command = FakeRelationCommandService(
            [
                {
                    "case_id": "case-active",
                    "row_ids": ["oa-active", "bank-active"],
                    "row_types": ["oa", "bank"],
                    "relation_mode": "manual_confirmed",
                    "amount_check": {"matched": True},
                    "month_scope": "2026-06",
                }
            ]
        )
        service = _service(
            oa_records=[_oa("oa-active", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-active", "100.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
        )

        payload = service.confirm_paid({"oa_row_id": "oa-active"}, actor_id="tester")

        self.assertEqual(payload["relation"]["status"], "already_confirmed")
        self.assertEqual(payload["bankTransactionIds"], ["bank-active"])
        self.assertEqual(relation_command.confirm_calls, [])
        self.assertEqual(payment_repository.marked_flow_ids, ["507f1f77bcf86cd799439012"])

    def test_confirm_paid_with_bank_reuses_existing_active_relation(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439012")
        relation_command = FakeRelationCommandService(
            [
                {
                    "case_id": "case-active",
                    "row_ids": ["oa-active", "bank-active"],
                    "row_types": ["oa", "bank"],
                    "relation_mode": "manual_confirmed",
                    "amount_check": {"matched": True},
                    "month_scope": "2026-06",
                }
            ]
        )
        service = _service(
            oa_records=[_oa("oa-active", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-active", "100.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
        )

        payload = service.confirm_paid({"oa_row_id": "oa-active", "bank_transaction_id": "bank-active"}, actor_id="tester")

        self.assertEqual(payload["relation"]["status"], "already_confirmed")
        self.assertEqual(relation_command.confirm_calls, [])
        self.assertEqual(payment_repository.marked_flow_ids, ["507f1f77bcf86cd799439012"])

    def test_link_bank_transactions_creates_relation_without_writing_mysql(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439015")
        relation_command = FakeRelationCommandService()
        refresh_calls: list[tuple[str, str, str]] = []
        service = _service(
            oa_records=[_oa("oa-link", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-link", "100.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
            refresh_calls=refresh_calls,
        )

        payload = service.link_bank_transactions(
            {"oa_row_ids": ["oa-link"], "bank_transaction_ids": ["bank-link"], "idempotency_key": "link-1"},
            actor_id="tester",
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["action"], "oa_pending_payment_link_bank_transactions")
        self.assertEqual(payment_repository.marked_flow_ids, [])
        self.assertEqual(len(relation_command.confirm_calls), 1)
        confirm_call = relation_command.confirm_calls[0]
        self.assertEqual(confirm_call["row_ids"], ["oa-link", "bank-link"])
        self.assertEqual(confirm_call["row_types"], ["oa", "bank"])
        self.assertEqual(confirm_call["history_operation_type"], "oa_pending_payment_link_bank")
        self.assertEqual(confirm_call["special_metadata"]["source_action"], "link_bank_transactions")
        self.assertEqual(
            refresh_calls,
            [
                ("workbench", "2026-06", "oa_pending_payment_link_bank_transactions"),
                ("oa_pending_payment", "2026-06", "oa_pending_payment_link_bank_transactions"),
                ("workbench", "all", "oa_pending_payment_link_bank_transactions"),
                ("oa_pending_payment", "all", "oa_pending_payment_link_bank_transactions"),
            ],
        )

    def test_link_bank_transactions_rejects_income_bank(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439016")
        relation_command = FakeRelationCommandService()
        service = _service(
            oa_records=[_oa("oa-link", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-income", "100.00", direction=TransactionDirection.INFLOW)],
            relation_command=relation_command,
            payment_repository=payment_repository,
        )

        with self.assertRaises(OaPendingPaymentError) as context:
            service.link_bank_transactions({"oa_row_ids": ["oa-link"], "bank_transaction_ids": ["bank-income"]}, actor_id="tester")

        self.assertEqual(context.exception.error_code, "bank_transaction_not_outflow")
        self.assertEqual(relation_command.confirm_calls, [])
        self.assertEqual(payment_repository.marked_flow_ids, [])

    def test_bank_transaction_candidates_marks_in_progress_linked_rows(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439017")
        relation_command = FakeRelationCommandService(
            [
                {
                    "case_id": "case-progress",
                    "row_ids": ["oa-progress", "bank-linked"],
                    "row_types": ["oa", "bank"],
                    "relation_mode": "manual_confirmed",
                    "amount_check": {"matched": True},
                    "month_scope": "2026-06",
                }
            ]
        )
        service = _service(
            oa_records=[_oa("oa-progress", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-linked", "100.00"), _bank("bank-free", "80.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
        )

        payload = service.bank_transaction_candidates({"relation_status": ["linked_in_progress"]})

        self.assertEqual([row["id"] for row in payload["rows"]], ["bank-linked"])
        self.assertEqual(payload["rows"][0]["relationStatusLabel"], "已关联进行中OA")

    def test_amount_mismatch_does_not_confirm_relation_or_write_mysql(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439013")
        relation_command = FakeRelationCommandService()
        service = _service(
            oa_records=[_oa("oa-mismatch", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-90", "90.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
        )

        with self.assertRaises(OaPendingPaymentError) as context:
            service.confirm_paid({"oa_row_id": "oa-mismatch", "bank_transaction_id": "bank-90"}, actor_id="tester")

        self.assertEqual(context.exception.error_code, "oa_payment_status_not_paid")
        self.assertEqual(relation_command.confirm_calls, [])
        self.assertEqual(payment_repository.marked_flow_ids, [])

    def test_completed_oa_is_rejected_before_resolving_flow_id(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439014")
        relation_command = FakeRelationCommandService()
        service = _service(
            oa_records=[_oa("oa-completed", "100.00", workflow_status="completed")],
            transactions=[_bank("bank-100", "100.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
        )

        with self.assertRaises(OaPendingPaymentError) as context:
            service.confirm_paid({"oa_row_id": "oa-completed", "bank_transaction_id": "bank-100"}, actor_id="tester")

        self.assertEqual(context.exception.error_code, "oa_workflow_status_not_in_progress")
        self.assertEqual(payment_repository.resolved_records, [])
        self.assertEqual(relation_command.confirm_calls, [])

    def test_missing_flow_id_is_rejected_before_confirming_candidate_relation(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id=None)
        relation_command = FakeRelationCommandService()
        service = _service(
            oa_records=[_oa("oa-no-flow", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-100", "100.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
        )

        with self.assertRaises(OaPendingPaymentError) as context:
            service.confirm_paid({"oa_row_id": "oa-no-flow", "bank_transaction_id": "bank-100"}, actor_id="tester")

        self.assertEqual(context.exception.error_code, "oa_flow_id_not_found")
        self.assertEqual(relation_command.confirm_calls, [])
        self.assertEqual(payment_repository.marked_flow_ids, [])


def _service(
    *,
    oa_records: list[OAApplicationRecord],
    transactions: list[BankTransaction],
    relation_command: FakeRelationCommandService,
    payment_repository: FakePaymentStatusRepository,
    refresh_calls: list[tuple[str, str, str]] | None = None,
) -> OaPendingPaymentCommandService:
    calls = refresh_calls if refresh_calls is not None else []

    def enqueue_workbench(scope_key: str, *, reason: str, **_kwargs: object) -> bool:
        calls.append(("workbench", scope_key, reason))
        return True

    def enqueue_oa_pending(scope_key: str, *, reason: str, **_kwargs: object) -> bool:
        calls.append(("oa_pending_payment", scope_key, reason))
        return True

    return OaPendingPaymentCommandService(
        import_service=ImportNormalizationService(existing_transactions=transactions),
        oa_projection=StaticOAProjection(oa_records),
        relation_command_service=relation_command,
        payment_status_repository=payment_repository,
        enqueue_workbench_refresh=enqueue_workbench,
        enqueue_oa_pending_payment_refresh=enqueue_oa_pending,
    )


def _oa(record_id: str, amount: str, *, workflow_status: str) -> OAApplicationRecord:
    return OAApplicationRecord(
        id=record_id,
        month="2026-06",
        section="open",
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
        detail_fields={"流程实例ID": "proc-from-record", "Mongo文档ID": record_id.removeprefix("oa-pay-")},
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
