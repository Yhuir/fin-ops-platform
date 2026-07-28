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
                        "relation_id": "turnover-1",
                        "flow_direction": "income",
                        "flow_amount": "140000.00",
                        "borrow_amount": "140000.00",
                        "repayment_amount": "0.00",
                        "business_type": "borrow_in",
                    },
                    {
                        "source_bank_row_id": "bank-expense",
                        "bank_row_ids": ["bank-expense"],
                        "relation_id": "turnover-1",
                        "flow_direction": "expense",
                        "flow_amount": "140000.00",
                        "borrow_amount": "0.00",
                        "repayment_amount": "140000.00",
                        "business_type": "borrow_in",
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
        self.assertTrue(group["cash_pair_linked"])
        self.assertFalse(group["paired_unsettled"])
        self.assertEqual(group["closed_amount"], "0.00")
        self.assertEqual(group["pending_direction"], "none")
        self.assertEqual(group["cash_closure_case_id"], "case-closure")
        self.assertEqual(group["rows"][0], group["summary_row"])
        self.assertEqual(
            [flow["cash_closure_linked"] for flow in group["flow_rows"]],
            [True, True],
        )

    def test_active_case_with_balance_is_paired_unsettled(self) -> None:
        rows = [
            self._group(
                [
                    self._flow("bank-income", "income", "100.00", "100.00", "0.00"),
                    self._flow("bank-expense", "expense", "60.00", "0.00", "60.00"),
                ]
            )
        ]

        [group] = apply_workbench_relation_context(
            rows,
            [self._active_case("case-open", ["bank-income", "bank-expense"])],
        )

        self.assertTrue(group["cash_pair_linked"])
        self.assertTrue(group["paired_unsettled"])
        self.assertFalse(group["cash_closure_linked"])
        self.assertEqual(group["pending_repayment_amount"], "40.00")
        self.assertEqual(group["pending_collection_amount"], "0.00")
        self.assertEqual(group["pending_direction"], "repayment")
        self.assertEqual(group["closed_amount"], "0.00")

    def test_active_cases_are_not_netted_across_case_boundaries(self) -> None:
        flows = [
            self._flow("case-a-in", "income", "100.00", "100.00", "0.00"),
            self._flow("case-a-out", "expense", "60.00", "0.00", "60.00"),
            self._flow("case-b-in", "income", "60.00", "60.00", "0.00"),
            self._flow("case-b-out", "expense", "100.00", "0.00", "100.00"),
        ]

        [group] = apply_workbench_relation_context(
            [self._group(flows)],
            [
                self._active_case("case-a", ["case-a-in", "case-a-out"]),
                self._active_case("case-b", ["case-b-in", "case-b-out"]),
            ],
        )

        self.assertEqual(group["pending_direction"], "mixed")
        self.assertEqual(group["pending_repayment_amount"], "40.00")
        self.assertEqual(group["pending_collection_amount"], "40.00")
        self.assertFalse(group["cash_closure_linked"])

    def test_active_case_pending_direction_uses_business_type_and_balance_sign(self) -> None:
        cases = [
            ("borrow_in", "100.00", "60.00", "repayment", "40.00", "0.00"),
            ("borrow_in", "60.00", "100.00", "collection", "0.00", "40.00"),
            ("borrow_out", "100.00", "60.00", "collection", "0.00", "40.00"),
            ("borrow_out", "60.00", "100.00", "repayment", "40.00", "0.00"),
        ]
        for business_type, principal, settlement, direction, repayment, collection in cases:
            with self.subTest(business_type=business_type, principal=principal, settlement=settlement):
                principal_direction = "income" if business_type == "borrow_in" else "expense"
                settlement_direction = "expense" if business_type == "borrow_in" else "income"
                [group] = apply_workbench_relation_context(
                    [
                        self._group(
                            [
                                self._flow(
                                    "bank-principal",
                                    principal_direction,
                                    principal,
                                    principal,
                                    "0.00",
                                    business_type=business_type,
                                ),
                                self._flow(
                                    "bank-settlement",
                                    settlement_direction,
                                    settlement,
                                    "0.00",
                                    settlement,
                                    business_type=business_type,
                                ),
                            ]
                        )
                    ],
                    [self._active_case("case-balance", ["bank-principal", "bank-settlement"])],
                )

                self.assertTrue(group["cash_pair_linked"])
                self.assertTrue(group["paired_unsettled"])
                self.assertEqual(group["pending_direction"], direction)
                self.assertEqual(group["pending_repayment_amount"], repayment)
                self.assertEqual(group["pending_collection_amount"], collection)

    def test_unpaired_zero_balance_is_not_closed(self) -> None:
        [group] = apply_workbench_relation_context(
            [
                self._group(
                    [
                        self._flow("bank-income", "income", "80.00", "80.00", "0.00"),
                        self._flow("bank-expense", "expense", "80.00", "0.00", "80.00"),
                    ]
                )
            ],
            [],
        )

        self.assertFalse(group["cash_pair_linked"])
        self.assertFalse(group["cash_closure_linked"])
        self.assertEqual(group["pending_direction"], "none")
        self.assertEqual(group["closed_amount"], "0.00")

    def test_relation_mode_does_not_close_cross_semantic_rows(self) -> None:
        rows = [
            self._group(
                [
                    self._flow("bank-income", "income", "90.00", "90.00", "0.00"),
                    self._flow(
                        "bank-expense",
                        "expense",
                        "90.00",
                        "0.00",
                        "90.00",
                        business_type="borrow_out",
                    ),
                ]
            )
        ]

        [group] = apply_workbench_relation_context(
            rows,
            [self._active_case("case-invalid", ["bank-income", "bank-expense"])],
        )

        self.assertFalse(group["cash_pair_linked"])
        self.assertFalse(group["cash_closure_linked"])
        self.assertEqual(group["closed_amount"], "0.00")

    def test_active_case_without_both_cash_directions_fails_closed(self) -> None:
        [group] = apply_workbench_relation_context(
            [
                self._group(
                    [
                        self._flow("bank-a", "income", "50.00", "50.00", "0.00"),
                        self._flow("bank-b", "income", "50.00", "0.00", "50.00"),
                    ]
                )
            ],
            [self._active_case("case-invalid-cash", ["bank-a", "bank-b"])],
        )

        self.assertFalse(group["cash_pair_linked"])
        self.assertFalse(group["cash_closure_linked"])

    @staticmethod
    def _flow(
        row_id: str,
        direction: str,
        amount: str,
        borrow_amount: str,
        repayment_amount: str,
        *,
        business_type: str = "borrow_in",
    ) -> dict[str, object]:
        return {
            "source_bank_row_id": row_id,
            "bank_row_ids": [row_id],
            "relation_id": "turnover-shared",
            "flow_direction": direction,
            "flow_amount": amount,
            "borrow_amount": borrow_amount,
            "repayment_amount": repayment_amount,
            "business_type": business_type,
            "category_code": "business_warranty_pending_collection"
            if business_type == "business_receivable"
            else "",
        }

    @staticmethod
    def _group(flows: list[dict[str, object]]) -> dict[str, object]:
        bank_row_ids = [str(flow["source_bank_row_id"]) for flow in flows]
        return {
            "bank_row_ids": bank_row_ids,
            "summary_row": {"bank_row_ids": bank_row_ids},
            "rows": [{"bank_row_ids": bank_row_ids}],
            "flow_rows": flows,
            "pending_repayment_amount": "0.00",
            "pending_collection_amount": "0.00",
            "closed_amount": "0.00",
        }

    @staticmethod
    def _active_case(case_id: str, row_ids: list[str]) -> dict[str, object]:
        normalized_payload = {
            "case_id": case_id,
            "relation_mode": "turnover_manual_closure",
            "status": "active",
            "row_ids": row_ids,
            "row_types": ["bank"] * len(row_ids),
        }
        return {
            **normalized_payload,
            "raw_payload": {"normalized_payload": normalized_payload},
        }


if __name__ == "__main__":
    unittest.main()
