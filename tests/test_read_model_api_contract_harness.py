from __future__ import annotations

from contextlib import nullcontext
import json
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path

from fin_ops_platform.app.server import Response
from fin_ops_platform.services.oa_pending_payment_query_service import OaPendingPaymentQueryService
from fin_ops_platform.tools.http_slo_probe import DEFAULT_API_PROBES
from tests.app_test_support import build_local_state_application as build_application


DIRECT_CANONICAL_PROBES = frozenset(
    {
        "workbench_settings",
        "bank_details_accounts",
        "bank_details_transactions",
        "bank_details_auto_tag_rules",
        "pending_invoices_rows",
        "pending_invoices_filter_options",
        "pending_invoices_rules",
        "input_invoice_usage_rows",
        "input_invoice_usage_filter_options",
        "input_invoice_usage_payment_status_rules",
        "oa_pending_payments_rows",
        "output_invoice_collections_rows",
        "output_invoice_collections_filter_options",
        "output_invoice_collections_status_rules",
        "tax_offset_summary",
        "tax_offset_rows",
        "cost_statistics_explorer_all",
        "bank_flow_rule_batches",
        "bank_flow_rule_batches_tag_rules",
        "turnover_ledger_grouped",
        "turnover_ledger_tag_selection",
    }
)
RETIRED_READ_MODEL_FIELDS = frozenset(
    {
        "read_model_status",
        "readModelStatus",
        "read_model_version",
        "readModelVersion",
        "read_model_scope_keys",
        "readModelScopeKeys",
        "source_versions",
        "sourceVersions",
        "refresh_enqueued",
        "refreshEnqueued",
        "freshness",
        "freshness_targets",
        "operation_barrier_targets",
        "cache_status",
        "fallback",
    }
)


class ReadModelApiContractHarnessTests(unittest.TestCase):
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
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_canonical_query_repository = SimpleNamespace(  # noqa: SLF001
                get_workbench_initial_page=lambda **_kwargs: {
                    "paired": {"groups": []},
                    "unpaired": {"groups": []},
                },
                get_workbench_groups_page=lambda **_kwargs: {
                    "groups": [],
                    "pagination": {"page": 1, "page_size": 50, "total": 0},
                },
            )
            bank_details_service = app._bank_details_application_service()  # noqa: SLF001
            bank_details_service._query_service = SimpleNamespace(  # noqa: SLF001
                accounts_payload=lambda **_kwargs: {"accounts": []},
                transactions_payload=lambda **_kwargs: {
                    "rows": [],
                    "pagination": {"page": 1, "page_size": 50, "total": 0},
                },
            )
            app._bank_details_application_service = lambda: bank_details_service  # type: ignore[method-assign]  # noqa: SLF001
            app._bank_flow_rule_batch_canonical_query_repository = SimpleNamespace(  # noqa: SLF001
                read_page=lambda *_args, **_kwargs: {
                    "tag_policy": {"active_tags": [], "rules": []},
                    "items": [],
                    "aggregates": [],
                    "total": 0,
                }
            )
            app._oa_pending_payment_query_service_instance = OaPendingPaymentQueryService(  # noqa: SLF001
                repository=SimpleNamespace(
                    snapshot=lambda: nullcontext(
                        SimpleNamespace(
                            select_page=lambda **_kwargs: {
                                "descriptors": [],
                                "pagination": {"page": 1, "page_size": 20, "total": 0},
                                "summary": {},
                                "statistics": {},
                                "filterOptions": {},
                            }
                        )
                    )
                )
            )

            required_keys_by_probe = {
                "session_me": ("user", "allowed", "can_access_app"),
                "workbench_initial_all": ("paired", "unpaired", "scope_key"),
                "workbench_groups_all_paired": ("groups", "pagination", "scope_key", "zone"),
                "workbench_settings": ("projects", "workbench_column_layouts"),
                "bank_details_accounts": ("accounts",),
                "bank_details_transactions": ("rows", "pagination"),
                "pending_invoices_rows": ("rows", "pagination", "summary"),
                "pending_invoices_filter_options": ("fields", "options"),
                "pending_invoices_rules": ("groups", "available_tags", "permissions"),
                "input_invoice_usage_payment_status_rules": ("rules", "permissions", "version"),
                "input_invoice_usage_rows": ("rows", "pagination", "summary", "filterConfig"),
                "input_invoice_usage_filter_options": ("context", "fields"),
                "oa_pending_payments_rows": ("rows", "pagination", "summary", "filterConfig"),
                "output_invoice_collections_status_rules": ("rules", "permissions", "version"),
                "output_invoice_collections_rows": (
                    "rows",
                    "pagination",
                    "summary",
                    "filterConfig",
                    "filterOptions",
                ),
                "output_invoice_collections_filter_options": ("context", "fields"),
                "tax_offset_summary": ("month", "summary", "statistics"),
                "tax_offset_rows": ("month", "summary", "statistics"),
                "cost_statistics_explorer_all": ("scope", "summary", "rows"),
                "bank_flow_rule_batches": ("summary", "batches", "pagination"),
                "bank_flow_rule_batches_tag_rules": ("version", "rules"),
                "turnover_ledger_grouped": ("groups", "pagination", "summary"),
                "turnover_ledger_tag_selection": ("version", "active_tags", "selected_tag_codes"),
            }

            for probe in DEFAULT_API_PROBES:
                with self.subTest(probe=probe.name, path=probe.path):
                    response = app.handle_request("GET", probe.path)
                    payload = self._json(response)

                    if probe.name in DIRECT_CANONICAL_PROBES:
                        self.assertEqual(response.status_code, 200)
                        for field in RETIRED_READ_MODEL_FIELDS:
                            self.assertNotIn(field, payload)
                    else:
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
                        continue
                    required_keys = required_keys_by_probe.get(probe.name, ())
                    self._assert_keys(payload, *required_keys)
                    self.assertNotIn(payload.get("error"), {"invalid_oa_session", "forbidden"})

    def test_contract_harness_keeps_auth_guard_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir), install_test_session=False)

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
