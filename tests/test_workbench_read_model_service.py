import unittest

from fin_ops_platform.services.workbench_read_model_service import WorkbenchReadModelService


class WorkbenchReadModelServiceTests(unittest.TestCase):
    def test_upsert_read_model_can_be_looked_up_by_scope(self) -> None:
        service = WorkbenchReadModelService()

        read_model = service.upsert_read_model(
            scope_key="all",
            payload={"summary": {"paired_count": 3}},
            ignored_rows=[{"id": "ignored-bank-001", "type": "bank"}],
            generated_at="2026-04-08T12:00:00+00:00",
        )

        self.assertEqual(read_model["scope_type"], "all_time")
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
                        "scope_key": "all",
                        "scope_type": "all_time",
                        "generated_at": "2026-04-08T12:00:00+00:00",
                        "payload": {"summary": {"paired_count": 5}},
                        "ignored_rows": [],
                    },
                    "2026-03": {
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


    def test_list_scope_keys_returns_current_scopes(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
