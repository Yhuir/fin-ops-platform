from __future__ import annotations

from http import HTTPStatus
import unittest

from fin_ops_platform.services.workbench_legacy_api_sql_read_provider import WorkbenchLegacyApiSqlReadProvider


class WorkbenchLegacyApiSqlReadProviderTests(unittest.TestCase):
    def test_returns_none_when_repository_has_no_view_port(self) -> None:
        provider = WorkbenchLegacyApiSqlReadProvider(
            repository_provider=lambda: object(),
            scope_key_for_month=lambda month: month,
            enqueue_workbench_refresh=lambda *_args, **_kwargs: None,
            stale_reasons=lambda *_args, **_kwargs: [],
            oa_sync_refresh_reason=lambda _view: None,
            enqueue_oa_projection_sync=lambda *_args, **_kwargs: None,
            current_oa_attachment_invoice_parser_version=lambda: "parser-v1",
            current_oa_projection_sync_version=lambda: "projection-v1",
        )

        self.assertIsNone(provider.read("2026-05"))

    def test_missing_sql_view_enqueues_refreshing_contract(self) -> None:
        class Repository:
            def get_workbench_view(self, **_kwargs: object) -> object:
                return None

        refreshes: list[tuple[str, str]] = []
        provider = WorkbenchLegacyApiSqlReadProvider(
            repository_provider=Repository,
            scope_key_for_month=lambda month: month,
            enqueue_workbench_refresh=lambda scope_key, *, reason: refreshes.append((scope_key, reason)),
            stale_reasons=lambda *_args, **_kwargs: [],
            oa_sync_refresh_reason=lambda _view: None,
            enqueue_oa_projection_sync=lambda *_args, **_kwargs: None,
            current_oa_attachment_invoice_parser_version=lambda: "parser-v1",
            current_oa_projection_sync_version=lambda: "projection-v1",
        )

        result = provider.read("2026-05")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status_code, HTTPStatus.ACCEPTED)
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(refreshes, [("2026-05", "api_miss")])

    def test_sql_view_maps_payload_metadata_and_query_arguments(self) -> None:
        calls: list[dict[str, object]] = []

        class Repository:
            def get_workbench_view(self, **kwargs: object) -> dict[str, object]:
                calls.append(kwargs)
                return {
                    "payload": {"open": {"groups": []}},
                    "refresh_status": "fresh",
                    "generated_at": "2026-05-22T09:30:00+00:00",
                    "rows_page": {"page": 3, "rows": [{"id": "bank-row-1"}]},
                }

        provider = WorkbenchLegacyApiSqlReadProvider(
            repository_provider=Repository,
            scope_key_for_month=lambda month: f"scope:{month}",
            enqueue_workbench_refresh=lambda *_args, **_kwargs: None,
            stale_reasons=lambda *_args, **_kwargs: [],
            oa_sync_refresh_reason=lambda _view: None,
            enqueue_oa_projection_sync=lambda *_args, **_kwargs: None,
            current_oa_attachment_invoice_parser_version=lambda: "parser-v1",
            current_oa_projection_sync_version=lambda: "projection-v1",
        )

        result = provider.read(
            "2026-05",
            page="3",
            page_size="10",
            status="open",
            source_kind="bank_transaction",
            search="supplier",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["read_model_status"], "fresh")
        self.assertEqual(result.payload["read_model_scope_key"], "scope:2026-05")
        self.assertEqual(result.payload["read_model_generated_at"], "2026-05-22T09:30:00+00:00")
        self.assertEqual(result.payload["rows_page"]["rows"], [{"id": "bank-row-1"}])
        self.assertEqual(
            calls,
            [
                {
                    "scope_key": "scope:2026-05",
                    "page": "3",
                    "page_size": "10",
                    "status": "open",
                    "source_kind": "bank_transaction",
                    "search": "supplier",
                }
            ],
        )

    def test_stale_source_versions_enqueue_refresh(self) -> None:
        class Repository:
            def get_workbench_view(self, **_kwargs: object) -> dict[str, object]:
                return {"payload": {"open": {"groups": []}}, "refresh_status": "fresh", "source_versions": {}}

        refreshes: list[tuple[str, str]] = []
        provider = WorkbenchLegacyApiSqlReadProvider(
            repository_provider=Repository,
            scope_key_for_month=lambda month: month,
            enqueue_workbench_refresh=lambda scope_key, *, reason: refreshes.append((scope_key, reason)),
            stale_reasons=lambda *_args, **_kwargs: ["builder_mismatch"],
            oa_sync_refresh_reason=lambda _view: None,
            enqueue_oa_projection_sync=lambda *_args, **_kwargs: None,
            current_oa_attachment_invoice_parser_version=lambda: "parser-v1",
            current_oa_projection_sync_version=lambda: "projection-v1",
        )

        result = provider.read("all")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.payload["read_model_status"], "stale")
        self.assertEqual(result.payload["read_model_stale_reasons"], ["builder_mismatch"])
        self.assertEqual(refreshes, [("all", "api_stale")])

    def test_oa_sync_refresh_reason_enqueues_projection_sync(self) -> None:
        class Repository:
            def get_workbench_view(self, **_kwargs: object) -> dict[str, object]:
                return {"payload": {"open": {"groups": []}}, "generated_at": "2026-05-22"}

        syncs: list[tuple[str, str]] = []
        provider = WorkbenchLegacyApiSqlReadProvider(
            repository_provider=Repository,
            scope_key_for_month=lambda month: month,
            enqueue_workbench_refresh=lambda *_args, **_kwargs: None,
            stale_reasons=lambda *_args, **_kwargs: [],
            oa_sync_refresh_reason=lambda _view: "oa_projection_sync_version_changed",
            enqueue_oa_projection_sync=lambda scope_key, *, reason: syncs.append((scope_key, reason)),
            current_oa_attachment_invoice_parser_version=lambda: "parser-v1",
            current_oa_projection_sync_version=lambda: "projection-v1",
        )

        result = provider.read("2026-05")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status_code, HTTPStatus.ACCEPTED)
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(result.payload["read_model_refresh_reason"], "oa_projection_sync_version_changed")
        self.assertEqual(result.payload["oa_attachment_invoice_parser_version"], "parser-v1")
        self.assertEqual(result.payload["oa_projection_sync_version"], "projection-v1")
        self.assertEqual(syncs, [("2026-05", "oa_projection_sync_version_changed")])


if __name__ == "__main__":
    unittest.main()
