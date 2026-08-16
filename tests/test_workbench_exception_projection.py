import unittest

from fin_ops_platform.services.workbench_exception_projection import (
    EXCEPTION_PROJECTION_VERSION,
    WorkbenchExceptionProjectionService,
)
from fin_ops_platform.services.workbench_override_service import WorkbenchOverrideService
from fin_ops_platform.services.workbench_row_identity import workbench_row_identity_key


def oa_row(row_id: str = "oa-001") -> dict[str, object]:
    return {
        "id": row_id,
        "type": "oa",
        "amount": "120.00",
        "counterparty_name": "云上客户",
        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
        "available_actions": ["detail", "confirm_link"],
        "summary_fields": {"OA和流水关联情况": "待找流水与发票", "备注": ""},
        "detail_fields": {"备注": ""},
    }


def bank_row(row_id: str = "bk-001") -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "debit_amount": "120.00",
        "credit_amount": "",
        "counterparty_name": "云上客户",
        "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
        "available_actions": ["detail", "view_relation", "cancel_link"],
        "summary_fields": {"和发票关联情况": "待匹配"},
        "detail_fields": {"备注": ""},
    }


def invoice_row(row_id: str = "iv-001") -> dict[str, object]:
    return {
        "id": row_id,
        "type": "invoice",
        "month": "2026-05",
        "total_with_tax": "120.00",
        "invoice_bank_relation": {
            "code": "pending_collection",
            "label": "待匹配流水",
            "tone": "warn",
        },
        "available_actions": ["detail", "confirm_link"],
        "detail_fields": {"备注": ""},
    }


class WorkbenchExceptionProjectionServiceTests(unittest.TestCase):
    def test_open_case_projection_contains_row_override_and_group_metadata(self) -> None:
        service = WorkbenchExceptionProjectionService()
        case_payload = {
            "id": "WEX-000001",
            "status": "open",
            "row_ids": ["oa-001"],
            "business_line": "expense",
            "scenario_code": "expense_oa_bank_missing_input_invoice_equal",
            "scenario_label": "OA 和支出流水一致，缺进项发票",
            "rule_version": "exception_rules_v1",
            "resolution": {"action_code": "wait_input_invoice", "action_label": "等待进项发票"},
            "workflow_projection": {"state": "WAIT_INPUT_INVOICE"},
            "amount_summary": {"oa_total": "120.00"},
            "audit": {"created_by": "tester", "created_at": "2026-05-11T09:00:00+00:00"},
            "display_tags": ["追票"],
            "comment": "缺进项发票，等待补票",
        }

        projection = service.project_exception_case(case_payload, [oa_row()])

        override = projection["row_overrides"]["oa-001"]
        self.assertEqual(override["projection_version"], EXCEPTION_PROJECTION_VERSION)
        self.assertEqual(override["case_id"], "WEX-000001")
        self.assertEqual(override["exception_case_id"], "WEX-000001")
        self.assertEqual(override["relation"]["code"], "wait_input_invoice")
        self.assertEqual(override["relation"]["tone"], "danger")
        self.assertEqual(override["available_actions"], ["detail"])
        self.assertTrue(override["handled_exception"])
        self.assertEqual(override["detail_note"], "缺进项发票，等待补票")
        self.assertEqual(override["scenario"]["code"], "expense_oa_bank_missing_input_invoice_equal")
        self.assertEqual(override["resolution"]["action_code"], "wait_input_invoice")
        self.assertEqual(override["display_tags"], ["追票"])
        self.assertEqual(projection["group_metadata"]["group_type"], "open_exception")
        self.assertIsNone(projection["processed_exception_summary"])

    def test_closed_relation_projection_contains_processed_summary_and_oa_exempt_tags(self) -> None:
        service = WorkbenchExceptionProjectionService()
        relation_payload = {
            "case_id": "WEX-000002",
            "exception_case_id": "WEX-000002",
            "status": "active",
            "row_ids": ["bk-001"],
            "row_types": ["bank"],
            "relation_mode": "oa_exempt",
            "display_tags": ["自动免OA", "工资"],
            "oa_exemption": {
                "source": "auto",
                "reason_code": "salary",
                "reason_label": "工资",
                "rule_code": "salary_personal_auto_match",
                "rule_version": "exception_rules_v1",
            },
            "amount_check": {"bank_expense_total": "120.00"},
            "note": "工资自动免 OA",
            "created_by": "system",
            "created_at": "2026-05-11T09:00:00+00:00",
        }

        projection = service.project_pair_relation(relation_payload, [bank_row()])

        override = projection["row_overrides"]["bk-001"]
        self.assertEqual(override["projection_version"], EXCEPTION_PROJECTION_VERSION)
        self.assertEqual(override["case_id"], "WEX-000002")
        self.assertEqual(override["relation"]["code"], "oa_exempt")
        self.assertEqual(override["relation"]["label"], "已处理：免 OA")
        self.assertEqual(override["relation"]["tone"], "success")
        self.assertEqual(override["relation_mode"], "oa_exempt")
        self.assertEqual(override["display_tags"], ["自动免OA", "工资"])
        self.assertEqual(override["tags"], ["自动免OA", "工资"])
        self.assertFalse(override["handled_exception"])
        self.assertEqual(override["available_actions"], ["detail", "cancel_link", "reopen_exception"])
        self.assertEqual(projection["group_metadata"]["group_type"], "processed_exception")
        self.assertEqual(projection["processed_exception_summary"]["relation_mode"], "oa_exempt")
        self.assertEqual(projection["processed_exception_summary"]["display_tags"], ["自动免OA", "工资"])


