from __future__ import annotations

from copy import deepcopy
import unittest

from fin_ops_platform.services.postgres_repositories.workbench_relation_receipt import (
    PostgresWorkbenchRelationReceiptRepository,
)


class _Connection:
    def __init__(self) -> None:
        self.receipt: dict[str, object] | None = None
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...]) -> dict[str, object] | None:
        self.calls.append((sql, params))
        if "from app.workbench_pair_relations" in sql:
            return {
                "id": "00000000-0000-4000-8000-000000000001",
                "case_id": "CASE-1",
                "version": 4,
                "row_ids": ["bank-legacy", "invoice-legacy"],
                "row_types": ["bank", "invoice"],
            }
        if "insert into app.workbench_relation_receipts" in sql:
            if self.receipt is not None:
                return None
            self.receipt = {
                "id": str(params[0]),
                "storage_uri": str(params[6]),
                "source_fingerprint": str(params[4]),
                "receipt_count": int(params[7]),
                "total_amount": str(params[8]),
                "snapshot": {"case_id": "CASE-1"},
                "generated_at": "2026-08-29T10:00:00+08:00",
            }
            return deepcopy(self.receipt)
        if "from app.workbench_relation_receipts" in sql:
            return deepcopy(self.receipt)
        raise AssertionError(sql)

    def fetch_all(self, sql: str, params: tuple[object, ...]) -> list[dict[str, object]]:
        self.calls.append((sql, params))
        if "from app.bank_transactions" in sql:
            return [{
                "id": "bank-id",
                "legacy_mongo_id": "bank-legacy",
                "txn_direction": "inflow",
                "amount": "100.00",
                "currency": "CNY",
            }]
        if "from app.invoices" in sql:
            return [{
                "id": "invoice-id",
                "legacy_mongo_id": "invoice-legacy",
                "invoice_type": "output",
                "invoice_no": "INV-1",
                "currency": "CNY",
            }]
        raise AssertionError(sql)


class PostgresWorkbenchRelationReceiptRepositoryTests(unittest.TestCase):
    def test_loads_the_active_relation_and_its_canonical_members(self) -> None:
        connection = _Connection()
        repository = PostgresWorkbenchRelationReceiptRepository(connection)

        relation = repository.load_active_relation("CASE-1")

        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["case_id"], "CASE-1")
        self.assertEqual([row["id"] for row in relation["bank_rows"]], ["bank-id"])
        self.assertEqual([row["id"] for row in relation["invoice_rows"]], ["invoice-id"])
        member_params = [params for sql, params in connection.calls if "= any" in sql]
        self.assertEqual(member_params, [
            (["bank-legacy", "invoice-legacy"],),
            (["bank-legacy", "invoice-legacy"],),
        ])

    def test_insert_is_idempotent_by_relation_source_fingerprint(self) -> None:
        connection = _Connection()
        repository = PostgresWorkbenchRelationReceiptRepository(connection)
        payload = {
            "id": "00000000-0000-4000-8000-000000000010",
            "relation_id": "00000000-0000-4000-8000-000000000001",
            "case_id": "CASE-1",
            "relation_version": 4,
            "source_fingerprint": "fingerprint-1",
            "file_object_id": "00000000-0000-4000-8000-000000000011",
            "storage_uri": "file:///receipt.pdf",
            "receipt_count": 1,
            "total_amount": "100.00",
            "snapshot": {"case_id": "CASE-1"},
            "generated_by_id": "user-1",
            "generated_by_account": "YNSYLP007",
            "generated_by_name": "财务用户",
        }

        first, first_created = repository.insert(payload)
        second, second_created = repository.insert(payload)

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["source_fingerprint"], "fingerprint-1")


if __name__ == "__main__":
    unittest.main()
