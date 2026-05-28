import unittest

from fin_ops_platform.app.worker import _build_oa_sync_source_adapter
from fin_ops_platform.services.mongo_oa_adapter import MongoOASettings


class OASyncWorkerWiringTests(unittest.TestCase):
    def test_oa_sync_source_adapter_uses_attachment_invoice_cache(self) -> None:
        cache = object()
        settings = MongoOASettings(host="127.0.0.1", database="form_data_db")

        adapter = _build_oa_sync_source_adapter(
            settings=settings,
            attachment_invoice_cache=cache,
        )

        self.assertIs(adapter._attachment_invoice_cache, cache)


if __name__ == "__main__":
    unittest.main()
