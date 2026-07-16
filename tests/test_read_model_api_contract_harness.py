from __future__ import annotations

from contextlib import contextmanager
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Iterator

from fin_ops_platform.app.server import Response
from tests.app_test_support import build_local_state_application as build_application
from fin_ops_platform.tools.http_slo_probe import DEFAULT_API_PROBES


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

    def _assert_error_message(self, payload: dict[str, object]) -> None:
        error = payload.get("error")
        if isinstance(error, dict):
            self.assertIn("code", error)
            self.assertIn("message", error)
            return
        self.assertIn("message", payload)

    def test_default_api_probes_expose_sanitized_local_envelopes(self) -> None:
        with self._default_test_auth(enabled=True), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._search_service._workbench_rows_loader = lambda _month: []  # noqa: SLF001

            required_keys_by_probe = {
                "session_me": ("user", "allowed", "can_access_app"),
                "workbench_settings": ("projects", "access_control", "workbench_column_layouts"),
                "pending_invoices_rules": ("groups", "available_tags", "permissions"),
                "input_invoice_usage_payment_status_rules": ("rules", "permissions", "version"),
                "input_invoice_usage_rows": ("rows", "pagination", "summary", "filterConfig"),
                "output_invoice_collections_status_rules": ("rules", "permissions", "version"),
                "output_invoice_collections_rows": ("rows", "pagination", "summary", "readModelStatus"),
                "tax_offset_summary": ("month", "summary", "item_counts"),
                "cost_statistics": ("month", "summary", "rows"),
                "search_all": ("query", "summary", "filters"),
            }

            for probe in DEFAULT_API_PROBES:
                with self.subTest(probe=probe.name, path=probe.path):
                    response = app.handle_request("GET", probe.path)
                    payload = self._json(response)

                    expected_statuses = set(probe.expected_statuses) | {503}
                    if probe.auth_scope == "admin":
                        expected_statuses.add(403)
                    if probe.name in {"import_facts_batches", "import_facts_files", "import_facts_invoices"}:
                        expected_statuses.add(501)
                    self.assertIn(response.status_code, expected_statuses)
                    if response.status_code == 403:
                        self.assertIn(payload.get("error"), {"admin_only", "forbidden"})
                        self._assert_error_message(payload)
                        continue
                    if response.status_code == 501:
                        self._assert_keys(payload, "error")
                        self._assert_error_message(payload)
                        continue
                    if response.status_code == 503:
                        self._assert_keys(payload, "error")
                        self._assert_error_message(payload)
                        if probe.path.startswith("/api/workbench/"):
                            self.assertEqual(payload.get("read_model_status"), "unavailable")
                        continue
                    required_keys = required_keys_by_probe.get(probe.name, ())
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
