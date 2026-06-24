from __future__ import annotations

from contextlib import contextmanager
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Iterator

from fin_ops_platform.app.server import Response, build_application


class ReadModelApiContractHarnessTests(unittest.TestCase):
    @contextmanager
    def _default_test_auth(self, enabled: bool) -> Iterator[None]:
        previous = os.environ.get("FIN_OPS_TEST_DEFAULT_AUTH")
        os.environ["FIN_OPS_TEST_DEFAULT_AUTH"] = "1" if enabled else "0"
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("FIN_OPS_TEST_DEFAULT_AUTH", None)
            else:
                os.environ["FIN_OPS_TEST_DEFAULT_AUTH"] = previous

    def _json(self, response: Response) -> dict[str, object]:
        self.assertIn(
            response.headers.get("Content-Type", ""),
            {"application/json; charset=utf-8", "application/json"},
        )
        payload = json.loads(response.body)
        self.assertIsInstance(payload, dict)
        return payload

    def _assert_keys(self, payload: dict[str, object], *keys: str) -> None:
        for key in keys:
            with self.subTest(key=key):
                self.assertIn(key, payload)

    def test_representative_read_model_get_routes_expose_sanitized_envelopes(self) -> None:
        with self._default_test_auth(enabled=True), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            cases = [
                ("/api/session/me", {200}, ("user", "allowed", "can_access_app")),
                ("/api/workbench/settings", {200}, ("projects", "access_control", "workbench_column_layouts")),
                ("/api/workbench/summary?month=all", {200, 202, 503}, ()),
                ("/api/pending-invoices/rules", {200}, ("groups", "available_tags", "permissions")),
                ("/api/pending-invoices/rows?direction=expense&page=1&page_size=5", {200, 202, 503}, ()),
                ("/api/input-invoice-usage/payment-status-rules", {200}, ("rules", "permissions", "version")),
                (
                    "/api/input-invoice-usage/rows?page=1&page_size=5",
                    {200},
                    ("rows", "pagination", "summary", "filterConfig"),
                ),
                ("/api/output-invoice-collections/status-rules", {200}, ("rules", "permissions", "version")),
                (
                    "/api/output-invoice-collections/rows?page=1&page_size=5",
                    {200},
                    ("rows", "pagination", "summary", "readModelStatus"),
                ),
                ("/api/tax-offset/summary?month=2026-03", {200}, ("month", "summary", "item_counts")),
                (
                    "/api/cost-statistics?month=2026-03&project_scope=active",
                    {200},
                    ("month", "summary", "rows"),
                ),
                (
                    "/api/search?q=%E5%85%AC%E5%8F%B8&scope=all&month=all&limit=5",
                    {200},
                    ("query", "summary", "filters"),
                ),
            ]

            for path, expected_statuses, required_keys in cases:
                with self.subTest(path=path):
                    response = app.handle_request("GET", path)
                    payload = self._json(response)

                    self.assertIn(response.status_code, expected_statuses)
                    if response.status_code == 503:
                        self._assert_keys(payload, "error", "message")
                        if path.startswith("/api/workbench/"):
                            self.assertEqual(payload.get("read_model_status"), "unavailable")
                        continue
                    self._assert_keys(payload, *required_keys)
                    self.assertNotIn(payload.get("error"), {"invalid_oa_session", "forbidden"})

    def test_contract_harness_keeps_auth_guard_explicit(self) -> None:
        with self._default_test_auth(enabled=False), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            for path in (
                "/api/workbench/settings",
                "/api/input-invoice-usage/rows?page=1&page_size=5",
                "/api/output-invoice-collections/rows?page=1&page_size=5",
            ):
                with self.subTest(path=path):
                    response = app.handle_request("GET", path)
                    payload = self._json(response)

                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(payload["error"], "invalid_oa_session")
                    self.assertIn("message", payload)
