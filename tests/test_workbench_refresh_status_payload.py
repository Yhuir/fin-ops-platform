from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_refresh_status_payload import WorkbenchRefreshStatusPayloadNormalizer


class WorkbenchRefreshStatusPayloadNormalizerTests(unittest.TestCase):
    def test_failed_dirty_scope_sets_failed_retryable_status_and_version(self) -> None:
        normalizer = WorkbenchRefreshStatusPayloadNormalizer()

        payload = normalizer.normalize(
            {
                "read_model_status": "stale",
                "dirty_scopes": [
                    {
                        "scope_key": "2026-05",
                        "status": "failed",
                        "last_error": "projection boom",
                        "source_version": 12,
                    }
                ],
            },
            scope_key="all",
        )

        self.assertEqual(payload["read_model_status"], "failed")
        self.assertEqual(payload["last_error"], "projection boom")
        self.assertEqual(payload["read_model_version"], 12)
        self.assertTrue(payload["retryable"])

    def test_requeued_failed_scope_is_refreshing_and_not_retryable(self) -> None:
        normalizer = WorkbenchRefreshStatusPayloadNormalizer()

        payload = normalizer.normalize(
            {
                "read_model_status": "refreshing",
                "dirty_scopes": [
                    {"scope_key": "2026-03", "status": "failed", "last_error": "old boom", "source_version": 12},
                    {"scope_key": "2026-03", "status": "processing", "source_version": 13},
                ],
            },
            scope_key="all",
        )

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIsNone(payload["last_error"])
        self.assertEqual(payload["read_model_version"], 12)
        self.assertFalse(payload["retryable"])

if __name__ == "__main__":
    unittest.main()
