from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import io
import json
import unittest
from unittest.mock import patch

from fin_ops_platform.services.import_audit_repair_service import build_import_audit_repair_plan
from fin_ops_platform.tools import import_audit_repair_ops


def _bank_file(*, batch_id: str = "batch-bank-1", decision: str = "created") -> dict[str, object]:
    normalized = {
        "source_unique_key": "bank-key-1",
        "account_no": "62220001",
        "pay_receive_time": "2026-07-01T10:00:00+08:00",
        "txn_direction": "expense",
        "amount": "100.00",
        "counterparty_name_raw": "供应商甲",
    }
    row_result = {
        "source_unique_key": "bank-key-1",
        "data_fingerprint": "fingerprint-1",
        "decision": decision,
        "decision_reason": "registered decision",
        "identity_kind": "stable",
        "account_no": normalized["account_no"],
        "trade_time": normalized["pay_receive_time"],
        "direction": normalized["txn_direction"],
        "amount": normalized["amount"],
        "counterparty_name": normalized["counterparty_name_raw"],
    }
    return {
        "file_id": "file-bank-1",
        "batch_id": batch_id,
        "raw_payload": {
            "normalized_payload": {
                "row_results": [row_result],
                "normalized_rows": [normalized],
            }
        },
        "row_count": 1,
        "success_count": 1 if decision == "created" else 0,
        "error_count": 0,
        "duplicate_count": 1 if decision == "duplicate_skipped" else 0,
        "suspected_duplicate_count": 0,
        "updated_count": 0,
    }


def _invoice_component(
    *,
    row_id: str,
    row_no: int,
    item: str,
    amount: str,
    tax_amount: str,
    total_with_tax: str,
) -> dict[str, object]:
    normalized = {
        "digital_invoice_no": "26117000001052654674",
        "invoice_no": "1052654674",
        "invoice_date": "2026-07-01",
        "seller_tax_no": "915300000000000001",
        "buyer_tax_no": "915300007194052520",
        "taxable_item_name": item,
        "amount": amount,
        "signed_amount": amount,
        "tax_amount": tax_amount,
        "total_with_tax": total_with_tax,
        "tax_rate": "13%",
    }
    return {
        "batch_id": "batch-invoice-1",
        "row_id": row_id,
        "row_no": row_no,
        "invoice_id": "invoice-1",
        "invoice_source_batch_id": "batch-invoice-1",
        "invoice_month": "2026-07",
        "row_raw_payload": {"normalized_payload": {"normalized_row": normalized}},
        "amount": "39.58",
        "signed_amount": "39.58",
        "tax_amount": "5.15",
        "total_with_tax": "44.73",
        "tax_rate": "13%",
        "invoice_raw_payload": {"normalized_payload": {"amount": "39.58"}},
    }


def _snapshot() -> dict[str, list[dict[str, object]]]:
    return {
        "bank_files": [_bank_file()],
        "bank_transactions": [
            {
                "transaction_id": "transaction-1",
                "source_unique_key": "bank-key-1",
                "data_fingerprint": "fingerprint-1",
                "source_batch_id": "batch-bank-1",
            }
        ],
        "bank_rows": [],
        "invoice_rows": [
            _invoice_component(
                row_id="row-invoice-1",
                row_no=1,
                item="服务",
                amount="39.58",
                tax_amount="5.15",
                total_with_tax="44.73",
            ),
            _invoice_component(
                row_id="row-invoice-2",
                row_no=2,
                item="折扣",
                amount="-1.77",
                tax_amount="-0.23",
                total_with_tax="-2.00",
            ),
        ],
    }


