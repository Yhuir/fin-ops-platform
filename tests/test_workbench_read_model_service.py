import unittest

from fin_ops_platform.services.workbench_read_model_service import (
    WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION,
    WorkbenchReadModelService,
)


class WorkbenchReadModelServiceTests(unittest.TestCase):
    def test_upsert_read_model_can_be_looked_up_by_scope(self) -> None:
        service = WorkbenchReadModelService()

        read_model = service.upsert_read_model(
            scope_key="all",
            payload={
                "workbench_read_model_schema_version": "application-payload-v1",
                "summary": {"paired_count": 3},
            },
            ignored_rows=[{"id": "ignored-bank-001", "type": "bank"}],
            generated_at="2026-04-08T12:00:00+00:00",
        )

        self.assertEqual(
            read_model["schema_version"],
            WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION,
        )
        self.assertEqual(read_model["scope_type"], "all_time")
        self.assertEqual(
            read_model["payload"]["workbench_read_model_schema_version"],
            "application-payload-v1",
        )
        self.assertEqual(read_model["ignored_rows"], [{"id": "ignored-bank-001", "type": "bank"}])
        self.assertEqual(service.get_read_model("all"), read_model)
        self.assertEqual(
            service.snapshot(),
            {
                "read_models": {
                    "all": read_model,
                }
            },
        )

    def test_delete_read_model_removes_scope(self) -> None:
        service = WorkbenchReadModelService.from_snapshot(
            {
                "read_models": {
                    "2026-03": {
                        "schema_version": WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION,
                        "scope_key": "2026-03",
                        "scope_type": "month",
                        "generated_at": "2026-04-08T12:00:00+00:00",
                        "payload": {"summary": {"paired_count": 2}},
                        "ignored_rows": [{"id": "ignored-invoice-001", "type": "invoice"}],
                    }
                }
            }
        )

        deleted = service.delete_read_model("2026-03")

        self.assertTrue(deleted)
        self.assertIsNone(service.get_read_model("2026-03"))
        self.assertEqual(service.snapshot(), {"read_models": {}})

    def test_snapshot_scope_keys_only_deepcopies_requested_models(self) -> None:
        service = WorkbenchReadModelService.from_snapshot(
            {
                "read_models": {
                    "all": {
                        "schema_version": WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION,
                        "scope_key": "all",
                        "scope_type": "all_time",
                        "generated_at": "2026-04-08T12:00:00+00:00",
                        "payload": {"summary": {"paired_count": 5}},
                        "ignored_rows": [],
                    },
                    "2026-03": {
                        "schema_version": WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION,
                        "scope_key": "2026-03",
                        "scope_type": "month",
                        "generated_at": "2026-04-08T12:00:00+00:00",
                        "payload": {"summary": {"paired_count": 2}},
                        "ignored_rows": [],
                    },
                }
            }
        )

        snapshot = service.snapshot_scope_keys(["2026-03"])

        self.assertEqual(
            snapshot,
            {
                "read_models": {
                    "2026-03": service.snapshot()["read_models"]["2026-03"],
                }
            },
        )
        self.assertEqual(
            snapshot["read_models"]["2026-03"]["schema_version"],
            WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION,
        )

    def test_from_snapshot_discards_read_models_with_old_schema_version(self) -> None:
        service = WorkbenchReadModelService.from_snapshot(
            {
                "read_models": {
                    "all": {
                        "schema_version": "old-schema",
                        "scope_key": "all",
                        "scope_type": "all_time",
                        "generated_at": "2026-04-08T12:00:00+00:00",
                        "payload": {"summary": {"paired_count": 5}},
                        "ignored_rows": [],
                    },
                    "2026-03": {
                        "schema_version": WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION,
                        "scope_key": "2026-03",
                        "scope_type": "month",
                        "generated_at": "2026-04-08T12:00:00+00:00",
                        "payload": {"summary": {"paired_count": 2}},
                        "ignored_rows": [],
                    },
                }
            }
        )

        self.assertIsNone(service.get_read_model("all"))
        self.assertIsNotNone(service.get_read_model("2026-03"))
        self.assertEqual(service.list_scope_keys(), ["2026-03"])

    def test_from_snapshot_discards_read_models_with_missing_schema_version(self) -> None:
        service = WorkbenchReadModelService.from_snapshot(
            {
                "read_models": {
                    "all": {
                        "scope_key": "all",
                        "scope_type": "all_time",
                        "generated_at": "2026-04-08T12:00:00+00:00",
                        "payload": {"summary": {"paired_count": 5}},
                        "ignored_rows": [],
                    },
                    "2026-03": {
                        "schema_version": WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION,
                        "scope_key": "2026-03",
                        "scope_type": "month",
                        "generated_at": "2026-04-08T12:00:00+00:00",
                        "payload": {"summary": {"paired_count": 2}},
                        "ignored_rows": [],
                    },
                }
            }
        )

        self.assertIsNone(service.get_read_model("all"))
        self.assertIsNotNone(service.get_read_model("2026-03"))
        self.assertEqual(service.list_scope_keys(), ["2026-03"])

    def test_list_scope_keys_returns_current_scopes(self) -> None:
        service = WorkbenchReadModelService.from_snapshot(
            {
                "read_models": {
                    "all": {
                        "schema_version": WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION,
                        "scope_key": "all",
                        "scope_type": "all_time",
                        "generated_at": "2026-04-08T12:00:00+00:00",
                        "payload": {"summary": {"paired_count": 5}},
                        "ignored_rows": [],
                    },
                    "2026-03": {
                        "schema_version": WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION,
                        "scope_key": "2026-03",
                        "scope_type": "month",
                        "generated_at": "2026-04-08T12:00:00+00:00",
                        "payload": {"summary": {"paired_count": 2}},
                        "ignored_rows": [],
                    },
                }
            }
        )

        self.assertCountEqual(service.list_scope_keys(), ["all", "2026-03"])

    def test_read_model_is_stale_when_case_snapshot_version_changes(self) -> None:
        service = WorkbenchReadModelService()
        read_model = service.upsert_read_model(
            scope_key="2026-05",
            payload={"month": "2026-05", "summary": {"paired_count": 0}},
            exception_rules_version="exception_rules_v1",
            exception_projection_version="exception_projection_v1",
            case_snapshot_version="case:v1",
            pair_relation_snapshot_version="relation:v1",
            candidate_snapshot_version="candidate:v1",
            matching_rules_version="matching:v1",
        )

        self.assertEqual(read_model["case_snapshot_version"], "case:v1")
        self.assertTrue(
            service.is_read_model_fresh(
                "2026-05",
                exception_rules_version="exception_rules_v1",
                exception_projection_version="exception_projection_v1",
                case_snapshot_version="case:v1",
                pair_relation_snapshot_version="relation:v1",
                candidate_snapshot_version="candidate:v1",
                matching_rules_version="matching:v1",
            )
        )
        self.assertFalse(
            service.is_read_model_fresh(
                "2026-05",
                exception_rules_version="exception_rules_v1",
                exception_projection_version="exception_projection_v1",
                case_snapshot_version="case:v2",
                pair_relation_snapshot_version="relation:v1",
                candidate_snapshot_version="candidate:v1",
                matching_rules_version="matching:v1",
            )
        )
        self.assertIsNone(
            service.get_read_model_if_fresh(
                "2026-05",
                case_snapshot_version="case:v2",
            )
        )

    def test_read_model_is_stale_when_relation_snapshot_version_changes(self) -> None:
        service = WorkbenchReadModelService()
        service.upsert_read_model(
            scope_key="2026-05",
            payload={"month": "2026-05"},
            source_versions={
                "exception_rules_version": "exception_rules_v1",
                "exception_projection_version": "exception_projection_v1",
                "case_snapshot_version": "case:v1",
                "pair_relation_snapshot_version": "relation:v1",
                "candidate_snapshot_version": "candidate:v1",
                "matching_rules_version": "matching:v1",
            },
        )

        self.assertFalse(
            service.is_read_model_fresh(
                "2026-05",
                source_versions={
                    "exception_rules_version": "exception_rules_v1",
                    "exception_projection_version": "exception_projection_v1",
                    "case_snapshot_version": "case:v1",
                    "pair_relation_snapshot_version": "relation:v2",
                    "candidate_snapshot_version": "candidate:v1",
                    "matching_rules_version": "matching:v1",
                },
            )
        )

    def test_snapshot_version_changes_when_payload_changes(self) -> None:
        first = WorkbenchReadModelService.snapshot_version({"cases": {"WEX-1": {"status": "open"}}})
        second = WorkbenchReadModelService.snapshot_version({"cases": {"WEX-1": {"status": "closed"}}})

        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
