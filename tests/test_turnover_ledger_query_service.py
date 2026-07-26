from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.services.postgres_repositories.turnover_ledger_snapshot import (
    turnover_ledger_canonical_snapshot,
)
from fin_ops_platform.services.turnover_ledger_query_service import TurnoverLedgerQueryService
from fin_ops_platform.services.turnover_ledger_relation_context import (
    apply_workbench_relation_context,
)


class _LocalLedger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_grouped_ledger(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("grouped", dict(kwargs)))
        return {
            "groups": [],
            "statistics": {
                "transaction_count": 0,
                "expense_transaction_count": 0,
                "income_transaction_count": 0,
                "ledger_group_count": 0,
                "closed_group_count": 0,
                "unclosed_group_count": 0,
                "linked_oa_transaction_count": 0,
                "linked_invoice_transaction_count": 0,
            },
            "pagination": {"page": 1, "page_size": 50, "total": 0},
        }

    def list_ledger(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("flat", dict(kwargs)))
        return {
            "rows": [],
            "pagination": {"page": 1, "page_size": 50, "total": 0},
        }

    def get_relation_detail(self, relation_id: str) -> dict[str, object]:
        self.calls.append(("detail", {"relation_id": relation_id}))
        return {"relation": {"relation_id": relation_id}}


class TurnoverLedgerQueryServiceTests(unittest.TestCase):
    def test_canonical_snapshot_is_one_repeatable_read_read_only_transaction(self) -> None:
        class Transaction:
            def __init__(self) -> None:
                self.statements: list[str] = []

            def execute(self, sql: str) -> None:
                self.statements.append(sql)

        transaction = Transaction()

        class Connection:
            @contextmanager
            def transaction(self):
                yield transaction

        with TemporaryDirectory() as temp_dir, patch(
            "fin_ops_platform.services.postgres_repositories.turnover_ledger_snapshot.default_data_dir",
            return_value=Path(temp_dir),
        ):
            with turnover_ledger_canonical_snapshot(Connection()) as state_store:
                self.assertIs(state_store._connection, transaction)

        self.assertEqual(
            transaction.statements,
            ["set transaction isolation level repeatable read read only"],
        )

    def test_grouped_query_reads_once_without_refresh_metadata(self) -> None:
        ledger = _LocalLedger()
        service = TurnoverLedgerQueryService(connection=None, local_ledger_service=ledger)  # type: ignore[arg-type]

        payload = service.list_ledger(view="grouped", family="personal", page=2, page_size=20)

        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("statistics_status", payload)
        self.assertNotIn("source_versions", payload)
        self.assertNotIn("refresh_enqueued", payload)
        self.assertNotIn("refresh_scope_keys", payload)
        self.assertEqual(
            ledger.calls,
            [
                (
                    "grouped",
                    {
                        "family": "personal",
                        "direction": "all",
                        "status": None,
                        "page": 2,
                        "page_size": 20,
                    },
                )
            ],
        )

    def test_relation_detail_uses_the_same_query_owner(self) -> None:
        ledger = _LocalLedger()
        service = TurnoverLedgerQueryService(connection=None, local_ledger_service=ledger)  # type: ignore[arg-type]

        payload = service.get_relation_detail("turnover-1")

        self.assertEqual(payload["relation"], {"relation_id": "turnover-1"})
        self.assertEqual(ledger.calls, [("detail", {"relation_id": "turnover-1"})])

    def test_missing_canonical_source_fails_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "canonical connection or local service"):
            TurnoverLedgerQueryService(connection=None)

    def test_canonical_relation_context_marks_both_sides_of_zero_difference_closure(self) -> None:
        rows = [
            {
                "bank_row_ids": ["bank-income", "bank-expense"],
                "summary_row": {"bank_row_ids": ["bank-income", "bank-expense"]},
                "rows": [{"bank_row_ids": ["bank-income", "bank-expense"]}],
                "flow_rows": [
                    {
                        "source_bank_row_id": "bank-income",
                        "bank_row_ids": ["bank-income"],
                        "flow_direction": "income",
                        "flow_amount": "140000.00",
                    },
                    {
                        "source_bank_row_id": "bank-expense",
                        "bank_row_ids": ["bank-expense"],
                        "flow_direction": "expense",
                        "flow_amount": "140000.00",
                    },
                ],
            }
        ]
        source_rows = [
            {
                "case_id": "case-closure",
                "relation_mode": "turnover_manual_closure",
                "status": "active",
                "row_ids": ["bank-income", "bank-expense"],
                "row_types": ["bank", "bank"],
                "raw_payload": {
                    "normalized_payload": {
                        "case_id": "case-closure",
                        "relation_mode": "turnover_manual_closure",
                        "status": "active",
                        "row_ids": ["bank-income", "bank-expense"],
                        "row_types": ["bank", "bank"],
                    }
                },
            }
        ]

        [group] = apply_workbench_relation_context(rows, source_rows)

        self.assertTrue(group["cash_closure_linked"])
        self.assertEqual(group["cash_closure_case_id"], "case-closure")
        self.assertEqual(group["rows"][0], group["summary_row"])
        self.assertEqual(
            [flow["cash_closure_linked"] for flow in group["flow_rows"]],
            [True, True],
        )


if __name__ == "__main__":
    unittest.main()
