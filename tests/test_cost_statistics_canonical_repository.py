from __future__ import annotations

from contextlib import contextmanager
import unittest
from unittest.mock import patch

from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.cost_statistics_canonical_repository import (
    LocalCostStatisticsCanonicalRepository,
    PostgresCostStatisticsCanonicalRepository,
    _cost_oa_payload,
)
from fin_ops_platform.services.oa_adapter import OAApplicationRecord


class _SnapshotTransaction:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.fetched: list[str] = []
        self.fetch_calls: list[tuple[str, tuple]] = []

    def execute(self, sql: str, _params: tuple = ()) -> None:
        self.executed.append(" ".join(sql.lower().split()))

    def fetch_one(self, sql: str, _params: tuple = ()):
        normalized = " ".join(sql.lower().split())
        self.fetched.append(normalized)
        self.fetch_calls.append((normalized, _params))
        if "from app.app_settings" in normalized:
            return {"settings_payload": {}}
        return None

    def fetch_all(self, sql: str, _params: tuple = ()):
        normalized = " ".join(sql.lower().split())
        self.fetched.append(normalized)
        self.fetch_calls.append((normalized, _params))
        return []


class _Connection:
    def __init__(self) -> None:
        self.transaction_count = 0
        self.snapshot_transaction = _SnapshotTransaction()

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield self.snapshot_transaction


class _PopulatedCostSnapshotTransaction(_SnapshotTransaction):
    def fetch_all(self, sql: str, _params: tuple = ()):
        normalized = " ".join(sql.lower().split())
        self.fetched.append(normalized)
        self.fetch_calls.append((normalized, _params))
        if "select row_id, effective_category_code" in normalized:
            return [
                {
                    "row_id": "bank-1",
                    "effective_category_code": "salary",
                    "effective_category_label": "工资",
                    "effective_category_primary_label": "薪资社保福利",
                    "effective_category_sub_label": "工资",
                    "effective_category_source": "manual_confirmation",
                }
            ]
        if "select distinct extract(year from approved_at)" in normalized:
            return [{"year": 2026}]
        if "from app.oa_applications" in normalized:
            return [
                {
                    "row_id": "oa-1",
                    "form_type": "支付申请",
                    "workflow_status": "completed",
                    "approved_at": "2026-03-12 09:30:00",
                    "normalized_payload": {
                        "project_name": "性能项目",
                        "expense_type": "材料费",
                        "amount": "100.00",
                    },
                }
            ]
        if "from app.workbench_pair_relations" in normalized:
            return [
                {
                    "case_id": "case-1",
                    "relation_mode": "manual_confirmed",
                    "row_ids": ["oa-1", "bank-1"],
                    "row_types": ["oa", "bank"],
                    "month_scope": "2026-03",
                    "special_metadata": {},
                    "raw_payload": {},
                }
            ]
        if "from app.bank_transactions" in normalized:
            return [
                {
                    "row_id": "bank-1",
                    "account_no": "62220001",
                    "account_name": "测试账户",
                    "txn_direction": "outflow",
                    "counterparty_name_raw": "供应商",
                    "amount": "100.00",
                    "signed_amount": "-100.00",
                    "txn_date": "2026-04-01",
                    "trade_time": "2026-04-01 10:00:00",
                    "pay_receive_time": "2026-04-01 10:00:00",
                    "summary": "材料款",
                    "remark": "",
                    "project_id": "",
                    "bank_text_fields": {},
                }
            ]
        return []


class _PopulatedCostConnection(_Connection):
    def __init__(self) -> None:
        super().__init__()
        self.snapshot_transaction = _PopulatedCostSnapshotTransaction()


class _ConfiguredNoOaCostSnapshotTransaction(_PopulatedCostSnapshotTransaction):
    def fetch_one(self, sql: str, _params: tuple = ()):
        normalized = " ".join(sql.lower().split())
        self.fetched.append(normalized)
        self.fetch_calls.append((normalized, _params))
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_transaction_tags": {
                        "version": 1,
                        "definitions": [
                            {
                                "code": "salary",
                                "label": "工资",
                                "output_primary_label": "薪资社保福利",
                                "output_sub_label": "工资",
                            }
                        ],
                    },
                    "cost_statistics_no_oa_projects": {
                        "version": 1,
                        "schema_version": 1,
                        "projects": [
                            {
                                "id": "no-oa-project",
                                "display_name": "无 OA 项目",
                                "tag_codes": ["salary"],
                            }
                        ],
                    },
                }
            }
        return None


