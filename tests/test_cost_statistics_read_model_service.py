import unittest

from fin_ops_platform.services.cost_statistics_read_model_service import (
    COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
    CostStatisticsReadModelService,
)


class CostStatisticsReadModelServiceTests(unittest.TestCase):
    def test_scope_key_validates_month_and_project_scope(self) -> None:
        self.assertEqual(
            CostStatisticsReadModelService.scope_key("2026-05", "active"),
            "active:2026-05",
        )
        self.assertEqual(CostStatisticsReadModelService.scope_key("all", "all"), "all:all")

        with self.assertRaises(ValueError):
            CostStatisticsReadModelService.scope_key("", "active")
        with self.assertRaises(ValueError):
            CostStatisticsReadModelService.scope_key("2026-05", "archived")
        with self.assertRaises(ValueError):
            CostStatisticsReadModelService.scope_key("202605", "active")

    def test_upsert_and_get_return_deep_copies(self) -> None:
        service = CostStatisticsReadModelService()
        payload = {
            "summary": {"transaction_count": "3"},
            "time_rows": [{"month": "2026-05"}],
        }

        read_model = service.upsert_read_model(
            "2026-05",
            "active",
            payload,
            generated_at="2026-05-04T12:00:00+00:00",
            source_scope_keys=["workbench:2026-05"],
        )
        payload["summary"]["transaction_count"] = 99
        read_model["payload"]["summary"]["transaction_count"] = 7

        loaded = service.get_read_model("2026-05", "active")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["scope_key"], "active:2026-05")
        self.assertEqual(loaded["scope_type"], "month")
        self.assertEqual(loaded["schema_version"], COST_STATISTICS_READ_MODEL_SCHEMA_VERSION)
        self.assertEqual(loaded["entry_count"], 3)
        self.assertEqual(loaded["payload"]["summary"]["transaction_count"], "3")
        loaded["payload"]["summary"]["transaction_count"] = 0
        self.assertEqual(
            service.get_read_model_by_scope_key("active:2026-05")["payload"]["summary"]["transaction_count"],
            "3",
        )

    def test_from_snapshot_discards_mismatched_schema_versions(self) -> None:
        service = CostStatisticsReadModelService.from_snapshot(
            {
                "read_models": {
                    "active:2026-05": {
                        "scope_key": "active:2026-05",
                        "scope_type": "month",
                        "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                        "month": "2026-05",
                        "project_scope": "active",
                        "generated_at": "2026-05-04T12:00:00+00:00",
                        "cache_status": "ready",
                        "entry_count": 2,
                        "payload": {"summary": {"transaction_count": 2}},
                        "source_scope_keys": [],
                    },
                    "active:2026-04": {
                        "scope_key": "active:2026-04",
                        "scope_type": "month",
                        "schema_version": "old",
                        "month": "2026-04",
                        "project_scope": "active",
                        "generated_at": "2026-05-04T12:00:00+00:00",
                        "cache_status": "ready",
                        "entry_count": 1,
                        "payload": {"summary": {"transaction_count": 1}},
                        "source_scope_keys": [],
                    },
                }
            }
        )

        self.assertEqual(service.list_scope_keys(), ["active:2026-05"])
        self.assertIsNone(service.get_read_model("2026-04", "active"))

    def test_invalidate_months_removes_months_and_all_time_scopes(self) -> None:
        service = CostStatisticsReadModelService()
        for month in ("2026-04", "2026-05", "all"):
            for project_scope in ("active", "all"):
                service.upsert_read_model(
                    month,
                    project_scope,
                    {"time_rows": [{"id": f"{project_scope}:{month}"}]},
                    generated_at="2026-05-04T12:00:00+00:00",
                )

        deleted = service.invalidate_months(["2026-05"], include_all=True)

        self.assertCountEqual(deleted, ["active:2026-05", "all:2026-05", "active:all", "all:all"])
        self.assertCountEqual(service.list_scope_keys(), ["active:2026-04", "all:2026-04"])

    def test_invalidate_months_treats_empty_month_values_as_all_time(self) -> None:
        service = CostStatisticsReadModelService()
        service.upsert_read_model(
            "all",
            "active",
            {"time_rows": [{"id": "active:all"}]},
            generated_at="2026-05-04T12:00:00+00:00",
        )

        self.assertEqual(service.invalidate_months([""], project_scopes=["active"]), ["active:all"])

    def test_list_read_model_metadata_uses_transaction_count_then_time_rows(self) -> None:
        service = CostStatisticsReadModelService()
        service.upsert_read_model(
            "2026-05",
            "active",
            {"summary": {"transaction_count": "4"}, "time_rows": [{"id": "ignored"}]},
            generated_at="2026-05-04T12:00:00+00:00",
        )
        service.upsert_read_model(
            "all",
            "all",
            {"summary": {"transaction_count": "invalid"}, "time_rows": [{"id": "a"}, {"id": "b"}]},
            generated_at="2026-05-04T12:01:00+00:00",
            cache_status="warming",
        )

        self.assertEqual(
            service.list_read_model_metadata(),
            [
                {
                    "scope_key": "active:2026-05",
                    "scope_type": "month",
                    "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                    "month": "2026-05",
                    "project_scope": "active",
                    "generated_at": "2026-05-04T12:00:00+00:00",
                    "cache_status": "ready",
                    "entry_count": 4,
                    "source_scope_keys": [],
                },
                {
                    "scope_key": "all:all",
                    "scope_type": "all_time",
                    "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                    "month": "all",
                    "project_scope": "all",
                    "generated_at": "2026-05-04T12:01:00+00:00",
                    "cache_status": "warming",
                    "entry_count": 2,
                    "source_scope_keys": [],
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
