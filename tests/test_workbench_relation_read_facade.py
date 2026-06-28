from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_relation_read_facade import WorkbenchRelationReadFacade


class FakeDirectRelationService:
    def __init__(self, relations: list[dict[str, object]]) -> None:
        self.relations = [dict(relation) for relation in relations]
        self.row_id_calls: list[list[str]] = []
        self.list_calls = 0

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, object]]:
        self.row_id_calls.append(list(row_ids))
        requested = {str(row_id) for row_id in row_ids}
        return [
            dict(relation)
            for relation in self.relations
            if requested.intersection({str(row_id) for row_id in list(relation.get("row_ids") or [])})
        ]

    def list_active_relations(self) -> list[dict[str, object]]:
        self.list_calls += 1
        return [dict(relation) for relation in self.relations]


class WorkbenchRelationReadFacadeTests(unittest.TestCase):
    def test_get_by_row_ids_reads_direct_canonical_relations(self) -> None:
        relation_service = FakeDirectRelationService(
            [
                {
                    "case_id": "case-1",
                    "row_ids": ["oa-1", "txn-1", "inv-1"],
                    "row_types": ["oa", "bank", "invoice"],
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "month_scope": "2026-01",
                    "special_metadata": {"source": "unit"},
                }
            ]
        )
        facade = WorkbenchRelationReadFacade(relation_service=relation_service)

        payload = facade.get_by_row_ids(["txn-1", "txn-missing"], month_hint="2026-01")

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual([row["row_id"] for row in payload["rows"]], ["txn-1", "txn-missing"])
        self.assertEqual(payload["rows"][0]["row_type"], "bank_transaction")
        self.assertEqual(payload["rows"][0]["relation_status"], "linked")
        self.assertEqual(payload["rows"][0]["group_ids"], ["case-1"])
        self.assertEqual(payload["rows"][1]["relation_status"], "unlinked")
        self.assertEqual(payload["groups"][0]["group_id"], "case-1")
        self.assertEqual(payload["groups"][0]["bank_transaction_ids"], ["txn-1"])
        self.assertEqual(payload["scope_keys"], ["2026-01"])
        self.assertEqual(payload["source_versions"]["workbench_relation_source"], "canonical")
        self.assertEqual(relation_service.row_id_calls, [["txn-1", "txn-missing"]])

    def test_month_group_and_source_version_reads_use_direct_relation_service(self) -> None:
        relation_service = FakeDirectRelationService(
            [
                {
                    "case_id": "case-1",
                    "row_ids": ["txn-1"],
                    "row_types": ["bank"],
                    "status": "active",
                    "relation_mode": "no_oa_bank_batch",
                    "month_scope": "2026-01",
                },
                {
                    "case_id": "case-2",
                    "row_ids": ["txn-2"],
                    "row_types": ["bank"],
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "month_scope": "2026-02",
                },
            ]
        )
        facade = WorkbenchRelationReadFacade(relation_service=relation_service)

        monthly = facade.list_by_month("2026-01", row_types=["bank_transaction"])
        source_versions = facade.source_versions_for_month("2026-01")
        groups = facade.relation_groups_by_ids(["case-2"])
        unlinked = facade.list_unlinked("2026-01")

        self.assertEqual(monthly["status"], "fresh")
        self.assertEqual([row["row_id"] for row in monthly["rows"]], ["txn-1"])
        self.assertEqual(monthly["scope_keys"], ["2026-01"])
        self.assertEqual(source_versions["source_versions"]["workbench_relation_case_ids"], ["case-1"])
        self.assertEqual([group["group_id"] for group in groups["groups"]], ["case-2"])
        self.assertEqual(groups["rows"][0]["row_id"], "txn-2")
        self.assertEqual(unlinked["status"], "fresh")
        self.assertEqual(unlinked["scope_keys"], ["2026-01"])

    def test_missing_direct_reader_returns_unavailable_without_refresh_enqueue_shape(self) -> None:
        facade = WorkbenchRelationReadFacade(relation_service=object())

        payload = facade.get_by_row_ids(["txn-1"], month_hint="2026-01")

        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["scope_keys"], ["2026-01"])
        self.assertEqual(payload["stale_reasons"], ["relation_service_unavailable"])
        self.assertNotIn("refresh_enqueued", payload)
        self.assertNotIn("read_model_scope_keys", payload)


if __name__ == "__main__":
    unittest.main()
