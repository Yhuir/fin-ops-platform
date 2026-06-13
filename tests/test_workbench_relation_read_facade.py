from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_relation_distribution_mapper import (
    relation_dicts_by_row_id_from_distribution_payload,
)
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.workbench_relation_read_facade import WorkbenchRelationReadFacade


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class FakeRelationRepository:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload
        self.row_id_calls: list[dict[str, object]] = []
        self.month_calls: list[dict[str, object]] = []
        self.group_calls: list[dict[str, object]] = []

    def get_workbench_relation_rows_by_ids(
        self,
        row_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        self.row_id_calls.append({"row_ids": list(row_ids), "tenant_id": tenant_id})
        return self.payload

    def list_workbench_relation_rows(
        self,
        *,
        month: str,
        row_types: list[str] | None = None,
        relation_status: str | None = None,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        self.month_calls.append(
            {
                "month": month,
                "row_types": list(row_types or []),
                "relation_status": relation_status,
                "tenant_id": tenant_id,
            }
        )
        return self.payload

    def get_workbench_relation_groups_by_ids(
        self,
        group_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        self.group_calls.append({"group_ids": list(group_ids), "tenant_id": tenant_id})
        return self.payload


class PartialFreshRelationConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        if "from read_model.workbench_relation_rows" in normalized:
            return [
                {
                    "row_id": "txn-present",
                    "row_type": "bank_transaction",
                    "scope_key": "2026-03",
                    "scope_month": "2026-03-01",
                    "relation_status": "unlinked",
                    "group_ids": [],
                    "linked_oa": [],
                    "linked_bank_transactions": [],
                    "linked_input_invoices": [],
                    "linked_output_invoices": [],
                    "source_versions": {"workbench_relation_schema_version": "test"},
                    "payload": {"row_id": "txn-present", "row_type": "bank_transaction", "relation_status": "unlinked"},
                    "raw_payload": {},
                }
            ]
        if "from read_model.workbench_relation_groups" in normalized:
            return []
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, object] | None:
        normalized = " ".join(sql.lower().split())
        if "from read_model.workbench_relation_scopes" in normalized:
            return {
                "scope_key": "2026-03",
                "row_count": 1,
                "group_count": 0,
                "source_versions": {"workbench_relation_schema_version": "test"},
                "cache_status": "fresh",
            }
        if "from job.read_model_dirty_scopes" in normalized:
            return None
        return None


class WorkbenchRelationReadFacadeTests(unittest.TestCase):
    def test_get_by_row_ids_returns_fresh_linked_and_unlinked_contexts(self) -> None:
        repository = FakeRelationRepository(
            {
                "read_model_status": "fresh",
                "rows": [
                    {
                        "row_id": "txn-1",
                        "row_type": "bank_transaction",
                        "relation_status": "linked",
                        "group_ids": ["rel-1"],
                        "linked_oa": [{"id": "oa-1", "applicant": "田孟维"}],
                        "linked_bank_transactions": [{"id": "txn-1", "amount": "196.00"}],
                        "linked_input_invoices": [
                            {"id": "oa-att-inv-1", "invoice_no": "INV-001", "total_with_tax": "70.00"},
                            {"id": "oa-att-inv-2", "invoice_no": "INV-002", "total_with_tax": "126.00"},
                        ],
                        "linked_output_invoices": [],
                    },
                    {
                        "row_id": "txn-2",
                        "row_type": "bank_transaction",
                        "relation_status": "unlinked",
                        "group_ids": [],
                        "linked_oa": [],
                        "linked_bank_transactions": [{"id": "txn-2", "amount": "500.00"}],
                        "linked_input_invoices": [],
                        "linked_output_invoices": [],
                    },
                ],
                "groups": [{"group_id": "rel-1", "relation_kind": "oa_bank_input_invoice"}],
                "source_versions": {"workbench_relation_schema_version": "test"},
                "read_model_scope_keys": ["2026-01"],
            }
        )
        queue = QueueRecorder()
        facade = WorkbenchRelationReadFacade(read_model_repository=repository, queue_repository=queue)

        payload = facade.get_by_row_ids(["txn-1", "txn-2"], require_fresh=True, reason="unit_test")

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual([row["row_id"] for row in payload["rows"]], ["txn-1", "txn-2"])
        self.assertEqual(payload["rows"][0]["linked_input_invoices"][1]["invoice_no"], "INV-002")
        self.assertEqual(payload["rows"][1]["relation_status"], "unlinked")
        self.assertEqual(queue.refreshes, [])

    def test_repository_treats_missing_row_in_fresh_scope_as_unlinked_context(self) -> None:
        repository = PostgresReadModelRepository(PartialFreshRelationConnection())

        payload = repository.get_workbench_relation_rows_by_ids(["txn-present", "txn-missing"])

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual([row["row_id"] for row in payload["rows"]], ["txn-present"])
        self.assertEqual(payload["read_model_scope_keys"], ["2026-03"])

    def test_non_fresh_result_enqueues_refresh_when_required(self) -> None:
        repository = FakeRelationRepository(
            {
                "read_model_status": "missing",
                "rows": [],
                "groups": [],
                "source_versions": {},
                "read_model_scope_keys": ["2026-01"],
                "stale_reasons": ["read_model_missing"],
            }
        )
        queue = QueueRecorder()
        facade = WorkbenchRelationReadFacade(read_model_repository=repository, queue_repository=queue)

        payload = facade.get_by_row_ids(["txn-1"], require_fresh=True, reason="pending_invoice_projection")

        self.assertEqual(payload["status"], "missing")
        self.assertEqual(payload["rows"], [])
        self.assertTrue(payload["refresh_enqueued"])
        self.assertEqual(queue.refreshes, [("workbench_relation", "2026-01", "pending_invoice_projection")])

    def test_list_unlinked_filters_by_status_and_row_type(self) -> None:
        repository = FakeRelationRepository(
            {
                "read_model_status": "fresh",
                "rows": [{"row_id": "txn-2", "row_type": "bank_transaction", "relation_status": "unlinked"}],
                "groups": [],
                "source_versions": {},
                "read_model_scope_keys": ["2026-01"],
            }
        )
        facade = WorkbenchRelationReadFacade(read_model_repository=repository)

        payload = facade.list_unlinked("2026-01", row_types=["bank_transaction"])

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(repository.month_calls[0]["relation_status"], "unlinked")
        self.assertEqual(repository.month_calls[0]["row_types"], ["bank_transaction"])

    def test_distribution_mapper_preserves_candidate_relation_status(self) -> None:
        relations_by_row_id = relation_dicts_by_row_id_from_distribution_payload(
            {
                "rows": [
                    {
                        "row_id": "txn-candidate",
                        "row_type": "bank_transaction",
                        "relation_status": "candidate",
                        "group_ids": ["decision-open-candidate"],
                    }
                ],
                "groups": [
                    {
                        "group_id": "decision-open-candidate",
                        "scope_month": "2026-01",
                        "relation_source": "automatic_decision",
                        "relation_status": "candidate",
                        "payload": {
                            "row_ids": ["oa-candidate", "txn-candidate"],
                            "row_types": ["oa", "bank"],
                            "relation_mode": "automatic_decision",
                            "relation_status": "candidate",
                        },
                    }
                ],
            }
        )

        relation = relations_by_row_id["txn-candidate"][0]
        self.assertEqual(relation["status"], "candidate")
        self.assertEqual(relation["relation_status"], "candidate")
        self.assertEqual(relation["relationStatus"], "candidate")
        self.assertEqual(relation["relation_source"], "automatic_decision")


if __name__ == "__main__":
    unittest.main()
