from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_exception_application_service import (
    WorkbenchExceptionApplicationConflict,
    WorkbenchExceptionApplicationService,
)
from fin_ops_platform.services.workbench_exception_case_service import WorkbenchExceptionCaseService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_command_service import (
    CallbackWorkbenchRelationRepository,
    WorkbenchRelationCommandService,
)


class StaticWorkbenchRows:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = {
            (str(row["type"]), str(row["id"])): dict(row)
            for row in rows
        }

    def __call__(
        self,
        month: str,
        row_ids: list[str],
        row_types: list[str],
    ) -> list[dict[str, object]]:
        return [
            dict(self._rows[(row_type, row_id)])
            for row_type, row_id in zip(row_types, row_ids, strict=True)
        ]


class FreshRelationFacade:
    def get_by_row_ids(self, row_ids: list[str], **kwargs: object) -> dict[str, object]:
        return {
            "status": "fresh",
            "rows": [],
            "groups": [],
            "read_model_scope_keys": list(kwargs.get("scope_keys_hint") or ["2026-05"]),
            "stale_reasons": [],
            "refresh_enqueued": False,
        }


class WriteBlockingPairRelationService(WorkbenchPairRelationService):
    def create_active_relation(self, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("WorkbenchExceptionApplicationService must delegate relation writes to command service.")


def relation_command_service_for(pair_relation_service: WorkbenchPairRelationService) -> WorkbenchRelationCommandService:
    def save_snapshot(snapshot: dict[str, object], *, changed_case_ids: list[str]) -> None:
        _ = changed_case_ids
        restored = WorkbenchPairRelationService.from_snapshot(snapshot)
        pair_relation_service._pair_relations = restored._pair_relations
        pair_relation_service._pair_relation_history = restored._pair_relation_history

    return WorkbenchRelationCommandService(
        relation_repository=CallbackWorkbenchRelationRepository(
            load_snapshot=pair_relation_service.snapshot,
            save_snapshot=save_snapshot,
        ),
    )


def oa_row(row_id: str = "oa-001", amount: str = "100.00") -> dict[str, object]:
    return {
        "id": row_id,
        "type": "oa",
        "month": "2026-05",
        "apply_type": "付款申请",
        "amount": amount,
        "counterparty_name": "供应商A",
    }


def expense_bank_row(
    row_id: str = "bank-001",
    amount: str = "100.00",
    *,
    summary: str = "支付供应商A",
) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "month": "2026-05",
        "pay_receive_time": "2026-05-11 09:00:00",
        "debit_amount": amount,
        "credit_amount": "",
        "summary": summary,
        "counterparty_name": "供应商A",
    }


def income_bank_row(row_id: str = "bank-income-001", amount: str = "100.00") -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "month": "2026-05",
        "pay_receive_time": "2026-05-11 09:00:00",
        "debit_amount": "",
        "credit_amount": amount,
        "summary": "客户回款",
        "counterparty_name": "客户A",
    }


def input_invoice_row(row_id: str = "invoice-001", amount: str = "100.00") -> dict[str, object]:
    return {
        "id": row_id,
        "type": "invoice",
        "month": "2026-05",
        "issue_date": "2026-05-10",
        "total_with_tax": amount,
        "invoice_type": "进项发票",
        "seller_name": "供应商A",
    }