class _ConfiguredNoOaCostConnection(_Connection):
    def __init__(self) -> None:
        super().__init__()
        self.snapshot_transaction = _ConfiguredNoOaCostSnapshotTransaction()


class _NoOaCandidateTransaction(_SnapshotTransaction):
    def __init__(self) -> None:
        super().__init__()
        self.reads: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()):
        normalized = " ".join(sql.lower().split())
        self.fetched.append(normalized)
        self.reads.append((normalized, params))
        if "select row_id, effective_category_code" in normalized:
            return [
                {
                    "row_id": "bank-unpaired-outflow",
                    "effective_category_code": "fee",
                    "effective_category_label": "手续费",
                    "effective_category_primary_label": "费用",
                    "effective_category_sub_label": "手续费",
                    "effective_category_source": "auto",
                }
            ]
        if "from app.workbench_pair_relations" in normalized:
            return [
                {
                    "case_id": "case-protected",
                    "relation_mode": "manual_confirmed",
                    "row_ids": ["oa-1", "bank-protected"],
                    "row_types": ["oa", "bank"],
                    "month_scope": "2026-03",
                    "special_metadata": {},
                    "raw_payload": {},
                }
            ]
        if "from app.bank_transactions" in normalized:
            return [
                self._bank_row("bank-unpaired-outflow", "outflow", "8.00"),
                self._bank_row("bank-protected", "outflow", "9.00"),
                self._bank_row("bank-unpaired-income", "inflow", "10.00"),
            ]
        return []

    @staticmethod
    def _bank_row(row_id: str, direction: str, amount: str) -> dict[str, str]:
        return {
            "row_id": row_id,
            "account_no": "62220001",
            "account_name": "测试账户",
            "txn_direction": direction,
            "counterparty_name_raw": "往来方",
            "amount": amount,
            "signed_amount": f"-{amount}" if direction == "outflow" else amount,
            "txn_date": "2026-03-01",
            "trade_time": "2026-03-01 10:00:00",
            "pay_receive_time": "2026-03-01 10:00:00",
            "summary": "手续费",
            "remark": "",
            "project_id": "",
            "bank_text_fields": {},
        }


class _NoOaCandidateConnection(_Connection):
    def __init__(self) -> None:
        super().__init__()
        self.snapshot_transaction = _NoOaCandidateTransaction()


class _CategoryProvider:
    def bulk_get_for_rows(self, _rows):
        return {}


