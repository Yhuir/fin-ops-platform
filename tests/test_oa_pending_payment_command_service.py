from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord, PAY_STATUS_PAID, PAY_STATUS_PENDING
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
    def __init__(
        self,
        *,
        flow_id: str | None = "507f1f77bcf86cd799439001",
        flow_ids: dict[str, str | None] | None = None,
        pay_status: int | None = PAY_STATUS_PENDING,
    ) -> None:
        self.flow_id = flow_id
        self.flow_ids = dict(flow_ids or {})
        self.pay_status = pay_status
        self.resolved_records: list[str] = []
        self.marked_flow_ids: list[str] = []

    def resolve_flow_id(self, record: OAApplicationRecord) -> str | None:
        self.resolved_records.append(record.id)
        if record.id in self.flow_ids:
            return self.flow_ids[record.id]
        return self.flow_id

    def get_payment_status(self, flow_id: str) -> OAPaymentStatusRecord | None:
        if self.pay_status is None:
            return None
        return OAPaymentStatusRecord(flow_id=flow_id, pay_status=self.pay_status)

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


class FakePendingRelationService:
    def __init__(self, active_relations: list[dict[str, object]] | None = None) -> None:
        self.active_relations = [dict(relation) for relation in list(active_relations or [])]
        self.create_calls: list[dict[str, object]] = []

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, object]]:
        wanted = {str(row_id) for row_id in row_ids}
        return [
            relation
            for relation in self.active_relations
            if wanted & {str(row_id) for row_id in list(relation.get("row_ids") or [])}
        ]

    def create_active_relation(self, **kwargs: object) -> dict[str, object]:
        self.create_calls.append(dict(kwargs))
        oa_row_ids = list(kwargs["oa_row_ids"])  # type: ignore[arg-type]
        bank_transaction_ids = list(kwargs["bank_transaction_ids"])  # type: ignore[arg-type]
        relation = {
            "case_id": kwargs["relation_id"],
            "relation_id": kwargs["relation_id"],
            "row_ids": [*oa_row_ids, *bank_transaction_ids],
            "row_types": [*(["oa"] * len(oa_row_ids)), *(["bank"] * len(bank_transaction_ids))],
            "oa_row_ids": oa_row_ids,
            "bank_transaction_ids": bank_transaction_ids,
            "relation_mode": "oa_pending_payment_in_progress",
            "amount_check": dict(kwargs["amount_check"]),  # type: ignore[arg-type]
            "month_scope": kwargs["month_scope"],
            "special_metadata": {
                "origin": "oa_pending_payment_in_progress",
                "source": "oa_pending_payment_bank_relations",
                "source_action": kwargs["source_action"],
            },
        }
        self.active_relations.append(relation)
        return {
            "status": "confirmed",
            "relation": relation,
            "changed_relation_ids": [kwargs["relation_id"]],
            "affected_months": [kwargs["month_scope"]],
        }