class WorkbenchExceptionApplicationServiceTests(unittest.TestCase):
    def build_service(
        self,
        rows: list[dict[str, object]],
        *,
        case_service: WorkbenchExceptionCaseService | None = None,
        pair_relation_service: WorkbenchPairRelationService | None = None,
        exception_evidence: list[dict[str, object]] | None = None,
        relation_command_service: object | None = None,
    ) -> WorkbenchExceptionApplicationService:
        pair_service = pair_relation_service or WorkbenchPairRelationService()
        return WorkbenchExceptionApplicationService(
            row_provider=StaticWorkbenchRows(rows),
            case_service=case_service or WorkbenchExceptionCaseService(),
            exception_evidence_provider=(
                (lambda _month, _row_ids, _row_types: [dict(item) for item in exception_evidence])
                if exception_evidence is not None
                else None
            ),
            relation_command_service=relation_command_service or relation_command_service_for(pair_service),
            source_versions_provider=lambda: {"workbench_exception_rules_version": "exception_rules_v1"},
        )

    def test_preview_oa_and_expense_bank_missing_invoice_has_no_side_effects(self) -> None:
        case_service = WorkbenchExceptionCaseService()
        pair_relation_service = WorkbenchPairRelationService()
        exception_evidence = [{"evidence_id": "evidence-1", "rule_code": "oa_bank_exact_amount"}]
        service = self.build_service(
            [oa_row(), expense_bank_row()],
            case_service=case_service,
            pair_relation_service=pair_relation_service,
            exception_evidence=exception_evidence,
        )

        preview = service.preview({"month": "2026-05", "row_ids": ["oa-001", "bank-001"], "row_types": ["oa", "bank"]})

        self.assertEqual(preview["scenario"]["business_line"], "expense")
        self.assertEqual(preview["scenario"]["scenario_code"], "expense_oa_bank_missing_input_invoice_equal")
        self.assertEqual(preview["amount_summary"]["expense_relation"], "oa_equals_bank_missing_input_invoice")
        self.assertEqual([action["action_code"] for action in preview["available_actions"]], ["wait_input_invoice"])
        self.assertEqual(preview["candidate_evidence"], exception_evidence)
        self.assertTrue(preview["can_apply"])
        self.assertEqual(case_service.snapshot()["cases"], {})
        self.assertEqual(pair_relation_service.snapshot()["pair_relations"], {})

    def test_preview_requires_aligned_typed_identities_and_preserves_cross_pane_collision(self) -> None:
        rows = [
            expense_bank_row(row_id="same-text-id"),
            input_invoice_row(row_id="same-text-id"),
        ]
        service = self.build_service(rows)

        with self.assertRaisesRegex(ValueError, "row_ids and row_types"):
            service.preview({"month": "2026-05", "row_ids": ["same-text-id"]})
        preview = service.preview(
            {
                "month": "2026-05",
                "row_ids": ["same-text-id", "same-text-id"],
                "row_types": ["bank", "invoice"],
            }
        )

        self.assertEqual(preview["scenario"]["scenario_code"], "expense_bank_input_invoice_missing_oa_equal")
        self.assertTrue(preview["can_apply"])

    def test_apply_wait_input_invoice_creates_open_v2_case_without_pair_relation(self) -> None:
        pair_relation_service = WorkbenchPairRelationService()
        service = self.build_service(
            [oa_row(), expense_bank_row()],
            pair_relation_service=pair_relation_service,
        )

        result = service.apply(
            {
                "month": "2026-05",
                "row_ids": ["oa-001", "bank-001"],
                "row_types": ["oa", "bank"],
                "scenario_code": "expense_oa_bank_missing_input_invoice_equal",
                "action_code": "wait_input_invoice",
                "payload": {"note": "继续追票"},
            },
            actor="finance-user",
        )

        case = result["case"]
        self.assertTrue(result["success"])
        self.assertEqual(case["schema_version"], 2)
        self.assertEqual(case["status"], "open")
        self.assertEqual(case["business_line"], "expense")
        self.assertEqual(case["scenario_code"], "expense_oa_bank_missing_input_invoice_equal")
        self.assertEqual(case["resolution"]["action_code"], "wait_input_invoice")
        self.assertEqual(case["resolution"]["note"], "继续追票")
        self.assertEqual(case["workflow_projection"]["state"], "WAIT_INPUT_INVOICE")
        self.assertEqual(case["candidate_ids"], [])
        self.assertEqual(case["row_ids"], ["oa-001", "bank-001"])
        self.assertEqual(case["row_types"], ["oa", "bank"])
        self.assertIsNone(result["pair_relation"])
        self.assertNotIn("workbench_refresh_required", result)
        self.assertEqual(pair_relation_service.snapshot()["pair_relations"], {})

    def test_apply_three_party_closed_creates_closed_case_and_pair_relation(self) -> None:
        pair_relation_service = WorkbenchPairRelationService()
        service = self.build_service(
            [oa_row(), expense_bank_row(), input_invoice_row()],
            pair_relation_service=pair_relation_service,
        )

        result = service.apply(
            {
                "month": "2026-05",
                "row_ids": ["oa-001", "bank-001", "invoice-001"],
                "row_types": ["oa", "bank", "invoice"],
                "scenario_code": "expense_all_equal",
                "action_code": "confirm_closed",
                "payload": {},
            },
            actor="finance-user",
        )

        self.assertEqual(result["case"]["status"], "closed")
        self.assertEqual(result["case"]["resolution"]["result_status"], "closed")
        relation = result["pair_relation"]
        self.assertIsNotNone(relation)
        self.assertEqual(relation["case_id"], result["case"]["id"])
        self.assertEqual(relation["exception_case_id"], result["case"]["id"])
        self.assertEqual(relation["relation_mode"], "normal_match")
        self.assertCountEqual(relation["row_ids"], ["oa-001", "bank-001", "invoice-001"])
        self.assertEqual(pair_relation_service.get_active_relation_by_case_id(result["case"]["id"]), relation)

    def test_apply_closed_exception_delegates_pair_relation_to_command_service(self) -> None:
        pair_relation_service = WriteBlockingPairRelationService()
        service = self.build_service(
            [oa_row(), expense_bank_row(), input_invoice_row()],
            pair_relation_service=pair_relation_service,
        )

        result = service.apply(
            {
                "month": "2026-05",
                "row_ids": ["oa-001", "bank-001", "invoice-001"],
                "row_types": ["oa", "bank", "invoice"],
                "scenario_code": "expense_all_equal",
                "action_code": "confirm_closed",
                "payload": {},
            },
            actor="finance-user",
        )

        relation = result["pair_relation"]
        self.assertEqual(relation["relation_mode"], "normal_match")
        self.assertEqual(pair_relation_service.get_active_relation_by_case_id(result["case"]["id"]), relation)

    def test_apply_auto_oa_exempt_writes_structured_relation_fields(self) -> None:
        service = self.build_service([expense_bank_row(summary="银行手续费")])

        result = service.apply(
            {
                "month": "2026-05",
                "row_ids": ["bank-001"],
                "row_types": ["bank"],
                "scenario_code": "expense_only_bank_auto_oa_exempt",
                "action_code": "confirm_oa_exempt_auto",
                "payload": {},
            },
            actor="system",
        )

        relation = result["pair_relation"]
        self.assertEqual(result["case"]["status"], "closed")
        self.assertEqual(relation["relation_mode"], "oa_exempt")
        self.assertEqual(relation["oa_exemption"]["source"], "auto")
        self.assertEqual(relation["oa_exemption"]["reason_code"], "bank_fee")
        self.assertEqual(relation["oa_exemption"]["rule_version"], "exception_rules_v1")
        self.assertIsNone(relation["oa_exemption"]["confirmed_by"])
        self.assertIn("自动免OA", relation["display_tags"])

    def test_apply_manual_oa_exempt_writes_confirmer_timestamp_and_note(self) -> None:
        service = self.build_service([expense_bank_row(), input_invoice_row()])

        result = service.apply(
            {
                "month": "2026-05",
                "row_ids": ["bank-001", "invoice-001"],
                "row_types": ["bank", "invoice"],
                "scenario_code": "expense_bank_input_invoice_missing_oa_equal",
                "action_code": "confirm_oa_exempt_manual",
                "payload": {
                    "reason_code": "manual_confirmed",
                    "reason_label": "人工确认免 OA",
                    "note": "供应商无需 OA",
                },
            },
            actor="finance-user",
        )

        relation = result["pair_relation"]
        self.assertEqual(relation["relation_mode"], "oa_exempt")
        self.assertEqual(relation["oa_exemption"]["source"], "manual")
        self.assertEqual(relation["oa_exemption"]["confirmed_by"], "finance-user")
        self.assertIsInstance(relation["oa_exemption"]["confirmed_at"], str)
        self.assertTrue(relation["oa_exemption"]["confirmed_at"])
        self.assertEqual(relation["oa_exemption"]["note"], "供应商无需 OA")
        self.assertIn("人工免OA", relation["display_tags"])

    def test_repeated_apply_is_idempotent_for_case_and_relation(self) -> None:
        case_service = WorkbenchExceptionCaseService()
        pair_relation_service = WorkbenchPairRelationService()
        service = self.build_service(
            [oa_row(), expense_bank_row(), input_invoice_row()],
            case_service=case_service,
            pair_relation_service=pair_relation_service,
        )
        payload = {
            "month": "2026-05",
            "row_ids": ["oa-001", "bank-001", "invoice-001"],
            "row_types": ["oa", "bank", "invoice"],
            "scenario_code": "expense_all_equal",
            "action_code": "confirm_closed",
            "payload": {},
        }

        first = service.apply(payload, actor="finance-user")
        second = service.apply(payload, actor="finance-user")

        self.assertEqual(first["case"]["id"], second["case"]["id"])
        self.assertEqual(first["pair_relation"]["case_id"], second["pair_relation"]["case_id"])
        self.assertEqual(len(case_service.snapshot()["cases"]), 1)
        self.assertEqual(len(pair_relation_service.snapshot()["pair_relations"]), 1)

    def test_apply_rejects_active_relation_conflict(self) -> None:
        pair_relation_service = WorkbenchPairRelationService()
        pair_relation_service.create_active_relation(
            case_id="CASE-EXISTING",
            row_ids=["bank-001"],
            row_types=["bank"],
            relation_mode="manual_confirmed",
            created_by="tester",
            month_scope="2026-05",
        )
        service = self.build_service(
            [expense_bank_row()],
            pair_relation_service=pair_relation_service,
        )

        with self.assertRaises(WorkbenchExceptionApplicationConflict) as context:
            service.apply(
                {
                    "month": "2026-05",
                    "row_ids": ["bank-001"],
                    "row_types": ["bank"],
                    "scenario_code": "expense_only_bank_auto_oa_exempt",
                    "action_code": "confirm_oa_exempt_auto",
                    "payload": {},
                },
                actor="system",
            )

        self.assertEqual(context.exception.code, "active_pair_relation_conflict")

    def test_preview_income_side_with_oa_returns_data_anomaly(self) -> None:
        service = self.build_service([oa_row(), income_bank_row()])

        preview = service.preview({"month": "2026-05", "row_ids": ["oa-001", "bank-income-001"], "row_types": ["oa", "bank"]})

        self.assertEqual(preview["scenario"]["business_line"], "data_anomaly")
        self.assertEqual(preview["scenario"]["scenario_code"], "income_contains_oa_data_anomaly")
        self.assertEqual([action["action_code"] for action in preview["available_actions"]], ["income_data_anomaly_manual_review"])
        self.assertTrue(preview["can_apply"])


if __name__ == "__main__":
    unittest.main()