class CostStatisticsCanonicalRepositoryTests(unittest.TestCase):
    def test_cost_category_projection_defers_unused_full_payload(self) -> None:
        connection = _PopulatedCostConnection()

        PostgresCostStatisticsCanonicalRepository(connection).load_snapshot(
            view="bank_account",
            include_statistics=False,
        )

        projection_sql = next(
            query
            for query in connection.snapshot_transaction.fetched
            if "select row_id, effective_category_code" in query
        )
        source_sql = projection_sql.split(
            "source_rows as materialized", 1
        )[1].split("display_rows as materialized", 1)[0]
        self.assertIn("'{}'::jsonb as normalized_payload", source_sql)
        self.assertIn("classified_with_semantics as not materialized", projection_sql)

    def test_all_scope_avoids_large_relation_member_filter(self) -> None:
        connection = _PopulatedCostConnection()

        PostgresCostStatisticsCanonicalRepository(connection).load_snapshot(
            view="project",
            include_statistics=False,
            include_cost_row_tags=False,
        )

        relation_sql = next(
            query
            for query in connection.snapshot_transaction.fetched
            if "from app.workbench_pair_relations" in query
        )
        self.assertNotIn("unnest(row_ids, row_types)", relation_sql)

    def test_all_scope_without_no_oa_assignments_loads_only_relation_bank_rows(self) -> None:
        connection = _PopulatedCostConnection()

        PostgresCostStatisticsCanonicalRepository(connection).load_snapshot(
            view="project",
            include_statistics=False,
            include_cost_row_tags=False,
        )

        bank_sql, bank_params = next(
            (query, params)
            for query, params in connection.snapshot_transaction.fetch_calls
            if "from app.bank_transactions" in query
            and "select row_id, effective_category_code" not in query
        )
        self.assertIn("legacy_mongo_id = any(%s::text[])", bank_sql)
        self.assertIn(["bank-1"], bank_params)
        self.assertFalse(
            any(
                "select row_id, effective_category_code" in query
                for query in connection.snapshot_transaction.fetched
            )
        )

    def test_all_scope_with_no_oa_assignment_keeps_full_bank_scan(self) -> None:
        connection = _ConfiguredNoOaCostConnection()

        PostgresCostStatisticsCanonicalRepository(connection).load_snapshot(
            view="project",
            include_statistics=False,
            include_cost_row_tags=False,
        )

        bank_sql = next(
            query
            for query in connection.snapshot_transaction.fetched
            if "from app.bank_transactions" in query
            and "select row_id, effective_category_code" not in query
        )
        self.assertNotIn("legacy_mongo_id = any(%s::text[])", bank_sql)
        self.assertTrue(
            any(
                "select row_id, effective_category_code" in query
                for query in connection.snapshot_transaction.fetched
            )
        )

    def test_scoped_relation_filter_uses_gin_prefilter_and_exact_member_types(self) -> None:
        connection = _PopulatedCostConnection()

        PostgresCostStatisticsCanonicalRepository(connection).load_snapshot(
            scope_kind="month",
            scope_value="2026-04",
            view="project",
            include_statistics=False,
        )

        relation_sql = next(
            query
            for query in connection.snapshot_transaction.fetched
            if "from app.workbench_pair_relations" in query
        )
        self.assertIn("row_ids && %s::text[]", relation_sql)
        self.assertIn("unnest(row_ids, row_types)", relation_sql)

    def test_manual_allocation_snapshot_loads_only_relation_bank_rows(self) -> None:
        connection = _PopulatedCostConnection()

        snapshot = PostgresCostStatisticsCanonicalRepository(
            connection
        ).load_manual_allocation_task_snapshot()

        self.assertEqual([row["id"] for row in snapshot["bank_rows"]], ["bank-1"])
        bank_sql = next(
            query
            for query in connection.snapshot_transaction.fetched
            if "from app.bank_transactions" in query
            and "select row_id, effective_category_code" not in query
        )
        self.assertIn("legacy_mongo_id = any(%s::text[])", bank_sql)
        self.assertFalse(
            any(
                "select row_id, effective_category_code" in query
                for query in connection.snapshot_transaction.fetched
            )
        )

    def test_no_oa_candidate_snapshot_skips_oa_payload_and_classifies_only_candidates(self) -> None:
        connection = _NoOaCandidateConnection()

        snapshot = PostgresCostStatisticsCanonicalRepository(
            connection
        ).load_no_oa_tag_candidate_snapshot()

        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(
            [row["id"] for row in snapshot["bank_rows"]],
            ["bank-unpaired-outflow"],
        )
        self.assertEqual(snapshot["oa_related_bank_ids"], ["bank-protected"])
        self.assertEqual(snapshot["active_relation_count"], 1)
        self.assertEqual(snapshot["cost_groups"], [])
        sql = "\n".join(connection.snapshot_transaction.fetched)
        self.assertNotIn("from app.oa_applications", sql)
        projection_call = next(
            params
            for query, params in connection.snapshot_transaction.reads
            if "select row_id, effective_category_code" in query
        )
        self.assertIn(["bank-unpaired-outflow"], projection_call)
        self.assertNotIn("bank-protected", repr(projection_call))
        self.assertNotIn("bank-unpaired-income", repr(projection_call))

    def test_local_no_oa_candidate_snapshot_does_not_load_oa_rows(self) -> None:
        classified_row_ids: list[str] = []

        class RecordingCategoryProvider:
            def bulk_get_for_rows(self, rows):
                classified_row_ids.extend(row["id"] for row in rows)
                return {
                    "bank-unpaired-outflow": {
                        "effective_category_code": "fee",
                        "effective_category_label": "手续费",
                        "effective_category_primary_label": "费用",
                        "effective_category_sub_label": "手续费",
                    }
                }

        repository = LocalCostStatisticsCanonicalRepository(
            bank_rows_provider=lambda: [
                {"id": "bank-unpaired-outflow", "amount": "8.00", "txn_direction": "outflow"},
                {"id": "bank-protected", "amount": "9.00", "txn_direction": "outflow"},
                {"id": "bank-unpaired-income", "amount": "10.00", "txn_direction": "inflow"},
            ],
            relations_provider=lambda: [
                {
                    "case_id": "case-protected",
                    "status": "active",
                    "row_ids": ["oa-1", "bank-protected"],
                    "row_types": ["oa", "bank"],
                }
            ],
            oa_rows_by_ids_provider=lambda _ids: self.fail(
                "No-OA candidate snapshot must not load OA payloads."
            ),
            settings_provider=lambda: {},
            category_provider=RecordingCategoryProvider(),
        )

        snapshot = repository.load_no_oa_tag_candidate_snapshot()

        self.assertEqual(classified_row_ids, ["bank-unpaired-outflow"])
        self.assertEqual(
            [row["id"] for row in snapshot["bank_rows"]],
            ["bank-unpaired-outflow"],
        )
        self.assertEqual(snapshot["oa_related_bank_ids"], ["bank-protected"])

    def test_load_uses_one_repeatable_read_snapshot_and_only_canonical_tables(self) -> None:
        connection = _Connection()

        with patch(
            "fin_ops_platform.services.cost_statistics_canonical_repository.BankAccountResolver",
            wraps=BankAccountResolver,
        ) as resolver_class:
            snapshot = PostgresCostStatisticsCanonicalRepository(connection).load_snapshot()

        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(resolver_class.call_count, 1)
        self.assertEqual(
            connection.snapshot_transaction.executed,
            [
                "set transaction isolation level repeatable read read only",
                "set local jit = off",
            ],
        )
        sql = "\n".join(connection.snapshot_transaction.fetched)
        self.assertIn("from app.app_settings", sql)
        self.assertIn("from app.bank_transactions", sql)
        self.assertNotIn("from app.bank_transaction_categories", sql)
        self.assertNotIn("from app.bank_transaction_category_confirmations", sql)
        self.assertNotIn("from app.oa_applications", sql)
        self.assertNotIn("from app.workbench_pair_relations", sql)
        self.assertNotIn("read_model.", sql)
        self.assertNotIn("job.", sql)
        self.assertEqual(snapshot["bank_rows"], [])
        self.assertEqual(snapshot["cost_groups"], [])

    def test_scoped_cost_view_uses_bounded_seven_query_bank_date_snapshot(self) -> None:
        connection = _PopulatedCostConnection()

        snapshot = PostgresCostStatisticsCanonicalRepository(connection).load_snapshot(
            scope_kind="month",
            scope_value="2026-03",
            view="project",
            include_statistics=False,
        )

        self.assertEqual(connection.transaction_count, 1)
        self.assertLessEqual(len(connection.snapshot_transaction.fetched), 8)
        sql = "\n".join(connection.snapshot_transaction.fetched)
        self.assertIn("txn_month >= %s and txn_month < %s", sql)
        self.assertNotIn("approved_at >= %s::date and approved_at < %s::date", sql)
        self.assertIn("from app.bank_transaction_categories", sql)
        self.assertIn("from app.bank_transaction_category_confirmations", sql)
        self.assertEqual(len(snapshot["cost_groups"]), 1)
        self.assertEqual(snapshot["bank_rows"][0]["bank_tag_code"], "salary")
        self.assertEqual(
            snapshot["bank_rows"][0]["bank_tag_primary_label"],
            "薪资社保福利",
        )
        self.assertEqual(snapshot["bank_rows"][0]["bank_tag_sub_label"], "工资")

    def test_scoped_cost_view_keeps_only_bank_rows_in_requested_period(self) -> None:
        bank_rows = [
            {
                "id": "bank-march",
                "amount": "100.00",
                "txn_direction": "outflow",
                "trade_time": "2026-03-31 23:00:00",
            },
            {
                "id": "bank-april",
                "amount": "50.00",
                "txn_direction": "outflow",
                "trade_time": "2026-04-01 01:00:00",
            },
        ]
        relation = {
            "case_id": "case-cross-month",
            "status": "active",
            "row_ids": ["oa-1", "bank-march", "bank-april"],
            "row_types": ["oa", "bank", "bank"],
        }
        repository = LocalCostStatisticsCanonicalRepository(
            bank_rows_provider=lambda: bank_rows,
            relations_provider=lambda: [relation],
            oa_rows_by_ids_provider=lambda _ids: [
                {
                    "id": "oa-1",
                    "apply_type": "支付申请",
                    "workflow_status": "completed",
                    "completed_at": "2026-03-15 10:00:00",
                    "project_name": "跨月项目",
                    "expense_type": "材料费",
                    "amount": "150.00",
                }
            ],
            settings_provider=lambda: {},
            category_provider=_CategoryProvider(),
        )

        snapshot = repository.load_snapshot(
            scope_kind="month",
            scope_value="2026-03",
            view="project",
            include_statistics=False,
        )

        self.assertEqual(
            {row["id"] for row in snapshot["bank_rows"]},
            {"bank-march"},
        )
        self.assertEqual(len(snapshot["cost_groups"]), 1)
        self.assertEqual(
            {row["id"] for row in snapshot["cost_groups"][0]["bank_rows"]},
            {"bank-march", "bank-april"},
        )
        self.assertEqual(snapshot["available_years"], ["2026"])

    def test_active_relation_with_unavailable_oa_still_protects_bank_from_no_oa(self) -> None:
        repository = LocalCostStatisticsCanonicalRepository(
            bank_rows_provider=lambda: [
                {
                    "id": "bank-protected",
                    "amount": "8.00",
                    "txn_direction": "outflow",
                    "trade_time": "2026-03-20 10:00:00",
                }
            ],
            relations_provider=lambda: [
                {
                    "case_id": "case-protected",
                    "status": "active",
                    "row_ids": ["oa-unavailable", "bank-protected"],
                    "row_types": ["oa", "bank"],
                }
            ],
            oa_rows_by_ids_provider=lambda _ids: [],
            settings_provider=lambda: {},
            category_provider=_CategoryProvider(),
        )

        snapshot = repository.load_snapshot(
            scope_kind="all",
            scope_value=None,
            view="project",
            include_statistics=False,
        )

        self.assertEqual(len(snapshot["cost_groups"]), 1)
        self.assertEqual(snapshot["cost_groups"][0]["declared_oa_ids"], ["oa-unavailable"])
        self.assertEqual(snapshot["cost_groups"][0]["oa_rows"], [])
        self.assertEqual(snapshot["oa_related_bank_ids"], ["bank-protected"])

    def test_snapshot_preserves_canonical_oa_expense_item_fields(self) -> None:
        expense_items = [
            {
                "expense_item_id": "item-1",
                "project_id": "P-001",
                "project_name": "项目A",
                "expense_type": "交通费",
                "expense_content": "市内交通",
                "amount": "100.00",
            }
        ]
        oa = OAApplicationRecord(
            id="oa-exp-1",
            month="2026-03",
            section="unpaired",
            case_id=None,
            applicant="申请人",
            project_name="项目A",
            apply_type="日常报销",
            amount="100.00",
            counterparty_name="",
            reason="市内交通",
            relation_code="pending_match",
            relation_label="待关联",
            relation_tone="warn",
            workflow_status="completed",
            completed_at="2026-03-01 09:00:00",
            expense_items=expense_items,
        )
        repository = LocalCostStatisticsCanonicalRepository(
            bank_rows_provider=lambda: [
                {
                    "id": "bank-1",
                    "amount": "100.00",
                    "txn_direction": "outflow",
                    "trade_time": "2026-03-01 12:00:00",
                }
            ],
            relations_provider=lambda: [
                {
                    "case_id": "case-1",
                    "status": "active",
                    "row_ids": ["oa-exp-1", "bank-1"],
                    "row_types": ["oa", "bank"],
                }
            ],
            oa_rows_by_ids_provider=lambda _ids: [oa],
            settings_provider=lambda: {},
            category_provider=_CategoryProvider(),
        )

        snapshot = repository.load_snapshot()

        self.assertEqual(
            snapshot["cost_groups"][0]["oa_rows"][0]["expense_items"],
            expense_items,
        )

    def test_postgres_cost_oa_payload_excludes_unconsumed_attachment_trees(self) -> None:
        payload = _cost_oa_payload(
            {
                "apply_type": "日常报销",
                "project_name": "项目A；项目B",
                "amount": "100.00",
                "attachment_invoices": [{"invoice_no": "unused-root"}],
                "detail_fields": {
                    "项目编号": "P-001",
                    "费用类型": "交通费",
                    "附件详情": {"unused": True},
                },
                "expense_items": [
                    {
                        "expense_item_id": "item-1",
                        "project_name": "项目A",
                        "expense_type": "交通费",
                        "expense_content": "市内交通",
                        "amount": "100.00",
                        "attachment_invoices": [{"invoice_no": "unused-item"}],
                    }
                ],
            },
            row_id="oa-exp-1",
            workflow_status="completed",
        )

        self.assertEqual(payload["id"], "oa-exp-1")
        self.assertEqual(payload["detail_fields"], {"项目编号": "P-001", "费用类型": "交通费"})
        self.assertEqual(
            payload["expense_items"],
            [
                {
                    "expense_item_id": "item-1",
                    "project_name": "项目A",
                    "expense_type": "交通费",
                    "expense_content": "市内交通",
                    "amount": "100.00",
                }
            ],
        )
        self.assertNotIn("attachment_invoices", payload)


if __name__ == "__main__":
    unittest.main()
