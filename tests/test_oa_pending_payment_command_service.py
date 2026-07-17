from __future__ import annotations

from decimal import Decimal
import unittest
from types import SimpleNamespace

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord, PAY_STATUS_PAID, PAY_STATUS_PENDING
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


class FakePaidStatusSnapshotWriter:
    def __init__(
        self,
        *,
        affected_scope_keys: tuple[str, ...] = ("2026-06",),
        error: Exception | None = None,
    ) -> None:
        self.affected_scope_keys = affected_scope_keys
        self.error = error
        self.calls: list[list[OAApplicationRecord]] = []

    def record_paid_statuses(self, *, records: list[OAApplicationRecord]) -> object:
        self.calls.append(list(records))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(oa_pending_payment_changed_scopes=self.affected_scope_keys)


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
    def test_manual_confirm_paid_command_is_not_exposed(self) -> None:
        self.assertFalse(hasattr(OaPendingPaymentCommandService, "confirm_paid"))

    def test_link_bank_transactions_creates_relation_then_auto_writes_mysql_when_amount_matches(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439015")
        relation_command = FakeRelationCommandService()
        pending_relation_service = FakePendingRelationService()
        refresh_calls: list[tuple[str, str, str]] = []
        snapshot_writer = FakePaidStatusSnapshotWriter()
        service = _service(
            oa_records=[_oa("oa-link", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-link", "100.00")],
            relation_command=relation_command,
            pending_relation_service=pending_relation_service,
            payment_repository=payment_repository,
            snapshot_writer=snapshot_writer,
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
        self.assertEqual([[record.id for record in call] for call in snapshot_writer.calls], [["oa-link"]])
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
            ],
        )
        self.assertEqual(payload["read_model_scope_keys"], ["2026-06"])
        self.assertEqual(
            payload["freshness_targets"],
            [{"read_model_key": "oa_pending_payment", "scope_key": "2026-06"}],
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

    def test_writeback_paid_writes_completed_oa_when_existing_relation_is_paid(self) -> None:
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
        refresh_calls: list[tuple[str, str, str]] = []
        service = _service(
            oa_records=[],
            completed_oa_records=[_oa("oa-completed-paid", "100.00", workflow_status="completed")],
            transactions=[_bank("bank-completed", "100.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
            refresh_calls=refresh_calls,
        )

        payload = service.writeback_paid({"oa_row_ids": ["oa-completed-paid"]}, actor_id="tester")

        self.assertEqual(payload["action"], "oa_pending_payment_writeback_paid")
        self.assertEqual(payload["writebackCount"], 1)
        self.assertEqual(payload["oaPaymentWritebacks"][0]["oaRowId"], "oa-completed-paid")
        self.assertEqual(payment_repository.marked_flow_ids, ["507f1f77bcf86cd799439020"])
        self.assertEqual(relation_command.confirm_calls, [])
        self.assertEqual(
            refresh_calls,
            [
                ("workbench", "2026-06", "oa_pending_payment_writeback_paid"),
                ("oa_pending_payment", "2026-06", "oa_pending_payment_writeback_paid"),
                ("workbench", "all", "oa_pending_payment_writeback_paid"),
            ],
        )

    def test_writeback_paid_uses_full_relation_for_amount_check_but_only_writes_requested_oa(self) -> None:
        payment_repository = FakePaymentStatusRepository(
            flow_id=None,
            flow_ids={
                "oa-completed-paid-a": "507f1f77bcf86cd799439025",
                "oa-completed-paid-b": "507f1f77bcf86cd799439026",
            },
            pay_status=PAY_STATUS_PENDING,
        )
        relation_command = FakeRelationCommandService(
            [
                {
                    "case_id": "case-completed-group",
                    "row_ids": ["oa-completed-paid-a", "oa-completed-paid-b", "bank-completed-group"],
                    "row_types": ["oa", "oa", "bank"],
                    "relation_mode": "manual_confirmed",
                    "amount_check": {"matched": True},
                    "month_scope": "2026-06",
                }
            ]
        )
        service = _service(
            oa_records=[],
            completed_oa_records=[
                _oa("oa-completed-paid-a", "100.00", workflow_status="completed"),
                _oa("oa-completed-paid-b", "100.00", workflow_status="completed"),
            ],
            transactions=[_bank("bank-completed-group", "200.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
        )

        payload = service.writeback_paid({"oa_row_ids": ["oa-completed-paid-a"]}, actor_id="tester")

        self.assertEqual(payload["writebackCount"], 1)
        self.assertEqual(payload["oaPaymentWritebacks"][0]["oaRowId"], "oa-completed-paid-a")
        self.assertEqual(payment_repository.marked_flow_ids, ["507f1f77bcf86cd799439025"])
        self.assertEqual(payment_repository.resolved_records, ["oa-completed-paid-a"])

    def test_writeback_paid_writes_in_progress_oa_when_pending_relation_is_paid(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439023", pay_status=PAY_STATUS_PENDING)
        pending_relation_service = FakePendingRelationService(
            [
                {
                    "case_id": "case-progress",
                    "relation_id": "case-progress",
                    "row_ids": ["oa-progress-paid", "bank-progress"],
                    "row_types": ["oa", "bank"],
                    "oa_row_ids": ["oa-progress-paid"],
                    "bank_transaction_ids": ["bank-progress"],
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
            oa_records=[_oa("oa-progress-paid", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-progress", "100.00")],
            relation_command=FakeRelationCommandService(),
            pending_relation_service=pending_relation_service,
            payment_repository=payment_repository,
        )

        payload = service.writeback_paid({"oa_row_ids": ["oa-progress-paid"]}, actor_id="tester")

        self.assertEqual(payload["writebackCount"], 1)
        self.assertEqual(payload["oaPaymentWritebacks"][0]["oaRowId"], "oa-progress-paid")
        self.assertEqual(payment_repository.marked_flow_ids, ["507f1f77bcf86cd799439023"])

    def test_writeback_paid_is_noop_when_oa_is_already_written(self) -> None:
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

        payload = service.writeback_paid({"oa_row_ids": ["oa-completed-paid"]}, actor_id="tester")

        self.assertEqual(payload["writebackCount"], 0)
        self.assertEqual(payload["oaPaymentWritebacks"], [])
        self.assertEqual(payload["readModelRefresh"]["enqueued"], False)
        self.assertEqual(payload["operation_barrier_targets"], [])
        self.assertEqual(payment_repository.marked_flow_ids, [])
        self.assertEqual(refresh_calls, [])
        self.assertEqual(relation_command.confirm_calls, [])

    def test_writeback_paid_repairs_snapshot_when_external_status_is_already_paid(self) -> None:
        payment_repository = FakePaymentStatusRepository(
            flow_id="507f1f77bcf86cd799439021",
            pay_status=PAY_STATUS_PAID,
        )
        snapshot_writer = FakePaidStatusSnapshotWriter(affected_scope_keys=("2026-06",))
        refresh_calls: list[tuple[str, str, str]] = []
        service = _service(
            oa_records=[],
            completed_oa_records=[_oa("oa-completed-paid", "100.00", workflow_status="completed")],
            transactions=[_bank("bank-completed", "100.00")],
            relation_command=FakeRelationCommandService(
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
            ),
            payment_repository=payment_repository,
            snapshot_writer=snapshot_writer,
            refresh_calls=refresh_calls,
        )

        payload = service.writeback_paid({"oa_row_ids": ["oa-completed-paid"]}, actor_id="tester")

        self.assertEqual(payload["writebackCount"], 0)
        self.assertEqual(payment_repository.marked_flow_ids, [])
        self.assertEqual([[record.id for record in call] for call in snapshot_writer.calls], [["oa-completed-paid"]])
        self.assertTrue(payload["readModelRefresh"]["enqueued"])
        self.assertIn(("oa_pending_payment", "2026-06", "oa_pending_payment_writeback_paid"), refresh_calls)

    def test_writeback_paid_surfaces_retryable_error_when_snapshot_commit_fails(self) -> None:
        payment_repository = FakePaymentStatusRepository(
            flow_id="507f1f77bcf86cd799439021",
            pay_status=PAY_STATUS_PENDING,
        )
        service = _service(
            oa_records=[],
            completed_oa_records=[_oa("oa-completed-paid", "100.00", workflow_status="completed")],
            transactions=[_bank("bank-completed", "100.00")],
            relation_command=FakeRelationCommandService(
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
            ),
            payment_repository=payment_repository,
            snapshot_writer=FakePaidStatusSnapshotWriter(error=RuntimeError("outbox unavailable")),
        )

        with self.assertRaises(OaPendingPaymentError) as context:
            service.writeback_paid({"oa_row_ids": ["oa-completed-paid"]}, actor_id="tester")

        self.assertEqual(context.exception.error_code, "oa_payment_status_snapshot_write_failed")
        self.assertEqual(payment_repository.marked_flow_ids, ["507f1f77bcf86cd799439021"])

    def test_writeback_paid_rejects_row_without_paid_relation(self) -> None:
        payment_repository = FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439024")
        relation_command = FakeRelationCommandService()
        service = _service(
            oa_records=[_oa("oa-not-paid", "100.00", workflow_status="in_progress")],
            transactions=[_bank("bank-free", "100.00")],
            relation_command=relation_command,
            payment_repository=payment_repository,
        )

        with self.assertRaises(OaPendingPaymentError) as context:
            service.writeback_paid({"oa_row_ids": ["oa-not-paid"]}, actor_id="tester")

        self.assertEqual(context.exception.error_code, "oa_payment_status_not_paid")
        self.assertEqual(payment_repository.marked_flow_ids, [])
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

    def test_bank_transaction_candidates_filters_by_relation_status_tabs(self) -> None:
        relation_command = FakeRelationCommandService(
            [
                {
                    "case_id": "case-matched",
                    "row_ids": ["oa-completed", "bank-matched"],
                    "row_types": ["oa", "bank"],
                    "relation_mode": "manual_confirmed",
                    "amount_check": {"matched": True},
                }
            ]
        )
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
            transactions=[
                _bank("bank-free", "80.00", trade_time="2026-06-19 10:00:00"),
                _bank("bank-matched", "90.00", trade_time="2026-06-18 10:00:00"),
                _bank("bank-linked", "100.00", trade_time="2026-06-17 10:00:00"),
            ],
            relation_command=relation_command,
            pending_relation_service=pending_relation_service,
            payment_repository=FakePaymentStatusRepository(flow_id="507f1f77bcf86cd799439012"),
        )

        all_payload = service.bank_transaction_candidates({"relation_status": ["all"]})
        unmatched_payload = service.bank_transaction_candidates({"relation_status": ["unmatched"]})
        matched_payload = service.bank_transaction_candidates({"relation_status": ["matched"]})
        linked_payload = service.bank_transaction_candidates({"relation_status": ["linked_in_progress"]})

        self.assertEqual([row["id"] for row in all_payload["rows"]], ["bank-free", "bank-matched", "bank-linked"])
        self.assertEqual([row["id"] for row in unmatched_payload["rows"]], ["bank-free"])
        self.assertEqual([row["id"] for row in matched_payload["rows"]], ["bank-matched"])
        self.assertEqual([row["id"] for row in linked_payload["rows"]], ["bank-linked"])

    def test_bank_transaction_candidates_with_selected_oa_returns_all_months(self) -> None:
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

        self.assertEqual([row["id"] for row in payload["rows"]], ["bank-june", "bank-may"])
        self.assertEqual(payload["filters"]["oaRowIds"], ["oa-june"])
        self.assertNotIn("monthScopes", payload["filters"])

    def test_bank_transaction_candidates_with_selected_oa_missing_month_still_returns_all(self) -> None:
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

        self.assertEqual([row["id"] for row in payload["rows"]], ["bank-history"])
        self.assertEqual(payload["filters"]["oaRowIds"], ["oa-no-month"])
        self.assertNotIn("monthScopes", payload["filters"])


def _service(
    *,
    oa_records: list[OAApplicationRecord],
    completed_oa_records: list[OAApplicationRecord] | None = None,
    transactions: list[BankTransaction],
    relation_command: FakeRelationCommandService,
    pending_relation_service: FakePendingRelationService | None = None,
    payment_repository: FakePaymentStatusRepository,
    snapshot_writer: FakePaidStatusSnapshotWriter | None = None,
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
        payment_status_snapshot_writer=snapshot_writer
        or FakePaidStatusSnapshotWriter(
            affected_scope_keys=() if payment_repository.pay_status == PAY_STATUS_PAID else ("2026-06",)
        ),
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
        section="unpaired",
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
