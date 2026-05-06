import unittest

from fin_ops_platform.services.tax_offset_read_model_service import (
    TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
    TaxOffsetReadModelService,
)


class TaxOffsetReadModelServiceTests(unittest.TestCase):
    def test_scope_key_validates_month(self) -> None:
        self.assertEqual(TaxOffsetReadModelService.scope_key("2026-05"), "2026-05")

        with self.assertRaises(ValueError):
            TaxOffsetReadModelService.scope_key("")
        with self.assertRaises(ValueError):
            TaxOffsetReadModelService.scope_key("all")
        with self.assertRaises(ValueError):
            TaxOffsetReadModelService.scope_key("202605")

    def test_upsert_and_get_return_deep_copies(self) -> None:
        service = TaxOffsetReadModelService()
        payload = {
            "output_items": [{"id": "output-1"}, {"id": "output-2"}],
            "input_plan_items": [{"id": "input-1"}],
            "certified_items": [{"id": "cert-1"}, {"id": "cert-2"}, {"id": "cert-3"}],
        }

        read_model = service.upsert_read_model(
            "2026-05",
            payload,
            generated_at="2026-05-04T12:00:00+00:00",
            source_scope_keys=["tax-offset:source:2026-05"],
        )
        payload["output_items"].append({"id": "mutated"})
        read_model["payload"]["output_items"].clear()

        loaded = service.get_read_model("2026-05")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["scope_key"], "2026-05")
        self.assertEqual(loaded["scope_type"], "month")
        self.assertEqual(loaded["schema_version"], TAX_OFFSET_READ_MODEL_SCHEMA_VERSION)
        self.assertEqual(loaded["output_count"], 2)
        self.assertEqual(loaded["input_plan_count"], 1)
        self.assertEqual(loaded["certified_count"], 3)
        self.assertEqual(len(loaded["payload"]["output_items"]), 2)
        loaded["payload"]["output_items"].append({"id": "mutated-again"})
        self.assertEqual(len(service.get_read_model_by_scope_key("2026-05")["payload"]["output_items"]), 2)

    def test_from_snapshot_discards_mismatched_schema_versions(self) -> None:
        service = TaxOffsetReadModelService.from_snapshot(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "scope_type": "month",
                        "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                        "month": "2026-05",
                        "generated_at": "2026-05-04T12:00:00+00:00",
                        "cache_status": "ready",
                        "output_count": 1,
                        "input_plan_count": 1,
                        "certified_count": 1,
                        "payload": {
                            "output_items": [{"id": "output-1"}],
                            "input_plan_items": [{"id": "input-1"}],
                            "certified_items": [{"id": "cert-1"}],
                        },
                        "source_scope_keys": [],
                    },
                    "2026-04": {
                        "scope_key": "2026-04",
                        "scope_type": "month",
                        "schema_version": "old",
                        "month": "2026-04",
                        "generated_at": "2026-05-04T12:00:00+00:00",
                        "cache_status": "ready",
                        "output_count": 1,
                        "input_plan_count": 1,
                        "certified_count": 1,
                        "payload": {
                            "output_items": [{"id": "output-1"}],
                            "input_plan_items": [{"id": "input-1"}],
                            "certified_items": [{"id": "cert-1"}],
                        },
                        "source_scope_keys": [],
                    },
                }
            }
        )

        self.assertEqual(service.list_scope_keys(), ["2026-05"])
        self.assertIsNone(service.get_read_model("2026-04"))

    def test_invalidate_months_removes_matching_months(self) -> None:
        service = TaxOffsetReadModelService()
        for month in ("2026-04", "2026-05"):
            service.upsert_read_model(
                month,
                {"output_items": [], "input_plan_items": [], "certified_items": []},
                generated_at="2026-05-04T12:00:00+00:00",
            )

        self.assertEqual(service.invalidate_months(["2026-05"]), ["2026-05"])
        self.assertEqual(service.list_scope_keys(), ["2026-04"])

    def test_list_read_model_metadata_contains_counts_without_payload(self) -> None:
        service = TaxOffsetReadModelService()
        service.upsert_read_model(
            "2026-05",
            {
                "output_items": [{"id": "output-1"}, {"id": "output-2"}],
                "input_plan_items": [{"id": "input-1"}],
                "certified_items": [{"id": "cert-1"}],
            },
            generated_at="2026-05-04T12:00:00+00:00",
            cache_status="warming",
        )

        self.assertEqual(
            service.list_read_model_metadata(),
            [
                {
                    "scope_key": "2026-05",
                    "scope_type": "month",
                    "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                    "month": "2026-05",
                    "generated_at": "2026-05-04T12:00:00+00:00",
                    "cache_status": "warming",
                    "output_count": 2,
                    "input_plan_count": 1,
                    "certified_count": 1,
                    "source_scope_keys": [],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