class OaPendingPaymentCommandServiceTests(unittest.TestCase):
    def test_confirm_paid_creates_relation_then_writes_mysql_payment_status(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439011")
        relation_command = FakeRelationCommandService()
        pending_relation_service = FakePendingRelationService()
        refresh_calls: list[tuple[str, str, str]] = []
        service = _service(
            oa_records=[_oa("oa-pay-2047", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-100", "100.00")],
            relation_command=relation_command,
            pending_relation_service=pending_relation_service,
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
        self.assertEqual(relation_command.confirm_calls, [])
        self.assertEqual(len(pending_relation_service.create_calls), 1)
        create_call = pending_relation_service.create_calls[0]
        self.assertEqual(create_call["oa_row_ids"], ["oa-pay-2047"])
        self.assertEqual(create_call["bank_transaction_ids"], ["bank-100"])
        self.assertEqual(create_call["source_action"], "confirm_paid")
        self.assertEqual(create_call["idempotency_key"], "idem-1")
        self.assertEqual(create_call["amount_check"]["matched"], True)
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

    def test_link_bank_transactions_creates_relation_then_auto_writes_mysql_when_amount_matches(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439015")
        relation_command = FakeRelationCommandService()
        pending_relation_service = FakePendingRelationService()
        refresh_calls: list[tuple[str, str, str]] = []
        service = _service(
            oa_records=[_oa("oa-link", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-link", "100.00")],
            relation_command=relation_command,
            pending_relation_service=pending_relation_service,
            payment_repository=payment_repository,
            refresh_calls=refresh_calls,
        )

        payload = service.link_bank_transactions(
            {"oa_row_ids": ["oa-link"], "bank_transaction_ids": ["bank-link"], "idempotency_key": "link-1"},
            actor_id="tester",
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["action"], "oa_pending_payment_link_bank_transactions")
        self.assertEqual(payload["autoWriteback"]["code"], "written")
        self.assertEqual(payload["oaPaymentWriteback"]["flowId"], "507f1f77bcf86cd799439015")
        self.assertEqual(payment_repository.marked_flow_ids, ["507f1f77bcf86cd799439015"])
        self.assertEqual(relation_command.confirm_calls, [])
        self.assertEqual(len(pending_relation_service.create_calls), 1)
        create_call = pending_relation_service.create_calls[0]
        self.assertEqual(create_call["oa_row_ids"], ["oa-link"])
        self.assertEqual(create_call["bank_transaction_ids"], ["bank-link"])
        self.assertEqual(create_call["source_action"], "link_bank_transactions")
        self.assertEqual(
            refresh_calls,
            [
                ("workbench", "2026-06", "oa_pending_payment_link_bank_transactions"),
                ("oa_pending_payment", "2026-06", "oa_pending_payment_link_bank_transactions"),
                ("workbench", "all", "oa_pending_payment_link_bank_transactions"),
                ("oa_pending_payment", "all", "oa_pending_payment_link_bank_transactions"),
            ],
        )

    def test_link_bank_transactions_keeps_relation_without_writeback_when_amount_mismatches(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439018")
        relation_command = FakeRelationCommandService()
        pending_relation_service = FakePendingRelationService()
        service = _service(
            oa_records=[_oa("oa-link-mismatch", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-link-90", "90.00")],
            relation_command=relation_command,
            pending_relation_service=pending_relation_service,
            payment_repository=payment_repository,
        )

        payload = service.link_bank_transactions(
            {"oa_row_ids": ["oa-link-mismatch"], "bank_transaction_ids": ["bank-link-90"]},
            actor_id="tester",
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["autoWriteback"]["code"], "not_required")
        self.assertEqual(payload["oaPaymentWritebacks"], [])
        self.assertEqual(payment_repository.marked_flow_ids, [])
        self.assertEqual(relation_command.confirm_calls, [])
        self.assertEqual(len(pending_relation_service.create_calls), 1)
        self.assertEqual(pending_relation_service.create_calls[0]["amount_check"]["matched"], False)

    def test_auto_reconcile_matches_unpaired_in_progress_oa_bank_and_writes_mysql(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439019")
        relation_command = FakeRelationCommandService()
        pending_relation_service = FakePendingRelationService()
        refresh_calls: list[tuple[str, str, str]] = []
        service = _service(
            oa_records=[_oa("oa-auto", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-auto", "100.00")],
            relation_command=relation_command,
            pending_relation_service=pending_relation_service,
            payment_repository=payment_repository,
            refresh_calls=refresh_calls,
        )

        payload = service.auto_reconcile_bank_transactions({"month": "2026-06"}, actor_id="tester")

        self.assertTrue(payload["success"])
        self.assertEqual(payload["autoMatchedCount"], 1)
        self.assertEqual(payload["writebackCount"], 1)
        self.assertEqual(payload["autoMatchedRelations"][0]["oaRowIds"], ["oa-auto"])
        self.assertEqual(payload["autoMatchedRelations"][0]["bankTransactionIds"], ["bank-auto"])
        self.assertEqual(payload["oaPaymentWritebacks"][0]["flowId"], "507f1f77bcf86cd799439019")
        self.assertEqual(payload["oaPaymentWritebacks"][0]["oaRowId"], "oa-auto")
        self.assertEqual(payment_repository.marked_flow_ids, ["507f1f77bcf86cd799439019"])
        self.assertEqual(relation_command.confirm_calls, [])
        self.assertEqual(len(pending_relation_service.create_calls), 1)
        self.assertEqual(pending_relation_service.create_calls[0]["raw_payload"]["history_operation_type"], "oa_pending_payment_auto_reconcile")
        self.assertEqual(pending_relation_service.create_calls[0]["amount_check"]["rule_code"], "oa_bank_exact_amount")
        self.assertEqual(
            refresh_calls,
            [
                ("workbench", "2026-06", "oa_pending_payment_auto_reconcile"),
                ("oa_pending_payment", "2026-06", "oa_pending_payment_auto_reconcile"),
                ("workbench", "all", "oa_pending_payment_auto_reconcile"),
                ("oa_pending_payment", "all", "oa_pending_payment_auto_reconcile"),
            ],
        )

    def test_auto_reconcile_all_months_groups_matches_by_month(self) -> None:
        payment_repository = FakePaymentStatusRepository(
            flow_ids={
                "oa-auto-apr": "flow-apr",
                "oa-auto-jun": "flow-jun",
            }
        )
        relation_command = FakeRelationCommandService()
        pending_relation_service = FakePendingRelationService()
        refresh_calls: list[tuple[str, str, str]] = []
        service = _service(
            oa_records=[
                _oa(
                    "oa-auto-apr",
                    "7000.00",
                    workflow_status="in_progress",
                    month="2026-04",
                    counterparty_name="云南心诚环保科技有限公司",
                    application_date="2026-04-16",
                ),
                _oa(
                    "oa-auto-jun",
                    "100.00",
                    workflow_status="in_progress",
                    month="2026-06",
                    counterparty_name="测试供应商",
                    application_date="2026-06-17",
                ),
            ],
            transactions=[
                _bank(
                    "bank-apr",
                    "7000.00",
                    counterparty_name="云南心诚环保科技有限公司",
                    txn_date="2026-04-23",
                    trade_time="2026-04-23 17:17:57",
                ),
                _bank("bank-jun", "100.00", counterparty_name="测试供应商"),
            ],
            relation_command=relation_command,
            pending_relation_service=pending_relation_service,
            payment_repository=payment_repository,
            refresh_calls=refresh_calls,
        )

        payload = service.auto_reconcile_bank_transactions({"month": "all"}, actor_id="tester")

        self.assertTrue(payload["success"])
        self.assertEqual(payload["autoMatchedCount"], 2)
        self.assertEqual(payload["writebackCount"], 2)
        self.assertEqual(sorted(payment_repository.marked_flow_ids), ["flow-apr", "flow-jun"])
        self.assertEqual(relation_command.confirm_calls, [])
        self.assertEqual(
            sorted((call["month_scope"], [*call["oa_row_ids"], *call["bank_transaction_ids"]]) for call in pending_relation_service.create_calls),
            [
                ("2026-04", ["oa-auto-apr", "bank-apr"]),
                ("2026-06", ["oa-auto-jun", "bank-jun"]),
            ],
        )
        self.assertIn(("workbench", "2026-04", "oa_pending_payment_auto_reconcile"), refresh_calls)
        self.assertIn(("oa_pending_payment", "2026-06", "oa_pending_payment_auto_reconcile"), refresh_calls)

    def test_auto_reconcile_writes_completed_oa_when_existing_relation_is_paid(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439020", pay_status=PAY_STATUS_PENDING)
        relation_command = FakeRelationCommandService(
            [
                {
                    "case_id": "case-completed",
                    "row_ids": ["oa-completed-paid", "bank-completed"],
                    "row_types": ["oa", "bank"],
                    "relation_mode": "manual_confirmed",
                    "amount_check": {"matched": True},
                    "month_scope": "2026-06",
                }
            ]
        )
        service = _service(
            oa_records=[],
            completed_oa_records=[_oa("oa-completed-paid", "100.00", workflow_status="completed")],
            transactions=[_bank("bank-completed", "100.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
        )

        payload = service.auto_reconcile_bank_transactions({"month": "2026-06"}, actor_id="tester")

        self.assertEqual(payload["autoMatchedCount"], 0)
        self.assertEqual(payload["writebackCount"], 1)
        self.assertEqual(payload["oaPaymentWritebacks"][0]["oaRowId"], "oa-completed-paid")
        self.assertEqual(payment_repository.marked_flow_ids, ["507f1f77bcf86cd799439020"])
        self.assertEqual(relation_command.confirm_calls, [])

    def test_auto_reconcile_writes_completed_oa_from_explicit_relation_ids_when_row_types_are_missing(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439022", pay_status=PAY_STATUS_PENDING)
        relation_command = FakeRelationCommandService(
            [
                {
                    "case_id": "case-completed-explicit",
                    "row_ids": ["oa-completed-explicit", "bank-completed-explicit"],
                    "row_types": [],
                    "oa_row_ids": ["oa-completed-explicit"],
                    "bank_transaction_ids": ["bank-completed-explicit"],
                    "relation_mode": "manual_confirmed",
                    "amount_check": {"matched": True},
                    "month_scope": "2026-06",
                }
            ]
        )
        service = _service(
            oa_records=[],
            completed_oa_records=[_oa("oa-completed-explicit", "100.00", workflow_status="completed")],
            transactions=[_bank("bank-completed-explicit", "100.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
        )

        payload = service.auto_reconcile_bank_transactions({"month": "2026-06"}, actor_id="tester")

        self.assertEqual(payload["autoMatchedCount"], 0)
        self.assertEqual(payload["writebackCount"], 1)
        self.assertEqual(payload["oaPaymentWritebacks"][0]["oaRowId"], "oa-completed-explicit")
        self.assertEqual(payment_repository.marked_flow_ids, ["507f1f77bcf86cd799439022"])
        self.assertEqual(relation_command.confirm_calls, [])

    def test_auto_reconcile_existing_paid_relation_is_noop_when_oa_is_already_written(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439021", pay_status=PAY_STATUS_PAID)
        relation_command = FakeRelationCommandService(
            [
                {
                    "case_id": "case-completed",
                    "row_ids": ["oa-completed-paid", "bank-completed"],
                    "row_types": ["oa", "bank"],
                    "relation_mode": "manual_confirmed",
                    "amount_check": {"matched": True},
                    "month_scope": "2026-06",
                }
            ]
        )
        refresh_calls: list[tuple[str, str, str]] = []
        service = _service(
            oa_records=[],
            completed_oa_records=[_oa("oa-completed-paid", "100.00", workflow_status="completed")],
            transactions=[_bank("bank-completed", "100.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
            refresh_calls=refresh_calls,
        )

        payload = service.auto_reconcile_bank_transactions({"month": "2026-06"}, actor_id="tester")

        self.assertEqual(payload["autoMatchedCount"], 0)
        self.assertEqual(payload["writebackCount"], 0)
        self.assertEqual(payload["oaPaymentWritebacks"], [])
        self.assertEqual(payload["readModelRefresh"]["enqueued"], False)
        self.assertEqual(payment_repository.marked_flow_ids, [])
        self.assertEqual(refresh_calls, [])
        self.assertEqual(relation_command.confirm_calls, [])

    def test_auto_reconcile_reports_skipped_exact_match_when_flow_id_is_missing(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id=None)
        relation_command = FakeRelationCommandService()
        service = _service(
            oa_records=[
                _oa(
                    "oa-xincheng-7000",
                    "7000.00",
                    workflow_status="in_progress",
                    month="2026-04",
                    counterparty_name="云南心诚环保科技有限公司",
                    applicant="樊祖芳",
                    project_name="昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目",
                    reason="申请支付昭通烟厂能源系统维护项目：环保数采仪1套，W5100HB-IIIPro，品牌;万维,合同金额：7000元，全额付款7000元。",
                    application_date="2026-04-16",
                )
            ],
            transactions=[
                _bank(
                    "bank-xincheng-7000",
                    "7000.00",
                    counterparty_name="云南心诚环保科技有限公司",
                    txn_date="2026-04-23",
                    trade_time="2026-04-23 17:17:57",
                )
            ],
            relation_command=relation_command,
            payment_repository=payment_repository,
        )

        payload = service.auto_reconcile_bank_transactions({"month": "2026-04"}, actor_id="tester")

        self.assertEqual(payload["autoMatchedCount"], 0)
        self.assertEqual(payload["writebackCount"], 0)
        self.assertEqual(len(payload["skippedAutoMatches"]), 1)
        skipped = payload["skippedAutoMatches"][0]
        self.assertEqual(skipped["oaRowIds"], ["oa-xincheng-7000"])
        self.assertEqual(skipped["bankTransactionIds"], ["bank-xincheng-7000"])
        self.assertEqual(skipped["ruleCode"], "oa_bank_exact_amount")
        self.assertEqual(skipped["errorCode"], "oa_flow_id_not_found")
        self.assertEqual(relation_command.confirm_calls, [])

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
        relation_command = FakeRelationCommandService()
        pending_relation_service = FakePendingRelationService(
            [
                {
                    "case_id": "case-progress",
                    "relation_id": "case-progress",
                    "row_ids": ["oa-progress", "bank-linked"],
                    "row_types": ["oa", "bank"],
                    "oa_row_ids": ["oa-progress"],
                    "bank_transaction_ids": ["bank-linked"],
                    "relation_mode": "oa_pending_payment_in_progress",
                    "amount_check": {"matched": True},
                    "month_scope": "2026-06",
                    "special_metadata": {
                        "origin": "oa_pending_payment_in_progress",
                        "source": "oa_pending_payment_bank_relations",
                    },
                }
            ]
        )
        service = _service(
            oa_records=[_oa("oa-progress", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-linked", "100.00"), _bank("bank-free", "80.00")],
            relation_command=relation_command,
            pending_relation_service=pending_relation_service,
            payment_repository=payment_repository,
        )

        payload = service.bank_transaction_candidates({"relation_status": ["linked_in_progress"]})

        self.assertEqual([row["id"] for row in payload["rows"]], ["bank-linked"])
        self.assertEqual(payload["rows"][0]["relationStatusLabel"], "已关联进行中OA")

    def test_bank_transaction_candidates_uses_selected_oa_month_scope(self) -> None:
        service = _service(
            oa_records=[_oa("oa-june", "2152.80", workflow_status="in_progress", month="2026-06")],
            transactions=[
                _bank("bank-june", "2152.80", txn_date="2026-06-18", trade_time="2026-06-18 10:00:00"),
                _bank("bank-may", "2152.80", txn_date="2026-05-18", trade_time="2026-05-18 10:00:00"),
            ],
            relation_command=FakeRelationCommandService(),
            payment_repository=FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439011"),
        )

        payload = service.bank_transaction_candidates({
            "oa_row_ids": ["oa-june"],
            "keyword": ["2152"],
        })

        self.assertEqual([row["id"] for row in payload["rows"]], ["bank-june"])
        self.assertEqual(payload["filters"]["oaRowIds"], ["oa-june"])
        self.assertEqual(payload["filters"]["monthScopes"], ["2026-06"])

    def test_bank_transaction_candidates_with_selected_oa_does_not_fallback_all_when_month_missing(self) -> None:
        service = _service(
            oa_records=[_oa("oa-no-month", "2152.80", workflow_status="in_progress", month="")],
            transactions=[_bank("bank-history", "2152.80", txn_date="2026-05-18")],
            relation_command=FakeRelationCommandService(),
            payment_repository=FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439011"),
        )

        payload = service.bank_transaction_candidates({
            "oa_row_ids": ["oa-no-month"],
            "keyword": ["2152"],
        })

        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["filters"]["oaRowIds"], ["oa-no-month"])
        self.assertEqual(payload["filters"]["monthScopes"], [])

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
    completed_oa_records: list[OAApplicationRecord] | None = None,
    transactions: list[BankTransaction],
    relation_command: FakeRelationCommandService,
    pending_relation_service: FakePendingRelationService | None = None,
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
        completed_oa_projection=StaticOAProjection(completed_oa_records or []),
        relation_command_service=relation_command,
        pending_relation_service=pending_relation_service or FakePendingRelationService(),
        payment_status_repository=payment_repository,
        enqueue_workbench_refresh=enqueue_workbench,
        enqueue_oa_pending_payment_refresh=enqueue_oa_pending,
    )


def _oa(
    record_id: str,
    amount: str,
    *,
    workflow_status: str,
    month: str = "2026-06",
    counterparty_name: str = "测试供应商",
    applicant: str = "刘际涛",
    project_name: str = "测试项目",
    reason: str = "测试付款",
    application_date: str = "2026-06-17",
) -> OAApplicationRecord:
    return OAApplicationRecord(
        id=record_id,
        month=month,
        section="open",
        case_id=None,
        applicant=applicant,
        project_name=project_name,
        apply_type="支付申请",
        amount=amount,
        counterparty_name=counterparty_name,
        reason=reason,
        relation_code="pending_match",
        relation_label="待找流水",
        relation_tone="warn",
        workflow_status=workflow_status,
        detail_fields={
            "流程实例ID": "proc-from-record",
            "Mongo文档ID": record_id.removeprefix("oa-pay-"),
            "申请日期": application_date,
        },
    )


def _bank(
    bank_id: str,
    amount: str,
    *,
    direction: TransactionDirection = TransactionDirection.OUTFLOW,
    counterparty_name: str = "测试供应商",
    txn_date: str = "2026-06-17",
    trade_time: str = "2026-06-17 10:00:00",
) -> BankTransaction:
    signed_amount = -Decimal(amount) if direction == TransactionDirection.OUTFLOW else Decimal(amount)
    return BankTransaction(
        id=bank_id,
        account_no="622200001234",
        txn_direction=direction,
        counterparty_name_raw=counterparty_name,
        amount=Decimal(amount),
        signed_amount=signed_amount,
        txn_date=txn_date,
        trade_time=trade_time,
        imported_bank_name="测试银行",
        imported_bank_last4="1234",
    )


if __name__ == "__main__":
    unittest.main()
