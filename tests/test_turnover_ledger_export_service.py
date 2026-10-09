from __future__ import annotations

import unittest
from datetime import date
from decimal import InvalidOperation
from io import BytesIO

from fin_ops_platform.services.turnover_ledger_export_service import (
    TURNOVER_LEDGER_EXPORT_ROW_LIMIT,
    TurnoverLedgerExportLimitError,
    TurnoverLedgerExportService,
)
from openpyxl import load_workbook


class TurnoverLedgerExportServiceTests(unittest.TestCase):
    def test_flow_tags_are_identical_in_formal_rows_and_workbook(self):
        payload = self._grouped_payload()
        group = payload["groups"][0]
        group["flow_rows"] = [{"source_bank_row_id": "tag-flow", "flow_amount": "12.34",
                               "flow_direction": "expense", "category_label_path": ["外部往来款付款", "保证金", "业务往来"],
                               "turnover_action_label": "待收款"}]
        service = TurnoverLedgerExportService(lambda **kwargs: payload)
        preview = {"rows": service._formal_rows(payload, family="all")}
        flow = next(row for row in preview["rows"] if row["source_bank_row_id"] == "tag-flow")
        self.assertEqual(flow["流水标签"], "外部往来款付款 / 保证金 / 业务往来")
        self.assertEqual(flow["往来标记"], "待收款")
        self.assertEqual(preview["rows"][0]["往来标记"], "")
        _, data, count = service.export()
        workbook = load_workbook(BytesIO(data))
        rows = list(workbook.active.values)
        self.assertEqual(rows[0][-2:], ("流水标签", "往来标记"))
        self.assertEqual(rows[2][-2:], (flow["流水标签"], "待收款"))
        workbook.close()

    def _grouped_payload(self) -> dict[str, object]:
        return {
            "summary": {
                "pending_repayment_amount": "100000.00",
                "pending_collection_amount": "5000.00",
            },
            "family_summaries": [],
            "filters": {"family": "all"},
            "pagination": {"page": 1, "page_size": 100, "total": 2},
            "groups": [
                {
                    "group_id": "counterparty:company:梁希涛",
                    "counterparty_name": "梁希涛",
                    "family": "company",
                    "family_label": "公司往来",
                    "pending_direction": "repayment",
                    "pending_amount": "100000.00",
                    "pending_repayment_amount": "100000.00",
                    "pending_collection_amount": "0.00",
                    "summary_row": {
                        "relation_id": "turnover_rel_001",
                        "row_kind": "summary",
                        "display_level": "group_summary",
                        "status": "suggested",
                        "status_label": "待人工确认",
                        "borrow_amount": "200000.00",
                        "borrow_date": "2026-02-04",
                        "repayment_amount": "100000.00",
                        "repayment_date": "2026-03-05",
                        "counterparty_bank_name": "建行 8106",
                        "repayment_remark": "还款",
                        "interest_rate_type": "annual",
                        "interest_rate_value": "0.060000",
                        "interest_paid_amount": "120.50",
                        "loan_days": None,
                        "accrued_interest": "953.42",
                        "interest_paid_date": "2026-04-01",
                        "interest_payment_method": "银行转账",
                        "note": "页面备注",
                        "bank_row_ids": ["bank_001", "bank_002"],
                        "row_tone": "warning",
                    },
                    "lot_rows": [
                        {
                            "relation_id": "turnover_rel_001",
                            "row_kind": "lot",
                            "lot_id": "lot_001",
                            "status": "suggested",
                            "status_label": "待人工确认",
                            "borrow_amount": "120000.00",
                            "borrow_date": "2026-02-04",
                            "repayment_amount": "100000.00",
                            "repayment_date": "2026-03-05",
                            "balance_amount": "20000.00",
                            "counterparty_bank_name": "建行 8106",
                            "repayment_remark": "还款",
                            "interest_rate_type": "annual",
                            "interest_rate_value": "0.060000",
                            "interest_paid_amount": "120.50",
                            "loan_days": 29,
                            "accrued_interest": "572.05",
                            "interest_paid_date": "2026-04-01",
                            "interest_payment_method": "银行转账",
                            "note": "页面备注",
                            "bank_row_ids": ["bank_001", "bank_002"],
                            "row_tone": "info",
                        },
                        {
                            "relation_id": "turnover_rel_001",
                            "row_kind": "lot",
                            "lot_id": "lot_002",
                            "status": "suggested",
                            "status_label": "待人工确认",
                            "borrow_amount": "80000.00",
                            "borrow_date": "2026-02-04",
                            "repayment_amount": "0.00",
                            "repayment_date": None,
                            "balance_amount": "80000.00",
                            "counterparty_bank_name": "建行 8106",
                            "repayment_remark": "",
                            "interest_rate_type": "annual",
                            "interest_rate_value": "0.060000",
                            "interest_paid_amount": "0.00",
                            "loan_days": 30,
                            "accrued_interest": "381.37",
                            "interest_paid_date": None,
                            "interest_payment_method": "",
                            "note": "",
                            "bank_row_ids": ["bank_003"],
                            "row_tone": "info",
                        },
                    ],
                    "allocation_lots": [
                        {
                            "relation_id": "turnover_rel_001",
                            "row_kind": "allocation_lot",
                            "lot_id": "lot_001",
                            "borrow_amount": "120000.00",
                            "allocated_repayment_amount": "100000.00",
                            "balance_amount": "20000.00",
                            "loan_days": 29,
                            "accrued_interest": "572.05",
                        },
                        {
                            "relation_id": "turnover_rel_001",
                            "row_kind": "allocation_lot",
                            "lot_id": "lot_002",
                            "borrow_amount": "80000.00",
                            "allocated_repayment_amount": "0.00",
                            "balance_amount": "80000.00",
                            "loan_days": 30,
                            "accrued_interest": "381.37",
                        },
                    ],
                    "flow_rows": [
                        {
                            "relation_id": "turnover_rel_001",
                            "row_kind": "flow",
                            "flow_id": "bank:bank_001",
                            "source_bank_row_id": "bank_001",
                            "flow_direction": "income",
                            "flow_amount": "120000.00",
                            "borrow_amount": "120000.00",
                            "borrow_date": "2026-02-04",
                            "repayment_amount": "0.00",
                            "repayment_date": None,
                            "counterparty_bank_name": "建行 8106",
                            "summary_text": "暂借款",
                            "status": "suggested",
                            "status_label": "待人工确认",
                            "interest_rate_type": "annual",
                            "interest_rate_value": "0.060000",
                            "interest_paid_amount": "0.00",
                            "loan_days": None,
                            "accrued_interest": "0.00",
                            "interest_paid_date": None,
                            "interest_payment_method": "",
                            "note": "",
                            "allocation_status": "allocated",
                            "allocated_lot_ids": ["lot_001"],
                            "bank_row_ids": ["bank_001"],
                        },
                        {
                            "relation_id": "turnover_rel_001",
                            "row_kind": "flow",
                            "flow_id": "bank:bank_002",
                            "source_bank_row_id": "bank_002",
                            "flow_direction": "income",
                            "flow_amount": "80000.00",
                            "borrow_amount": "80000.00",
                            "borrow_date": "2026-02-04",
                            "repayment_amount": "0.00",
                            "repayment_date": None,
                            "counterparty_bank_name": "建行 8106",
                            "summary_text": "暂借款",
                            "status": "suggested",
                            "status_label": "待人工确认",
                            "interest_rate_type": "annual",
                            "interest_rate_value": "0.060000",
                            "interest_paid_amount": "0.00",
                            "loan_days": None,
                            "accrued_interest": "0.00",
                            "interest_paid_date": None,
                            "interest_payment_method": "",
                            "note": "",
                            "allocation_status": "unallocated",
                            "allocated_lot_ids": ["lot_002"],
                            "bank_row_ids": ["bank_002"],
                        },
                        {
                            "relation_id": "turnover_rel_001",
                            "row_kind": "flow",
                            "flow_id": "bank:bank_003",
                            "source_bank_row_id": "bank_003",
                            "flow_direction": "expense",
                            "flow_amount": "100000.00",
                            "borrow_amount": "0.00",
                            "borrow_date": None,
                            "repayment_amount": "100000.00",
                            "repayment_date": "2026-03-05",
                            "counterparty_bank_name": "建行 8106",
                            "summary_text": "还款",
                            "status": "suggested",
                            "status_label": "待人工确认",
                            "interest_rate_type": "annual",
                            "interest_rate_value": "0.060000",
                            "interest_paid_amount": "0.00",
                            "loan_days": None,
                            "accrued_interest": "0.00",
                            "interest_paid_date": None,
                            "interest_payment_method": "",
                            "note": "",
                            "allocation_status": "allocated",
                            "allocated_lot_ids": ["lot_001"],
                            "bank_row_ids": ["bank_003"],
                        },
                    ],
                    "rows": [
                        {
                            "relation_id": "turnover_rel_001",
                            "status": "suggested",
                            "status_label": "待人工确认",
                            "borrow_amount": "200000.00",
                            "borrow_date": "2026-02-04",
                            "repayment_amount": "100000.00",
                            "repayment_date": "2026-03-05",
                            "counterparty_bank_name": "建行 8106",
                            "repayment_remark": "还款",
                            "interest_rate_type": "annual",
                            "interest_rate_value": "0.060000",
                            "interest_paid_amount": "120.50",
                            "loan_days": 29,
                            "accrued_interest": "953.42",
                            "interest_paid_date": "2026-04-01",
                            "interest_payment_method": "银行转账",
                            "note": "页面备注",
                            "bank_row_ids": ["bank_001", "bank_002"],
                            "row_tone": "warning",
                        }
                    ],
                },
                {
                    "group_id": "counterparty:business:昆明建设集团",
                    "counterparty_name": "昆明建设集团",
                    "family": "business",
                    "family_label": "业务往来",
                    "pending_direction": "collection",
                    "pending_amount": "5000.00",
                    "pending_repayment_amount": "0.00",
                    "pending_collection_amount": "5000.00",
                    "summary_row": {
                            "relation_id": "turnover_rel_002",
                            "status": "suggested",
                            "status_label": "待人工确认",
                            "borrow_amount": "5000.00",
                            "borrow_date": "2026-03-06",
                            "repayment_amount": "0.00",
                            "repayment_date": None,
                            "counterparty_bank_name": "交行 3847",
                            "repayment_remark": "质保金",
                            "interest_rate_type": "none",
                            "interest_rate_value": "0.000000",
                            "interest_paid_amount": "0.00",
                            "loan_days": 0,
                            "accrued_interest": "0.00",
                            "interest_paid_date": None,
                            "interest_payment_method": "",
                            "note": "",
                    },
                    "flow_rows": [],
                },
            ],
        }

    def test_export_keeps_both_pending_directions_from_canonical_group(self) -> None:
        payload = self._grouped_payload()
        group = payload["groups"][0]
        group.update(pending_direction="mixed", pending_repayment_amount="100000.00",
                     pending_collection_amount="50000.00", pending_amount="150000.00")
        group["summary_row"].update(business_type="borrow_in", balance_amount="50000.00")
        group["flow_rows"] = [{"source_bank_row_id": "mixed-flow", "business_type": "borrow_out",
                               "flow_direction": "expense", "flow_amount": "50000.00", "balance_amount": "50000.00"}]
        service = TurnoverLedgerExportService(lambda **_: payload)

        _, data, count = service.export(family="company")

        workbook = load_workbook(BytesIO(data), read_only=True)
        try:
            rows = list(workbook.active.values)
            self.assertEqual(count, 1)
            self.assertEqual(rows[1][1], "合计")
            self.assertEqual(rows[1][7:10], ("100000.00", "50000.00", "150000.00"))
            self.assertEqual(rows[2][1:5], ("真实流水", "mixed-flow", "expense", "50000.00"))
            self.assertEqual(rows[2][7:10], ("0.00", "50000.00", "50000.00"))
        finally:
            workbook.close()

    def test_export_does_not_replace_missing_or_invalid_group_totals_with_zero(self) -> None:
        for field in ("pending_repayment_amount", "pending_collection_amount", "pending_amount"):
            with self.subTest(field=field, state="missing"):
                payload = self._grouped_payload()
                del payload["groups"][0][field]
                with self.assertRaises(KeyError):
                    TurnoverLedgerExportService(lambda **_: payload).export(family="company")
            with self.subTest(field=field, state="invalid"):
                payload = self._grouped_payload()
                payload["groups"][0][field] = "invalid"
                with self.assertRaises(InvalidOperation):
                    TurnoverLedgerExportService(lambda **_: payload).export(family="company")

    def test_export_keeps_settled_canonical_totals_at_zero(self) -> None:
        payload = self._grouped_payload()
        group = payload["groups"][0]
        group.update(pending_direction="none", pending_repayment_amount="0.00",
                     pending_collection_amount="0.00", pending_amount="0.00")
        group["summary_row"].update(business_type="borrow_in", balance_amount="100000.00")
        service = TurnoverLedgerExportService(lambda **_: payload)

        _, data, count = service.export(family="company")

        workbook = load_workbook(BytesIO(data), read_only=True)
        try:
            self.assertEqual(count, 1)
            self.assertEqual(list(workbook.active.values)[1][7:10], ("0.00", "0.00", "0.00"))
        finally:
            workbook.close()

    def test_formal_rows_keep_summary_and_real_flow_rows(self) -> None:
        service = TurnoverLedgerExportService(lambda **_: self._grouped_payload())

        payload = {"rows": service._formal_rows(self._grouped_payload(), family="company")}

        self.assertEqual(len(payload["rows"]), 4)
        row = payload["rows"][0]
        flow_row = payload["rows"][1]
        self.assertEqual([item["row_type"] for item in payload["rows"]], ["summary", "flow", "flow", "flow"])
        self.assertEqual(row["行类型"], "合计")
        self.assertEqual(row["row_type"], "summary")
        self.assertEqual(row["source_bank_row_id"], "")
        self.assertEqual(row["flow_direction"], "")
        self.assertEqual(row["flow_amount"], "0.00")
        self.assertEqual(row["lot_id"], "")
        self.assertEqual(row["balance_amount"], "100000.00")
        self.assertEqual(flow_row["行类型"], "真实流水")
        self.assertEqual(flow_row["源银行流水ID"], "bank_001")
        self.assertEqual(flow_row["流水方向"], "income")
        self.assertEqual(flow_row["流水金额"], "120000.00")
        self.assertEqual(flow_row["source_bank_row_id"], "bank_001")
        self.assertEqual(flow_row["flow_direction"], "income")
        self.assertEqual(flow_row["flow_amount"], "120000.00")
        self.assertEqual(flow_row["lot_id"], "")
        self.assertEqual(flow_row["余额"], "100000.00")
        self.assertEqual(flow_row["balance_amount"], "100000.00")
        self.assertEqual(row["往来大类"], "公司往来")
        self.assertEqual(row["对方户名"], "梁希涛")
        self.assertEqual(row["待还款金额"], "100000.00")
        self.assertEqual(row["待收款金额"], "0.00")
        self.assertEqual(row["关系状态"], "待人工确认")
        self.assertEqual(
            [item["source_bank_row_id"] for item in payload["rows"] if item["row_type"] == "flow"],
            ["bank_001", "bank_002", "bank_003"],
        )
        self.assertNotIn("row_tone", row)
        self.assertNotIn("bank_row_ids", row)
        self.assertNotIn("allocation_status", flow_row)
        self.assertNotIn("allocated_lot_ids", flow_row)

    def test_export_does_not_replace_missing_flow_rows_with_lot_rows(self) -> None:
        payload = self._grouped_payload()
        company_group = payload["groups"][0]
        company_group.pop("flow_rows")
        service = TurnoverLedgerExportService(lambda **_: payload)

        preview = {"rows": service._formal_rows(payload, family="company")}

        self.assertEqual([row["row_type"] for row in preview["rows"]], ["summary"])

    def test_summary_is_count_only_and_keeps_exact_scope(self):
        from unittest.mock import Mock
        loader = Mock(return_value={"row_count": 2})
        service = TurnoverLedgerExportService(loader)
        result = service.export_summary(family="company", query="梁", settlement_status="unsettled")
        self.assertEqual(result, {"row_count": 2})
        loader.assert_called_once_with(family="company", query="梁", settlement_status="unsettled", count_only=True)
        with self.assertRaisesRegex(ValueError, "分类无效"):
            service.export_summary(family="invalid")
        loader.side_effect = RuntimeError("database unavailable")
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            service.export_summary()

    def test_summary_empty_result_has_only_zero_count(self):
        service = TurnoverLedgerExportService(lambda **_: {"row_count": 0})
        self.assertEqual(service.export_summary(), {"row_count": 0})

    def test_export_builds_xlsx_and_filename_for_family_scope(self) -> None:
        service = TurnoverLedgerExportService(lambda **_: self._grouped_payload())

        filename, content, count = service.export(family="business", today=date(2026, 5, 12))
        workbook = load_workbook(BytesIO(content))
        sheet = workbook.active

        self.assertEqual(filename, "往来款台账-业务往来-2026-05-12.xlsx")
        self.assertEqual(sheet.cell(row=1, column=1).value, "序号")
        self.assertEqual(sheet.cell(row=1, column=2).value, "行类型")
        self.assertEqual(sheet.cell(row=1, column=3).value, "源银行流水ID")
        self.assertEqual(sheet.cell(row=1, column=10).value, "余额")
        self.assertEqual(sheet.cell(row=2, column=2).value, "合计")
        self.assertEqual(sheet.cell(row=2, column=6).value, "业务往来")
        self.assertEqual(sheet.cell(row=2, column=7).value, "昆明建设集团")
        self.assertEqual(sheet.max_row, 2)

    def test_export_rejects_group_count_above_sync_row_limit(self) -> None:
        payload = self._grouped_payload()
        payload["pagination"] = {"page": 1, "page_size": 10000, "total": TURNOVER_LEDGER_EXPORT_ROW_LIMIT + 1}
        service = TurnoverLedgerExportService(lambda **_: payload)

        with self.assertRaises(TurnoverLedgerExportLimitError) as export_context:
            service.export(family="all")
        self.assertEqual(export_context.exception.error_code, "turnover_ledger_export_row_limit_exceeded")
        self.assertEqual(export_context.exception.details, {"total": TURNOVER_LEDGER_EXPORT_ROW_LIMIT + 1, "limit": TURNOVER_LEDGER_EXPORT_ROW_LIMIT})

    def test_export_rejects_flattened_flow_rows_above_sync_row_limit(self) -> None:
        payload = self._grouped_payload()
        group = dict(payload["groups"][0])
        group["flow_rows"] = [
            {
                "source_bank_row_id": f"bank-large-{index}",
                "flow_direction": "income",
                "flow_amount": "1.00",
                "balance_amount": "1.00",
            }
            for index in range(TURNOVER_LEDGER_EXPORT_ROW_LIMIT)
        ]
        payload["groups"] = [group]
        payload["pagination"] = {"page": 1, "page_size": 1, "total": 1}
        service = TurnoverLedgerExportService(lambda **_: payload)

        with self.assertRaises(TurnoverLedgerExportLimitError) as context:
            service.export(family="all")

        self.assertEqual(context.exception.details, {"total": TURNOVER_LEDGER_EXPORT_ROW_LIMIT + 1, "limit": TURNOVER_LEDGER_EXPORT_ROW_LIMIT})


if __name__ == "__main__":
    unittest.main()
