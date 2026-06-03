from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_relation_sql_projection import WorkbenchRelationSqlProjectionBuilder


class CaptureWorkbenchRelationRepository:
    def __init__(self) -> None:
        self.saved: list[dict[str, object]] = []

    def save_workbench_relation_distribution(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        groups: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
        tenant_id: str = "default",
    ) -> None:
        self.saved.append(
            {
                "scope_key": scope_key,
                "rows": list(rows),
                "groups": list(groups),
                "source_versions": dict(source_versions or {}),
                "tenant_id": tenant_id,
            }
        )


class WorkbenchRelationProjectionConnection:
    def __init__(self) -> None:
        self.sql_statements: list[str] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        self.sql_statements.append(sql)
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                {
                    "row_id": "txn-tian-196",
                    "counterparty_name_raw": "田孟维",
                    "trade_time": "2026-01-20 10:40:01",
                    "txn_date": "2026-01-20",
                    "amount": "196.00",
                    "txn_direction": "outflow",
                    "summary": "报销",
                    "remark": "",
                    "bank_serial_no": "SERIAL-196",
                    "account_name": "建行 8106",
                    "account_no": "622200008106",
                    "txn_month": "2026-01-01",
                },
                {
                    "row_id": "txn-unlinked",
                    "counterparty_name_raw": "田孟维",
                    "trade_time": "2026-01-21 10:40:01",
                    "txn_date": "2026-01-21",
                    "amount": "500.00",
                    "txn_direction": "outflow",
                    "summary": "过节费",
                    "remark": "",
                    "bank_serial_no": "SERIAL-500",
                    "account_name": "建行 8106",
                    "account_no": "622200008106",
                    "txn_month": "2026-01-01",
                },
            ]
        if "from app.oa_applications" in normalized:
            return [
                {
                    "row_id": "oa-tian-196",
                    "form_id": "OA-196",
                    "form_type": "日常报销",
                    "status": "completed",
                    "applicant": "田孟维",
                    "application_date": "2026-01-20",
                    "project_name": "云南溯源科技; 大理卷烟厂余...",
                    "amount": "196.00",
                }
            ]
        if "from app.invoices" in normalized:
            return []
        if "from read_model.workbench_rows" in normalized and "oa_attachment_invoice" in normalized:
            return [
                {
                    "row_id": "oa-att-inv-70",
                    "scope_month": "2026-01-01",
                    "payload": {
                        "invoice_no": "9132019MA1XM5TX71",
                        "issue_date": "2026-01-20",
                        "seller_name": "中科视拓（南京）科技有限公司",
                        "seller_tax_no": "9132019MA1XM5TX71",
                        "buyer_name": "云南溯源科技有限公司",
                        "total_with_tax": "70.00",
                    },
                },
                {
                    "row_id": "oa-att-inv-126",
                    "scope_month": "2026-01-01",
                    "payload": {
                        "invoice_no": "92532324MAC296HG5K",
                        "issue_date": "2026-01-20",
                        "seller_name": "南华县沙桥镇润华清真饭店",
                        "seller_tax_no": "92532324MAC296HG5K",
                        "buyer_name": "云南溯源科技有限公司",
                        "total_with_tax": "126.00",
                    },
                },
            ]
        if "from read_model.workbench_reconciliation_decisions" in normalized:
            return []
        if "from app.workbench_pair_relations" in normalized:
            return [
                {
                    "case_id": "case-tian-196",
                    "relation_mode": "manual_confirmed",
                    "month_scope": "2026-01-01",
                    "row_ids": ["oa-tian-196", "txn-tian-196", "oa-att-inv-70", "oa-att-inv-126"],
                    "row_types": ["oa", "bank", "invoice", "invoice"],
                    "source_versions": {},
                    "raw_payload": {},
                }
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, object] | None:
        return {
            "pair_relations_updated_at": "2026-06-03T00:00:00+08:00",
            "bank_transactions_updated_at": "2026-06-03T00:00:00+08:00",
            "invoices_updated_at": "2026-06-03T00:00:00+08:00",
            "oa_projection_updated_at": "2026-06-03T00:00:00+08:00",
        }


class WorkbenchRelationSqlProjectionTests(unittest.TestCase):
    def test_rebuild_writes_linked_and_unlinked_relation_rows(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        connection = WorkbenchRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        result = builder.rebuild_workbench_relation_read_model_scope("2026-01")

        self.assertEqual(result["scope_key"], "2026-01")
        saved = repository.saved[0]
        self.assertEqual(saved["scope_key"], "2026-01")
        self.assertEqual(len(saved["groups"]), 1)
        group = saved["groups"][0]
        self.assertEqual(group["group_id"], "case-tian-196")
        self.assertEqual(group["relation_kind"], "oa_bank_input_invoice")
        self.assertEqual(group["input_invoice_ids"], ["oa-att-inv-70", "oa-att-inv-126"])
        rows_by_id = {row["row_id"]: row for row in saved["rows"]}
        linked = rows_by_id["txn-tian-196"]
        self.assertEqual(linked["relation_status"], "linked")
        self.assertEqual(linked["group_ids"], ["case-tian-196"])
        self.assertEqual(linked["linked_oa"][0]["id"], "oa-tian-196")
        self.assertEqual(linked["linked_bank_transactions"][0]["id"], "txn-tian-196")
        self.assertEqual(linked["linked_bank_transactions"][0]["amount"], "196.00")
        self.assertEqual(
            [invoice["id"] for invoice in linked["linked_input_invoices"]],
            ["oa-att-inv-70", "oa-att-inv-126"],
        )
        self.assertEqual(rows_by_id["txn-unlinked"]["relation_status"], "unlinked")
        self.assertEqual(rows_by_id["txn-unlinked"]["group_ids"], [])
        self.assertTrue(any("gen.generation_id = r.generation_id" in sql for sql in connection.sql_statements))
        self.assertFalse(any("gen.id = r.generation_id" in sql for sql in connection.sql_statements))


if __name__ == "__main__":
    unittest.main()