class WorkbenchOverrideProjectionTests(unittest.TestCase):
    def test_ambiguous_legacy_raw_id_override_fails_closed_across_panes(self) -> None:
        service = WorkbenchOverrideService.from_snapshot(
            {
                "row_overrides": {
                    "same-id": {
                        "case_id": "WEX-LEGACY-UNTYPED",
                        "ignored": True,
                    }
                }
            }
        )

        self.assertNotIn("ignored", service.apply_to_row(bank_row("same-id")))
        self.assertNotIn("ignored", service.apply_to_row(invoice_row("same-id")))

    def test_same_text_id_overrides_remain_independent_across_panes(self) -> None:
        service = WorkbenchOverrideService.from_snapshot(
            {
                "row_overrides": {
                    workbench_row_identity_key("bank", "same-id"): {
                        "case_id": "WEX-BANK",
                        "exception_case_id": "WEX-BANK",
                        "relation": {"code": "bank_fee", "label": "银行手续费", "tone": "warn"},
                    },
                    workbench_row_identity_key("invoice", "same-id"): {
                        "case_id": "WEX-INVOICE",
                        "exception_case_id": "WEX-INVOICE",
                        "ignored": True,
                    },
                }
            }
        )
        bank = bank_row("same-id")
        invoice = invoice_row("same-id")

        snapshot = service.snapshot()["row_overrides"]
        self.assertEqual(
            set(snapshot),
            {
                workbench_row_identity_key("bank", "same-id"),
                workbench_row_identity_key("invoice", "same-id"),
            },
        )
        self.assertEqual(service.apply_to_row(bank)["exception_case_id"], "WEX-BANK")
        self.assertNotIn("ignored", service.apply_to_row(bank))
        self.assertEqual(service.apply_to_row(invoice)["exception_case_id"], "WEX-INVOICE")
        self.assertTrue(service.apply_to_row(invoice)["ignored"])
        self.assertEqual(service.apply_to_row(bank)["invoice_relation"]["code"], "bank_fee")

    def test_oa_rows_only_expose_detail_in_both_zones(self) -> None:
        service = WorkbenchOverrideService()

        self.assertEqual(service.available_actions("oa", "paired"), ["detail"])
        self.assertEqual(service.available_actions("oa", "unpaired"), ["detail"])
        self.assertEqual(service.apply_to_row(oa_row())["available_actions"], ["detail"])

    def test_apply_relation_projection_and_clear_by_relation_case(self) -> None:
        service = WorkbenchOverrideService()
        row = bank_row()
        relation_payload = {
            "case_id": "WEX-REL-001",
            "status": "active",
            "row_ids": ["bk-001"],
            "row_types": ["bank"],
            "relation_mode": "oa_exempt",
            "display_tags": ["人工免OA"],
            "note": "人工确认无需 OA",
        }

        updated_rows = service.apply_relation_projection(relation_payload, [row])

        self.assertEqual(updated_rows[0]["case_id"], "WEX-REL-001")
        self.assertEqual(updated_rows[0]["invoice_relation"]["code"], "oa_exempt")
        self.assertEqual(updated_rows[0]["display_tags"], ["人工免OA"])

        self.assertEqual(service.clear_projection_for_relation("WEX-REL-001"), ["bk-001"])
        restored = service.apply_to_row(row)
        self.assertNotIn("case_id", restored)
        self.assertEqual(restored["invoice_relation"]["code"], "pending_match")


if __name__ == "__main__":
    unittest.main()
