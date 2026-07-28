from __future__ import annotations

from contextlib import contextmanager
import unittest

from fin_ops_platform.services.cost_statistics_canonical_repository import (
    LocalCostStatisticsCanonicalRepository,
    PostgresCostStatisticsCanonicalRepository,
)
from fin_ops_platform.services.oa_adapter import OAApplicationRecord


class _SnapshotTransaction:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.fetched: list[str] = []

    def execute(self, sql: str, _params: tuple = ()) -> None:
        self.executed.append(" ".join(sql.lower().split()))

    def fetch_one(self, sql: str, _params: tuple = ()):
        self.fetched.append(" ".join(sql.lower().split()))
        if "from app.app_settings" in self.fetched[-1]:
            return {"settings_payload": {}}
        return None

    def fetch_all(self, sql: str, _params: tuple = ()):
        normalized = " ".join(sql.lower().split())
        self.fetched.append(normalized)
        return []


class _Connection:
    def __init__(self) -> None:
        self.transaction_count = 0
        self.snapshot_transaction = _SnapshotTransaction()

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield self.snapshot_transaction


class _CategoryProvider:
    def bulk_get_for_rows(self, _rows):
        return {}


class CostStatisticsCanonicalRepositoryTests(unittest.TestCase):
    def test_load_uses_one_repeatable_read_snapshot_and_only_canonical_tables(self) -> None:
        connection = _Connection()

        snapshot = PostgresCostStatisticsCanonicalRepository(connection).load_snapshot()

        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(
            connection.snapshot_transaction.executed,
            ["set transaction isolation level repeatable read read only"],
        )
        sql = "\n".join(connection.snapshot_transaction.fetched)
        self.assertIn("from app.app_settings", sql)
        self.assertIn("from app.bank_transactions", sql)
        self.assertIn("from app.bank_transaction_categories", sql)
        self.assertIn("from app.bank_transaction_category_confirmations", sql)
        self.assertIn("from app.workbench_pair_relations", sql)
        self.assertNotIn("read_model.", sql)
        self.assertNotIn("job.", sql)
        self.assertEqual(snapshot["bank_rows"], [])
        self.assertEqual(snapshot["cost_groups"], [])

    def test_scoped_bank_flow_skips_oa_relation_io(self) -> None:
        connection = _Connection()

        PostgresCostStatisticsCanonicalRepository(connection).load_snapshot(
            scope_kind="month",
            scope_value="2026-03",
            view="time",
            include_statistics=False,
        )

        sql = "\n".join(connection.snapshot_transaction.fetched)
        self.assertIn("from app.bank_transactions", sql)
        self.assertIn("txn_month >= %s and txn_month < %s", sql)
        self.assertNotIn("from app.workbench_pair_relations", sql)
        self.assertNotIn("from app.oa_applications", sql)

    def test_scoped_cost_view_keeps_cross_month_members_of_matching_relation(self) -> None:
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
                    "workflow_status": "completed",
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
            {"bank-march", "bank-april"},
        )
        self.assertEqual(len(snapshot["cost_groups"]), 1)
        self.assertEqual(snapshot["available_years"], ["2026"])

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


if __name__ == "__main__":
    unittest.main()