class ImportAuditRepairPlanTests(unittest.TestCase):
    def test_plan_restores_bank_provenance_and_aggregates_invoice_components(self) -> None:
        plan = build_import_audit_repair_plan(_snapshot())

        self.assertEqual(len(plan["bank_rows"]), 1)
        self.assertEqual(plan["bank_rows"][0]["row_id"], "batch_row:batch-bank-1:00001")
        self.assertEqual(plan["bank_rows"][0]["linked_object_id"], "transaction-1")
        self.assertEqual(len(plan["invoice_updates"]), 1)
        self.assertEqual(plan["invoice_updates"][0]["amount"], "37.81")
        self.assertEqual(plan["invoice_updates"][0]["tax_amount"], "4.92")
        self.assertEqual(plan["invoice_updates"][0]["total_with_tax"], "42.73")
        self.assertEqual(plan["affected_invoice_months"], ["2026-07"])
        self.assertEqual(
            plan["rollback_manifest"]["delete_bank_row_ids"],
            ["batch_row:batch-bank-1:00001"],
        )

    def test_plan_is_idempotent_when_deterministic_bank_row_and_invoice_totals_exist(self) -> None:
        snapshot = _snapshot()
        first_plan = build_import_audit_repair_plan(snapshot)
        bank_row = first_plan["bank_rows"][0]
        snapshot["bank_rows"] = [
            {
                key: bank_row.get(key)
                for key in (
                    "row_id",
                    "batch_id",
                    "row_no",
                    "source_unique_key",
                    "data_fingerprint",
                    "decision",
                    "linked_object_id",
                    "identity_kind",
                )
            }
        ]
        invoice_update = first_plan["invoice_updates"][0]
        for component in snapshot["invoice_rows"]:
            component.update(
                {
                    "amount": invoice_update["amount"],
                    "signed_amount": invoice_update["signed_amount"],
                    "tax_amount": invoice_update["tax_amount"],
                    "total_with_tax": invoice_update["total_with_tax"],
                    "tax_rate": invoice_update["tax_rate"],
                }
            )

        second_plan = build_import_audit_repair_plan(snapshot)

        self.assertEqual(second_plan["bank_rows"], [])
        self.assertEqual(second_plan["invoice_updates"], [])

    def test_plan_does_not_sum_identical_duplicate_invoice_rows(self) -> None:
        snapshot = _snapshot()
        duplicate = deepcopy(snapshot["invoice_rows"][0])
        duplicate["row_id"] = "row-invoice-duplicate"
        duplicate["row_no"] = 2
        snapshot["invoice_rows"] = [snapshot["invoice_rows"][0], duplicate]

        plan = build_import_audit_repair_plan(snapshot)

        self.assertEqual(plan["invoice_updates"], [])

    def test_plan_fails_closed_when_registered_counts_conflict_with_canonical_bank_owner(self) -> None:
        snapshot = _snapshot()
        snapshot["bank_transactions"][0]["source_batch_id"] = "different-batch"

        with self.assertRaisesRegex(ValueError, "decision counts"):
            build_import_audit_repair_plan(snapshot)

    def test_plan_resolves_preview_created_duplicate_from_canonical_batch_ownership(self) -> None:
        snapshot = _snapshot()
        bank_file = snapshot["bank_files"][0]
        payload = bank_file["raw_payload"]["normalized_payload"]
        payload["row_results"].append(deepcopy(payload["row_results"][0]))
        payload["normalized_rows"].append(deepcopy(payload["normalized_rows"][0]))
        bank_file.update({"row_count": 2, "success_count": 1, "duplicate_count": 1})

        plan = build_import_audit_repair_plan(snapshot)

        self.assertEqual([row["decision"] for row in plan["bank_rows"]], ["created", "duplicate_skipped"])
        self.assertEqual(
            [row["linked_object_id"] for row in plan["bank_rows"]],
            ["transaction-1", "transaction-1"],
        )

    def test_plan_fails_closed_on_legacy_existing_bank_row_ids(self) -> None:
        snapshot = _snapshot()
        snapshot["bank_rows"] = [
            {
                "row_id": "batch_row_00001",
                "batch_id": "batch-bank-1",
                "row_no": 1,
                "source_unique_key": "bank-key-1",
                "decision": "created",
            }
        ]

        with self.assertRaisesRegex(ValueError, "non-deterministic ids"):
            build_import_audit_repair_plan(snapshot)

    def test_cli_dry_run_uses_repeatable_read_snapshot(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.statements: list[str] = []

            @contextmanager
            def transaction(self):
                yield self

            def execute(self, sql: str, _params: tuple = ()) -> int:
                self.statements.append(sql)
                return 0

        connection = Connection()
        output = io.StringIO()
        with (
            patch.object(import_audit_repair_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(import_audit_repair_ops, "PostgresConnection", return_value=connection),
            patch.object(import_audit_repair_ops, "load_import_audit_repair_snapshot", return_value=_snapshot()),
        ):
            result = import_audit_repair_ops.main(["--dry-run"], stdout=output)

        self.assertEqual(result, 0)
        self.assertEqual(connection.statements, ["set transaction isolation level repeatable read read only"])
        self.assertFalse(json.loads(output.getvalue())["written"])

    def test_cli_execute_rejects_changed_fingerprint_before_writes(self) -> None:
        class Connection:
            @contextmanager
            def transaction(self):
                yield self

            def execute(self, _sql: str, _params: tuple = ()) -> int:
                return 0

            def fetch_one(self, _sql: str, _params: tuple = ()) -> dict[str, object]:
                return {"locked": True}

        connection = Connection()
        with (
            patch.object(import_audit_repair_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(import_audit_repair_ops, "PostgresConnection", return_value=connection),
            patch.object(import_audit_repair_ops, "load_import_audit_repair_snapshot", return_value=_snapshot()),
            patch.object(import_audit_repair_ops, "apply_import_audit_repair") as apply_repair,
            self.assertRaisesRegex(RuntimeError, "source changed"),
        ):
            import_audit_repair_ops.main(["--execute", "--expected-fingerprint", "stale"])

        apply_repair.assert_not_called()


if __name__ == "__main__":
    unittest.main()
