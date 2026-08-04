import unittest

from fin_ops_platform.app.worker import _load_oa_runtime_settings
from fin_ops_platform.services.mongo_oa_adapter import MongoOASettings
from fin_ops_platform.services.oa_sync_source_adapter import build_oa_sync_source_adapter


class OASyncWorkerWiringTests(unittest.TestCase):
    def test_oa_sync_source_adapter_uses_attachment_invoice_cache(self) -> None:
        cache = object()
        settings = MongoOASettings(host="127.0.0.1", database="form_data_db")

        adapter = build_oa_sync_source_adapter(
            settings=settings,
            attachment_invoice_cache=cache,
        )

        self.assertIs(adapter._attachment_invoice_cache, cache)

    def test_oa_sync_runtime_settings_include_attachment_invoice_promotion_mode(self) -> None:
        class Connection:
            def fetch_one(self, sql: str, params: object) -> dict[str, object]:
                return {
                    "settings_payload": {
                        "oa_import": {
                            "attachment_invoice_promotion_mode": "create_missing",
                        }
                    }
                }

        settings = _load_oa_runtime_settings(Connection())

        self.assertEqual(
            settings["oa_import"]["attachment_invoice_promotion_mode"],
            "create_missing",
        )


if __name__ == "__main__":
    unittest.main()
