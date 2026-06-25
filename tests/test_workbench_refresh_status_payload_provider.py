from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_refresh_status_payload import WorkbenchRefreshStatusPayloadNormalizer
from fin_ops_platform.services.workbench_refresh_status_payload_provider import WorkbenchRefreshStatusPayloadProvider


class WorkbenchRefreshStatusPayloadProviderTests(unittest.TestCase):
    def test_unavailable_when_repository_has_no_refresh_status_port(self) -> None:
        provider = WorkbenchRefreshStatusPayloadProvider(
            repository_provider=lambda: object(),
            source_freshness=lambda payload, **_kwargs: payload,
            normalizer=WorkbenchRefreshStatusPayloadNormalizer(),
        )

        payload = provider.payload_for_scope("2026-05")

        self.assertEqual(payload["scope_key"], "2026-05")
        self.assertEqual(payload["read_model_status"], "unavailable")
        self.assertTrue(payload["retryable"])

    def test_normalizes_repository_payload_after_source_freshness(self) -> None:
        class Repository:
            def get_workbench_refresh_status(self, *, scope_key: str) -> dict[str, object]:
                return {"scope_key": scope_key, "read_model_status": "fresh"}

        def mark_stale(payload: dict[str, object], **_kwargs: object) -> dict[str, object]:
            return {**payload, "read_model_status": "stale", "read_model_stale_reasons": ["builder_mismatch"]}

        provider = WorkbenchRefreshStatusPayloadProvider(
            repository_provider=Repository,
            source_freshness=mark_stale,
            normalizer=WorkbenchRefreshStatusPayloadNormalizer(),
        )

        payload = provider.payload_for_scope("all")

        self.assertEqual(payload["read_model_status"], "stale")
        self.assertEqual(payload["read_model_stale_reasons"], ["builder_mismatch"])
        self.assertTrue(payload["retryable"])

    def test_non_dict_repository_payload_uses_unavailable_fallback(self) -> None:
        class Repository:
            def get_workbench_refresh_status(self, *, scope_key: str) -> object:
                return None

        provider = WorkbenchRefreshStatusPayloadProvider(
            repository_provider=Repository,
            source_freshness=lambda payload, **_kwargs: payload,
            normalizer=WorkbenchRefreshStatusPayloadNormalizer(),
        )

        payload = provider.payload_for_scope("all")

        self.assertEqual(payload["read_model_status"], "unavailable")
        self.assertTrue(payload["retryable"])


if __name__ == "__main__":
    unittest.main()
