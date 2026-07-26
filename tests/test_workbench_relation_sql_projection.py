from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_relation_sql_projection import WorkbenchRelationSqlProjectionBuilder
from fin_ops_platform.services.workbench_relation_sql_projection import (
    WORKBENCH_RELATION_SQL_PROJECTION_SCHEMA_VERSION,
)


class CaptureWorkbenchRelationRepository:
    def __init__(self) -> None:
        self.saved: list[dict[str, object]] = []
        self.saved_rows: list[dict[str, object]] = []
        self.existing_scope_summary: dict[str, object] | None = None
        self.scope_summary_calls: list[dict[str, object]] = []
        self.previous_distribution: dict[str, object] | None = None
        self.previous_distribution_calls: list[dict[str, object]] = []
        self.row_id_aliases: dict[str, str] = {}
        self.row_id_alias_calls: list[list[str]] = []

    def get_workbench_relation_rows_by_ids(
        self,
        row_ids: list[str],
        *,
        tenant_id: str = "default",
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, object] | None:
        self.previous_distribution_calls.append(
            {
                "row_ids": list(row_ids),
                "tenant_id": tenant_id,
                "scope_keys_hint": list(scope_keys_hint or []),
            }
        )
        return self.previous_distribution

    def workbench_relation_row_id_aliases(
        self,
        row_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, str]:
        self.row_id_alias_calls.append(list(row_ids))
        return {
            row_id: self.row_id_aliases.get(row_id, row_id)
            for row_id in row_ids
        }

    def workbench_relation_scope_summary(
        self,
        *,
        scope_key: str,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        self.scope_summary_calls.append({"scope_key": scope_key, "tenant_id": tenant_id})
        return self.existing_scope_summary

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

    def save_workbench_relation_distribution_rows(
        self,
        *,
        scope_key: str,
        affected_row_ids: list[str],
        rows: list[dict[str, object]],
        groups: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
        tenant_id: str = "default",
    ) -> None:
        self.saved_rows.append(
            {
                "scope_key": scope_key,
                "affected_row_ids": list(affected_row_ids),
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


class CrossMonthRelationProjectionConnection(WorkbenchRelationProjectionConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transaction_relation_claims" in normalized:
            self.sql_statements.append(sql)
            return []
        if "from app.bank_transactions" in normalized:
            self.sql_statements.append(sql)
            explicit_ids = set(params[0]) if params and isinstance(params[0], list) else set()
            month = str(params[1])[:7] if len(params) > 1 else ""
            if month == "2026-04" or "bank-nanjing" in explicit_ids:
                return [
                    {
                        "row_id": "bank-nanjing",
                        "counterparty_name_raw": "南京联升仪表有限公司",
                        "trade_time": "2026-04-23 17:22:27",
                        "txn_date": "2026-04-23",
                        "amount": "584.50",
                        "txn_direction": "outflow",
                        "summary": "货款",
                        "remark": "",
                        "bank_serial_no": "3847",
                        "account_name": "交行 3847",
                        "account_no": "622200003847",
                        "txn_month": "2026-04-01",
                    }
                ]
            return []
        if "from app.oa_applications" in normalized:
            self.sql_statements.append(sql)
            explicit_ids = (
                set(params[2])
                if len(params) > 2 and isinstance(params[2], list)
                else set(params[1])
                if len(params) > 1 and isinstance(params[1], list)
                else set(params[0])
                if params and isinstance(params[0], list)
                else set()
            )
            month = str(params[0])[:7] if params else ""
            if month == "2026-04" or "oa-yang" in explicit_ids:
                return [
                    {
                        "row_id": "oa-yang",
                        "form_id": "OA-YANG",
                        "form_type": "支付申请",
                        "status": "completed",
                        "applicant": "杨丽萍",
                        "application_date": "2026-04-21",
                        "project_name": "大理卷烟厂余热综合利用项目",
                        "amount": "584.50",
                    }
                ]
            return []
        if "from app.invoices" in normalized:
            self.sql_statements.append(sql)
            explicit_ids = (
                set(params[1])
                if len(params) > 1 and isinstance(params[1], list)
                else set(params[0])
                if params and isinstance(params[0], list)
                else set()
            )
            month = str(params[0])[:7] if params else ""
            if month == "2026-05" or "input-invoice-nanjing" in explicit_ids:
                return [
                    {
                        "row_id": "input-invoice-nanjing",
                        "invoice_type": "input",
                        "invoice_code": None,
                        "invoice_no": "26322000003919774666",
                        "digital_invoice_no": "26322000003919774666",
                        "invoice_date": "2026-05-19",
                        "invoice_month": "2026-05-01",
                        "seller_name": "南京联升仪表有限公司",
                        "seller_tax_no": "91320191MA1MW2LL48",
                        "buyer_name": "云南溯源科技有限公司",
                        "buyer_tax_no": "915300007194052520",
                        "amount": "517.26",
                        "total_with_tax": "584.50",
                        "raw_payload": {},
                    }
                ]
            return []
        if "from app.workbench_pair_relations" in normalized:
            self.sql_statements.append(sql)
            requested_ids = (
                set(params[1])
                if len(params) > 1 and isinstance(params[1], list)
                else set(params[0])
                if params and isinstance(params[0], list)
                else set()
            )
            relation_ids = {"oa-yang", "bank-nanjing", "input-invoice-nanjing"}
            if requested_ids & relation_ids:
                return [
                    {
                        "case_id": "case-nanjing-cross-month",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "2026-04-01",
                        "row_ids": ["oa-yang", "bank-nanjing", "input-invoice-nanjing"],
                        "row_types": ["oa", "bank", "invoice"],
                        "amount_check": {"matched": True},
                        "source_versions": {},
                        "raw_payload": {},
                    }
                ]
            return []
        return []


class FailIfFetchAllRelationProjectionConnection(WorkbenchRelationProjectionConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        raise AssertionError("source-version unchanged projection should not scan source rows")


class ScopedSourceVersionsRelationProjectionConnection(WorkbenchRelationProjectionConnection):
    def __init__(self) -> None:
        super().__init__()
        self.fetch_one_calls: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, object] | None:
        self.fetch_one_calls.append((" ".join(sql.lower().split()), params))
        return {
            "pair_relations_updated_at": "2026-04-30T00:00:00+08:00",
            "reconciliation_decisions_updated_at": "2026-04-29T00:00:00+08:00",
            "oa_pending_payment_bank_claims_updated_at": "2026-04-28T00:00:00+08:00",
            "bank_transactions_updated_at": "2026-04-27T00:00:00+08:00",
            "invoices_updated_at": "2026-05-20T00:00:00+08:00",
            "oa_projection_updated_at": "2026-04-26T00:00:00+08:00",
        }


class BulkScopedSourceVersionsRelationProjectionConnection(WorkbenchRelationProjectionConnection):
    def __init__(self) -> None:
        super().__init__()
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized_sql = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized_sql, params))
        return [
            {
                "scope_key": str(scope_month)[:7],
                "pair_relations_updated_at": f"{str(scope_month)[:7]}-28T00:00:00+08:00",
                "oa_pending_payment_bank_claims_updated_at": f"{str(scope_month)[:7]}-27T00:00:00+08:00",
                "bank_transactions_updated_at": f"{str(scope_month)[:7]}-26T00:00:00+08:00",
                "invoices_updated_at": f"{str(scope_month)[:7]}-25T00:00:00+08:00",
                "oa_projection_updated_at": f"{str(scope_month)[:7]}-24T00:00:00+08:00",
            }
            for scope_month in params[0]
        ]


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




class PendingClaimedBankRelationProjectionConnection(WorkbenchRelationProjectionConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transaction_relation_claims" in normalized:
            self.sql_statements.append(sql)
            return [{"bank_transaction_id": "txn-unlinked"}]
        return super().fetch_all(sql, params)




class LegacyCompletedOaRelationProjectionConnection(CrossMonthRelationProjectionConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        if "from app.oa_applications" in normalized:
            self.sql_statements.append(sql)
            if "已完成" not in sql:
                return []
            return [
                {
                    "row_id": "oa-yang",
                    "form_id": "OA-YANG",
                    "form_type": "支付申请",
                    "status": "已完成",
                    "applicant": "杨丽萍",
                    "application_date": "2026-04-21",
                    "project_name": "大理卷烟厂余热综合利用项目",
                    "amount": "584.50",
                }
            ]
        return super().fetch_all(sql, params)


class RemovedOaMemberRelationProjectionConnection(CrossMonthRelationProjectionConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        if "from app.workbench_pair_relations" in normalized:
            self.sql_statements.append(sql)
            requested_ids = next(
                (set(param) for param in params if isinstance(param, list)),
                set(),
            )
            if requested_ids & {"bank-nanjing", "oa-yang"}:
                return [
                    {
                        "case_id": "turnover:target",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "2026-04-01",
                        "row_ids": ["bank-nanjing"],
                        "row_types": ["bank"],
                        "amount_check": {"matched": True},
                        "source_versions": {},
                        "raw_payload": {},
                    }
                ]
            return []
        return super().fetch_all(sql, params)


class WorkbenchRelationSqlProjectionTests(unittest.TestCase):
    def _statement_count(self, connection: WorkbenchRelationProjectionConnection, fragment: str) -> int:
        return sum(fragment in " ".join(sql.lower().split()) for sql in connection.sql_statements)

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
        self.assertEqual(self._statement_count(connection, "from app.bank_transactions"), 1)
        self.assertEqual(self._statement_count(connection, "from app.oa_applications"), 1)
        self.assertEqual(self._statement_count(connection, "from app.invoices"), 1)

    def test_shared_distribution_excludes_turnover_manual_closure_relations(self) -> None:
        class TurnoverClosureConnection(WorkbenchRelationProjectionConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
                normalized = " ".join(sql.lower().split())
                if "from app.workbench_pair_relations" in normalized:
                    self.sql_statements.append(sql)
                    if "relation_mode <> %s" in normalized:
                        self.assert_turnover_mode_parameter(params)
                        return []
                    return [
                        {
                            "case_id": "turnover:closure",
                            "relation_mode": "turnover_manual_closure",
                            "month_scope": "2026-01-01",
                            "row_ids": ["txn-tian-196"],
                            "row_types": ["bank"],
                            "source_versions": {},
                            "raw_payload": {},
                        }
                    ]
                return super().fetch_all(sql, params)

            @staticmethod
            def assert_turnover_mode_parameter(params: tuple) -> None:
                if "turnover_manual_closure" not in params:
                    raise AssertionError("shared distribution must parameterize the excluded relation mode")

        repository = CaptureWorkbenchRelationRepository()
        connection = TurnoverClosureConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        builder.rebuild_workbench_relation_read_model_scope("2026-01")

        saved = repository.saved[0]
        self.assertEqual(saved["groups"], [])
        rows_by_id = {row["row_id"]: row for row in saved["rows"]}
        self.assertEqual(rows_by_id["txn-tian-196"]["relation_status"], "unlinked")
        self.assertEqual(rows_by_id["txn-tian-196"]["group_ids"], [])

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

    def test_rebuild_indexes_cross_month_relation_members_in_current_scope(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        connection = CrossMonthRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        builder.rebuild_workbench_relation_read_model_scope("2026-04")

        saved = repository.saved[0]
        self.assertEqual(saved["scope_key"], "2026-04")
        group = saved["groups"][0]
        self.assertEqual(group["group_id"], "case-nanjing-cross-month")
        self.assertEqual(group["input_invoice_ids"], ["input-invoice-nanjing"])
        rows_by_id = {row["row_id"]: row for row in saved["rows"]}
        self.assertIn("input-invoice-nanjing", rows_by_id)
        invoice_row = rows_by_id["input-invoice-nanjing"]
        self.assertEqual(invoice_row["scope_key"], "2026-04")
        self.assertEqual(invoice_row["relation_status"], "linked")
        self.assertEqual(invoice_row["group_ids"], ["case-nanjing-cross-month"])
        self.assertEqual([row["id"] for row in invoice_row["linked_oa"]], ["oa-yang"])
        self.assertEqual([row["id"] for row in invoice_row["linked_bank_transactions"]], ["bank-nanjing"])
        bank_row = rows_by_id["bank-nanjing"]
        self.assertEqual(bank_row["relation_status"], "linked")
        self.assertEqual([row["id"] for row in bank_row["linked_oa"]], ["oa-yang"])
        self.assertEqual([row["id"] for row in bank_row["linked_input_invoices"]], ["input-invoice-nanjing"])
        self.assertEqual(self._statement_count(connection, "from app.bank_transactions"), 1)
        self.assertEqual(self._statement_count(connection, "from app.oa_applications"), 1)
        self.assertEqual(self._statement_count(connection, "from app.invoices"), 2)
        invoice_queries = [
            " ".join(sql.lower().split())
            for sql in connection.sql_statements
            if "from app.invoices" in " ".join(sql.lower().split())
        ]
        self.assertTrue(any("invoice_month =" in sql for sql in invoice_queries))
        self.assertTrue(any("invoice_month =" not in sql for sql in invoice_queries))

    def test_rebuild_rows_uses_changed_row_ids_without_month_source_scan(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        connection = CrossMonthRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        result = builder.rebuild_workbench_relation_read_model_rows("2026-04", row_ids=["bank-nanjing"])

        self.assertTrue(result["partial"])
        saved = repository.saved_rows[0]
        self.assertEqual(saved["scope_key"], "2026-04")
        self.assertEqual(saved["affected_row_ids"], ["bank-nanjing"])
        rows_by_id = {row["row_id"]: row for row in saved["rows"]}
        self.assertEqual(set(rows_by_id), {"oa-yang", "bank-nanjing", "input-invoice-nanjing"})
        self.assertEqual(saved["groups"][0]["group_id"], "case-nanjing-cross-month")
        self.assertEqual(self._statement_count(connection, "from app.bank_transactions"), 1)
        self.assertEqual(self._statement_count(connection, "from app.oa_applications"), 1)
        self.assertEqual(self._statement_count(connection, "from app.invoices"), 1)
        source_queries = [" ".join(sql.lower().split()) for sql in connection.sql_statements]
        self.assertFalse(
            any(
                "txn_month =" in sql
                for sql in source_queries
                if "from app.bank_transactions" in sql
            )
        )
        self.assertFalse(
            any(
                "application_date >=" in sql
                for sql in source_queries
                if "from app.oa_applications" in sql
            )
        )
        self.assertFalse(
            any(
                "invoice_month =" in sql
                for sql in source_queries
                if "from app.invoices" in sql
            )
        )

    def test_relation_delta_uses_exact_scope_proof_and_narrow_active_relation_query(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        connection = CrossMonthRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        result = builder.rebuild_workbench_relation_read_model_relation_delta(
            "2026-04",
            row_ids=["bank-nanjing"],
        )

        self.assertTrue(result["relation_delta"])
        self.assertEqual(repository.saved_rows[0]["groups"][0]["group_id"], "case-nanjing-cross-month")
        relation_queries = [
            " ".join(sql.lower().split())
            for sql in connection.sql_statements
            if "from app.workbench_pair_relations" in " ".join(sql.lower().split())
        ]
        self.assertEqual(len(relation_queries), 1)
        self.assertIn("row_ids && %s::text[]", relation_queries[0])
        self.assertNotIn("month_scope =", relation_queries[0])
        claim_queries = [
            " ".join(sql.lower().split())
            for sql in connection.sql_statements
            if "from app.bank_transaction_relation_claims" in " ".join(sql.lower().split())
        ]
        self.assertEqual(len(claim_queries), 1)
        self.assertIn("bank_transaction_id = any(%s::text[])", claim_queries[0])

    def test_relation_delta_does_not_depend_on_cached_scope_proof(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        connection = CrossMonthRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        result = builder.rebuild_workbench_relation_read_model_relation_delta(
            "2026-04",
            row_ids=["bank-nanjing"],
        )

        self.assertTrue(result["relation_delta"])
        self.assertEqual(repository.saved, [])
        self.assertEqual(len(repository.saved_rows), 1)

    def test_rebuild_rows_reprojects_members_removed_from_previous_group(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        repository.previous_distribution = {
            "read_model_status": "refreshing",
            "rows": [],
            "groups": [
                {
                    "group_id": "turnover:target",
                    "scope_key": "2026-04",
                    "oa_row_ids": ["oa-yang"],
                    "bank_transaction_ids": ["bank-nanjing"],
                    "input_invoice_ids": [],
                    "output_invoice_ids": [],
                }
            ],
        }
        connection = RemovedOaMemberRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        result = builder.rebuild_workbench_relation_read_model_rows("2026-04", row_ids=["bank-nanjing"])

        self.assertEqual(result["affected_row_count"], 2)
        self.assertEqual(
            repository.previous_distribution_calls,
            [
                {
                    "row_ids": ["bank-nanjing"],
                    "tenant_id": "default",
                    "scope_keys_hint": ["2026-04"],
                }
            ],
        )
        saved = repository.saved_rows[0]
        self.assertEqual(saved["affected_row_ids"], ["bank-nanjing", "oa-yang"])
        rows_by_id = {row["row_id"]: row for row in saved["rows"]}
        self.assertEqual(rows_by_id["bank-nanjing"]["group_ids"], ["turnover:target"])
        self.assertEqual(rows_by_id["oa-yang"]["relation_status"], "unlinked")
        self.assertEqual(rows_by_id["oa-yang"]["group_ids"], [])
        self.assertEqual(saved["groups"][0]["oa_row_ids"], [])
        self.assertEqual(saved["groups"][0]["bank_transaction_ids"], ["bank-nanjing"])
        self.assertEqual(self._statement_count(connection, "from app.bank_transactions"), 1)
        self.assertEqual(self._statement_count(connection, "from app.oa_applications"), 1)
        self.assertEqual(self._statement_count(connection, "from app.invoices"), 0)

    def test_relation_delta_expands_uuid_and_legacy_aliases_before_replacing_old_group(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        repository.row_id_aliases = {
            "781cbe29-c790-4ad4-b6fb-7b4530813fa6": "bank-nanjing",
            "bank-nanjing": "bank-nanjing",
        }
        repository.previous_distribution = {
            "read_model_status": "refreshing",
            "rows": [],
            "groups": [
                {
                    "group_id": "turnover:target",
                    "scope_key": "2026-04",
                    "oa_row_ids": ["oa-yang"],
                    "bank_transaction_ids": ["bank-nanjing"],
                    "input_invoice_ids": [],
                    "output_invoice_ids": [],
                }
            ],
        }
        connection = RemovedOaMemberRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        builder.rebuild_workbench_relation_read_model_relation_delta(
            "2026-04",
            row_ids=["781cbe29-c790-4ad4-b6fb-7b4530813fa6"],
        )

        self.assertEqual(
            repository.previous_distribution_calls[0]["row_ids"],
            ["781cbe29-c790-4ad4-b6fb-7b4530813fa6", "bank-nanjing"],
        )
        self.assertEqual(
            repository.saved_rows[0]["affected_row_ids"],
            [
                "781cbe29-c790-4ad4-b6fb-7b4530813fa6",
                "bank-nanjing",
                "oa-yang",
            ],
        )
        self.assertEqual(
            repository.saved_rows[0]["groups"][0]["bank_transaction_ids"],
            ["bank-nanjing"],
        )

    def test_cross_month_member_index_schema_change_invalidates_old_scope(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        connection = CrossMonthRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )
        source_versions = builder._source_versions()
        self.assertEqual(
            source_versions["workbench_relation_schema_version"],
            "2026-07-26-exact-membership-proof-v1",
        )
        self.assertNotIn("workbench_reconciliation_decisions_updated_at", source_versions)
        repository.existing_scope_summary = {
            "scope_key": "2026-04",
            "row_count": 2,
            "group_count": 1,
            "source_versions": {
                **source_versions,
                "workbench_relation_schema_version": "2026-06-oa-pending-bank-claim-exclusion-v1",
            },
            "cache_status": "fresh",
        }

        result = builder.rebuild_workbench_relation_read_model_scope("2026-04")

        self.assertNotIn("skip_reason", result)
        saved = repository.saved[0]
        self.assertEqual(
            saved["source_versions"]["workbench_relation_schema_version"],
            "2026-07-26-exact-membership-proof-v1",
        )
        rows_by_id = {row["row_id"]: row for row in saved["rows"]}
        self.assertIn("input-invoice-nanjing", rows_by_id)

    def test_source_versions_are_scoped_to_month_and_active_relation_members(self) -> None:
        connection = ScopedSourceVersionsRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=CaptureWorkbenchRelationRepository(),
        )

        source_versions = builder._source_versions("2026-04")

        self.assertEqual(
            source_versions["workbench_relation_schema_version"],
            "2026-07-26-exact-membership-proof-v1",
        )
        self.assertNotIn("workbench_reconciliation_decisions_updated_at", source_versions)
        self.assertEqual(
            connection.fetch_one_calls[0][1],
            ("2026-04-01", "turnover_manual_closure"),
        )
        sql = connection.fetch_one_calls[0][0]
        self.assertIn("with scope as", sql)
        self.assertIn("scoped_relations as", sql)
        self.assertIn("relation.row_ids && objects.row_ids", sql)
        self.assertIn("active_relation_row_ids as", sql)
        self.assertIn("workbench_pair_relations_membership_digest", source_versions)
        self.assertIn("membership_digest", sql)
        self.assertIn("where status = 'active'", sql)
        self.assertIn("application_date >= scope.scope_month", sql)
        self.assertIn("application_date < scope.scope_month + interval '1 month'", sql)
        self.assertNotIn("workbench_reconciliation_decisions", sql)

    def test_bulk_source_versions_use_one_query_and_preserve_per_scope_relation_members(self) -> None:
        connection = BulkScopedSourceVersionsRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=CaptureWorkbenchRelationRepository(),
        )

        source_versions_by_scope = builder.source_versions_for_scopes(
            ["2026-04", "2026-05", "2026-04"]
        )

        self.assertEqual(list(source_versions_by_scope), ["2026-04", "2026-05"])
        self.assertEqual(len(connection.fetch_all_calls), 1)
        sql, params = connection.fetch_all_calls[0]
        self.assertEqual(
            params,
            (["2026-04-01", "2026-05-01"], "turnover_manual_closure"),
        )
        self.assertIn("with requested_scopes as", sql)
        self.assertIn("eligible_relations as", sql)
        self.assertIn("scoped_relations as", sql)
        self.assertIn("relation.row_ids && objects.row_ids", sql)
        self.assertIn("active_relation_row_ids as", sql)
        self.assertIn("where relations.status = 'active'", sql)
        self.assertIn("scope_row_ids as", sql)
        self.assertIn("application_date >= scopes.scope_month", sql)
        self.assertIn("application_date < scopes.scope_month + interval '1 month'", sql)
        self.assertNotIn("workbench_reconciliation_decisions", sql)
        self.assertEqual(
            source_versions_by_scope["2026-05"]["workbench_pair_relations_updated_at"],
            "2026-05-28T00:00:00+08:00",
        )
        self.assertEqual(
            source_versions_by_scope["2026-05"]["workbench_relation_schema_version"],
            "2026-07-26-exact-membership-proof-v1",
        )

    def test_bulk_source_versions_reject_non_month_scope(self) -> None:
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=BulkScopedSourceVersionsRelationProjectionConnection(),
            read_model_repository=CaptureWorkbenchRelationRepository(),
        )

        with self.assertRaisesRegex(ValueError, "month shards YYYY-MM"):
            builder.source_versions_for_scopes(["all"])

    def test_rebuild_keeps_oa_summary_for_legacy_completed_workflow_status(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        connection = LegacyCompletedOaRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        builder.rebuild_workbench_relation_read_model_scope("2026-04")

        rows_by_id = {row["row_id"]: row for row in repository.saved[0]["rows"]}
        bank_row = rows_by_id["bank-nanjing"]
        self.assertEqual([row["id"] for row in bank_row["linked_oa"]], ["oa-yang"])
        self.assertEqual(bank_row["linked_oa"][0]["status"], "已完成")
        oa_queries = [
            sql
            for sql in connection.sql_statements
            if "from app.oa_applications" in " ".join(sql.lower().split())
        ]
        self.assertTrue(any("已完成" in sql for sql in oa_queries))



    def test_rebuild_skips_unchanged_scope_without_scanning_or_resaving_distribution(self) -> None:
        repository = CaptureWorkbenchRelationRepository()
        connection = FailIfFetchAllRelationProjectionConnection()
        builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )
        source_versions = builder._source_versions("2026-01")
        repository.existing_scope_summary = {
            "scope_key": "2026-01",
            "row_count": 399,
            "group_count": 21,
            "source_versions": source_versions,
            "cache_status": "fresh",
        }

        result = builder.rebuild_workbench_relation_read_model_scope("2026-01")

        self.assertEqual(
            result,
            {
                "scope_key": "2026-01",
                "row_count": 399,
                "group_count": 21,
                "source_versions": source_versions,
                "skipped": True,
                "skip_reason": "source_versions_unchanged",
            },
        )
        self.assertEqual(repository.saved, [])
        self.assertEqual(repository.scope_summary_calls, [{"scope_key": "2026-01", "tenant_id": "default"}])


if __name__ == "__main__":
    unittest.main()
