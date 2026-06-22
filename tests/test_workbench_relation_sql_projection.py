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
            return [
                {
                    "row_id": "oa-att-inv-70",
                    "invoice_type": "input",
                    "invoice_code": None,
                    "invoice_no": "9132019MA1XM5TX71",
                    "digital_invoice_no": None,
                    "invoice_date": "2026-01-20",
                    "invoice_month": "2026-01-01",
                    "seller_name": "中科视拓（南京）科技有限公司",
                    "seller_tax_no": "9132019MA1XM5TX71",
                    "buyer_name": "云南溯源科技有限公司",
                    "buyer_tax_no": None,
                    "amount": "70.00",
                    "total_with_tax": "70.00",
                    "raw_payload": {"source_links": [{"source_type": "oa_attachment_invoice"}]},
                },
                {
                    "row_id": "oa-att-inv-126",
                    "invoice_type": "input",
                    "invoice_code": None,
                    "invoice_no": "92532324MAC296HG5K",
                    "digital_invoice_no": None,
                    "invoice_date": "2026-01-20",
                    "invoice_month": "2026-01-01",
                    "seller_name": "南华县沙桥镇润华清真饭店",
                    "seller_tax_no": "92532324MAC296HG5K",
                    "buyer_name": "云南溯源科技有限公司",
                    "buyer_tax_no": None,
                    "amount": "126.00",
                    "total_with_tax": "126.00",
                    "raw_payload": {"source_links": [{"source_type": "oa_attachment_invoice"}]},
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


class DuplicateInvoiceIdentityRelationProjectionConnection(WorkbenchRelationProjectionConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        if "from app.invoices" in normalized:
            return [
                {
                    "row_id": "oa-att-inv-project-1",
                    "invoice_type": "input",
                    "invoice_code": None,
                    "invoice_no": "265320000000992",
                    "digital_invoice_no": "265320000000992",
                    "invoice_date": "2026-01-20",
                    "invoice_month": "2026-01-01",
                    "seller_name": "溯源科技有限公司",
                    "seller_tax_no": "300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "buyer_tax_no": None,
                    "amount": "283.02",
                    "total_with_tax": "300.00",
                    "raw_payload": {"source_links": [{"source_type": "oa_attachment_invoice"}]},
                },
                {
                    "row_id": "invoice-formal-project-1",
                    "invoice_type": "input",
                    "invoice_code": None,
                    "invoice_no": "265320000000992",
                    "digital_invoice_no": "265320000000992",
                    "invoice_date": "2026-01-20",
                    "invoice_month": "2026-01-01",
                    "seller_name": "溯源科技有限公司",
                    "seller_tax_no": "300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "buyer_tax_no": None,
                    "amount": "283.02",
                    "total_with_tax": "300.00",
                    "raw_payload": {},
                }
            ]
        if "from app.workbench_pair_relations" in normalized:
            return [
                {
                    "case_id": "case-project-1",
                    "relation_mode": "manual_confirmed",
                    "month_scope": "2026-01-01",
                    "row_ids": ["oa-tian-196", "txn-tian-196", "oa-att-inv-project-1", "invoice-formal-project-1"],
                    "row_types": ["oa", "bank", "invoice", "invoice"],
                    "source_versions": {},
                    "raw_payload": {},
                }
            ]
        return super().fetch_all(sql, params)


class CandidateDecisionRelationProjectionConnection(WorkbenchRelationProjectionConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        if "from read_model.workbench_reconciliation_decisions" in normalized:
            self.sql_statements.append(sql)
            if "display_state = 'open'" not in normalized and "decision_status in" not in normalized:
                return []
            return [
                {
                    "decision_key": "decision-open-candidate",
                    "scope_month": "2026-01-01",
                    "row_ids": ["oa-tian-196", "txn-tian-196", "oa-att-inv-70"],
                    "row_types": [],
                    "oa_row_ids": ["oa-tian-196"],
                    "bank_row_ids": ["txn-tian-196"],
                    "invoice_row_ids": ["oa-att-inv-70"],
                    "amount": "196.00",
                    "payment_amount_closed": False,
                    "invoice_amount_closed": False,
                    "source_versions": {"decision": "v1"},
                    "raw_payload": {"decision_status": "open", "display_state": "open"},
                }
            ]
        if "from app.workbench_pair_relations" in normalized:
            return []
        return super().fetch_all(sql, params)


class PendingClaimedBankRelationProjectionConnection(WorkbenchRelationProjectionConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transaction_relation_claims" in normalized:
            self.sql_statements.append(sql)
            return [{"bank_transaction_id": "txn-unlinked"}]
        return super().fetch_all(sql, params)


class PendingClaimedCandidateDecisionProjectionConnection(CandidateDecisionRelationProjectionConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transaction_relation_claims" in normalized:
            self.sql_statements.append(sql)
            return [{"bank_transaction_id": "txn-tian-196"}]
        return super().fetch_all(sql, params)


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
        self.assertFalse(any("from read_model.workbench_rows" in sql for sql in connection.sql_statements))

    def test_rebuild_excludes_unlinked_bank_rows_claimed_by_in_progress_oa(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        connection = PendingClaimedBankRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        builder.rebuild_workbench_relation_read_model_scope("2026-01")

        rows_by_id = {row["row_id"]: row for row in repository.saved[0]["rows"]}
        self.assertIn("txn-tian-196", rows_by_id)
        self.assertNotIn("txn-unlinked", rows_by_id)
        self.assertTrue(any("from app.bank_transaction_relation_claims" in sql for sql in connection.sql_statements))

    def test_rebuild_deduplicates_formal_and_oa_attachment_invoice_with_same_identity(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        connection = DuplicateInvoiceIdentityRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        builder.rebuild_workbench_relation_read_model_scope("2026-01")

        group = repository.saved[0]["groups"][0]
        self.assertEqual(group["input_invoice_ids"], ["oa-att-inv-project-1"])
        rows_by_id = {row["row_id"]: row for row in repository.saved[0]["rows"]}
        linked = rows_by_id["txn-tian-196"]
        self.assertEqual(
            [invoice["digital_invoice_no"] for invoice in linked["linked_input_invoices"]],
            ["265320000000992"],
        )
        self.assertEqual(
            linked["linked_input_invoices"][0]["object_identity_key"],
            "265320000000992",
        )

    def test_rebuild_distributes_open_reconciliation_decision_as_candidate_relation(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        connection = CandidateDecisionRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        result = builder.rebuild_workbench_relation_read_model_scope("2026-01")

        self.assertEqual(result["group_count"], 1)
        saved = repository.saved[0]
        group = saved["groups"][0]
        self.assertEqual(group["group_id"], "decision-open-candidate")
        self.assertEqual(group["relation_source"], "automatic_decision")
        self.assertEqual(group["relation_status"], "candidate")
        self.assertEqual(group["payload"]["relation_status"], "candidate")
        rows_by_id = {row["row_id"]: row for row in saved["rows"]}
        self.assertEqual(rows_by_id["txn-tian-196"]["relation_status"], "candidate")
        self.assertEqual(rows_by_id["txn-tian-196"]["group_ids"], ["decision-open-candidate"])
        self.assertEqual(rows_by_id["txn-tian-196"]["linked_oa"][0]["relation_status"], "candidate")
        self.assertEqual(rows_by_id["txn-unlinked"]["relation_status"], "unlinked")

    def test_rebuild_excludes_candidate_decisions_using_in_progress_oa_claimed_bank_rows(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        connection = PendingClaimedCandidateDecisionProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        result = builder.rebuild_workbench_relation_read_model_scope("2026-01")

        self.assertEqual(result["group_count"], 0)
        self.assertEqual(repository.saved[0]["groups"], [])
        rows_by_id = {row["row_id"]: row for row in repository.saved[0]["rows"]}
        self.assertNotIn("txn-tian-196", rows_by_id)
        self.assertEqual(rows_by_id["txn-unlinked"]["relation_status"], "unlinked")


if __name__ == "__main__":
    unittest.main()
